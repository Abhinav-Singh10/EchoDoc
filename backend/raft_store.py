from pathlib import Path
import sqlite3

from collab.raft.v1 import raft_pb2


class RaftStore:
    def __init__(self, database):
        database = Path(database)
        database.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(database)
        self._db.row_factory = sqlite3.Row
        try:
            with self._db:
                self._db.execute("""
                    CREATE TABLE IF NOT EXISTS raft_state (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        current_term INTEGER NOT NULL CHECK (current_term >= 0),
                        voted_for TEXT
                    )
                """)
                self._db.execute("""
                    INSERT OR IGNORE INTO raft_state (id, current_term, voted_for)
                    VALUES (1, 0, NULL)
                """)
                self._db.execute("""
                    CREATE TABLE IF NOT EXISTS raft_log (
                        log_index INTEGER PRIMARY KEY CHECK (log_index >= 1),
                        term INTEGER NOT NULL CHECK (term >= 1),
                        command BLOB NOT NULL
                    )
                """)
        except Exception:
            self._db.close()
            raise

    def get_state(self):
        return dict(self._db.execute(
            "SELECT current_term, voted_for FROM raft_state WHERE id = 1",
        ).fetchone())

    def save_state(self, term, voted_for):
        if type(term) is not int or term < 0:
            raise ValueError("Term must be a nonnegative integer")
        if voted_for is not None and (not isinstance(voted_for, str) or not voted_for.strip()):
            raise ValueError("Vote must be a nonempty node ID or None")
        with self._db:
            state = self.get_state()
            if term < state["current_term"]:
                raise ValueError("Term cannot decrease")
            if (term == state["current_term"] and state["voted_for"] is not None
                    and voted_for != state["voted_for"]):
                raise ValueError("Cannot clear or change a vote in the same term")
            self._db.execute(
                "UPDATE raft_state SET current_term = ?, voted_for = ? WHERE id = 1",
                (term, voted_for),
            )

    def last_log_position(self):
        row = self._db.execute(
            "SELECT log_index, term FROM raft_log ORDER BY log_index DESC LIMIT 1",
        ).fetchone()
        return (row["log_index"], row["term"]) if row is not None else (0, 0)

    def get_entry(self, index):
        self._check_index(index)
        row = self._db.execute(
            "SELECT log_index, term, command FROM raft_log WHERE log_index = ?", (index,),
        ).fetchone()
        if row is None:
            return None
        return raft_pb2.LogEntry(index=row["log_index"], term=row["term"], command=row["command"])

    def read_entries(self, start_index=1, limit=None):
        self._check_index(start_index)
        if limit is not None and (type(limit) is not int or limit < 1):
            raise ValueError("Log read limit must be a positive integer or None")
        rows = self._db.execute("""
            SELECT log_index, term, command FROM raft_log
            WHERE log_index >= ? ORDER BY log_index LIMIT ?
        """, (start_index, limit if limit is not None else -1)).fetchall()
        return [raft_pb2.LogEntry(
            index=row["log_index"], term=row["term"], command=row["command"],
        ) for row in rows]

    def append_entries(self, entries):
        entries = list(entries)
        with self._db:
            start_index = self.last_log_position()[0] + 1
            self._check_entries(start_index, entries)
            self._insert_entries(entries)

    def replace_suffix(self, start_index, entries):
        """The future Raft caller must ensure this suffix is not committed."""
        self._check_index(start_index)
        entries = list(entries)
        with self._db:
            if start_index > self.last_log_position()[0] + 1:
                raise ValueError("Replacement cannot leave a gap in the log")
            self._check_entries(start_index, entries)
            self._db.execute("DELETE FROM raft_log WHERE log_index >= ?", (start_index,))
            self._insert_entries(entries)

    @staticmethod
    def _check_index(index):
        if type(index) is not int or index < 1:
            raise ValueError("Log index must be a positive integer")

    @staticmethod
    def _check_entries(start_index, entries):
        for index, entry in enumerate(entries, start=start_index):
            if entry.index != index:
                raise ValueError("Log entries must have consecutive indices starting at the insertion point")
            if entry.term < 1:
                raise ValueError("Log entry term must be positive")

    def _insert_entries(self, entries):
        self._db.executemany(
            "INSERT INTO raft_log (log_index, term, command) VALUES (?, ?, ?)",
            [(entry.index, entry.term, entry.command) for entry in entries],
        )

    def close(self):
        self._db.close()
