"""Regression tests against the real Alfa Laval report, in its original English.

This is the file that actually arrives from support@aliotportal.com. It settled
three things that guesswork had got wrong:

* the event timestamp is day-first (``24-07-2026`` is 24 July),
* the labels are "Time Of Event (UTC)" and "Equipment Condition", not the
  "EVENT TIME" / "EQUIPMENT STATUS" that had been configured,
* pdfplumber cannot read this font — see ``pdf_parser.read_pages``.
"""

from datetime import datetime
from pathlib import Path

import pytest

from clariot.config import load_labels, load_value_noise
from clariot.glossary import UNTRANSLATED_MARK, Glossary
from clariot.pdf_parser import parse_pdf
from clariot.store import parse_event_datetime

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE = PROJECT_ROOT / "Imagenes" / "clariot original.pdf"
CONFIG = PROJECT_ROOT / "config"

pytestmark = pytest.mark.skipif(
    not SAMPLE.exists(), reason="real English report not available"
)


@pytest.fixture(scope="module")
def parsed():
    return parse_pdf(SAMPLE, load_labels(CONFIG), load_value_noise(CONFIG))


def test_no_unmapped_glyphs_survive(parsed):
    """pdfplumber emitted NUL for this font; PyMuPDF must not."""
    assert not any("\x00" in value for value in parsed.fields.values())


def test_event_timestamp_is_complete_and_day_first(parsed):
    assert parsed.fields["event_date"] == "24-07-2026 22:34"
    assert parse_event_datetime(parsed.fields["event_date"]) == datetime(
        2026, 7, 24, 22, 34
    )


def test_client_and_plant(parsed):
    assert parsed.company == "Soprole"
    # The SECTION value is rendered under the PLANT column by the generator; it
    # must not be appended to the plant name.
    assert parsed.fields["plant"] == "Soprole - San Bernardo Planta 4"


def test_equipment_columns_are_not_mixed_up(parsed):
    assert parsed.fields["serial_number"] == "VX-3037575"
    assert parsed.fields["machine_type"] == "Centrifugal_pump"


def test_the_machine_name_is_reproduced_exactly(parsed):
    """No cleanup, no reinterpretation: the asset name as the report writes it.

    PyMuPDF's own plain-text extraction of that line is 'VX-RetCIPLin1 1206230'.
    """
    assert parsed.machine == "VX-RetCIPLin1 1206230"


def test_empty_sensor_id_stays_empty(parsed):
    assert parsed.get("sensor_id") is None


def test_the_labels_that_were_wrong_now_resolve(parsed):
    assert parsed.fields["equipment_status"] == "Potential impeller damage or imbalance."
    assert parsed.fields["event_type"] == "Mechanical"


def test_wrapped_paragraph_is_complete(parsed):
    cause = parsed.fields["possible_cause"]
    assert cause.startswith("Can sometimes be caused by a foreign object")
    assert cause.endswith("vibrations will damage the pump.")


def test_urgency_and_recommended_action(parsed):
    assert parsed.urgency == "Perform check at next planned stop of the pump."
    assert parsed.fields["recommended_action"].startswith("Open pump and check impeller")


def test_the_glossary_covers_this_report(parsed):
    """Every phrase of a real report is translated, none left marked."""
    result = Glossary.load(CONFIG).apply(parsed)

    assert result.complete, f"faltan en el glosario: {result.missing}"
    assert UNTRANSLATED_MARK not in " ".join(result.report.fields.values())
    assert result.report.fields["machine_type"] == "Bomba centrífuga"
    assert result.report.urgency == (
        "Realizar la revisión en la próxima parada programada de la bomba."
    )
