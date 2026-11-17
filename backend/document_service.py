import uuid
import grpc
import asyncio
from google.protobuf.empty_pb2 import Empty

from collections import defaultdict
from pycrdt import Doc, Text
from collab.document.v1 import document_pb2
from collab.document.v1 import document_pb2_grpc
from backend.commands import CreateDocumentCommand, SubmitUpdateCommand
from backend.document_store import DocumentStore, StoreError
from backend.mutations import route_write, submit_write


class DocumentService(document_pb2_grpc.DocumentServiceServicer):
    def __init__(self, auth, store: DocumentStore, raft, state_machine):
        self.auth = auth
        self.store = store
        self.raft = raft
        self.locks = state_machine.locks
        state_machine.on_update = self.broadcast_update
        self.subscribers = defaultdict(dict)
        self.presence = defaultdict(dict)
        self.presence_sessions = defaultdict(dict)

    async def CreateDocument(self, request, context):
        forwarded, deadline = await route_write(
            self.raft, request, context, document_pb2_grpc.DocumentServiceStub, "CreateDocument",
        )
        if forwarded is not None:
            return forwarded
        await self.auth.require_session(context)

        title = request.title.strip()
        if not title:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "Document title is required",
            )

        document_id = str(uuid.uuid4())
        doc = Doc({"content": Text()})

        command = CreateDocumentCommand(document_id, title, doc.get_update())
        result = await submit_write(self.raft, self.store, command, context, deadline)

        return document_pb2.DocumentInfo(
            document_id=document_id,
            title=title,
            revision=result.revision,
        )

    def broadcast_presence(self, document_id):
        event = document_pb2.DocumentEvent(
            kind="presence",
            users=list(self.presence[document_id].values()),
        )

        for queue in self.subscribers[document_id].values():
            queue.put_nowait(event)

    async def UpdatePresence(self, request, context):
        token, _ = await self.auth.require_session(context)
        doc_id, conn_id = request.document_id, request.connection_id
        async with self.locks[doc_id]:
            if self.presence_sessions[doc_id].get(conn_id) != token:
                await context.abort(
                    grpc.StatusCode.PERMISSION_DENIED,
                    "Presence belongs to an active connection in this session",
                )
            peer = self.presence[doc_id][conn_id]
            if peer.editing != request.editing:
                peer.editing = request.editing
                self.broadcast_presence(doc_id)
        return Empty()

    async def ListDocuments(self, request, context):
        await self.auth.require_session(context)

        try:
            rows = self.store.list_documents()
        except StoreError as error:
            await context.abort(grpc.StatusCode[error.code], str(error))

        documents = [
            document_pb2.DocumentInfo(
                document_id=row["document_id"],
                title=row["title"],
                revision=row["revision"],
            )
            for row in rows
        ]

        return document_pb2.ListDocumentsResponse(
            documents=documents,
        )

    async def GetDocument(self, request, context):
        await self.auth.require_session(context)

        try:
            row = self.store.get_document(request.document_id)
        except StoreError as error:
            await context.abort(grpc.StatusCode[error.code], str(error))

        return document_pb2.GetDocumentResponse(
            document=document_pb2.DocumentInfo(
                document_id=row["document_id"],
                title=row["title"],
                revision=row["revision"],
            ),
            state=row["state"],
        )

    async def SubmitUpdate(self, request, context):
        forwarded, deadline = await route_write(
            self.raft, request, context, document_pb2_grpc.DocumentServiceStub, "SubmitUpdate",
        )
        if forwarded is not None:
            return forwarded
        _, session = await self.auth.require_session(context)
        author = session["user"].user_id

        if not request.request_id:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "Request ID is required",
            )

        command = SubmitUpdateCommand(
            document_id=request.document_id, request_id=request.request_id,
            author=author, update=request.update,
        )
        # The application worker takes the document lock; never hold it here.
        result = await submit_write(self.raft, self.store, command, context, deadline)
        return document_pb2.SubmitUpdateResponse(revision=result.revision)

    def broadcast_update(self, command, outcome):
        event = document_pb2.DocumentEvent(
            kind="update", update=command.update, revision=outcome.revision,
            request_id=command.request_id,
        )
        for queue in self.subscribers[command.document_id].values():
            queue.put_nowait(event)

    async def WatchDocument(self, request, context):
        token, session = await self.auth.require_session(context)

        document_id = request.document_id
        connection_id = request.connection_id

        if not connection_id:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "Connection ID is required",
            )

        queue = asyncio.Queue()

        async with self.locks[document_id]:
            try:
                row = self.store.get_document(document_id)
            except StoreError as error:
                await context.abort(grpc.StatusCode[error.code], str(error))

            if connection_id in self.subscribers[document_id]:
                await context.abort(
                    grpc.StatusCode.ALREADY_EXISTS,
                    "Connection is already subscribed",
                )

            snapshot = document_pb2.DocumentEvent(
                kind="snapshot",
                update=row["state"],
                revision=row["revision"],
            )

            self.subscribers[document_id][connection_id] = queue
            self.presence[document_id][connection_id] = document_pb2.Presence(
                connection_id=connection_id,
                username=session["user"].username,
                editing=False,
            )

            self.presence_sessions[document_id][connection_id] = token
            self.broadcast_presence(document_id)

        try:
            await self.auth.require_session(context)
            yield snapshot

            while True:
                await self.auth.require_session(context)

                try:
                    event = await asyncio.wait_for(
                        queue.get(),
                        timeout=1,
                    )
                except asyncio.TimeoutError:
                    continue

                await self.auth.require_session(context)
                yield event
        finally:
            async with self.locks[document_id]:
                self.subscribers[document_id].pop(connection_id, None)
                self.presence[document_id].pop(connection_id, None)
                self.presence_sessions[document_id].pop(connection_id, None)
                self.broadcast_presence(document_id)
