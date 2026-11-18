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
            self._db.execute("""
                CREATE TABLE IF NOT EXISTS document_versions (
                    document_id TEXT NOT NULL,
                    revision INTEGER NOT NULL CHECK (revision >= 0),
                    state BLOB NOT NULL,
                    author_id TEXT NOT NULL,
                    PRIMARY KEY (document_id, revision)
                )
            """)

    def initialize_history(self):
        try:
            with self._db:
                self._db.execute("BEGIN")
                documents = self._db.execute("""
                    SELECT * FROM documents d WHERE NOT EXISTS (
                        SELECT 1 FROM document_versions v WHERE v.document_id = d.id
                    ) ORDER BY id
                """).fetchall()
                if not documents:
                    return
                members = json.loads(self._db.execute(
                    "SELECT member_ids FROM application_state WHERE id = 1",
                ).fetchone()[0])
                creations = self._find_applied_creations({row["id"] for row in documents})
                for row in documents:
                    self._backfill_document_history(row, creations.get(row["id"]), len(members) == 1)
        except (sqlite3.Error, ValueError, StoreError) as error:
            raise StoreError("INTERNAL", f"Could not initialize document history: {error}") from error

    def _find_applied_creations(self, document_ids):
        creations = {}
        for row in self._db.execute("""
            SELECT l.command FROM raft_log l
            JOIN applied_results a ON a.log_index = l.log_index
            WHERE l.log_index <= ? AND a.changed = 1 AND a.error_code IS NULL
            ORDER BY l.log_index
        """, (self.get_last_applied(),)):
            command = decode_command(row[0])
            if isinstance(command, CreateDocumentCommand) and command.document_id in document_ids:
                creations.setdefault(command.document_id, command)
        return creations

    def _backfill_document_history(self, document, creation, single_node):
        document_id = document["id"]
        if creation is None:
            if not single_node:
                raise ValueError(f"No successful applied creation for cluster document {document_id}")
            self._record_version(document_id, document["revision"], document["state"], "")
            return

        state, revision = creation.state, 0
        self._record_version(document_id, 0, state, "")
        for saved in self._db.execute("""
            SELECT revision, author, update_bytes FROM updates
            WHERE document_id = ? ORDER BY revision
        """, (document_id,)):
            if saved["revision"] != revision + 1 or saved["revision"] > document["revision"]:
                raise ValueError(f"Nonconsecutive saved updates for document {document_id}")
            state = self._merge_update(state, saved["update_bytes"])
            revision = saved["revision"]
            self._record_version(document_id, revision, state, saved["author"])
        if revision != document["revision"] or state != document["state"]:
            raise ValueError(f"Reconstructed history differs from saved document {document_id}")

    def _record_version(self, document_id, revision, state, author_id):
        self._db.execute(
            "INSERT INTO document_versions VALUES (?, ?, ?, ?)",
            (document_id, revision, state, author_id),
        )

    @staticmethod
    def _merge_update(state, update):
        doc = Doc()
        doc.apply_update(state)
        try:
            doc.apply_update(update)
        except Exception as error:
            raise StoreError("INVALID_ARGUMENT", "Invalid CRDT update") from error
        return doc.get_update()

    def apply(self, command):
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
        self._record_version(command.document_id, 0, command.state, "")
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

        state = self._merge_update(row["state"], command.update)
        revision = row["revision"] + 1
        self._db.execute(
            "UPDATE documents SET state = ?, revision = ? WHERE id = ?",
            (state, revision, command.document_id),
        )
        self._db.execute("""
            INSERT INTO updates (document_id, request_id, author, update_bytes, revision)
            VALUES (?, ?, ?, ?, ?)
        """, (command.document_id, command.request_id, command.author, command.update, revision))
        self._record_version(command.document_id, revision, state, command.author)
        return ApplyResult(revision=revision, changed=True)

    def _version_bounds(self, document_id, current):
        count, oldest, latest = self._db.execute("""
            SELECT count(*), min(revision), max(revision) FROM document_versions
            WHERE document_id = ?
        """, (document_id,)).fetchone()
        if not count or oldest < 0 or latest != current or count != current - oldest + 1:
            raise StoreError("INTERNAL", "Saved document history is incomplete")
        return oldest

    def list_document_versions(self, document_id, before_revision=None):
        if before_revision is not None and (type(before_revision) is not int or before_revision < 0):
            raise StoreError("INVALID_ARGUMENT", "Revision cursor must be a nonnegative integer")
        try:
            current = self.get_revision(document_id)
            oldest = self._version_bounds(document_id, current)
            if before_revision is None or before_revision > current:
                rows = self._db.execute("""
                    SELECT revision, author_id FROM document_versions
                    WHERE document_id = ? ORDER BY revision DESC LIMIT 51
                """, (document_id,)).fetchall()
            else:
                rows = self._db.execute("""
                    SELECT revision, author_id FROM document_versions
                    WHERE document_id = ? AND revision < ? ORDER BY revision DESC LIMIT 51
                """, (document_id, before_revision)).fetchall()
            return {
                "current_revision": current, "oldest_available_revision": oldest,
                "versions": [dict(row) for row in rows[:50]],
                "next_before_revision": rows[49]["revision"] if len(rows) > 50 else None,
            }
        except sqlite3.Error as error:
            raise StoreError("INTERNAL", "Could not list document versions") from error

    def get_document_version(self, document_id, revision):
        if type(revision) is not int or revision < 0:
            raise StoreError("INVALID_ARGUMENT", "Revision must be a nonnegative integer")
        try:
            document = self.get_document(document_id)
            oldest = self._version_bounds(document_id, document["revision"])
            if not oldest <= revision <= document["revision"]:
                raise StoreError("NOT_FOUND", "Document version is outside the available history")
            row = self._db.execute("""
                SELECT state, author_id FROM document_versions
                WHERE document_id = ? AND revision = ?
            """, (document_id, revision)).fetchone()
            if row is None:
                raise StoreError("INTERNAL", "Saved document version is missing")
            return {"document_id": document_id, "title": document["title"], "revision": revision,
                    "state": row["state"], "author_id": row["author_id"]}
        except sqlite3.Error as error:
            raise StoreError("INTERNAL", "Could not load document version") from error

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
