"""Full-document translation through Google Cloud Translation v3.

Chosen over DeepL for this workload for one reason: billing. DeepL's Document API
charges a minimum of 50,000 characters per file regardless of its real size, and
these reports hold roughly 3,000. Google charges per page, and the reports are one
page, so a translated alert costs about USD 0.08 instead of a 50,000-character
bite out of a monthly quota.

Layout is preserved on the service side, the same way the technician's manual
Google Translate pass works today.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PDF_MIME = "application/pdf"


class TranslationError(RuntimeError):
    """Raised when the document could not be translated."""


class GoogleDocumentTranslator:
    """Translates the whole PDF, layout preserved. Billed per page."""
    def __init__(
        self,
        project_id: str,
        location: str = "us-central1",
        target_lang: str = "es",
        source_lang: str = "",
    ) -> None:
        if not project_id:
            raise TranslationError(
                "GOOGLE_CLOUD_PROJECT is empty. Put the Google Cloud project id "
                "in .env, or in settings.yaml under translation.google.project_id."
            )

        try:
            from google.cloud import translate_v3
        except ImportError as exc:  # pragma: no cover
            raise TranslationError(
                "The 'google-cloud-translate' package is not installed"
            ) from exc

        try:
            self._client = translate_v3.TranslationServiceClient()
        except Exception as exc:  # noqa: BLE001 - credential discovery failure
            raise TranslationError(
                "Could not authenticate against Google Cloud. Set "
                "GOOGLE_APPLICATION_CREDENTIALS in .env to the path of the "
                f"service account JSON file. Underlying error: {exc}"
            ) from exc

        # Document translation is not served from the 'global' endpoint; it needs
        # a real region.
        self._parent = f"projects/{project_id}/locations/{location}"
        self.target_lang = target_lang.lower()
        self.source_lang = source_lang.lower()

    def usage(self) -> str:
        """Google exposes no quota endpoint; report the unit price instead."""
        return "por pagina (~USD 0.08); revisa el consumo en la consola de Google Cloud"

    def translate(self, source: Path, destination: Path) -> Path:
        """Translate a PDF into ``destination``, preserving the layout."""
        destination.parent.mkdir(parents=True, exist_ok=True)

        request: dict = {
            "parent": self._parent,
            "target_language_code": self.target_lang,
            "document_input_config": {
                "content": source.read_bytes(),
                "mime_type": PDF_MIME,
            },
        }
        # Left empty by default so the service detects the language: reports have
        # been seen both in English and already translated.
        if self.source_lang:
            request["source_language_code"] = self.source_lang

        try:
            response = self._client.translate_document(request=request)
        except Exception as exc:  # noqa: BLE001
            raise TranslationError(f"Document translation failed: {exc}") from exc

        outputs = list(response.document_translation.byte_stream_outputs)
        if not outputs:
            raise TranslationError(
                f"Google returned no document for {source.name}. If the report is "
                "already in Spanish, there is nothing to translate."
            )

        destination.write_bytes(outputs[0])
        if destination.stat().st_size == 0:
            raise TranslationError(f"Google returned an empty document for {source.name}")

        detected = response.document_translation.detected_language_code
        if detected:
            logger.info("Detected source language: %s", detected)
        return destination
