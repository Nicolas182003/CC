"""Decides whether an alarm goes out today or waits for the weekly report.

Pure logic over a list of stored events, so every rule is testable without a
database, without Outlook and without PDFs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence

from .store import StoredEvent
from .textutils import normalize

logger = logging.getLogger(__name__)

LEVEL_CRITICAL = "critical"
LEVEL_URGENT = "urgent"
LEVEL_NORMAL = "normal"

IMMEDIATE_LEVELS = (LEVEL_CRITICAL, LEVEL_URGENT)

# Higher means worse. A report only goes out when severity climbs.
SEVERITY = {LEVEL_NORMAL: 0, LEVEL_URGENT: 1, LEVEL_CRITICAL: 2}


@dataclass(frozen=True)
class Classification:
    """A level, why it was chosen, and the alarms it was chosen from."""
    level: str
    reason: str
    """Human-readable justification. Ends up in the log and the audit trail."""
    events: tuple[StoredEvent, ...]
    """Every event of that machine inside the window, newest first."""

    @property
    def immediate(self) -> bool:
        return self.level in IMMEDIATE_LEVELS

    @property
    def count(self) -> int:
        return len(self.events)


class Classifier:
    """Assigns a severity level to an alarm from its machine's recent history."""
    def __init__(
        self,
        *,
        window_days: int = 7,
        urgent_threshold: int = 2,
        same_day_is_critical: bool = True,
        urgency_cooldown_days: int = 7,
        critical_urgencies: frozenset[str] = frozenset(),
    ) -> None:
        self.window_days = window_days
        self.urgent_threshold = urgent_threshold
        self.same_day_is_critical = same_day_is_critical
        self.urgency_cooldown_days = urgency_cooldown_days
        self.critical_urgencies = critical_urgencies

    def _in_window(
        self, event: StoredEvent, history: Sequence[StoredEvent], now: datetime
    ) -> list[StoredEvent]:
        reference = event.event_at or now
        cutoff = reference - timedelta(days=self.window_days)
        selected = [
            other
            for other in history
            # An event with no parseable timestamp still counts: dropping it would
            # hide a real alarm.
            if other.event_at is None or other.event_at >= cutoff
        ]
        if all(other.event_key != event.event_key for other in selected):
            selected.append(event)
        return sorted(
            selected,
            key=lambda e: e.event_at or datetime.min,
            reverse=True,
        )

    def _same_day(
        self, event: StoredEvent, window: Sequence[StoredEvent]
    ) -> list[StoredEvent]:
        if event.event_at is None:
            return []
        day = event.event_at.date()
        return [
            other
            for other in window
            if other.event_at is not None and other.event_at.date() == day
        ]

    def _declared_critical(self, event: StoredEvent) -> bool:
        return bool(event.urgency) and normalize(event.urgency) in self.critical_urgencies

    def classify(
        self,
        event: StoredEvent,
        history: Sequence[StoredEvent],
        *,
        last_urgency_report: datetime | None = None,
        last_urgency_level: str | None = None,
        now: datetime | None = None,
    ) -> Classification:
        """Assign a level to a freshly stored event.

        ``history`` is every stored event of the same machine, the new one
        included or not — either way it is counted exactly once.
        """
        now = now or datetime.now()
        window = self._in_window(event, history, now)
        same_day = self._same_day(event, window)

        if self.same_day_is_critical and len(same_day) >= self.urgent_threshold:
            level, reason = LEVEL_CRITICAL, (
                f"{len(same_day)} eventos del mismo equipo el mismo dia "
                f"({event.event_at.date().isoformat()})"  # type: ignore[union-attr]
            )
            return self._respect_cooldown(
                level, reason, window, last_urgency_report, last_urgency_level, now
            )

        if len(window) >= self.urgent_threshold:
            level, reason = LEVEL_URGENT, (
                f"{len(window)} eventos del mismo equipo en {self.window_days} dias"
            )
        elif self._declared_critical(event):
            level, reason = LEVEL_URGENT, (
                f"urgencia declarada por el reporte: {event.urgency!r}"
            )
        else:
            return Classification(
                LEVEL_NORMAL, "evento aislado", tuple(window)
            )

        return self._respect_cooldown(
            level, reason, window, last_urgency_report, last_urgency_level, now
        )

    def _respect_cooldown(
        self,
        level: str,
        reason: str,
        window: Sequence[StoredEvent],
        last_report: datetime | None,
        last_level: str | None,
        now: datetime,
    ) -> Classification:
        """Suppress a report unless severity actually climbed.

        The client should hear from us when things get worse, not every time the
        same condition repeats. Within the cooldown a report only goes out if its
        level is higher than the last one sent for that machine.
        """
        if last_report is None or self.urgency_cooldown_days <= 0:
            return Classification(level, reason, tuple(window))

        elapsed = now - last_report
        if elapsed >= timedelta(days=self.urgency_cooldown_days):
            return Classification(level, reason, tuple(window))

        if SEVERITY.get(level, 0) > SEVERITY.get(last_level or LEVEL_NORMAL, 0):
            return Classification(
                level, f"{reason}; escala desde '{last_level}'", tuple(window)
            )

        logger.info(
            "Already reported at level '%s' %s ago; deferring to the weekly report",
            last_level,
            elapsed,
        )
        return Classification(
            LEVEL_NORMAL,
            f"{reason}, pero ya se informo al mismo nivel hace {elapsed.days} dia(s)",
            tuple(window),
        )
