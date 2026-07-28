"""Durable store of the alarm events extracted from the reports.

Separate from the ledger on purpose, because they guard different things:

* ``ledger`` — has this *email* been processed? Prevents duplicate work.
* ``store``  — has this *event* been counted? Prevents duplicate counting.

The distinction matters. Alert systems resend notifications, so two emails can
describe one event. Counting emails would fire a false urgency report for a
single real problem.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Sequence

from .models import AlertReport
from .textutils import normalize

logger = logging.getLogger(__name__)

REPORT_PENDING = ""
REPORT_URGENT = "urgent"
REPORT_CRITICAL = "critical"
REPORT_WEEKLY = "weekly"
# An isolated alarm reported on its own. Deliberately NOT an urgency level, so it
# never counts as "already escalated" when the next alarm arrives.
REPORT_SINGLE = "single"

# Day-first, matching the observed "21-07-2026 20:14". Verify against a real
# English original: an American generator could emit month-first instead.
_DATE_FORMATS = (
    "%d-%m-%Y %H:%M",
    "%d/%m/%Y %H:%M",
    "%d-%m-%Y %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%Y-%m-%d",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_key          TEXT PRIMARY KEY,
    equipment_key      TEXT NOT NULL,
    company            TEXT,
    plant              TEXT,
    machine            TEXT,
    serial_number      TEXT,
    machine_type       TEXT,
    event_at           TEXT,
    event_date_raw     TEXT,
    event_type         TEXT,
    equipment_status   TEXT,
    possible_cause     TEXT,
    recommended_action TEXT,
    urgency            TEXT,
    pdf_path           TEXT,
    pdf_translated     TEXT,
    message_key        TEXT,
    ingested_at        TEXT NOT NULL,
    reported_at        TEXT,
    report_kind        TEXT NOT NULL DEFAULT '',
    -- Set when no draft could be built yet, e.g. the glossary is missing a
    -- phrase. Cleared once the draft exists.
    blocked_reason     TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_equipment ON events (equipment_key);
CREATE INDEX IF NOT EXISTS idx_events_pending ON events (reported_at);

-- Translations already resolved. A phrase is paid for once, then reused, so the
-- same condition is always worded the same way in every report.
CREATE TABLE IF NOT EXISTS phrase_cache (
    source_key TEXT PRIMARY KEY,
    source     TEXT NOT NULL,
    target     TEXT NOT NULL,
    provider   TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- One open draft per machine, which later alarms of the same week join instead
-- of producing a second email.
CREATE TABLE IF NOT EXISTS open_drafts (
    equipment_key  TEXT PRIMARY KEY,
    entry_id       TEXT NOT NULL,
    kind           TEXT NOT NULL,
    first_event_at TEXT,
    updated_at     TEXT NOT NULL
);
"""


def parse_event_datetime(text: str | None) -> datetime | None:
    """Best-effort parse of the report's event timestamp."""
    if not text:
        return None
    cleaned = re.sub(r"\s+", " ", text.replace("­", "-")).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    logger.warning("Could not parse the event timestamp %r", text)
    return None


def serial_from_subject(subject: str | None) -> str:
    """Pull the equipment serial out of the email subject.

    Observed subject: ``Event notification report - VX-3037575``, where the
    trailing token is the serial and everything before it is boilerplate. Matching
    on the tail rather than the prefix means a reworded prefix — "2nd
    notification", a "Re:" — does not break it.

    This is a fallback for when the PDF layout changes and the parser stops
    finding the serial. Without a serial the grouping falls back to the machine
    name, and repeated alarms on one pump would stop being detected — which is the
    whole point of the system.
    """
    if not subject:
        return ""
    # Split on " - ", not on "-": the serial itself contains a hyphen
    # ("VX-3037575"), so a bare hyphen split would cut it in half.
    candidate = re.split(r"\s+-\s+", subject.strip())[-1].strip()
    # Real subjects end in a full stop: "Event notification report - VX-3037575."
    # Left in, the serial would not match the one parsed from the PDF and the same
    # pump would count as two machines.
    candidate = candidate.strip(" .,;:")
    # An identifier: no spaces, and long enough not to be a stray character.
    if len(candidate) < 3 or " " in candidate or candidate == subject.strip():
        return ""
    return candidate


