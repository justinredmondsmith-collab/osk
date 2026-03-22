from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "chromebook_reverse_tunnel.sh"


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_run_dry_run_emits_reverse_tunnel_command() -> None:
    result = _run_script(
        "run",
        "--host-target",
        "host-user@198.51.100.42",
        "--identity",
        "/home/chromebook-user/.ssh/id_ed25519",
        "--dry-run",
        "--json",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["action"] == "run"
    assert payload["host_target"] == "host-user@198.51.100.42"
    assert payload["identity_path"] == "/home/chromebook-user/.ssh/id_ed25519"
    assert payload["remote_port"] == 22022
    assert payload["local_host"] == "localhost"
    assert payload["local_port"] == 22
    assert payload["host_access_command"].endswith(" true")
    assert "-R 22022:localhost:22" in payload["run_command"]
    assert "/dev/tcp/127.0.0.1/22022" in payload["port_probe_command"]
    assert "-o ServerAliveInterval=15" in payload["run_command"]


def test_install_dry_run_emits_service_path() -> None:
    result = _run_script(
        "install-user-service",
        "--host-target",
        "host-user@198.51.100.42",
        "--service-dir",
        "/tmp/osk-systemd-user",
        "--service-name",
        "osk-test-tunnel.service",
        "--dry-run",
        "--json",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["action"] == "install-user-service"
    assert payload["service_dir"] == "/tmp/osk-systemd-user"
    assert payload["service_name"] == "osk-test-tunnel.service"
    assert payload["service_path"] == "/tmp/osk-systemd-user/osk-test-tunnel.service"
    assert payload["script_path"].endswith("/scripts/chromebook_reverse_tunnel.sh")


def test_preflight_dry_run_emits_probe_commands() -> None:
    result = _run_script(
        "preflight",
        "--host-target",
        "host-user@198.51.100.42",
        "--remote-port",
        "22023",
        "--dry-run",
        "--json",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["action"] == "preflight"
    assert payload["allow_existing_port"] is False
    assert payload["host_target"] == "host-user@198.51.100.42"
    assert payload["host_access_command"].endswith(" true")
    assert "/dev/tcp/127.0.0.1/22023" in payload["port_probe_command"]


def test_install_dry_run_expands_default_service_dir_to_home() -> None:
    result = _run_script(
        "install-user-service",
        "--host-target",
        "host-user@198.51.100.42",
        "--dry-run",
        "--json",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["service_dir"].endswith("/.config/systemd/user")
    assert "/~/" not in payload["service_path"]


def test_service_status_dry_run_does_not_require_host_target() -> None:
    result = _run_script("service-status", "--dry-run", "--json")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["action"] == "service-status"
    assert payload["host_target"] == ""
    assert payload["run_command"] == ""


def test_missing_host_target_fails() -> None:
    result = _run_script("run", "--dry-run", "--json")

    assert result.returncode == 1
    assert "--host-target is required for run" in result.stderr
