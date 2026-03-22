from __future__ import annotations

from pathlib import Path

from osk.config import OskConfig, load_config, save_config


def test_default_config() -> None:
    cfg = OskConfig()
    assert cfg.max_sensors == 10
    assert cfg.transcriber_backend == "fake"
    assert cfg.whisper_model == "small"
    assert cfg.vision_backend == "fake"
    assert cfg.location_backend == "fake"
    assert cfg.synthesis_backend == "heuristic"
    assert cfg.ffmpeg_binary == "ffmpeg"
    assert cfg.sitrep_interval_minutes == 10
    assert cfg.alert_cooldown_seconds == 60
    assert cfg.audio_queue_size == 128
    assert cfg.frame_queue_size == 64
    assert cfg.frame_queue_depth_per_member == 4
    assert cfg.intelligence_recent_observation_limit == 25
    assert cfg.location_sample_ttl_seconds == 120
    assert cfg.location_cluster_radius_m == 150.0
    assert cfg.location_cluster_min_size == 2
    assert cfg.synthesis_cooldown_seconds == 60
    assert cfg.max_audio_payload_bytes == 2_000_000
    assert cfg.max_frame_payload_bytes == 4_000_000
    assert cfg.ingest_idempotency_window_seconds == 900
    assert cfg.ingest_idempotency_cache_size == 4096
    assert cfg.ingest_receipt_retention_hours == 24
    assert cfg.ingest_receipt_cleanup_interval_seconds == 900
    assert cfg.frame_change_threshold == 0.15
    assert cfg.observer_clip_rate_limit == 3
    assert cfg.luks_volume_size_gb == 1
    assert cfg.hotspot_band == "5GHz"
    assert cfg.storage_backend == "luks"


def test_load_missing_config(tmp_path: Path) -> None:
    cfg = load_config(tmp_path / "nonexistent.toml")
    assert cfg == OskConfig()


def test_save_and_load_config(tmp_path: Path) -> None:
    cfg = OskConfig(
        max_sensors=5,
        transcriber_backend="whisper",
        whisper_model="tiny",
        vision_backend="ollama",
    )
    path = tmp_path / "config.toml"
    save_config(cfg, path)
    loaded = load_config(path)
    assert loaded.max_sensors == 5
    assert loaded.transcriber_backend == "whisper"
    assert loaded.whisper_model == "tiny"
    assert loaded.vision_backend == "ollama"


def test_config_partial_file(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("max_sensors = 3\n")
    cfg = load_config(path)
    assert cfg.max_sensors == 3
    assert cfg.transcriber_backend == "fake"
    assert cfg.whisper_model == "small"