def equipment_key(report: AlertReport) -> str:
    """Stable identity of a machine, scoped to its company.

    Serial number first: machine names are spelled differently across reports,
    serial numbers are not.
    """
    company = normalize(report.company or "")
    serial = normalize(report.fields.get("serial_number") or "")
    machine = normalize(report.machine or "")
    return f"{company}|{serial or machine or 'SIN-EQUIPO'}"


def event_key(report: AlertReport, fallback: str) -> str:
    """Identity of one alarm event.

    Equipment plus the report's own timestamp, so a resent notification about the
    same event resolves to the same key. When the report carries no timestamp the
    fallback keeps events distinct — better one urgency report too many than a
    lost alarm.
    """
    stamp = parse_event_datetime(report.fields.get("event_date"))
    if stamp is None:
        return f"{equipment_key(report)}|sin-fecha|{fallback}"
    return f"{equipment_key(report)}|{stamp.isoformat()}"


@dataclass(frozen=True)
class StoredEvent:
    """One alarm as recorded, with the report's original wording.

    Kept untranslated on purpose: translating at report time means improving the
    glossary later also improves events ingested before the phrase was known.
    """
    event_key: str
    equipment_key: str
    company: str
    plant: str
    machine: str
    serial_number: str
    machine_type: str
    event_at: datetime | None
    event_date_raw: str
    event_type: str
    equipment_status: str
    possible_cause: str
    recommended_action: str
    urgency: str
    pdf_path: str
    pdf_translated: str
    message_key: str
    ingested_at: str
    reported_at: str | None
    report_kind: str
    blocked_reason: str | None = None

    @property
    def machine_label(self) -> str:
        return self.machine or "Equipo sin identificar"

    @property
    def reported(self) -> bool:
        return bool(self.reported_at)


_COLUMNS = (
    "event_key",
    "equipment_key",
    "company",
    "plant",
    "machine",
    "serial_number",
    "machine_type",
    "event_at",
    "event_date_raw",
    "event_type",
    "equipment_status",
    "possible_cause",
    "recommended_action",
    "urgency",
    "pdf_path",
    "pdf_translated",
    "message_key",
    "ingested_at",
    "reported_at",
    "report_kind",
    "blocked_reason",
)


def _row_to_event(row: Sequence) -> StoredEvent:
    data = dict(zip(_COLUMNS, row))
    raw_at = data.pop("event_at")
    return StoredEvent(
        event_at=datetime.fromisoformat(raw_at) if raw_at else None, **data
    )


def build_event(
    report: AlertReport,
    *,
    message_key: str,
    pdf_path: str = "",
    pdf_translated: str = "",
    now: datetime | None = None,
) -> StoredEvent:
    """Turn a parsed report into an event, without persisting anything.

    Used by ``EventStore.record`` and by everything that needs an event but must
    leave no trace: ``--dry-run`` and ``--preview``.
    """
    stamp = parse_event_datetime(report.fields.get("event_date"))
    return StoredEvent(
        event_key=event_key(report, fallback=message_key),
        equipment_key=equipment_key(report),
        company=report.company or "",
        plant=report.fields.get("plant") or "",
        machine=report.machine or "",
        serial_number=report.fields.get("serial_number") or "",
        machine_type=report.fields.get("machine_type") or "",
        event_at=stamp,
        event_date_raw=report.fields.get("event_date") or "",
        event_type=report.fields.get("event_type") or "",
        equipment_status=report.fields.get("equipment_status") or "",
        possible_cause=report.fields.get("possible_cause") or "",
        recommended_action=report.fields.get("recommended_action") or "",
        urgency=report.urgency or "",
        pdf_path=pdf_path,
        pdf_translated=pdf_translated,
        message_key=message_key,
        ingested_at=(now or datetime.now()).isoformat(timespec="seconds"),
        reported_at=None,
        report_kind=REPORT_PENDING,
        blocked_reason=None,
    )


