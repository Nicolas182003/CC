from clariot.pdf_parser import parse_report, split_label_value


def test_splits_on_first_colon_and_keeps_value_casing():
    assert split_label_value("MACHINE NAME: Bba retor CIP Buffer VX") == (
        "MACHINE NAME",
        "Bba retor CIP Buffer VX",
    )


def test_splits_on_wide_whitespace_gap_when_no_separator():
    assert split_label_value("URGENCY      Critical") == ("URGENCY", "Critical")


def test_returns_none_for_prose_lines():
    assert split_label_value("Vibration levels remain within range") is None


def test_parses_english_labels(labels):
    lines = [
        "ALFA LAVAL VIBRATION REPORT",
        "COMPANY: Prolesur",
        "MACHINE NAME: Bba retor CIP Buffer VX",
        "SENSOR ID: SN-44219",
        "EVENT TYPE: High vibration",
        "URGENCY: Critical",
    ]
    report = parse_report(lines, labels)

    assert report.company == "Prolesur"
    assert report.machine == "Bba retor CIP Buffer VX"
    assert report.fields["sensor_id"] == "SN-44219"
    assert report.urgency == "Critical"


def test_parses_spanish_labels_with_accents(labels):
    lines = [
        "COMPAÑÍA: Nestlé Chile",
        "NOMBRE DE LA MÁQUINA: Bomba centrífuga 3",
        "URGENCIA: Alta",
    ]
    report = parse_report(lines, labels)

    assert report.company == "Nestlé Chile"
    assert report.machine == "Bomba centrífuga 3"
    assert report.urgency == "Alta"


def test_longer_label_wins_over_shorter_prefix(labels):
    report = parse_report(["MACHINE NAME: Bomba 7"], labels)
    assert report.machine == "Bomba 7"


def test_value_on_the_following_line(labels):
    report = parse_report(["NOMBRE DE LA MAQUINA:", "Bba retor CIP Buffer VX"], labels)
    assert report.machine == "Bba retor CIP Buffer VX"


def test_first_occurrence_wins(labels):
    report = parse_report(["COMPANY: Prolesur", "COMPANY: Otra"], labels)
    assert report.company == "Prolesur"


def test_leading_bullet_noise_is_ignored(labels):
    report = parse_report(["- URGENCY: Low"], labels)
    assert report.urgency == "Low"


def test_report_is_empty_when_nothing_matches(labels):
    report = parse_report(["Some unrelated prose", "Another line"], labels)
    assert report.is_empty
    assert report.machine_label == "Equipo sin identificar"
