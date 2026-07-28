from clariot.config import ClientDirectory
from clariot.models import ClientRoute


def test_matches_substring_ignoring_case_and_accents(directory):
    assert directory.resolve("NESTLÉ CHILE S.A.").display_name == "Nestlé"
    assert directory.resolve("prolesur osorno").display_name == "Prolesur"


def test_unknown_company_returns_none(directory):
    assert directory.resolve("Empresa X") is None


def test_missing_company_returns_none(directory):
    assert directory.resolve(None) is None
    assert directory.resolve("") is None


def test_more_specific_pattern_wins_over_the_corporate_default():
    directory = ClientDirectory(
        routes=[
            (("NESTLE",), ClientRoute("Nestlé", ("corp@nestle.example",), ())),
            (("NESTLE OSORNO",), ClientRoute("Nestlé Osorno", ("osorno@nestle.example",), ())),
        ]
    )
    assert directory.resolve("Nestle Osorno").to == ("osorno@nestle.example",)
    assert directory.resolve("Nestle Santiago").to == ("corp@nestle.example",)
