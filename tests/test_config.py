import pytest
import yaml

from clariot.config import ConfigError, load_settings

BASE = {
    "outlook": {
        "source_folders": ["1_Auditoria_Clariot"],
        "include_subfolders": True,
        "processed_folder": "2_Auditoria_Procesado",
        "mark_as_read": True,
        "max_attachment_mb": 20,
    },
    "translation": {"target_lang": "ES", "formality": "more", "attach_original": True},
    "paths": {},
    "email": {"subject_template": "{machine}"},
    "urgency": {"critical_values": ["Critical", "Crítica"]},
}


def write_config(tmp_path, overrides=None):
    data = {key: dict(value) for key, value in BASE.items()}
    for section, values in (overrides or {}).items():
        data[section].update(values)

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "settings.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    return config_dir


def test_source_folders_accepts_a_list(tmp_path):
    config_dir = write_config(tmp_path)
    settings = load_settings(tmp_path, config_dir)
    assert settings.outlook.source_folders == ("1_Auditoria_Clariot",)


def test_source_folders_accepts_a_bare_string(tmp_path):
    config_dir = write_config(tmp_path, {"outlook": {"source_folders": "Alertas"}})
    settings = load_settings(tmp_path, config_dir)
    assert settings.outlook.source_folders == ("Alertas",)


def test_empty_source_folders_is_rejected(tmp_path):
    config_dir = write_config(tmp_path, {"outlook": {"source_folders": []}})
    with pytest.raises(ConfigError):
        load_settings(tmp_path, config_dir)


def test_processed_folder_inside_a_source_folder_is_rejected(tmp_path):
    """Otherwise processed mail sits inside the tree that gets rescanned."""
    config_dir = write_config(
        tmp_path,
        {"outlook": {"processed_folder": "1_Auditoria_Clariot/Procesados"}},
    )
    with pytest.raises(ConfigError):
        load_settings(tmp_path, config_dir)


def test_urgency_values_are_normalized(tmp_path):
    config_dir = write_config(tmp_path)
    settings = load_settings(tmp_path, config_dir)
    assert "CRITICA" in settings.critical_urgencies
