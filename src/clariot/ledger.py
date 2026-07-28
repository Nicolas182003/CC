"""Durable record of which alerts have been processed.

The Outlook read flag is not a safe source of truth: a technician previewing a
message marks it read (the alert would be skipped forever), and a crash between
draft creation and the read flag update would produce a duplicate draft. This
ledger is the authority; the read flag is only a visual cue for humans.

Messages are keyed by their Internet Message-ID when available, because an
Outlook EntryID changes as soon as the item is moved to another folder.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

STATUS_IN_PROGRESS = "in_progress"
STATUS_DONE = "done"
STATUS_FAILED = "failed"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS processed_messages (
    message_key TEXT PRIMARY KEY,
    entry_id    TEXT,
    subject     TEXT,
    status      TEXT NOT NULL,
    attempts    INTEGER NOT NULL DEFAULT 0,
    updated_at  TEXT NOT NULL,
    error       TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Ledger:
    """Which emails have been processed. The authority, not Outlook's read flag."""
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.executescript(_SCHEMA)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    def status(self, message_key: str) -> str | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT status FROM processed_messages WHERE message_key = ?",
                (message_key,),
            ).fetchone()
        return row[0] if row else None

    def attempts(self, message_key: str) -> int:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT attempts FROM processed_messages WHERE message_key = ?",
                (message_key,),
            ).fetchone()
        return row[0] if row else 0

    def should_process(self, message_key: str, max_attempts: int = 3) -> bool:
        """Skip anything already delivered, or failing past the retry budget.

        An ``in_progress`` row means a previous run died mid-flight. Retrying is
        the right call: the draft either was never created, or the technician
        will see a duplicate, which is far better than a lost alert.
        """
        current = self.status(message_key)
        if current == STATUS_DONE:
            return False
        if current == STATUS_FAILED and self.attempts(message_key) >= max_attempts:
            return False
        return True

    def mark_in_progress(self, message_key: str, entry_id: str, subject: str) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO processed_messages
                    (message_key, entry_id, subject, status, attempts, updated_at)
                VALUES (?, ?, ?, ?, 1, ?)
                ON CONFLICT(message_key) DO UPDATE SET
                    status = excluded.status,
                    entry_id = excluded.entry_id,
                    attempts = processed_messages.attempts + 1,
                    updated_at = excluded.updated_at
                """,
                (message_key, entry_id, subject, STATUS_IN_PROGRESS, _now()),
            )
            conn.commit()

    def _set_status(self, message_key: str, status: str, error: str | None) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                UPDATE processed_messages
                   SET status = ?, error = ?, updated_at = ?
                 WHERE message_key = ?
                """,
                (status, error, _now(), message_key),
            )
            conn.commit()

    def mark_done(self, message_key: str) -> None:
        self._set_status(message_key, STATUS_DONE, None)

    def mark_failed(self, message_key: str, error: str) -> None:
        self._set_status(message_key, STATUS_FAILED, error[:2000])
