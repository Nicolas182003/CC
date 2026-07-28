from datetime import datetime

import pytest

from clariot.aggregate import (
    distinct_details,
    group_by_company,
    group_by_equipment,
    period_of,
    spanish_date,
    spanish_period,
    summarize_equipment,
)
from clariot.glossary import Glossary
from clariot.store import StoredEvent

CRITICAL = frozenset({"REQUIERE ACCION INMEDIATA"})


def event(
    when,
    *,
    company="Soprole",
    serial="VX-3037575",
    machine="VX-RetCIPLin1 1206230",
    event_type="Mechanical",
    urgency="Perform check at next planned stop of the pump.",
    status="Potential impeller damage or imbalance.",
    action="Open pump and check impeller.",
    cause="A foreign object may have passed through the pump.",
):
    return StoredEvent(
        event_key=f"{company}|{serial}|{when.isoformat() if when else 'x'}",
        equipment_key=f"{company.upper()}|{serial}",
        company=company,
        plant=f"{company} - San Bernardo",
        machine=machine,
        serial_number=serial,
        machine_type="Centrifugal_pump",
        event_at=when,
        event_date_raw=when.strftime("%d-%m-%Y %H:%M") if when else "",
        event_type=event_type,
        equipment_status=status,
        possible_cause=cause,
        recommended_action=action,
        urgency=urgency,
        pdf_path="",
        pdf_translated="",
        message_key="<x@clariot>",
        ingested_at=(when or datetime(2026, 7, 27)).isoformat(),
        reported_at=None,
        report_kind="",
    )


@pytest.fixture
def glossary():
    return Glossary(
        {
            "Mechanical": "Mecánico",
            "Centrifugal_pump": "Bomba centrífuga",
            "Potential impeller damage or imbalance.": "Posible daño del impulsor.",
            "Perform check at next planned stop of the pump.": "Revisar en la próxima parada.",
        }
    )


# --- one machine ------------------------------------------------------------


def test_a_single_event_summary(glossary):
    summary = summarize_equipment([event(datetime(2026, 7, 24, 22, 34))], glossary)

    assert summary.count == 1
    assert summary.repeated is False
    assert summary.machine_type == "Bomba centrífuga"
    assert summary.latest_status == "Posible daño del impulsor."
    assert summary.urgency == "Revisar en la próxima parada."


def test_the_label_carries_the_serial_number(glossary):
    summary = summarize_equipment([event(datetime(2026, 7, 24))], glossary)
    assert summary.label == "VX-RetCIPLin1 1206230 (VX-3037575)"


def test_event_types_are_counted_and_ranked(glossary):
    events = [
        event(datetime(2026, 7, 24), event_type="Mechanical"),
        event(datetime(2026, 7, 25), event_type="Mechanical"),
        event(datetime(2026, 7, 26), event_type="Imbalance"),
    ]
    summary = summarize_equipment(events, glossary)

    assert summary.event_types[0] == ("Mecánico", 2)
    # "Imbalance" is not in the glossary, so it stays visibly untranslated.
    assert ("[EN] Imbalance", 1) in summary.event_types


def test_the_latest_event_supplies_the_narrative(glossary):
    old = event(datetime(2026, 7, 20), status="Old condition.")
    new = event(datetime(2026, 7, 26), status="Potential impeller damage or imbalance.")

    summary = summarize_equipment([old, new], glossary)

    assert summary.latest_status == "Posible daño del impulsor."
    assert summary.events[0].event_at == datetime(2026, 7, 26)


# --- the detail of every alarm, not only the latest -------------------------


def test_the_same_condition_repeated_becomes_one_block_with_every_date(glossary):
    """Three reports of one looseness must not print the same paragraph thrice."""
    events = [
        event(datetime(2026, 7, 22, 6, 12)),
        event(datetime(2026, 7, 23, 14, 48)),
        event(datetime(2026, 7, 24, 21, 5)),
    ]
    details = distinct_details(summarize_equipment(events, glossary).timeline)

    assert len(details) == 1
    assert details[0].count == 3
    assert details[0].equipment_status == "Posible daño del impulsor."


def test_different_conditions_each_keep_their_own_detail(glossary):
    """The case that used to be lost: the earlier condition vanished entirely.

    Showing only the latest alarm meant a pump reporting looseness and then a
    bearing told the client about the bearing and nothing else.
    """
    holgura = event(
        datetime(2026, 7, 22),
        event_type="Mechanical",
        status="Looseness or installation issue.",
        action="Check the fixing bolts.",
    )
    rodamiento = event(
        datetime(2026, 7, 24),
        event_type="Bearing",
        status="Bearing wear on the drive end.",
        action="Replace the drive end bearing.",
    )
    details = distinct_details(summarize_equipment([holgura, rodamiento], glossary).timeline)

    assert len(details) == 2
    # Newest first: the client reads the current condition before the history.
    assert details[0].equipment_status.endswith("Bearing wear on the drive end.")
    assert details[1].equipment_status.endswith("Looseness or installation issue.")
    assert all(detail.count == 1 for detail in details)


