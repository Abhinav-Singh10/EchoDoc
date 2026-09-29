import sqlite3
import uuid
import grpc
import asyncio
from google.protobuf.empty_pb2 import Empty

from collections import defaultdict
from pycrdt import Doc, Text
from collab.document.v1 import document_pb2
from pathlib import Path
from collab.document.v1 import document_pb2_grpc


class DocumentService(document_pb2_grpc.DocumentServiceServicer):
    def __init__(self, auth):
        self.auth = auth
        self.locks = defaultdict(asyncio.Lock)
        self.subscribers = defaultdict(dict)
        self.presence = defaultdict(dict)
        self.presence_sessions = defaultdict(dict)


        database = Path("data/documents.sqlite3")
        database.parent.mkdir(parents=True, exist_ok=True)

        self.db = sqlite3.connect(database)
        self.db.row_factory = sqlite3.Row

        self.db.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                state BLOB NOT NULL,
                revision INTEGER NOT NULL DEFAULT 0
            )
        """)
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS updates (
                document_id TEXT NOT NULL,
                request_id TEXT NOT NULL,
                author TEXT NOT NULL,
                update_bytes BLOB NOT NULL,
                revision INTEGER NOT NULL,
                PRIMARY KEY (document_id, request_id)
            )
        """)
        self.db.commit()

    async def CreateDocument(self, request, context):
        await self.auth.require_session(context)

        title = request.title.strip()
        if not title:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "Document title is required",
            )

        document_id = str(uuid.uuid4())
        doc = Doc({"content": Text()})

        with self.db:
            self.db.execute(
                """
                INSERT INTO documents (id, title, state, revision)
                VALUES (?, ?, ?, ?)
                """,
                (document_id, title, doc.get_update(), 0),
            )

        return document_pb2.DocumentInfo(
            document_id=document_id,
            title=title,
            revision=0,
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
                await context.abort(grpc.StatusCode.PERMISSION_DENIED,
                                    "Presence belongs to an active connection in this session")
            peer = self.presence[doc_id][conn_id]
            if peer.editing != request.editing:
                peer.editing = request.editing
                self.broadcast_presence(doc_id)
        return Empty()

    async def ListDocuments(self, request, context):
        await self.auth.require_session(context)

        rows = self.db.execute(
            """
            SELECT id, title, revision
            FROM documents
            ORDER BY title, id
            """
        ).fetchall()

        documents = [
            document_pb2.DocumentInfo(
                document_id=row["id"],
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

        row = self.db.execute(
            """
            SELECT id, title, state, revision
            FROM documents
            WHERE id = ?
            """,
            (request.document_id,),
        ).fetchone()

        if row is None:
            await context.abort(
                grpc.StatusCode.NOT_FOUND,
                "Document not found",
            )

        return document_pb2.GetDocumentResponse(
            document=document_pb2.DocumentInfo(
                document_id=row["id"],
                title=row["title"],
                revision=row["revision"],
            ),
            state=row["state"],
        )


    async def SubmitUpdate(self, request, context):
        _, session = await self.auth.require_session(context)
        author = session["user"].user_id

        if not request.request_id:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "Request ID is required",
            )

        async with self.locks[request.document_id]:
            row = self.db.execute(
                "SELECT state, revision FROM documents WHERE id = ?",
                (request.document_id,),
            ).fetchone()

            if row is None:
                await context.abort(
                    grpc.StatusCode.NOT_FOUND,
                    "Document not found",
                )

            previous = self.db.execute(
                """
                SELECT author, update_bytes, revision
                FROM updates
                WHERE document_id = ? AND request_id = ?
                """,
                (request.document_id, request.request_id),
            ).fetchone()

            if previous is not None:
                if (
                    previous["author"] != author
                    or previous["update_bytes"] != request.update
                ):
                    await context.abort(
                        grpc.StatusCode.ALREADY_EXISTS,
                        "Request ID was already used for a different update",
                    )

                return document_pb2.SubmitUpdateResponse(
                    revision=previous["revision"],
                )

            doc = Doc()
            doc.apply_update(row["state"])

            try:
                doc.apply_update(request.update)
            except Exception:
                await context.abort(
                    grpc.StatusCode.INVALID_ARGUMENT,
                    "Invalid CRDT update",
                )

            revision = row["revision"] + 1

            try:
                with self.db:
                    self.db.execute(
                        """
                        UPDATE documents
                        SET state = ?, revision = ?
                        WHERE id = ?
                        """,
                        (doc.get_update(), revision, request.document_id),
                    )

                    self.db.execute(
                        """
                        INSERT INTO updates (
                            document_id, request_id, author,
                            update_bytes, revision
                        )
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            request.document_id,
                            request.request_id,
                            author,
                            request.update,
                            revision,
                        ),
                    )
            except sqlite3.Error:
                await context.abort(
                    grpc.StatusCode.INTERNAL,
                    "Could not save the document",
                )

            event = document_pb2.DocumentEvent(
                kind="update",
                update=request.update,
                revision=revision,
                request_id=request.request_id,
            )

            for queue in self.subscribers[request.document_id].values():
                queue.put_nowait(event)

            return document_pb2.SubmitUpdateResponse(
                revision=revision,
            )

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
            row = self.db.execute(
                "SELECT state, revision FROM documents WHERE id = ?",
                (document_id,),
            ).fetchone()

            if row is None:
                await context.abort(
                    grpc.StatusCode.NOT_FOUND,
                    "Document not found",
                )

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
