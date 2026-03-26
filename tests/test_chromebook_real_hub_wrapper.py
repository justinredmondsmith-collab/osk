from __future__ import annotations

import json
import os
import subprocess
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "chromebook_real_hub_validation.sh"


def _write_executable(path: Path, content: str) -> Path:
    path.write_text(content)
    path.chmod(0o755)
    return path


def _write_lab_control_script(path: Path) -> Path:
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


def _write_validation_runner_stub(path: Path) -> Path:
    return _write_executable(
        path,
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import json
            import sys
            from pathlib import Path

            args = sys.argv[1:]

            def read_arg(flag: str) -> str:
                return args[args.index(flag) + 1]

            artifact_root = Path(read_arg("--artifact-root"))
            run_label = read_arg("--timestamp")
            result_path = artifact_root / run_label / "result.json"
            args_path = artifact_root / run_label / "runner-args.json"
            args_path.write_text(json.dumps(args, indent=2) + "\\n")
            payload = {
                "contract_version": 1,
                "status": "passed",
                "execution_mode": "chromebook_cdp",
                "scenario": read_arg("--scenario"),
                "hub_url": read_arg("--hub-url"),
                "join_url": read_arg("--join-url"),
                "device_id": read_arg("--device-id"),
                "ssh_target": read_arg("--ssh-target"),
                "debug_port": int(read_arg("--debug-port")),
                "artifact_dir": str(result_path.parent),
                "result_path": str(result_path),
                "captures": {
                    "closure_summary_path": None,
                    "doctor_snapshot_path": None,
                    "hub_preflight_path": None,
                    "members_snapshot_path": None,
                    "member_shell_smoke_latest_path": None,
                    "member_shell_smoke_result_path": None,
                    "operator_session_bootstrap_path": None,
                    "status_snapshot_path": None,
                    "cdp_version_path": None,
                    "audit_slice_path": None,
                    "wipe_readiness_path": None,
                },
                "steps": [],
                "summary": {"message": "stub"},
                "failure": None,
                "provenance": {
                    "artifact_version": 1,
                    "run_label": run_label,
                    "trigger": "test",
                    "invocation": "real_hub_validation.py",
                    "git_sha": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
                    "git_branch": "justinredmondsmith-collab/feat/chromebook-real-hub-wrapper",
                    "git_commit_subject": "feat(validation): Add Chromebook real-hub wrapper",
                    "runner_hostname": "lab-host",
                    "device_id": read_arg("--device-id"),
                    "worktree_dirty": False,
                    "started_at_utc": "2026-03-23T19:04:05+00:00",
                    "completed_at_utc": "2026-03-23T19:05:05+00:00",
                },
            }
            result_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\\n")
            raise SystemExit(0)
            """
        ),
    )


def _run_wrapper(
    tmp_path: Path,
    *,
    runner_script: Path,
    lab_control_script: Path,
    fail_action: str | None = None,
    scenario: str = "baseline",
) -> subprocess.CompletedProcess[str]:
    artifact_root = tmp_path / "artifacts"
    env = os.environ.copy()
    env.update(
        {
            "OSK_REAL_HUB_VALIDATION_RUNNER": str(runner_script),
            "OSK_LAB_CONTROL_SCRIPT": str(lab_control_script),
            "OSK_TEST_LAB_CONTROL_LOG": str(tmp_path / "lab-control.log"),
            "OSK_TEST_PREFLIGHT_OUTPUT": "\n".join(
                [
                    "XDG_RUNTIME_DIR=/run/user/1000",
                    "WAYLAND_DISPLAY=wayland-0",
                    "DISPLAY=:0",
                    "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus",
                    "OZONE_FLAG=--ozone-platform=wayland",
                ]
            ),
            "OSK_SMOKE_GIT_SHA": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
            "OSK_SMOKE_GIT_BRANCH": "justinredmondsmith-collab/feat/chromebook-real-hub-wrapper",
            "OSK_SMOKE_GIT_COMMIT_SUBJECT": "feat(validation): Add Chromebook real-hub wrapper",
            "OSK_SMOKE_RUNNER_HOSTNAME": "lab-host",
            "OSK_SMOKE_TRIGGER": "test",
            "OSK_SMOKE_WORKTREE_DIRTY": "false",
            "OSK_SMOKE_STARTED_AT_UTC": "2026-03-23T19:04:05+00:00",
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
            "--hub-url",
            "https://127.0.0.1:8443",
            "--join-url",
            "https://osk.local/join?token=test",
            "--scenario",
            scenario,
            "--artifact-root",
            str(artifact_root),
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _load_result(artifact_root: Path) -> dict[str, object]:
    run_dirs = sorted(path for path in artifact_root.iterdir() if path.is_dir())
    assert len(run_dirs) == 1
    return json.loads((run_dirs[0] / "result.json").read_text())


def _load_latest(artifact_root: Path) -> dict[str, object]:
    return json.loads((artifact_root / "latest.json").read_text())


def test_wrapper_prepares_launches_and_forwards_real_hub_args(tmp_path: Path) -> None:
    runner_script = _write_validation_runner_stub(tmp_path / "real-hub-runner-stub.py")
    lab_control_script = _write_lab_control_script(tmp_path / "chromebook_lab_control_stub.sh")

    result = _run_wrapper(
        tmp_path,
        runner_script=runner_script,
        lab_control_script=lab_control_script,
    )

    payload = _load_result(tmp_path / "artifacts")
    latest = _load_latest(tmp_path / "artifacts")
    run_dir = Path(payload["artifact_dir"])
    runner_args = json.loads((run_dir / "runner-args.json").read_text())
    log_lines = (tmp_path / "lab-control.log").read_text().splitlines()

    assert result.returncode == 0
    assert log_lines[:4] == ["prepare", "preflight", "launch", "cleanup"]
    assert "--dry-run" not in runner_args
    assert runner_args[runner_args.index("--hub-url") + 1] == "https://127.0.0.1:8443"
    assert runner_args[runner_args.index("--join-url") + 1] == "https://osk.local/join?token=test"
    assert runner_args[runner_args.index("--device-id") + 1] == "lab-book"
    assert runner_args[runner_args.index("--ssh-target") + 1] == "lab-book"
    assert runner_args[runner_args.index("--debug-port") + 1] == "9222"
    assert payload["launch_preflight"] == {
        "dbus_session_bus_address": "unix:path=/run/user/1000/bus",
        "display": ":0",
        "ozone_flag": "--ozone-platform=wayland",
        "wayland_display": "wayland-0",
        "xdg_runtime_dir": "/run/user/1000",
    }
    assert latest["launch_preflight"] == payload["launch_preflight"]
    assert payload["provenance"]["git_branch"] == (
        "justinredmondsmith-collab/feat/chromebook-real-hub-wrapper"
    )
    assert payload["captures"] == {
        "audit_slice_path": None,
        "cdp_version_path": None,
        "closure_summary_path": None,
        "doctor_snapshot_path": None,
        "hub_preflight_path": None,
        "members_snapshot_path": None,
        "member_shell_smoke_latest_path": None,
        "member_shell_smoke_result_path": None,
        "operator_session_bootstrap_path": None,
        "status_snapshot_path": None,
        "wipe_readiness_path": None,
    }
    assert latest["captures"] == payload["captures"]
    assert latest["status"] == "passed"


def test_wrapper_records_prepare_failure_before_runner_executes(tmp_path: Path) -> None:
    runner_script = _write_validation_runner_stub(tmp_path / "real-hub-runner-stub.py")
    lab_control_script = _write_lab_control_script(tmp_path / "chromebook_lab_control_stub.sh")

    result = _run_wrapper(
        tmp_path,
        runner_script=runner_script,
        lab_control_script=lab_control_script,
        fail_action="prepare",
        scenario="restart",
    )

    payload = _load_result(tmp_path / "artifacts")
    latest = _load_latest(tmp_path / "artifacts")
    log_lines = (tmp_path / "lab-control.log").read_text().splitlines()

    assert result.returncode == 23
    assert payload["status"] == "failed"
    assert payload["scenario"] == "restart"
    assert payload["failure"]["stage"] == "prepare"
    assert payload["hub_url"] == "https://127.0.0.1:8443"
    assert payload["join_url"] == "https://osk.local/join?token=test"
    assert payload["device_id"] == "lab-book"
    assert payload["captures"] == {
        "audit_slice_path": None,
        "cdp_version_path": None,
        "closure_summary_path": None,
        "doctor_snapshot_path": None,
        "hub_preflight_path": None,
        "members_snapshot_path": None,
        "member_shell_smoke_latest_path": None,
        "member_shell_smoke_result_path": None,
        "operator_session_bootstrap_path": None,
        "status_snapshot_path": None,
        "wipe_readiness_path": None,
    }
    assert latest["captures"] == payload["captures"]
    assert latest["failure_stage"] == "prepare"
    assert log_lines == ["prepare", "cleanup"]