def test_a_condition_with_no_events_yields_no_blocks():
    assert distinct_details([]) == ()


def test_a_critical_urgency_wins_over_the_latest_one(glossary):
    routine = event(datetime(2026, 7, 26))
    urgent = event(datetime(2026, 7, 20), urgency="Requiere accion inmediata")

    summary = summarize_equipment([routine, urgent], glossary, CRITICAL)

    assert summary.is_critical_urgency is True
    assert "inmediata" in summary.urgency


def test_the_period_spans_first_to_last(glossary):
    events = [
        event(datetime(2026, 7, 21, 20, 14)),
        event(datetime(2026, 7, 26, 14, 2)),
    ]
    summary = summarize_equipment(events, glossary)

    assert summary.first_at == datetime(2026, 7, 21, 20, 14)
    assert summary.last_at == datetime(2026, 7, 26, 14, 2)


def test_undated_events_do_not_break_the_summary(glossary):
    summary = summarize_equipment([event(None), event(datetime(2026, 7, 26))], glossary)

    assert summary.count == 2
    assert summary.last_at == datetime(2026, 7, 26)


def test_an_empty_set_is_rejected():
    with pytest.raises(ValueError):
        summarize_equipment([])


# --- many machines ----------------------------------------------------------


def test_recurrence_outranks_everything_else(glossary):
    events = [
        event(datetime(2026, 7, 26), serial="A-1"),
        event(datetime(2026, 7, 25), serial="B-2"),
        event(datetime(2026, 7, 24), serial="B-2"),
        event(datetime(2026, 7, 23), serial="B-2"),
    ]
    summaries = group_by_equipment(events, glossary)

    assert [s.serial_number for s in summaries] == ["B-2", "A-1"]
    assert summaries[0].count == 3


def test_urgency_breaks_ties_on_equal_counts(glossary):
    events = [
        event(datetime(2026, 7, 25), serial="A-1"),
        event(datetime(2026, 7, 26), serial="B-2", urgency="Requiere accion inmediata"),
    ]
    summaries = group_by_equipment(events, glossary, CRITICAL)

    assert summaries[0].serial_number == "B-2"


def test_each_machine_gets_its_own_summary(glossary):
    events = [event(datetime(2026, 7, 26), serial=f"S-{i}") for i in range(4)]
    assert len(group_by_equipment(events, glossary)) == 4


# --- clients ----------------------------------------------------------------


def test_events_split_per_client():
    events = [
        event(datetime(2026, 7, 26), company="Soprole"),
        event(datetime(2026, 7, 25), company="Prolesur"),
        event(datetime(2026, 7, 24), company="Soprole"),
    ]
    groups = group_by_company(events)

    assert set(groups) == {"Soprole", "Prolesur"}
    assert len(groups["Soprole"]) == 2


def test_client_grouping_ignores_case_and_accents_but_keeps_the_spelling():
    events = [
        event(datetime(2026, 7, 26), company="Nestlé Chile"),
        event(datetime(2026, 7, 25), company="NESTLE CHILE"),
    ]
    groups = group_by_company(events)

    assert list(groups) == ["Nestlé Chile"]
    assert len(groups["Nestlé Chile"]) == 2


def test_events_without_a_company_are_still_grouped():
    groups = group_by_company([event(datetime(2026, 7, 26), company="")])
    assert list(groups) == ["Cliente sin identificar"]


# --- dates for humans -------------------------------------------------------


def test_dates_are_written_in_spanish():
    assert spanish_date(datetime(2026, 7, 24)) == "24 de julio"
    assert spanish_date(datetime(2026, 7, 24, 22, 34), with_time=True) == (
        "24 de julio, 22:34"
    )
    assert spanish_date(None) == "sin fecha"


def test_a_period_inside_one_month_is_written_short():
    assert spanish_period(datetime(2026, 7, 21), datetime(2026, 7, 27)) == (
        "21 al 27 de julio"
    )


def test_a_period_across_months_names_both():
    assert spanish_period(datetime(2026, 6, 28), datetime(2026, 7, 3)) == (
        "28 de junio al 3 de julio"
    )


def test_a_single_day_period():
    assert spanish_period(datetime(2026, 7, 24), datetime(2026, 7, 24, 23)) == (
        "24 de julio"
    )


def test_period_of_events():
    start, end = period_of(
        [event(datetime(2026, 7, 21)), event(datetime(2026, 7, 26)), event(None)]
    )
    assert start == datetime(2026, 7, 21)
    assert end == datetime(2026, 7, 26)