class EventStore:
    """The alarms, the phrase cache and the open drafts, in one SQLite file."""
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.executescript(_SCHEMA)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    # ------------------------------------------------------------------ writing

    def record(
        self,
        report: AlertReport,
        *,
        message_key: str,
        pdf_path: str = "",
        pdf_translated: str = "",
        now: datetime | None = None,
    ) -> tuple[StoredEvent, bool]:
        """Store an event. Returns the event and whether it was new.

        A repeat of an already-known event is not stored again and reports
        ``False``, so the caller can archive the PDF without counting the alarm
        twice.
        """
        key = event_key(report, fallback=message_key)
        existing = self.get(key)
        if existing is not None:
            logger.info(
                "Event already counted (%s); the report is a resend of %s",
                key,
                existing.event_date_raw or "an undated event",
            )
            return existing, False

        event = build_event(
            report,
            message_key=message_key,
            pdf_path=pdf_path,
            pdf_translated=pdf_translated,
            now=now,
        )
        values = {name: getattr(event, name) for name in _COLUMNS}
        values["event_at"] = event.event_at.isoformat() if event.event_at else None

        placeholders = ", ".join("?" for _ in _COLUMNS)
        with closing(self._connect()) as conn:
            conn.execute(
                f"INSERT INTO events ({', '.join(_COLUMNS)}) VALUES ({placeholders})",
                [values[name] for name in _COLUMNS],
            )
            conn.commit()
        return self.get(key), True  # type: ignore[return-value]

    def mark_blocked(self, key: str, reason: str) -> None:
        """No draft could be built for this alarm yet. It will be retried."""
        with closing(self._connect()) as conn:
            conn.execute(
                "UPDATE events SET blocked_reason = ? WHERE event_key = ?",
                (reason[:500], key),
            )
            conn.commit()

    def clear_blocked(self, keys: Iterable[str]) -> None:
        with closing(self._connect()) as conn:
            conn.executemany(
                "UPDATE events SET blocked_reason = NULL WHERE event_key = ?",
                [(key,) for key in keys],
            )
            conn.commit()

    def blocked(self) -> list[StoredEvent]:
        """Alarms held back, oldest first. Nothing reached the client for these."""
        return self._query(
            "WHERE reported_at IS NULL AND blocked_reason IS NOT NULL "
            "ORDER BY ingested_at ASC"
        )

    def mark_reported(
        self, keys: Iterable[str], kind: str, now: datetime | None = None
    ) -> int:
        stamp = (now or datetime.now()).isoformat(timespec="seconds")
        keys = list(keys)
        if not keys:
            return 0
        with closing(self._connect()) as conn:
            conn.executemany(
                "UPDATE events SET reported_at = ?, report_kind = ?, "
                "blocked_reason = NULL WHERE event_key = ?",
                [(stamp, kind, key) for key in keys],
            )
            conn.commit()
        return len(keys)

    # ------------------------------------------------------------------ reading

    def _query(self, where: str, params: Sequence = ()) -> list[StoredEvent]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"SELECT {', '.join(_COLUMNS)} FROM events {where}", tuple(params)
            ).fetchall()
        return [_row_to_event(row) for row in rows]

    def get(self, key: str) -> StoredEvent | None:
        found = self._query("WHERE event_key = ?", (key,))
        return found[0] if found else None

    def history_for(
        self, equipment: str, since: datetime | None = None
    ) -> list[StoredEvent]:
        """Every stored event of one machine, newest first.

        Filtering by date happens in Python: events with no parseable timestamp
        must not be silently dropped from the count.
        """
        events = self._query(
            "WHERE equipment_key = ? ORDER BY ingested_at DESC", (equipment,)
        )
        if since is None:
            return events
        return [
            event
            for event in events
            if event.event_at is None or event.event_at >= since
        ]

    def pending(self) -> list[StoredEvent]:
        """Events not yet included in any report, oldest first."""
        return self._query("WHERE reported_at IS NULL ORDER BY ingested_at ASC")

    def last_urgency_level(self, equipment: str) -> str | None:
        """Severity of the most recent urgency report for this machine.

        Lets the classifier escalate only when things get worse, instead of
        emailing the client the same level again.
        """
        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT report_kind FROM events
                 WHERE equipment_key = ? AND report_kind IN (?, ?)
                 ORDER BY reported_at DESC LIMIT 1
                """,
                (equipment, REPORT_URGENT, REPORT_CRITICAL),
            ).fetchone()
        return row[0] if row else None

    def last_urgency_report(self, equipment: str) -> datetime | None:
        """When an urgency report was last issued for this machine."""
        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT MAX(reported_at) FROM events
                 WHERE equipment_key = ? AND report_kind IN (?, ?)
                """,
                (equipment, REPORT_URGENT, REPORT_CRITICAL),
            ).fetchone()
        return datetime.fromisoformat(row[0]) if row and row[0] else None

    # -------------------------------------------------------------- open drafts

    def remember_draft(
        self,
        equipment: str,
        entry_id: str,
        kind: str,
        first_event_at: datetime | None,
        now: datetime | None = None,
    ) -> None:
        """Record which draft later alarms of this machine should join."""
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO open_drafts
                    (equipment_key, entry_id, kind, first_event_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(equipment_key) DO UPDATE SET
                    entry_id = excluded.entry_id,
                    kind = excluded.kind,
                    first_event_at = excluded.first_event_at,
                    updated_at = excluded.updated_at
                """,
                (
                    equipment,
                    entry_id,
                    kind,
                    first_event_at.isoformat() if first_event_at else None,
                    (now or datetime.now()).isoformat(timespec="seconds"),
                ),
            )
            conn.commit()

    def open_draft(self, equipment: str) -> tuple[str, str, datetime | None] | None:
        """The draft later alarms may join: ``(entry_id, kind, first_event_at)``."""
        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT entry_id, kind, first_event_at FROM open_drafts
                 WHERE equipment_key = ?
                """,
                (equipment,),
            ).fetchone()
        if not row:
            return None
        return row[0], row[1], datetime.fromisoformat(row[2]) if row[2] else None

    def open_draft_level(self, equipment: str) -> str | None:
        """Severity the open draft currently carries, so it is never downgraded."""
        record = self.open_draft(equipment)
        if record is None:
            return None
        kind = record[1]
        # Draft kinds map back to classifier levels.
        return {REPORT_CRITICAL: "critical", REPORT_URGENT: "urgent"}.get(kind, "normal")

    def forget_draft(self, equipment: str) -> None:
        """Stop joining that draft: it was sent, deleted or its week is over."""
        with closing(self._connect()) as conn:
            conn.execute("DELETE FROM open_drafts WHERE equipment_key = ?", (equipment,))
            conn.commit()

    # ------------------------------------------------------------ phrase cache

    def cached_phrase(self, source_key: str) -> str | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT target FROM phrase_cache WHERE source_key = ?", (source_key,)
            ).fetchone()
        return row[0] if row else None

    def cache_phrase(
        self,
        source_key: str,
        source: str,
        target: str,
        provider: str,
        now: datetime | None = None,
    ) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO phrase_cache (source_key, source, target, provider, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source_key) DO UPDATE SET
                    target = excluded.target,
                    provider = excluded.provider,
                    created_at = excluded.created_at
                """,
                (
                    source_key,
                    source,
                    target,
                    provider,
                    (now or datetime.now()).isoformat(timespec="seconds"),
                ),
            )
            conn.commit()

    def cached_phrases(self) -> list[tuple[str, str, str]]:
        """Everything translated so far: ``(source, target, provider)``.

        Useful to review the wording and promote anything worth fixing into
        config/glossary.yaml, which overrides the cache.
        """
        with closing(self._connect()) as conn:
            return [
                (row[0], row[1], row[2])
                for row in conn.execute(
                    "SELECT source, target, provider FROM phrase_cache ORDER BY created_at"
                ).fetchall()
            ]

    def count(self) -> int:
        with closing(self._connect()) as conn:
            return conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    def purge_older_than(self, days: int, now: datetime | None = None) -> int:
        """Drop reported events past their retention window."""
        cutoff = ((now or datetime.now()) - timedelta(days=days)).isoformat()
        with closing(self._connect()) as conn:
            cursor = conn.execute(
                "DELETE FROM events WHERE reported_at IS NOT NULL AND ingested_at < ?",
                (cutoff,),
            )
            conn.commit()
            return cursor.rowcount
