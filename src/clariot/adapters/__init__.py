"""Adapters to the outside world: Outlook (COM) and the translation services."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

PROVIDER_NONE = "none"
PROVIDER_GOOGLE = "google"
PROVIDER_DEEPL = "deepl"
PROVIDERS = (PROVIDER_NONE, PROVIDER_GOOGLE, PROVIDER_DEEPL)


def build_translator(settings):
    """Return the configured document translator, or None when disabled.

    Every provider exposes the same two methods, ``translate(src, dst)`` and
    ``usage()``, so the pipeline never knows which one it is talking to.
    """
    provider = settings.translation.provider

    if provider == PROVIDER_NONE:
        logger.info("Translation disabled; drafts will carry the original report")
        return None

    if provider == PROVIDER_GOOGLE:
        from .google_translator import GoogleDocumentTranslator

        return GoogleDocumentTranslator(
            project_id=settings.google_project_id,
            location=settings.translation.google_location,
            target_lang=settings.translation.target_lang,
            source_lang=settings.translation.source_lang,
        )

    if provider == PROVIDER_DEEPL:
        from .deepl_translator import DeepLDocumentTranslator

        return DeepLDocumentTranslator(
            settings.deepl_api_key,
            settings.translation.target_lang,
            settings.translation.formality,
            allow_free_key=settings.allow_free_deepl_key,
        )

    raise ValueError(
        f"Unknown translation.provider '{provider}'. Valid values: {', '.join(PROVIDERS)}"
    )


def build_text_translator(settings, terms=None):
    """Return the phrase translator, or None when none is configured.

    Deliberately independent of the PDF provider: an AI Studio key costs nothing
    and needs no credit card, so phrases can be translated even while Cloud
    billing is unavailable.
    """
    provider = settings.glossary.phrase_provider

    if provider in ("", PROVIDER_NONE):
        return None

    if provider == "gemini":
        from .gemini_text import GeminiTextTranslator

        return GeminiTextTranslator(
            api_key=settings.gemini_api_key,
            model=settings.glossary.gemini_model,
            terms=terms,
        )

    if provider == PROVIDER_GOOGLE:
        from .google_text import GoogleTextTranslator

        return GoogleTextTranslator(
            project_id=settings.google_project_id,
            location=settings.translation.google_location,
            target_lang=settings.translation.target_lang,
            source_lang=settings.translation.source_lang or "en",
            terms=terms,
        )

    raise ValueError(
        f"Unknown glossary.phrase_provider '{provider}'. Valid values: none, gemini, google"
    )
