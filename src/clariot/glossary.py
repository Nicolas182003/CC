"""Phrase-level translation from an approved glossary.

The reports are template-generated, so their wording comes from a closed
catalogue. Translating whole phrases from a reviewed list beats a generic
translator on the two things that matter here: correct technical terminology and
identical wording across reports.

Anything absent from the glossary is left in English and marked, never guessed.
A wrong technical term reaching a client is worse than an obviously untranslated
one, because the untranslated one gets noticed and fixed.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import yaml

from .models import AlertReport
from .textutils import normalize

logger = logging.getLogger(__name__)

UNTRANSLATED_MARK = "[EN]"

DEFAULT_TRANSLATABLE = (
    "event_type",
    "equipment_status",
    "possible_cause",
    "recommended_action",
    "urgency",
    "machine_type",
)


def _key(text: str) -> str:
    """Lookup key: accent-, case- and punctuation-insensitive."""
    return re.sub(r"[.;,]+$", "", normalize(text)).strip()


@dataclass(frozen=True)
class TranslationResult:
    """A translated report plus whatever could not be resolved."""
    report: AlertReport
    missing: tuple[tuple[str, str], ...]
    """Field name and original text for every phrase not in the glossary."""

    @property
    def complete(self) -> bool:
        return not self.missing


class Glossary:
    """The phrases and vocabulary Emeltec approved. Overrides everything else."""
    def __init__(
        self,
        phrases: Mapping[str, str],
        translatable_fields: Sequence[str] = DEFAULT_TRANSLATABLE,
        terms: Mapping[str, str] | None = None,
    ) -> None:
        self._phrases = {_key(source): target for source, target in phrases.items()}
        self._fields = tuple(translatable_fields)
        self._terms = dict(terms or {})

    @classmethod
    def load(cls, config_dir: Path) -> "Glossary":
        path = config_dir / "glossary.yaml"
        if not path.exists():
            logger.warning("No glossary at %s; values will be left in English", path)
            return cls({})

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        phrases = data.get("phrases") or {}
        if not isinstance(phrases, Mapping):
            raise ValueError("glossary.yaml: 'phrases' must be a mapping")

        fields = data.get("translatable_fields") or DEFAULT_TRANSLATABLE
        terms = data.get("terms") or {}
        return cls(
            {str(source): str(target) for source, target in phrases.items()},
            tuple(str(name) for name in fields),
            {str(source): str(target) for source, target in terms.items()},
        )

    def __len__(self) -> int:
        return len(self._phrases)

    @property
    def translatable_fields(self) -> tuple[str, ...]:
        return self._fields

    @property
    def terms(self) -> dict[str, str]:
        """Domain vocabulary, passed to the translation service as a hint."""
        return dict(self._terms)

    def lookup(self, text: str) -> str | None:
        return self._phrases.get(_key(text))

    def is_spanish_already(self, text: str) -> bool:
        """True when the phrase is already an approved Spanish target.

        Some reports arrive pre-translated. Marking those as untranslated would
        send the technician chasing phantom gaps.
        """
        targets = {_key(target) for target in self._phrases.values()}
        return _key(text) in targets

    def apply(self, report: AlertReport) -> TranslationResult:
        """Translate the configured fields, marking whatever is missing."""
        translated = dict(report.fields)
        missing: list[tuple[str, str]] = []

        for name in self._fields:
            original = report.fields.get(name)
            if not original:
                continue

            target = self.lookup(original)
            if target:
                translated[name] = target
            elif self.is_spanish_already(original):
                continue
            else:
                translated[name] = f"{UNTRANSLATED_MARK} {original}"
                missing.append((name, original))

        if missing:
            logger.warning(
                "%s phrase(s) missing from config/glossary.yaml: %s",
                len(missing),
                "; ".join(f"{name}={text!r}" for name, text in missing),
            )

        return TranslationResult(
            report=AlertReport(fields=translated), missing=tuple(missing)
        )
