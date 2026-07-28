from datetime import datetime

import pytest

from clariot.classifier import (
    LEVEL_CRITICAL,
    LEVEL_NORMAL,
    LEVEL_URGENT,
    Classifier,
)
from clariot.store import StoredEvent

NOW = datetime(2026, 7, 27, 10, 0)
CRITICAL_WORDS = frozenset({"REQUIERE ACCION INMEDIATA", "INMEDIATO"})


def event(when: datetime | None, urgency="En un plazo de 3 a 5 dias.", key=None):
    return StoredEvent(
        event_key=key or f"PROLESUR|202611-VX|{when.isoformat() if when else 'sin-fecha'}",
        equipment_key="PROLESUR|202611-VX",
        company="Prolesur",
        plant="Los Lagos",
        machine="Bba retor CIP Buffer VX",
        serial_number="202611-VX",
        machine_type="Centrifugal_pump",
        event_at=when,
        event_date_raw=when.strftime("%d-%m-%Y %H:%M") if when else "",
        event_type="Holgura o instalacion",
        equipment_status="Problema de holgura",
        possible_cause="Holgura detectada",
        recommended_action="Verificar apoyo de los pies",
        urgency=urgency,
        pdf_path="",
        pdf_translated="",
        message_key="<x@clariot>",
        ingested_at=NOW.isoformat(),
        reported_at=None,
        report_kind="",
    )


@pytest.fixture
def classifier():
    return Classifier(critical_urgencies=CRITICAL_WORDS)


def test_a_lone_event_waits_for_the_weekly_report(classifier):
    result = classifier.classify(event(datetime(2026, 7, 27, 9, 0)), [], now=NOW)

    assert result.level == LEVEL_NORMAL
    assert result.immediate is False
    assert result.count == 1


def test_two_events_in_the_window_are_urgent(classifier):
    new = event(datetime(2026, 7, 27, 9, 0))
    old = event(datetime(2026, 7, 23, 14, 0))

    result = classifier.classify(new, [old], now=NOW)

    assert result.level == LEVEL_URGENT
    assert result.count == 2
    assert "7 dias" in result.reason


def test_two_events_the_same_day_are_critical(classifier):
    """Dylan's rule: a repeat within the day means it is degrading now."""
    new = event(datetime(2026, 7, 27, 9, 0))
    earlier = event(datetime(2026, 7, 27, 3, 30))

    result = classifier.classify(new, [earlier], now=NOW)

    assert result.level == LEVEL_CRITICAL
    assert "mismo dia" in result.reason


def test_events_outside_the_window_do_not_group(classifier):
    """Documented limit: a pump alarming every 10 days is not grouped."""
    new = event(datetime(2026, 7, 27, 9, 0))
    old = event(datetime(2026, 7, 15, 9, 0))

    result = classifier.classify(new, [old], now=NOW)

    assert result.level == LEVEL_NORMAL
    assert result.count == 1


def test_a_single_event_declared_critical_goes_out_immediately(classifier):
    result = classifier.classify(
        event(datetime(2026, 7, 27, 9, 0), urgency="Requiere accion inmediata"),
        [],
        now=NOW,
    )

    assert result.level == LEVEL_URGENT
    assert "urgencia declarada" in result.reason


def test_declared_urgency_matching_ignores_case_and_accents(classifier):
    result = classifier.classify(
        event(datetime(2026, 7, 27, 9, 0), urgency="requiere acción inmediata"),
        [],
        now=NOW,
    )
    assert result.level == LEVEL_URGENT


def test_an_undated_event_still_counts(classifier):
    """Losing an alarm is worse than one urgency report too many."""
    result = classifier.classify(
        event(None), [event(datetime(2026, 7, 26, 9, 0))], now=NOW
    )

    assert result.level == LEVEL_URGENT
    assert result.count == 2


def test_the_new_event_is_never_counted_twice(classifier):
    """History may or may not already contain it; the count must not change."""
    new = event(datetime(2026, 7, 27, 9, 0))
    old = event(datetime(2026, 7, 26, 9, 0))

    without = classifier.classify(new, [old], now=NOW)
    with_itself = classifier.classify(new, [old, new], now=NOW)

    assert without.count == with_itself.count == 2


def test_the_same_level_is_not_reported_twice(classifier):
    """The client hears from us when things get worse, not on every repeat."""
    new = event(datetime(2026, 7, 27, 9, 0))
    old = event(datetime(2026, 7, 25, 9, 0))

    result = classifier.classify(
        new,
        [old],
        last_urgency_report=datetime(2026, 7, 25, 10, 0),
        last_urgency_level=LEVEL_URGENT,
        now=NOW,
    )

    assert result.level == LEVEL_NORMAL
    assert "ya se informo al mismo nivel" in result.reason


def test_climbing_from_urgent_to_critical_does_go_out(classifier):
    """Same-day repetition after an urgent report is a genuine escalation."""
    new = event(datetime(2026, 7, 27, 9, 0))
    earlier = event(datetime(2026, 7, 27, 2, 0))

    result = classifier.classify(
        new,
        [earlier],
        last_urgency_report=datetime(2026, 7, 26, 10, 0),
        last_urgency_level=LEVEL_URGENT,
        now=NOW,
    )

    assert result.level == LEVEL_CRITICAL
    assert "escala desde 'urgent'" in result.reason


def test_critical_is_not_repeated_either(classifier):
    """Once at the top level, further repeats join the weekly report."""
    new = event(datetime(2026, 7, 27, 9, 0))
    earlier = event(datetime(2026, 7, 27, 2, 0))

    result = classifier.classify(
        new,
        [earlier],
        last_urgency_report=datetime(2026, 7, 27, 3, 0),
        last_urgency_level=LEVEL_CRITICAL,
        now=NOW,
    )

    assert result.level == LEVEL_NORMAL


def test_cooldown_expires(classifier):
    new = event(datetime(2026, 7, 27, 9, 0))
    old = event(datetime(2026, 7, 26, 9, 0))

    result = classifier.classify(
        new,
        [old],
        last_urgency_report=datetime(2026, 7, 1, 10, 0),
        last_urgency_level=LEVEL_URGENT,
        now=NOW,
    )

    assert result.level == LEVEL_URGENT


def test_the_threshold_is_configurable():
    strict = Classifier(urgent_threshold=3, critical_urgencies=CRITICAL_WORDS)
    new = event(datetime(2026, 7, 27, 9, 0))
    old = event(datetime(2026, 7, 26, 9, 0))

    assert strict.classify(new, [old], now=NOW).level == LEVEL_NORMAL


def test_same_day_escalation_can_be_switched_off():
    plain = Classifier(same_day_is_critical=False, critical_urgencies=CRITICAL_WORDS)
    new = event(datetime(2026, 7, 27, 9, 0))
    earlier = event(datetime(2026, 7, 27, 3, 0))

    assert plain.classify(new, [earlier], now=NOW).level == LEVEL_URGENT


def test_events_come_back_newest_first(classifier):
    new = event(datetime(2026, 7, 27, 9, 0))
    old = event(datetime(2026, 7, 23, 9, 0))
    middle = event(datetime(2026, 7, 25, 9, 0))

    result = classifier.classify(new, [old, middle], now=NOW)

    assert [e.event_at.day for e in result.events] == [27, 25, 23]
