from pathlib import Path

from clariot.glossary import UNTRANSLATED_MARK, Glossary
from clariot.models import AlertReport

PROJECT_ROOT = Path(__file__).resolve().parents[1]

PHRASES = {
    "Looseness or installation problem.": "Problema de holgura o instalación.",
    "Within 3 to 5 days.": "En un plazo de 3 a 5 días.",
    "Centrifugal pump": "Bomba centrífuga",
}


def glossary():
    return Glossary(PHRASES)


def report(**fields):
    return AlertReport(fields=fields)


def test_known_phrase_is_translated():
    result = glossary().apply(report(equipment_status="Looseness or installation problem."))

    assert result.report.fields["equipment_status"] == "Problema de holgura o instalación."
    assert result.complete


def test_matching_ignores_case_and_trailing_period():
    result = glossary().apply(report(urgency="within 3 to 5 days"))
    assert result.report.urgency == "En un plazo de 3 a 5 días."


def test_unknown_phrase_is_marked_never_guessed():
    """A wrong technical term reaching a client is worse than an obvious gap."""
    result = glossary().apply(report(equipment_status="Misalignment between motor and pump"))

    value = result.report.fields["equipment_status"]
    assert value.startswith(UNTRANSLATED_MARK)
    assert "Misalignment between motor and pump" in value
    assert result.missing == (("equipment_status", "Misalignment between motor and pump"),)


def test_proper_nouns_are_never_touched():
    alert = report(
        company="Prolesur",
        plant="Prolesur - Los Lagos",
        machine="Bba retor CIP Buffer VX",
        serial_number="202611-VX",
        event_date="21-07-2026 20:14",
    )
    result = glossary().apply(alert)

    assert result.report.fields == alert.fields
    assert result.complete


def test_already_translated_reports_are_not_flagged():
    """Some reports arrive pre-translated; those are not glossary gaps."""
    result = glossary().apply(report(equipment_status="Problema de holgura o instalación."))

    assert result.complete
    assert UNTRANSLATED_MARK not in result.report.fields["equipment_status"]


def test_missing_fields_are_skipped():
    result = glossary().apply(report(machine="Bomba 3"))
    assert result.complete


def test_shipped_glossary_loads_and_declares_translatable_fields():
    loaded = Glossary.load(PROJECT_ROOT / "config")

    assert len(loaded) > 0
    assert loaded.lookup("Centrifugal pump") == "Bomba centrífuga"


def test_absent_glossary_file_leaves_everything_in_english(tmp_path):
    loaded = Glossary.load(tmp_path)
    result = loaded.apply(report(urgency="Within 3 to 5 days."))

    assert result.report.urgency.startswith(UNTRANSLATED_MARK)
