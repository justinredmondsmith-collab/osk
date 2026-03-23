from __future__ import annotations

import json
import os
import subprocess
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "chromebook_member_shell_smoke.sh"


def _write_executable(path: Path, content: str) -> Path:
    path.write_text(content)
    path.chmod(0o755)
    return path


def _write_helper_script(path: Path, join_url: str) -> Path:
    return _write_executable(
        path,
        textwrap.dedent(
            f"""\
            #!/usr/bin/env python3
            import json
            import sys
            from pathlib import Path

            args = sys.argv[1:]
            metadata_path = Path(args[args.index("--metadata-path") + 1])
            metadata_path.write_text(
                json.dumps(
                    {{
                        "join_url": "{join_url}",
                        "operation_name": "Chromebook Member Smoke",
                        "controls": {{"wipe_url": "http://127.0.0.1:8123/__smoke/wipe"}},
                    }}
                )
                + "\\n"
            )
            """
        ),
    )


def _write_lab_control_script(path: Path, *, fail_action: str | None = None) -> Path:
    body = """\
#!/usr/bin/env bash
set -euo pipefail
action="${1:?missing action}"
printf '%s\n' "${action}" >> "${OSK_TEST_LAB_CONTROL_LOG:?missing log path}"
if [[ "${action}" == "preflight" && -n "${OSK_TEST_PREFLIGHT_OUTPUT:-}" ]]; then
  printf '%s\n' "${OSK_TEST_PREFLIGHT_OUTPUT}"
fi
if [[ -n "${OSK_TEST_FAIL_ACTION:-}" && "${action}" == "${OSK_TEST_FAIL_ACTION}" ]]; then
  exit 23
fi
"""
    return _write_executable(path, body)


