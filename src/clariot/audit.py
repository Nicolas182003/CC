"""Append-only audit trail of every alert the pipeline touched."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

HEADERS = (
    "processed_at",
    "message_key",
    "original_subject",
    "company",
    "machine",
    "urgency",
    "recipients",
    "draft_subject",
    "status",
    "detail",
)


class AuditLog:
    """Append-only CSV of every alert touched and the decision taken."""
    def __init__(self, csv_path: Path) -> None:
        self.csv_path = csv_path
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        if not csv_path.exists():
            with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
                csv.writer(handle, delimiter=";").writerow(HEADERS)

    def record(self, **values: str) -> None:
        row = [values.get(header, "") for header in HEADERS]
        row[0] = values.get("processed_at") or datetime.now().isoformat(timespec="seconds")
        with self.csv_path.open("a", newline="", encoding="utf-8-sig") as handle:
            csv.writer(handle, delimiter=";").writerow(row)
