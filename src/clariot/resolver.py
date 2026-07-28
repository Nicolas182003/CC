"""Resolves a report's phrases into Spanish, in three layers.

    1. config/glossary.yaml   — wording Emeltec chose. Always wins.
    2. the phrase cache       — already translated once. Free and identical.
    3. the translation API    — a phrase nobody has seen before.

Layer 2 is what makes this trustworthy. A translation service asked the same
question twice can answer differently, and a client comparing January's report
against March's would see the same condition described two ways. Caching the
first answer removes that: every phrase is resolved once and reused forever.

Layer 1 exists so the team can override anything they dislike without waiting for
anyone. Write it in the YAML and it wins from that moment on.

Exposes the same ``apply()`` as :class:`~clariot.glossary.Glossary`, so it drops
into the report pipeline unchanged.
"""

from __future__ import annotations

import logging
from typing import Sequence

from .glossary import Glossary, TranslationResult, UNTRANSLATED_MARK, _key
from .models import AlertReport

logger = logging.getLogger(__name__)


class PhraseResolver:
    """Resolves phrases through the glossary, then the cache, then the API."""
    def __init__(
        self,
        glossary: Glossary,
        store,
        translator=None,
        mark_unresolved: bool = True,
    ) -> None:
        self.glossary = glossary
        self.store = store
        self.translator = translator
        self.mark_unresolved = mark_unresolved
        self.api_calls = 0
        self.api_phrases = 0

    # ------------------------------------------------------------------ lookup

    def _resolve_many(self, texts: Sequence[str]) -> dict[str, str]:
        """Map each source phrase to its Spanish, translating what is unknown."""
        found: dict[str, str] = {}
        unknown: list[str] = []

        for text in texts:
            target = self.glossary.lookup(text)
            if target:
                found[text] = target
                continue
            if self.glossary.is_spanish_already(text):
                found[text] = text
                continue
            cached = self.store.cached_phrase(_key(text))
            if cached:
                found[text] = cached
                continue
            unknown.append(text)

        if not unknown:
            return found

        if self.translator is None:
            logger.warning(
                "%s phrase(s) are new and no translator is configured", len(unknown)
            )
            return found

        try:
            translations = self.translator.translate(unknown)
        except Exception as exc:  # noqa: BLE001 - network or auth failure
            # Degrades instead of breaking: the caller decides whether to hold the
            # draft or mark it. Nothing is cached, so the next run retries.
            logger.error("Could not translate %s new phrase(s): %s", len(unknown), exc)
            return found

        self.api_calls += 1
        self.api_phrases += len(unknown)
        provider = getattr(self.translator, "name", "api")

        for source, target in zip(unknown, translations):
            if not target:
                continue
            self.store.cache_phrase(_key(source), source, target, provider)
            found[source] = target
            logger.info("Nueva frase traducida y guardada: %r -> %r", source, target)

        return found

    # ------------------------------------------------------------------- apply

    def apply(self, report: AlertReport) -> TranslationResult:
        fields = self.glossary.translatable_fields
        originals = {
            name: report.fields[name]
            for name in fields
            if report.fields.get(name)
        }

        resolved = self._resolve_many(list(dict.fromkeys(originals.values())))

        translated = dict(report.fields)
        missing: list[tuple[str, str]] = []
        for name, original in originals.items():
            target = resolved.get(original)
            if target:
                translated[name] = target
            else:
                missing.append((name, original))
                if self.mark_unresolved:
                    translated[name] = f"{UNTRANSLATED_MARK} {original}"

        return TranslationResult(
            report=AlertReport(fields=translated), missing=tuple(missing)
        )

    def __len__(self) -> int:
        return len(self.glossary)