def _write_curl_script(path: Path, *, exit_code: int) -> Path:
    return _write_executable(
        path,
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            exit {exit_code}
            """
        ),
    )


def _run_wrapper(
    tmp_path: Path,
    *,
    helper_script: Path,
    curl_script: Path,
    lab_control_script: Path,
    fail_action: str | None = None,
) -> subprocess.CompletedProcess[str]:
    artifact_root = tmp_path / "artifacts"
    log_path = tmp_path / "lab-control.log"
    env = os.environ.copy()
    env.update(
        {
            "OSK_MEMBER_SMOKE_SCRIPT": str(helper_script),
            "OSK_CURL_BIN": str(curl_script),
            "OSK_LAB_CONTROL_SCRIPT": str(lab_control_script),
            "OSK_HELPER_READY_ATTEMPTS": "10",
            "OSK_HELPER_READY_SLEEP_SECONDS": "0.05",
            "OSK_TEST_LAB_CONTROL_LOG": str(log_path),
        }
    )
    if fail_action is not None:
        env["OSK_TEST_FAIL_ACTION"] = fail_action

    return subprocess.run(
        [
            "bash",
            str(SCRIPT_PATH),
            "--chromebook-host",
            "lab-book",
            "--advertise-host",
            "198.51.100.42",
            "--artifact-root",
            str(artifact_root),
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _load_result(artifact_root: Path) -> dict[str, object]:
    run_dirs = sorted(artifact_root.iterdir())
    assert len(run_dirs) == 1
    return json.loads((run_dirs[0] / "result.json").read_text())


def test_wrapper_fails_fast_when_helper_never_becomes_reachable(tmp_path: Path) -> None:
    helper_script = _write_helper_script(
        tmp_path / "member_shell_smoke_stub.py",
        "http://127.0.0.1:65535/join?token=test",
    )
    curl_script = _write_curl_script(tmp_path / "curl-fail.sh", exit_code=1)
    lab_control_script = _write_lab_control_script(tmp_path / "chromebook_lab_control_stub.sh")

    result = _run_wrapper(
        tmp_path,
        helper_script=helper_script,
        curl_script=curl_script,
        lab_control_script=lab_control_script,
    )

    payload = _load_result(tmp_path / "artifacts")
    log_path = tmp_path / "lab-control.log"

    assert result.returncode == 1
    assert payload["status"] == "failed"
    assert payload["failure"]["stage"] == "helper-ready"
    assert payload["smoke_metadata"]["join_url"] == "http://127.0.0.1:65535/join?token=test"
    assert "prepare" not in (log_path.read_text() if log_path.exists() else "")


def test_wrapper_writes_failed_result_when_prepare_step_fails(tmp_path: Path) -> None:
    helper_script = _write_helper_script(
        tmp_path / "member_shell_smoke_stub.py",
        "http://127.0.0.1:8123/join?token=test",
    )
    curl_script = _write_curl_script(tmp_path / "curl-success.sh", exit_code=0)
    lab_control_script = _write_lab_control_script(tmp_path / "chromebook_lab_control_stub.sh")

    result = _run_wrapper(
        tmp_path,
        helper_script=helper_script,
        curl_script=curl_script,
        lab_control_script=lab_control_script,
        fail_action="prepare",
    )

    payload = _load_result(tmp_path / "artifacts")
    log_path = tmp_path / "lab-control.log"
    log_lines = log_path.read_text().splitlines()

    assert result.returncode == 23
    assert payload["status"] == "failed"
    assert payload["failure"]["stage"] == "prepare"
    assert payload["smoke_metadata"]["join_url"] == "http://127.0.0.1:8123/join?token=test"
    assert "prepare" in log_lines
    assert "launch" not in log_lines


def test_wrapper_records_launch_preflight_when_launch_step_fails(tmp_path: Path) -> None:
    helper_script = _write_helper_script(
        tmp_path / "member_shell_smoke_stub.py",
        "http://127.0.0.1:8123/join?token=test",
    )
    curl_script = _write_curl_script(tmp_path / "curl-success.sh", exit_code=0)
    lab_control_script = _write_lab_control_script(tmp_path / "chromebook_lab_control_stub.sh")

    env = os.environ.copy()
    env.update(
        {
            "OSK_MEMBER_SMOKE_SCRIPT": str(helper_script),
            "OSK_CURL_BIN": str(curl_script),
            "OSK_LAB_CONTROL_SCRIPT": str(lab_control_script),
            "OSK_HELPER_READY_ATTEMPTS": "10",
            "OSK_HELPER_READY_SLEEP_SECONDS": "0.05",
            "OSK_TEST_LAB_CONTROL_LOG": str(tmp_path / "lab-control.log"),
            "OSK_TEST_FAIL_ACTION": "launch",
            "OSK_TEST_PREFLIGHT_OUTPUT": "\n".join(
                [
                    "XDG_RUNTIME_DIR=/run/user/1000",
                    "WAYLAND_DISPLAY=wayland-0",
                    "DISPLAY=:0",
                    "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus",
                    "OZONE_FLAG=--ozone-platform=wayland",
                ]
            ),
        }
    )

    result = subprocess.run(
        [
            "bash",
            str(SCRIPT_PATH),
            "--chromebook-host",
            "lab-book",
            "--advertise-host",
            "198.51.100.42",
            "--artifact-root",
            str(tmp_path / "artifacts"),
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    payload = _load_result(tmp_path / "artifacts")
    log_lines = (tmp_path / "lab-control.log").read_text().splitlines()

    assert result.returncode == 23
    assert payload["status"] == "failed"
    assert payload["failure"]["stage"] == "launch"
    assert payload["launch_preflight"] == {
        "xdg_runtime_dir": "/run/user/1000",
        "wayland_display": "wayland-0",
        "display": ":0",
        "dbus_session_bus_address": "unix:path=/run/user/1000/bus",
        "ozone_flag": "--ozone-platform=wayland",
    }
    assert log_lines[:3] == ["prepare", "preflight", "launch"]
