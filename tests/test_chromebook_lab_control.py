from __future__ import annotations

import json
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
    assert "--user-data-dir=/var/tmp/osk-chromebook-lab" in launch_command
    assert "--remote-debugging-port=9222" in launch_command
    assert "/opt/google/chrome/chrome" in launch_command


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


def test_missing_action_fails_with_usage() -> None:
    result = _run_script("--dry-run", "--json")

    assert result.returncode == 1
    assert "Usage:" in result.stderr
