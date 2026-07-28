from clariot.ledger import Ledger


def make(tmp_path):
    return Ledger(tmp_path / "state" / "ledger.db")


def test_new_message_is_processed(tmp_path):
    ledger = make(tmp_path)
    assert ledger.should_process("<msg-1@clariot>") is True


def test_done_message_is_never_reprocessed(tmp_path):
    ledger = make(tmp_path)
    ledger.mark_in_progress("<msg-1@clariot>", "ENTRY-1", "Alert")
    ledger.mark_done("<msg-1@clariot>")

    assert ledger.should_process("<msg-1@clariot>") is False


def test_interrupted_run_is_retried(tmp_path):
    """A crash between draft creation and completion must not lose the alert."""
    ledger = make(tmp_path)
    ledger.mark_in_progress("<msg-1@clariot>", "ENTRY-1", "Alert")

    assert ledger.should_process("<msg-1@clariot>") is True


def test_failures_stop_after_the_retry_budget(tmp_path):
    ledger = make(tmp_path)
    for _ in range(3):
        ledger.mark_in_progress("<msg-1@clariot>", "ENTRY-1", "Alert")
        ledger.mark_failed("<msg-1@clariot>", "DeepL timeout")

    assert ledger.attempts("<msg-1@clariot>") == 3
    assert ledger.should_process("<msg-1@clariot>", max_attempts=3) is False


def test_ledger_survives_reopening(tmp_path):
    ledger = make(tmp_path)
    ledger.mark_in_progress("<msg-1@clariot>", "ENTRY-1", "Alert")
    ledger.mark_done("<msg-1@clariot>")

    assert make(tmp_path).should_process("<msg-1@clariot>") is False
