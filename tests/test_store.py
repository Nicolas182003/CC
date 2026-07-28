from datetime import datetime

from clariot.models import AlertReport
from clariot.store import (
    EventStore,
    REPORT_URGENT,
    REPORT_WEEKLY,
    equipment_key,
    event_key,
    parse_event_datetime,
    serial_from_subject,
)


def report(**fields):
    base = {
        "company": "Prolesur",
        "plant": "Prolesur - Los Lagos",
        "machine": "Bba retor CIP Buffer VX",
        "serial_number": "202611-VX",
        "event_date": "21-07-2026 20:14",
        "event_type": "Holgura o instalación",
        "urgency": "En un plazo de 3 a 5 días.",
    }
    base.update(fields)
    return AlertReport(fields={k: v for k, v in base.items() if v is not None})


def store(tmp_path):
    return EventStore(tmp_path / "state" / "events.db")


# --- date parsing -----------------------------------------------------------


def test_parses_the_observed_day_first_format():
    assert parse_event_datetime("21-07-2026 20:14") == datetime(2026, 7, 21, 20, 14)


def test_parses_soft_hyphens_from_the_pdf():
    assert parse_event_datetime("21­07­2026 20:14") == datetime(2026, 7, 21, 20, 14)


def test_unparseable_timestamp_returns_none():
    assert parse_event_datetime("el martes por la tarde") is None
    assert parse_event_datetime("") is None
    assert parse_event_datetime(None) is None


# --- identity ---------------------------------------------------------------


def test_equipment_identity_prefers_the_serial_number():
    a = report(machine="Bba retor CIP Buffer VX")
    b = report(machine="BBA RETOR CIP BUFFER V.X.")  # same pump, spelled differently
    assert equipment_key(a) == equipment_key(b)


def test_equipment_identity_falls_back_to_the_machine_name():
    a = report(serial_number=None, machine="Bomba 7")
    b = report(serial_number=None, machine="bomba 7")
    assert equipment_key(a) == equipment_key(b)


def test_same_machine_name_at_different_companies_is_different_equipment():
    a = report(company="Prolesur", serial_number=None, machine="Bomba 7")
    b = report(company="Nestle", serial_number=None, machine="Bomba 7")
    assert equipment_key(a) != equipment_key(b)


def test_the_same_event_resent_resolves_to_one_key():
    assert event_key(report(), "correo-A") == event_key(report(), "correo-B")


def test_events_without_a_timestamp_stay_distinct():
    a = event_key(report(event_date=None), "correo-A")
    b = event_key(report(event_date=None), "correo-B")
    assert a != b


# --- storing ----------------------------------------------------------------


def test_first_record_is_new(tmp_path):
    event, is_new = store(tmp_path).record(report(), message_key="<a@clariot>")
    assert is_new
    assert event.machine == "Bba retor CIP Buffer VX"
    assert event.event_at == datetime(2026, 7, 21, 20, 14)
    assert event.reported is False


def test_a_resent_notification_is_not_counted_twice(tmp_path):
    """Two emails describing one event must not fire a false urgency report."""
    s = store(tmp_path)
    s.record(report(), message_key="<primero@clariot>")
    event, is_new = s.record(report(), message_key="<reenvio@clariot>")

    assert is_new is False
    assert s.count() == 1
    assert event.message_key == "<primero@clariot>"


def test_two_real_events_are_both_counted(tmp_path):
    s = store(tmp_path)
    s.record(report(event_date="21-07-2026 20:14"), message_key="<a@clariot>")
    s.record(report(event_date="22-07-2026 08:30"), message_key="<b@clariot>")
    assert s.count() == 2


# --- querying ---------------------------------------------------------------


def test_history_is_scoped_to_the_machine(tmp_path):
    s = store(tmp_path)
    s.record(report(), message_key="<a@clariot>")
    s.record(
        report(serial_number="OTRA-99", event_date="22-07-2026 09:00"),
        message_key="<b@clariot>",
    )

    history = s.history_for(equipment_key(report()))
    assert len(history) == 1
    assert history[0].serial_number == "202611-VX"


