"""Reporting stage: one weekly draft per client, from what has accumulated.

Run on Friday. Takes every stored event that no report has covered yet, groups it
per client and per machine, and leaves a draft for review.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from jinja2 import Environment

from .aggregate import group_by_company, group_by_equipment, period_of, spanish_period
from .audit import AuditLog
from .config import ClientDirectory, Settings
from .report_builder import build_weekly_draft
from .store import EventStore

logger = logging.getLogger(__name__)


@dataclass
class WeeklyReport:
    """What one weekly run did."""
    clients: int = 0
    events: int = 0
    drafts: int = 0
    pending_recipient: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        if not self.events:
            return "no hay alarmas pendientes de informar"
        parts = [
            f"{self.events} alarmas",
            f"{self.clients} cliente(s)",
            f"{self.drafts} informes listos",
        ]
        if self.pending_recipient:
            parts.append(f"{self.pending_recipient} esperan destinatario")
        if self.failed:
            parts.append(f"{self.failed} con error")
        return " | ".join(parts)


class WeeklyReporter:
    """Builds one consolidated draft per client from what has accumulated."""
    def __init__(
        self,
        *,
        settings: Settings,
        glossary,
        directory: ClientDirectory,
        outlook,
        store: EventStore,
        audit: AuditLog,
        env: Environment,
        dry_run: bool = False,
    ) -> None:
        self.settings = settings
        self.glossary = glossary
        self.directory = directory
        self.outlook = outlook
        self.store = store
        self.audit = audit
        self.env = env
        self.dry_run = dry_run

    def run(self) -> WeeklyReport:
        report = WeeklyReport()
        pending = self.store.pending()

        if not pending:
            logger.info("Nothing pending: no weekly report to build")
            return report

        start, end = period_of(pending)
        logger.info(
            "%s pending alarm(s) covering %s", len(pending), spanish_period(start, end)
        )

        report.events = len(pending)
        by_client = group_by_company(pending)
        report.clients = len(by_client)

        for company, events in by_client.items():
            try:
                self._one_client(company, events, report)
            except Exception as exc:  # noqa: BLE001 - one client must not break the rest
                logger.exception("Failed to build the weekly report for %s", company)
                report.failed += 1
                report.errors.append(f"{company}: {exc}")

        return report

    def _one_client(self, company: str, events, report: WeeklyReport) -> None:
        summaries = group_by_equipment(
            events, self.glossary, self.settings.critical_urgencies
        )
        draft = build_weekly_draft(
            company, summaries, self.directory, self.settings, self.env
        )

        if self.dry_run:
            logger.info(
                "[dry-run] Would create the weekly report for %s: %s",
                company,
                draft.subject,
            )
            return

        self.outlook.create_draft(
            subject=draft.subject,
            html_body=draft.html_body,
            to=draft.to,
            cc=draft.cc,
            attachments=draft.attachments,
            sender_account=self.settings.email.sender_account,
            target_folder=self.settings.outlook.draft_folder,
            target_folder_parent=self.settings.outlook.draft_folder_parent,
        )
        # Marked as soon as the draft exists: a failure afterwards must not send
        # the same alarms out twice next week.
        self.store.mark_reported(draft.event_keys, draft.kind)

        report.drafts += 1
        if not draft.client_resolved:
            report.pending_recipient += 1

        start, end = period_of(events)
        self.audit.record(
            message_key=f"informe-semanal/{company}",
            original_subject=f"{len(events)} alarmas de {company}",
            company=company,
            recipients="; ".join(draft.to),
            draft_subject=draft.subject,
            status="informe_semanal",
            detail=(
                f"{len(summaries)} equipo(s), periodo {spanish_period(start, end)}"
                + ("" if draft.client_resolved else "; destinatario a completar")
            ),
        )
