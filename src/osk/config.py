"""Configuration management for Osk."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib


DEFAULT_CONFIG_PATH = Path.home() / ".config" / "osk" / "config.toml"


class OskConfig(BaseModel):
    max_sensors: int = 10
    whisper_model: str = "small"
    vision_model: str = "llama3.2-vision:11b-instruct-q4_K_M"
    summarizer_model: str = "mistral"
    sitrep_interval_minutes: int = 10
    alert_cooldown_seconds: int = 60
    gps_interval_moving_seconds: int = 10
    gps_interval_stationary_seconds: int = 60
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
