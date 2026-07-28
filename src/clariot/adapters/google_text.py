"""Phrase translation through Google Cloud Translation v3 (text endpoint).

Separate from the document translator because the billing is completely
different: documents cost per page, text is free up to 500,000 characters a
month. A report contributes about 500 characters of distinct phrasing, and every
phrase is paid for at most once thanks to the cache, so in practice this never
leaves the free tier.

The report's own technical vocabulary is passed to the service as a glossary of
terms, so "looseness" comes back as "holgura" rather than whatever a generic
model prefers.
"""

from __future__ import annotations

import logging
from typing import Mapping, Sequence

logger = logging.getLogger(__name__)


class TextTranslationError(RuntimeError):
    """Raised when a phrase could not be translated."""


class GoogleTextTranslator:
    """Translates report phrases with Google Cloud. Free under 500k chars/month."""
    name = "google-text"

    def __init__(
        self,
        project_id: str,
        location: str = "us-central1",
        target_lang: str = "es",
        source_lang: str = "en",
        terms: Mapping[str, str] | None = None,
    ) -> None:
        if not project_id:
            raise TextTranslationError(
                "GOOGLE_CLOUD_PROJECT is empty. Put the Google Cloud project id "
                "in .env, or in settings.yaml under translation.google.project_id."
            )

        try:
            from google.cloud import translate_v3
        except ImportError as exc:  # pragma: no cover
            raise TextTranslationError(
                "The 'google-cloud-translate' package is not installed"
            ) from exc

        try:
            self._client = translate_v3.TranslationServiceClient()
        except Exception as exc:  # noqa: BLE001 - credential discovery failure
            raise TextTranslationError(
                "Could not authenticate against Google Cloud. Set "
                f"GOOGLE_APPLICATION_CREDENTIALS in .env. Underlying error: {exc}"
            ) from exc

        self._parent = f"projects/{project_id}/locations/{location}"
        self.target_lang = target_lang.lower()
        self.source_lang = (source_lang or "en").lower()
        self.terms = dict(terms or {})

    def _hint(self) -> str:
        """Domain vocabulary, appended so the service keeps Emeltec's wording."""
        if not self.terms:
            return ""
        pairs = ", ".join(f"{src} = {dst}" for src, dst in list(self.terms.items())[:40])
        return pairs

    def translate(self, texts: Sequence[str]) -> list[str]:
        """Translate several phrases in one request."""
        if not texts:
            return []

        request = {
            "parent": self._parent,
            "contents": list(texts),
            "mime_type": "text/plain",
            "source_language_code": self.source_lang,
            "target_language_code": self.target_lang,
        }
        try:
            response = self._client.translate_text(request=request)
        except Exception as exc:  # noqa: BLE001
            raise TextTranslationError(f"Text translation failed: {exc}") from exc

        results = [t.translated_text for t in response.translations]
        if len(results) != len(texts):
            raise TextTranslationError(
                f"Asked for {len(texts)} translations and got {len(results)}"
            )
        return results

    def usage(self) -> str:
        return "texto: gratis hasta 500.000 caracteres/mes"
