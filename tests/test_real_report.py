"""Regression tests against the real Alfa Laval report for Prolesur.

This PDF is the reason the parser is coordinate-based: its plain text puts every
label of a row on one line and every value on the next, with nothing tying them
together.
"""

from pathlib import Path

import pytest

from clariot.config import load_labels, load_value_noise
from clariot.pdf_parser import parse_pdf

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE = PROJECT_ROOT / "Imagenes" / "ejemplo clariot.pdf"

pytestmark = pytest.mark.skipif(not SAMPLE.exists(), reason="sample report not available")


@pytest.fixture(scope="module")
def parsed():
    config_dir = PROJECT_ROOT / "config"
    return parse_pdf(SAMPLE, load_labels(config_dir), load_value_noise(config_dir))


def test_company_comes_from_the_column_header_below(parsed):
    assert parsed.company == "Prolesur"


def test_machine_name_is_not_confused_with_the_next_column(parsed):
    """The label row holds four headers; none may become another's value."""
    assert parsed.machine == "Bba retor CIP Buffer VX"
    assert parsed.fields["serial_number"] == "202611-VX"
    assert parsed.fields["machine_type"] == "bomba centrífuga"


def test_empty_column_yields_no_value(parsed):
    """SENSOR ID has no value in this report; it must not borrow a neighbour's."""
    assert parsed.get("sensor_id") is None


def test_label_left_value_right_fields(parsed):
    assert parsed.fields["event_type"] == "Instalación o mecánica relacionada"
    assert parsed.fields["equipment_status"] == "Problema de holgura o instalación."
    assert parsed.urgency == "En un plazo de 3 a 5 días."


def test_soft_hyphens_become_real_hyphens(parsed):
    assert parsed.fields["event_date"] == "21-07-2026 20:14"


def test_help_link_is_stripped_from_the_timestamp(parsed):
    assert "UTC?" not in parsed.fields["event_date"]


def test_wrapped_paragraph_is_joined_across_rows(parsed):
    action = parsed.fields["recommended_action"]
    assert action.startswith("Compruebe visualmente")
    assert action.endswith("Realice acciones correctivas si necesario.")


def test_headers_are_never_returned_as_values(parsed):
    headers = {"SECCION", "CANAL", "PLANTA", "OFICINA DE VENTAS"}
    assert not any(value.upper() in headers for value in parsed.fields.values())
