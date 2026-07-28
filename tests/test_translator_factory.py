from dataclasses import replace
from importlib.util import find_spec

import pytest

from clariot.adapters import build_translator

# The translation providers are optional: the current design attaches the
# original PDF and needs neither package. See requirements-optional.txt.
needs_deepl = pytest.mark.skipif(
    find_spec("deepl") is None, reason="optional 'deepl' package not installed"
)
needs_google = pytest.mark.skipif(
    find_spec("google.cloud.translate") is None,
    reason="optional 'google-cloud-translate' package not installed",
)


def with_provider(settings, provider):
    return replace(settings, translation=replace(settings.translation, provider=provider))


def test_provider_none_disables_translation(settings):
    assert build_translator(with_provider(settings, "none")) is None
    assert with_provider(settings, "none").translation.enabled is False


def test_unknown_provider_is_rejected_by_name(settings):
    with pytest.raises(ValueError, match="Unknown translation.provider"):
        build_translator(with_provider(settings, "chatgpt"))


@needs_google
def test_google_requires_a_project_id(settings):
    from clariot.adapters.google_translator import TranslationError

    broken = replace(with_provider(settings, "google"), google_project_id="")
    with pytest.raises(TranslationError, match="GOOGLE_CLOUD_PROJECT"):
        build_translator(broken)


@needs_deepl
def test_deepl_rejects_a_free_key(settings):
    from clariot.adapters.deepl_translator import TranslationError

    free = replace(
        with_provider(settings, "deepl"),
        deepl_api_key="abc123:fx",
        allow_free_deepl_key=False,
    )
    with pytest.raises(TranslationError, match="Free key"):
        build_translator(free)


@needs_deepl
def test_deepl_free_key_allowed_when_explicitly_enabled(settings):
    allowed = replace(
        with_provider(settings, "deepl"),
        deepl_api_key="abc123:fx",
        allow_free_deepl_key=True,
    )
    # Constructing the client does no network call, so this must succeed.
    assert build_translator(allowed) is not None