def test_history_since_keeps_events_without_a_timestamp(tmp_path):
    """An undated event must not vanish from the count."""
    s = store(tmp_path)
    s.record(report(event_date=None), message_key="<a@clariot>")

    history = s.history_for(equipment_key(report()), since=datetime(2030, 1, 1))
    assert len(history) == 1


def test_pending_excludes_what_was_already_reported(tmp_path):
    s = store(tmp_path)
    first, _ = s.record(report(), message_key="<a@clariot>")
    s.record(report(event_date="22-07-2026 08:30"), message_key="<b@clariot>")

    s.mark_reported([first.event_key], REPORT_WEEKLY)
    pending = s.pending()

    assert len(pending) == 1
    assert pending[0].event_date_raw == "22-07-2026 08:30"


def test_last_urgency_report_ignores_weekly_reports(tmp_path):
    s = store(tmp_path)
    first, _ = s.record(report(), message_key="<a@clariot>")
    second, _ = s.record(
        report(event_date="22-07-2026 08:30"), message_key="<b@clariot>"
    )
    equipment = equipment_key(report())

    s.mark_reported([first.event_key], REPORT_WEEKLY)
    assert s.last_urgency_report(equipment) is None

    s.mark_reported([second.event_key], REPORT_URGENT, now=datetime(2026, 7, 22, 9, 0))
    assert s.last_urgency_report(equipment) == datetime(2026, 7, 22, 9, 0)


def test_purge_keeps_events_that_were_never_reported(tmp_path):
    s = store(tmp_path)
    old, _ = s.record(report(), message_key="<a@clariot>", now=datetime(2020, 1, 1))
    s.record(
        report(event_date="22-07-2026 08:30"),
        message_key="<b@clariot>",
        now=datetime(2020, 1, 1),
    )
    s.mark_reported([old.event_key], REPORT_WEEKLY)

    assert s.purge_older_than(30) == 1
    assert s.count() == 1


# --- the serial in the subject, as a fallback -------------------------------


def test_the_serial_comes_out_of_the_real_subject():
    assert (
        serial_from_subject("Event notification report - VX-3037575") == "VX-3037575"
    )


def test_a_reworded_prefix_does_not_break_it():
    """Matching the tail, not the prefix: a "2nd notification" still works."""
    for subject in (
        "Event Report - 2nd Notification - VX-3037575",
        "Re: Event notification report - VX-3037575",
        "FW: Event notification report  -  VX-3037575",
    ):
        assert serial_from_subject(subject) == "VX-3037575"


def test_a_subject_without_a_serial_yields_nothing():
    for subject in ("Event notification report", "Su factura - ", "", None):
        assert serial_from_subject(subject) == ""


def test_a_trailing_word_is_not_mistaken_for_a_serial():
    """Two words after the dash is prose, not an identifier."""
    assert serial_from_subject("Aviso - de mantenimiento programado") == ""


def test_the_trailing_full_stop_of_a_real_subject_is_stripped():
    """Real subjects end in a period; left in, the same pump counts as two."""
    from clariot.models import AlertReport
    from clariot.store import equipment_key

    assert serial_from_subject("RV: Event notification report - VX-3037575.") == (
        "VX-3037575"
    )
    # And it has to match what the PDF yields, or grouping breaks.
    del_pdf = AlertReport(fields={"company": "Soprole", "serial_number": "VX-3037575"})
    del_asunto = AlertReport(
        fields={
            "company": "Soprole",
            "serial_number": serial_from_subject(
                "RV: Event notification report - VX-3037575."
            ),
        }
    )
    assert equipment_key(del_pdf) == equipment_key(del_asunto)


def test_a_serial_with_several_hyphens_survives():
    assert serial_from_subject("Event notification report - VX-TPS3050-1205.") == (
        "VX-TPS3050-1205"
    )
