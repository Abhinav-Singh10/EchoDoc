"""SQLite application state and atomic progress through the committed Raft log."""

from dataclasses import dataclass, replace
import json
import os
from pathlib import Path
import sqlite3

from pycrdt import Doc
from backend.commands import (
    CommandOutcome, CreateDocumentCommand, CreateSessionCommand, NoOpCommand,
    RevokeSessionCommand, SubmitUpdateCommand,
)
from backend.raft_commands import decode_command


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

    def initialize_application(self, member_ids):
        """Adopt compatible legacy data once; refuse incompatible data before DDL."""
        members = json.dumps(sorted(member_ids))
        tables = {row[0] for row in self._db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if "application_state" in tables:
            state = self._db.execute("SELECT member_ids FROM application_state WHERE id = 1").fetchone()
            if state is None or state["member_ids"] != members:
                raise ValueError("Application membership differs from this database; use new database paths and retain the old files")
            return
        incompatible = len(member_ids) > 1 and any(self._db.execute(
            f"SELECT 1 FROM {table} LIMIT 1",
        ).fetchone() is not None for table in ("documents", "updates"))
        if "raft_log" in tables:
            try:
                incompatible |= any(not isinstance(decode_command(row[0]), NoOpCommand)
                                    for row in self._db.execute("SELECT command FROM raft_log"))
            except (ValueError, TypeError):
                incompatible = True
        if incompatible:
            raise ValueError("Legacy cluster documents or synthetic log entries cannot be adopted automatically; use new database paths and retain the old files")
        with self._db:
            self._db.execute("BEGIN")
            self._db.execute("""
                CREATE TABLE sessions (
                    token TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                    username TEXT NOT NULL, expires_at INTEGER NOT NULL
                )
            """)
            self._db.execute("""
                CREATE TABLE application_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    last_applied INTEGER NOT NULL, member_ids TEXT NOT NULL
                )
            """)
            self._db.execute("INSERT INTO application_state VALUES (1, 0, ?)", (members,))
            self._db.execute("""
                CREATE TABLE applied_results (
                    log_index INTEGER PRIMARY KEY, revision INTEGER, changed INTEGER NOT NULL,
                    error_code TEXT, error_message TEXT
                )
            """)

    def get_last_applied(self):
        return self._db.execute("SELECT last_applied FROM application_state WHERE id = 1").fetchone()[0]

    def get_outcome(self, index):
        row = self._db.execute("""
            SELECT revision, changed, error_code, error_message FROM applied_results WHERE log_index = ?
        """, (index,)).fetchone()
        if row is None:
            raise ValueError(f"No application outcome for log index {index}")
        return CommandOutcome(row["revision"], bool(row["changed"]), row["error_code"], row["error_message"])

    def get_session(self, token):
        row = self._db.execute(
            "SELECT user_id, username, expires_at FROM sessions WHERE token = ?", (token,),
        ).fetchone()
        return dict(row) if row else None

    def apply_committed(self, index, command):
        if type(index) is not int or index < 1:
            raise ValueError("Applied index must be positive")
        with self._db:
            last = self.get_last_applied()
            if index <= last:
                return replace(self.get_outcome(index), changed=False)
            if index != last + 1:
                raise ValueError("Committed entries must be applied consecutively")
            # BEGIN is needed because SAVEPOINT alone would commit on RELEASE.
            self._db.execute("BEGIN")
            self._db.execute("SAVEPOINT command")
            try:
                outcome = self._apply_command(command)
            except StoreError as error:
                if error.code not in ("NOT_FOUND", "INVALID_ARGUMENT", "ALREADY_EXISTS"):
                    raise
                self._db.execute("ROLLBACK TO command")
                outcome = CommandOutcome(error_code=error.code, error_message=str(error))
            self._db.execute("RELEASE command")
            self._db.execute("INSERT INTO applied_results VALUES (?, ?, ?, ?, ?)", (
                index, outcome.revision, outcome.changed, outcome.error_code, outcome.error_message,
            ))
            self._db.execute("UPDATE application_state SET last_applied = ? WHERE id = 1", (index,))
            return outcome

    def _apply_command(self, command):
        if isinstance(command, CreateDocumentCommand):
            result = self._create(command)
            return CommandOutcome(result.revision, result.changed)
        elif isinstance(command, SubmitUpdateCommand):
            result = self._update(command)
            return CommandOutcome(result.revision, result.changed)
        elif isinstance(command, NoOpCommand):
            return CommandOutcome()
        elif isinstance(command, CreateSessionCommand):
            if not command.token or not command.user_id or not command.username or command.expires_at < 0:
                raise StoreError("INVALID_ARGUMENT", "Invalid session command")
            existing = self.get_session(command.token)
            values = {"user_id": command.user_id, "username": command.username, "expires_at": command.expires_at}
            if existing is not None:
                if existing != values:
                    raise StoreError("ALREADY_EXISTS", "Session token already exists")
                return CommandOutcome()
            self._db.execute("INSERT INTO sessions VALUES (?, ?, ?, ?)", (
                command.token, command.user_id, command.username, command.expires_at,
            ))
            return CommandOutcome(changed=True)
        elif isinstance(command, RevokeSessionCommand):
            changed = self._db.execute("DELETE FROM sessions WHERE token = ?", (command.token,)).rowcount > 0
            return CommandOutcome(changed=changed)
        raise TypeError(f"Unsupported application command: {type(command).__name__}")

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
