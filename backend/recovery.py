"""Read-only checks of restored Raft/application metadata before serving RPCs."""

from contextlib import closing
from pathlib import Path
import sqlite3


def validate_recovery(node_id, database):
    database = Path(database).resolve()
    try:
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
            state = db.execute("SELECT current_term FROM raft_state WHERE id = 1").fetchone()
            if state is None or type(state[0]) is not int or state[0] < 0:
                raise ValueError("Missing or invalid current term")
            last_index, previous_term = 0, 0
            for index, term in db.execute("SELECT log_index, term FROM raft_log ORDER BY log_index"):
                if index != last_index + 1:
                    raise ValueError(f"Log indices must be consecutive from 1; expected {last_index + 1}, found {index}")
                if type(term) is not int or not 0 < term <= state[0] or term < previous_term:
                    raise ValueError(f"Invalid term {term} at log index {index}; terms must be positive, nondecreasing, and at most current term {state[0]}")
                last_index, previous_term = index, term
            progress = db.execute("SELECT last_applied FROM application_state WHERE id = 1").fetchone()
            if progress is None or type(progress[0]) is not int or not 0 <= progress[0] <= last_index:
                raise ValueError(f"Applied progress must be between 0 and log tail {last_index}")
            applied = progress[0]
            count, first, last = db.execute(
                "SELECT count(*), min(log_index), max(log_index) FROM applied_results",
            ).fetchone()
            if count != applied or (count and (first != 1 or last != applied)):
                raise ValueError(f"Saved outcomes must cover exactly indices 1..{applied}")
            return last_index, applied
    except (sqlite3.Error, ValueError) as error:
        raise ValueError(
            f"Recovery refused for {node_id} at {database}: {error}. "
            "Retain this database for inspection; no automatic repair was attempted."
        ) from error
