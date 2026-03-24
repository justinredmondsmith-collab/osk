from __future__ import annotations

import json
import os
import shlex
import socket
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "chromebook_lab_control.sh"


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _run_bash(
    script: str, *, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env is not None:
        merged_env.update(env)
    return subprocess.run(
        ["bash", "-lc", script],
        capture_output=True,
        text=True,
        check=False,
        env=merged_env,
    )


def _bind_unix_socket(path: Path) -> socket.socket:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(str(path))
    return sock


def _probe_launch_env(
    runtime_dir: Path, **overrides: str
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    env = os.environ.copy()
    env.update(
        {
            "XDG_RUNTIME_DIR": str(runtime_dir),
            "WAYLAND_DISPLAY": "",
            "DISPLAY": "",
            "DBUS_SESSION_BUS_ADDRESS": "",
        }
    )
    env.update(overrides)
    result = _run_bash(
        (
            f"source {shlex.quote(str(SCRIPT_PATH))}; "
            "unset ozone_flag; "
            "detect_crostini_gui_env; "
            "printf '%s\\n' "
            '"$XDG_RUNTIME_DIR" '
            '"${WAYLAND_DISPLAY:-}" '
            '"${DISPLAY:-}" '
            '"${DBUS_SESSION_BUS_ADDRESS:-}" '
            '"${ozone_flag:-}"'
        ),
        env=env,
    )
    return result, result.stdout.splitlines()


def test_prepare_dry_run_emits_json_plan() -> None:
    result = _run_script("prepare", "--ssh-target", "lab-book", "--dry-run", "--json")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["action"] == "prepare"
    assert payload["ssh_target"] == "lab-book"
    assert payload["ssh_port"] is None
    assert payload["ssh_identity"] is None
    assert payload["profile_dir"] == "/var/tmp/osk-chromebook-lab"
    assert payload["debug_port"] == 9222
    assert payload["ssh_prefix"] == ["ssh", "-F", "/dev/null"]
    assert [step["name"] for step in payload["steps"]] == [
        "check_ssh",
        "check_chrome",
        "kill_lab_browser",
        "reset_profile",
    ]


def test_launch_dry_run_uses_explicit_user_data_dir() -> None:
    result = _run_script(
        "launch",
        "--ssh-target",
        "lab-book",
        "--chrome-binary",
        "/opt/google/chrome/chrome",
        "--dry-run",
        "--json",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["action"] == "launch"
    assert payload["ssh_prefix"] == ["ssh", "-F", "/dev/null"]
    launch_command = payload["steps"][0]["command"]
    assert launch_command.startswith("ssh -F /dev/null lab-book ")
    assert "detect_crostini_gui_env" in launch_command
    assert "XDG_RUNTIME_DIR" in launch_command
    assert "WAYLAND_DISPLAY" in launch_command
    assert "--ozone-platform=wayland" in launch_command
    assert "--user-data-dir=/var/tmp/osk-chromebook-lab" in launch_command
    assert "--remote-debugging-port=9222" in launch_command
    assert "/opt/google/chrome/chrome" in launch_command


def test_launch_dry_run_includes_extra_chrome_flags() -> None:
    result = _run_script(
        "launch",
        "--ssh-target",
        "lab-book",
        "--chrome-flag",
        "--ignore-certificate-errors",
        "--chrome-flag",
        "--allow-insecure-localhost",
        "--dry-run",
        "--json",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    launch_command = payload["steps"][0]["command"]
    assert "--ignore-certificate-errors" in launch_command
    assert "--allow-insecure-localhost" in launch_command


def test_prepare_dry_run_includes_non_default_ssh_port() -> None:
    result = _run_script(
        "prepare",
        "--ssh-target",
        "localhost",
        "--ssh-port",
        "22022",
        "--dry-run",
        "--json",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ssh_port"] == 22022
    assert payload["ssh_prefix"] == ["ssh", "-F", "/dev/null", "-p", "22022"]


def test_prepare_dry_run_includes_explicit_identity_file() -> None:
    result = _run_script(
        "prepare",
        "--ssh-target",
        "chromebook-user@localhost",
        "--ssh-port",
        "22022",
        "--ssh-identity",
        "/home/host-user/.ssh/osk_chromebook_lab",
        "--dry-run",
        "--json",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ssh_identity"] == "/home/host-user/.ssh/osk_chromebook_lab"
    assert payload["ssh_prefix"] == [
        "ssh",
        "-F",
        "/dev/null",
        "-p",
        "22022",
        "-i",
        "/home/host-user/.ssh/osk_chromebook_lab",
    ]


def test_cleanup_dry_run_emits_browser_stop_plan() -> None:
    result = _run_script("cleanup", "--ssh-target", "lab-book", "--dry-run", "--json")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["action"] == "cleanup"
    assert payload["ssh_port"] is None
    assert payload["ssh_identity"] is None
    assert payload["ssh_prefix"] == ["ssh", "-F", "/dev/null"]
    assert [step["name"] for step in payload["steps"]] == ["kill_lab_browser"]
    assert "/var/tmp/osk-chromebook-lab.pid" in payload["steps"][0]["command"]


def test_preflight_dry_run_emits_launch_diagnostics_plan() -> None:
    result = _run_script("preflight", "--ssh-target", "lab-book", "--dry-run", "--json")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["action"] == "preflight"
    assert [step["name"] for step in payload["steps"]] == ["capture_launch_diagnostics"]
    preflight_command = payload["steps"][0]["command"]
    assert preflight_command.startswith("ssh -F /dev/null lab-book ")
    assert "detect_crostini_gui_env" in preflight_command
    assert "XDG_RUNTIME_DIR=" in preflight_command
    assert "WAYLAND_DISPLAY=" in preflight_command
    assert "DISPLAY=" in preflight_command


def test_cleanup_dry_run_matches_by_binary_name_for_wrapper_browsers() -> None:
    result = _run_script("cleanup", "--ssh-target", "lab-book", "--dry-run", "--json")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    kill_command = payload["steps"][0]["command"]
    assert "resolved_bin:-chromium" in kill_command
    assert "bin_name" in kill_command
    assert "--user-data-dir=/var/tmp/osk-chromebook-lab" in kill_command


def test_detect_crostini_gui_env_prefers_existing_wayland_display(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    bus_socket = _bind_unix_socket(runtime_dir / "bus")
    preferred_socket = _bind_unix_socket(runtime_dir / "wayland-custom")
    fallback_socket = _bind_unix_socket(runtime_dir / "wayland-0")
    (runtime_dir / "DISPLAY-:0-wl").touch()

    try:
        result, lines = _probe_launch_env(runtime_dir, WAYLAND_DISPLAY="wayland-custom")
    finally:
        fallback_socket.close()
        preferred_socket.close()
        bus_socket.close()

    assert result.returncode == 0
    assert lines == [
        str(runtime_dir),
        "wayland-custom",
        ":0",
        f"unix:path={runtime_dir / 'bus'}",
        "--ozone-platform=wayland",
    ]


def test_detect_crostini_gui_env_falls_back_to_wayland_1(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    bus_socket = _bind_unix_socket(runtime_dir / "bus")
    wayland_socket = _bind_unix_socket(runtime_dir / "wayland-1")
    (runtime_dir / "DISPLAY-:1-wl").touch()

    try:
        result, lines = _probe_launch_env(runtime_dir)
    finally:
        wayland_socket.close()
        bus_socket.close()

    assert result.returncode == 0
    assert lines == [
        str(runtime_dir),
        "wayland-1",
        ":1",
        f"unix:path={runtime_dir / 'bus'}",
        "--ozone-platform=wayland",
    ]


def test_detect_crostini_gui_env_leaves_gui_vars_empty_without_session(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()

    result, lines = _probe_launch_env(runtime_dir)

    assert result.returncode == 0
    assert lines == [
        str(runtime_dir),
        "",
        "",
        "",
        "",
    ]


def test_detect_crostini_gui_env_preserves_existing_display_and_bus(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    wayland_socket = _bind_unix_socket(runtime_dir / "wayland-1")

    try:
        result, lines = _probe_launch_env(
            runtime_dir,
            DISPLAY=":9",
            DBUS_SESSION_BUS_ADDRESS="unix:path=/tmp/custom-bus",
        )
    finally:
        wayland_socket.close()

    assert result.returncode == 0
    assert lines == [
        str(runtime_dir),
        "wayland-1",
        ":9",
        "unix:path=/tmp/custom-bus",
        "--ozone-platform=wayland",
    ]


def test_missing_action_fails_with_usage() -> None:
    result = _run_script("--dry-run", "--json")

    assert result.returncode == 1
    assert "Usage:" in result.stderr
