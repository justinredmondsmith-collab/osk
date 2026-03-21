from __future__ import annotations

from pathlib import Path

from osk.config import OskConfig, load_config, save_config


def test_default_config() -> None:
    cfg = OskConfig()
    assert cfg.max_sensors == 10
    assert cfg.whisper_model == "small"
    assert cfg.sitrep_interval_minutes == 10
    assert cfg.alert_cooldown_seconds == 60
    assert cfg.frame_change_threshold == 0.15
    assert cfg.observer_clip_rate_limit == 3
    assert cfg.luks_volume_size_gb == 1
    assert cfg.hotspot_band == "5GHz"


def test_load_missing_config(tmp_path: Path) -> None:
    cfg = load_config(tmp_path / "nonexistent.toml")
    assert cfg == OskConfig()


def test_save_and_load_config(tmp_path: Path) -> None:
    cfg = OskConfig(max_sensors=5, whisper_model="tiny")
    path = tmp_path / "config.toml"
    save_config(cfg, path)
    loaded = load_config(path)
    assert loaded.max_sensors == 5
    assert loaded.whisper_model == "tiny"


def test_config_partial_file(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("max_sensors = 3\n")
    cfg = load_config(path)
    assert cfg.max_sensors == 3
    assert cfg.whisper_model == "small"
