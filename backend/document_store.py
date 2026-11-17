"""SQLite document state. Prepared commands can later arrive from a Raft log."""

from dataclasses import dataclass
import os
from pathlib import Path
import sqlite3

from pycrdt import Doc


@dataclass(frozen=True)
class CreateDocumentCommand:
    document_id: str
    title: str
    state: bytes


@dataclass(frozen=True)
class SubmitUpdateCommand:
    document_id: str
    request_id: str
    author: str
    update: bytes


@dataclass(frozen=True)
class ApplyResult:
    revision: int
    changed: bool


class StoreError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class DocumentStore:
    def __init__(self, database=None):
        database = Path(database or os.getenv("DATABASE_PATH", "data/documents.sqlite3"))
        database.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(database)
        self._db.row_factory = sqlite3.Row
        with self._db:
            self._db.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    state BLOB NOT NULL,
                    revision INTEGER NOT NULL DEFAULT 0
                )
            """)
            self._db.execute("""
                CREATE TABLE IF NOT EXISTS updates (
                    document_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    author TEXT NOT NULL,
                    update_bytes BLOB NOT NULL,
                    revision INTEGER NOT NULL,
                    PRIMARY KEY (document_id, request_id)
                )
            """)

    def apply(self, command):
        # Returning from inside this block commits before the caller gets a result.
        # Any exception rolls back both the document and the request record.
        try:
            with self._db:
                if isinstance(command, CreateDocumentCommand):
                    return self._create(command)
                elif isinstance(command, SubmitUpdateCommand):
                    return self._update(command)
                else:
                    raise TypeError(f"Unsupported document command: {type(command).__name__}")
        except sqlite3.Error as error:
            raise StoreError("INTERNAL", "Could not save the document") from error

    def _create(self, command):
        if not command.title.strip():
            raise StoreError("INVALID_ARGUMENT", "Document title is required")
        existing = self._db.execute(
            "SELECT 1 FROM documents WHERE id = ?", (command.document_id,),
        ).fetchone()
        if existing is not None:
            raise StoreError("ALREADY_EXISTS", "Document ID already exists")
        self._db.execute(
            "INSERT INTO documents (id, title, state, revision) VALUES (?, ?, ?, 0)",
            (command.document_id, command.title, command.state),
        )
        return ApplyResult(revision=0, changed=True)

    def _update(self, command):
        if not command.request_id:
            raise StoreError("INVALID_ARGUMENT", "Request ID is required")
        row = self.get_document(command.document_id)
        previous = self._db.execute("""
            SELECT author, update_bytes, revision FROM updates
            WHERE document_id = ? AND request_id = ?
        """, (command.document_id, command.request_id)).fetchone()
        if previous is not None:
            if previous["author"] != command.author or previous["update_bytes"] != command.update:
                raise StoreError("ALREADY_EXISTS", "Request ID was already used for a different update")
            return ApplyResult(revision=previous["revision"], changed=False)

        doc = Doc()
        doc.apply_update(row["state"])
        try:
            doc.apply_update(command.update)
        except Exception as error:
            raise StoreError("INVALID_ARGUMENT", "Invalid CRDT update") from error
        revision = row["revision"] + 1
        self._db.execute(
            "UPDATE documents SET state = ?, revision = ? WHERE id = ?",
            (doc.get_update(), revision, command.document_id),
        )
        self._db.execute("""
            INSERT INTO updates (document_id, request_id, author, update_bytes, revision)
            VALUES (?, ?, ?, ?, ?)
        """, (command.document_id, command.request_id, command.author, command.update, revision))
        return ApplyResult(revision=revision, changed=True)

    def get_document(self, document_id):
        try:
            row = self._db.execute("""
                SELECT id AS document_id, title, state, revision FROM documents WHERE id = ?
            """, (document_id,)).fetchone()
        except sqlite3.Error as error:
            raise StoreError("INTERNAL", "Could not load the document") from error
        if row is None:
            raise StoreError("NOT_FOUND", "Document not found")
        return dict(row)

    def list_documents(self):
        try:
            rows = self._db.execute("""
                SELECT id AS document_id, title, revision FROM documents ORDER BY title, id
            """).fetchall()
        except sqlite3.Error as error:
            raise StoreError("INTERNAL", "Could not list documents") from error
        return [dict(row) for row in rows]

    def get_revision(self, document_id):
        try:
            row = self._db.execute(
                "SELECT revision FROM documents WHERE id = ?", (document_id,),
            ).fetchone()
        except sqlite3.Error as error:
            raise StoreError("INTERNAL", "Could not load the document revision") from error
        if row is None:
            raise StoreError("NOT_FOUND", "Document not found")
        return row["revision"]

    def close(self):
        self._db.close()
