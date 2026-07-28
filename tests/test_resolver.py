"""The three-layer phrase resolution: glossary override, cache, API."""

from clariot.glossary import Glossary, UNTRANSLATED_MARK
from clariot.models import AlertReport
from clariot.resolver import PhraseResolver
from clariot.store import EventStore


class FakeTranslator:
    """Counts calls, so the tests can prove the cache is doing its job."""

    name = "fake"

    def __init__(self, answers=None, fail=False):
        self.answers = answers or {}
        self.fail = fail
        self.calls = 0
        self.asked = []

    def translate(self, texts):
        self.calls += 1
        self.asked.extend(texts)
        if self.fail:
            raise RuntimeError("la API no responde")
        return [self.answers.get(text, f"ES::{text}") for text in texts]


def glossary():
    return Glossary({"Mechanical": "Mecánico (aprobado)"})


def store(tmp_path):
    return EventStore(tmp_path / "events.db")


def report(**fields):
    return AlertReport(fields=fields)


# --- layer 1: the glossary wins ---------------------------------------------


def test_the_glossary_overrides_the_api(tmp_path):
    api = FakeTranslator()
    resolver = PhraseResolver(glossary(), store(tmp_path), api)

    result = resolver.apply(report(event_type="Mechanical"))

    assert result.report.fields["event_type"] == "Mecánico (aprobado)"
    assert api.calls == 0, "no debería consultarse la API por una frase del glosario"


# --- layer 3 then 2: translate once, reuse forever ---------------------------


def test_a_new_phrase_is_translated_and_cached(tmp_path):
    api = FakeTranslator({"Cavitation": "Cavitación"})
    shared = store(tmp_path)

    first = PhraseResolver(glossary(), shared, api).apply(report(event_type="Cavitation"))
    assert first.report.fields["event_type"] == "Cavitación"
    assert first.complete
    assert api.calls == 1

    # A brand new resolver, same store: the cache answers, the API is untouched.
    second_api = FakeTranslator()
    second = PhraseResolver(glossary(), shared, second_api).apply(
        report(event_type="Cavitation")
    )

    assert second.report.fields["event_type"] == "Cavitación"
    assert second_api.calls == 0


def test_the_same_phrase_is_always_worded_identically(tmp_path):
    """The point of the cache: January's report reads like March's."""
    shared = store(tmp_path)
    drifting = FakeTranslator({"Cavitation": "Cavitación"})
    PhraseResolver(glossary(), shared, drifting).apply(report(event_type="Cavitation"))

    # The service now answers differently, as services do.
    drifting.answers["Cavitation"] = "Fenómeno de cavitación"
    again = PhraseResolver(glossary(), shared, drifting).apply(
        report(event_type="Cavitation")
    )

    assert again.report.fields["event_type"] == "Cavitación"


def test_repeated_phrases_cost_one_translation(tmp_path):
    api = FakeTranslator()
    resolver = PhraseResolver(glossary(), store(tmp_path), api)

    resolver.apply(report(event_type="Imbalance", equipment_status="Imbalance"))

    assert api.asked == ["Imbalance"]


def test_several_new_phrases_go_in_one_request(tmp_path):
    api = FakeTranslator()
    resolver = PhraseResolver(glossary(), store(tmp_path), api)

    resolver.apply(
        report(
            event_type="Imbalance",
            equipment_status="Bearing wear",
            urgency="Within 24 hours",
        )
    )

    assert api.calls == 1
    assert len(api.asked) == 3


# --- degrading without breaking ---------------------------------------------


def test_an_api_failure_marks_instead_of_crashing(tmp_path):
    api = FakeTranslator(fail=True)
    resolver = PhraseResolver(glossary(), store(tmp_path), api)

    result = resolver.apply(report(event_type="Cavitation"))

    assert not result.complete
    assert result.report.fields["event_type"].startswith(UNTRANSLATED_MARK)


def test_a_failed_translation_is_not_cached(tmp_path):
    """The next run must retry, not inherit the outage."""
    shared = store(tmp_path)
    PhraseResolver(glossary(), shared, FakeTranslator(fail=True)).apply(
        report(event_type="Cavitation")
    )

    working = FakeTranslator({"Cavitation": "Cavitación"})
    result = PhraseResolver(glossary(), shared, working).apply(
        report(event_type="Cavitation")
    )

    assert result.report.fields["event_type"] == "Cavitación"


def test_without_a_translator_it_falls_back_to_the_glossary(tmp_path):
    resolver = PhraseResolver(glossary(), store(tmp_path), None)

    result = resolver.apply(report(event_type="Mechanical", equipment_status="Cavitation"))

    assert result.report.fields["event_type"] == "Mecánico (aprobado)"
    assert result.report.fields["equipment_status"].startswith(UNTRANSLATED_MARK)


# --- what must never be touched ---------------------------------------------


def test_proper_nouns_are_never_translated(tmp_path):
    api = FakeTranslator()
    resolver = PhraseResolver(glossary(), store(tmp_path), api)

    alert = report(
        company="Soprole",
        plant="Soprole - San Bernardo Planta 4",
        machine="VX-RetCIPLin1 1206230",
        serial_number="VX-3037575",
        event_date="24-07-2026 22:34",
    )
    result = resolver.apply(alert)

    assert result.report.fields == alert.fields
    assert api.calls == 0


def test_only_the_technical_phrase_leaves_the_company(tmp_path):
    """Compliance: no client name, plant, machine or serial reaches the service."""
    api = FakeTranslator()
    resolver = PhraseResolver(glossary(), store(tmp_path), api)

    resolver.apply(
        report(
            company="Soprole",
            machine="VX-RetCIPLin1 1206230",
            serial_number="VX-3037575",
            equipment_status="Potential impeller damage.",
        )
    )

    assert api.asked == ["Potential impeller damage."]


def test_an_already_spanish_phrase_is_left_alone(tmp_path):
    api = FakeTranslator()
    resolver = PhraseResolver(glossary(), store(tmp_path), api)

    result = resolver.apply(report(event_type="Mecánico (aprobado)"))

    assert result.complete
    assert api.calls == 0
