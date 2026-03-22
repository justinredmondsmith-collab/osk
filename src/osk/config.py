"""Configuration management for Osk."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib


DEFAULT_CONFIG_PATH = Path.home() / ".config" / "osk" / "config.toml"


class OskConfig(BaseModel):
    max_sensors: int = 10
    transcriber_backend: Literal["fake", "whisper"] = "fake"
    whisper_model: str = "small"
    vision_backend: Literal["fake", "ollama"] = "fake"
    vision_model: str = "llama3.2-vision:11b-instruct-q4_K_M"
    location_backend: Literal["fake"] = "fake"
    synthesis_backend: Literal["heuristic"] = "heuristic"
    ffmpeg_binary: str = "ffmpeg"
    summarizer_model: str = "mistral"
    sitrep_interval_minutes: int = 10
    alert_cooldown_seconds: int = 60
    gps_interval_moving_seconds: int = 10
    gps_interval_stationary_seconds: int = 60
    member_heartbeat_timeout_seconds: int = 45
    member_heartbeat_check_interval_seconds: int = 15
    audio_queue_size: int = 128
    frame_queue_size: int = 64
    frame_queue_depth_per_member: int = 4
    intelligence_recent_observation_limit: int = 25
    location_sample_ttl_seconds: int = 120
    location_cluster_radius_m: float = 150.0
    location_cluster_min_size: int = 2
    synthesis_cooldown_seconds: int = 60
    max_audio_payload_bytes: int = 2_000_000
    max_frame_payload_bytes: int = 4_000_000
    ingest_idempotency_window_seconds: int = 900
    ingest_idempotency_cache_size: int = 4096
    ingest_receipt_retention_hours: int = 24
    ingest_receipt_cleanup_interval_seconds: int = 900
    frame_change_threshold: float = 0.15
    frame_baseline_interval_seconds: int = 30
    frame_sampling_fps: float = 2.0
    observer_clip_rate_limit: int = 3
    luks_volume_size_gb: int = 1
    tls_cert_path: str = str(Path.home() / ".config" / "osk" / "cert.pem")
    tls_key_path: str = str(Path.home() / ".config" / "osk" / "key.pem")
    hotspot_ssid: str = ""
    hotspot_band: str = "5GHz"
    map_tile_cache_path: str = str(Path.home() / ".config" / "osk" / "tiles")
    hub_port: int = 8443
    hub_host: str = "0.0.0.0"
    join_host: str = "127.0.0.1"
    database_url: str = "postgresql://osk:osk@localhost:5432/osk"
    ollama_base_url: str = "http://localhost:11434"
    auto_manage_local_services: bool = True
    operator_bootstrap_ttl_minutes: int = 15
    operator_session_ttl_minutes: int = 240
    dashboard_bootstrap_ttl_minutes: int = 5
    dashboard_session_ttl_minutes: int = 120
    member_runtime_bootstrap_ttl_minutes: int = 5
    member_runtime_session_ttl_minutes: int = 240
    storage_backend: Literal["luks", "directory"] = "luks"


def _toml_literal(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> OskConfig:
    if not path.exists():
        return OskConfig()
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    return OskConfig(**data)


def save_config(config: OskConfig, path: Path = DEFAULT_CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{key} = {_toml_literal(value)}" for key, value in config.model_dump().items()]
    path.write_text("\n".join(lines) + "\n")
