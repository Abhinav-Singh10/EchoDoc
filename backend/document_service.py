import sqlite3
import uuid
import grpc

from pycrdt import Doc, Text
from collab.document.v1 import document_pb2
from pathlib import Path
from collab.document.v1 import document_pb2_grpc


class DocumentService(document_pb2_grpc.DocumentServiceServicer):
    def __init__(self, auth):
        self.auth = auth

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
        await self.auth.require_session(context)

        row = self.db.execute(
            "SELECT state, revision FROM documents WHERE id = ?",
            (request.document_id,),
        ).fetchone()

        if row is None:
            await context.abort(
                grpc.StatusCode.NOT_FOUND,
                "Document not found",
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
        except sqlite3.Error:
            await context.abort(
                grpc.StatusCode.INTERNAL,
                "Could not save the document",
            )

        return document_pb2.SubmitUpdateResponse(
            revision=revision,
        )