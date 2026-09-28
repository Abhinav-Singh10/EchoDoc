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