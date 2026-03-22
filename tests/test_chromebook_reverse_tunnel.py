from __future__ import annotations

import json
import os
import subprocess
import textwrap
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


def _write_executable(path: Path, content: str) -> Path:
    path.write_text(content)
    path.chmod(0o755)
    return path


def test_install_user_service_enables_absolute_service_path_for_custom_dir(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    systemctl_log = tmp_path / "systemctl.log"
    ssh_log = tmp_path / "ssh.log"

    _write_executable(
        fake_bin / "systemctl",
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            printf '%s\n' "$*" >> "${OSK_SYSTEMCTL_LOG:?missing systemctl log}"
            exit 0
            """
        ),
    )
    _write_executable(
        fake_bin / "ssh",
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            printf '%s\n' "$*" >> "${OSK_SSH_LOG:?missing ssh log}"
            if [[ "$*" == *"/dev/tcp/127.0.0.1/"* ]]; then
              exit 1
            fi
            exit 0
            """
        ),
    )

    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home_dir),
            "PATH": f"{fake_bin}:{env['PATH']}",
            "OSK_SYSTEMCTL_LOG": str(systemctl_log),
            "OSK_SSH_LOG": str(ssh_log),
        }
    )
    service_dir = tmp_path / "custom-systemd-user"
    result = subprocess.run(
        [
            "bash",
            str(SCRIPT_PATH),
            "install-user-service",
            "--host-target",
            "host-user@198.51.100.42",
            "--service-dir",
            str(service_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    service_path = service_dir / "osk-chromebook-reverse-tunnel.service"

    assert result.returncode == 0
    assert service_path.exists()
    assert any(
        f"--user enable --now {service_path}" in line
        for line in systemctl_log.read_text().splitlines()
    )
