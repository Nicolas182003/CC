"""DeepL document translation.

Two things about PDFs are worth remembering when reading the output:

* DeepL re-lays out the document. Reports with dense tables and charts can shift
  visually, which is why the original PDF is attached alongside the translation.
* Text baked into raster charts (vibration spectra axis labels) is never
  translated, because it is not text as far as any translator is concerned.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

FREE_KEY_SUFFIX = ":fx"
_VALID_FORMALITY = {"more", "less", "prefer_more", "prefer_less"}


class TranslationError(RuntimeError):
    """Raised when the document could not be translated."""


class DeepLDocumentTranslator:
    """Translates the whole PDF with DeepL. Bills a 50,000-character minimum."""
    def __init__(
        self,
        api_key: str,
        target_lang: str = "ES",
        formality: str = "default",
        *,
        allow_free_key: bool = False,
    ) -> None:
        if not api_key:
            raise TranslationError(
                "DEEPL_API_KEY is empty. Copy config/env.example to .env and fill it in."
            )
        if api_key.endswith(FREE_KEY_SUFFIX) and not allow_free_key:
            raise TranslationError(
                "This is a DeepL API Free key. Its terms forbid submitting "
                "confidential content, and submitted text is used to train their "
                "models. Use an API Pro key, or set DEEPL_ALLOW_FREE_KEY=true "
                "only for testing with synthetic PDFs."
            )

        try:
            import deepl
        except ImportError as exc:  # pragma: no cover
            raise TranslationError("The 'deepl' package is not installed") from exc

        self._deepl = deepl
        # DeepLClient is the current entry point; Translator remains for older
        # versions of the library.
        client_factory = getattr(deepl, "DeepLClient", None) or deepl.Translator
        self._client = client_factory(api_key)
        self.target_lang = target_lang
        self.formality = formality if formality in _VALID_FORMALITY else None

    def usage(self) -> str:
        """Human-readable quota line, used by the --self-check command."""
        usage = self._client.get_usage()
        if usage.document is not None and usage.document.valid:
            return f"documents {usage.document.count}/{usage.document.limit}"
        if usage.character is not None and usage.character.valid:
            return f"characters {usage.character.count}/{usage.character.limit}"
        return "quota information unavailable"

    def translate(self, source: Path, destination: Path) -> Path:
        """Translate ``source`` into ``destination``. Returns the output path."""
        destination.parent.mkdir(parents=True, exist_ok=True)

        try:
            self._translate_once(source, destination, self.formality)
        except Exception as exc:  # noqa: BLE001
            if self.formality and "formality" in str(exc).lower():
                logger.warning(
                    "Target language does not support formality; retrying without it"
                )
                self._translate_once(source, destination, None)
            else:
                self._raise(exc)

        if not destination.exists() or destination.stat().st_size == 0:
            raise TranslationError(f"DeepL returned an empty document for {source.name}")
        return destination

    def _translate_once(self, source: Path, destination: Path, formality: str | None) -> None:
        kwargs = {"target_lang": self.target_lang}
        if formality:
            kwargs["formality"] = formality
        self._client.translate_document_from_filepath(
            str(source), str(destination), **kwargs
        )

    def _raise(self, exc: Exception) -> None:
        document_exception = getattr(self._deepl, "DocumentTranslationException", None)
        if document_exception and isinstance(exc, document_exception):
            # The handle lets you recover a document that was already billed.
            raise TranslationError(
                f"Document translation failed (handle: {exc.document_handle}): {exc}"
            ) from exc
        raise TranslationError(f"Document translation failed: {exc}") from exc
