import sqlite3
import uuid
import grpc
import asyncio

from collections import defaultdict
from pycrdt import Doc, Text
from collab.document.v1 import document_pb2
from pathlib import Path
from collab.document.v1 import document_pb2_grpc


class DocumentService(document_pb2_grpc.DocumentServiceServicer):
    def __init__(self, auth):
        self.auth = auth
        self.locks = defaultdict(asyncio.Lock)

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

            return document_pb2.SubmitUpdateResponse(
                revision=revision,
            )