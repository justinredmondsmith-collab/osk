from __future__ import annotations

import importlib.util
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "chromebook_member_shell_smoke.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("chromebook_member_shell_smoke", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _set_provenance_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OSK_SMOKE_GIT_SHA", "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef")
    monkeypatch.setenv(
        "OSK_SMOKE_GIT_BRANCH",
        "justinredmondsmith-collab/feat/chromebook-lab-gate",
    )
    monkeypatch.setenv("OSK_SMOKE_GIT_COMMIT_SUBJECT", "feat(chromebook): Add lab gate")
    monkeypatch.setenv("OSK_SMOKE_RUNNER_HOSTNAME", "lab-host")
    monkeypatch.setenv("OSK_SMOKE_TRIGGER", "test")
    monkeypatch.setenv("OSK_SMOKE_WORKTREE_DIRTY", "false")
    monkeypatch.setenv("OSK_SMOKE_STARTED_AT_UTC", "2026-03-22T19:04:05+00:00")


def test_parse_args_defaults_ssh_target_to_chromebook_host() -> None:
    smoke = _load_module()

    args = smoke.parse_args(
        [
            "--chromebook-host",
            "lab-book",
            "--smoke-metadata",
            "metadata.json",
            "--dry-run",
        ]
    )

    assert args.chromebook_host == "lab-book"
    assert args.ssh_target == "lab-book"
    assert args.debug_port == 9222
    assert args.dry_run is True


def test_load_smoke_metadata_requires_join_url(tmp_path: Path) -> None:
    smoke = _load_module()
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(json.dumps({"operation_name": "Smoke Test"}) + "\n")

    with pytest.raises(ValueError, match="join_url"):
        smoke.load_smoke_metadata(metadata_path)


def test_make_artifact_dir_uses_timestamped_run_directory(tmp_path: Path) -> None:
    smoke = _load_module()

    artifact_dir = smoke.make_artifact_dir(
        tmp_path,
        now=datetime(2026, 3, 22, 19, 4, 5, tzinfo=timezone.utc),
    )

    assert artifact_dir == tmp_path / "20260322T190405Z"


def test_build_ssh_tunnel_command_forwards_local_debug_port() -> None:
    smoke = _load_module()

    command = smoke.build_ssh_tunnel_command("chromebook-user@192.0.2.25", 9333, 9222)

    assert command == [
        "ssh",
        "-F",
        "/dev/null",
        "-o",
        "ExitOnForwardFailure=yes",
        "-N",
        "-L",
        "9333:127.0.0.1:9222",
        "chromebook-user@192.0.2.25",
    ]


def test_build_ssh_tunnel_command_supports_non_default_ssh_port() -> None:
    smoke = _load_module()

    command = smoke.build_ssh_tunnel_command("localhost", 9333, 9222, 22022)

    assert command == [
        "ssh",
        "-F",
        "/dev/null",
        "-o",
        "ExitOnForwardFailure=yes",
        "-N",
        "-L",
        "9333:127.0.0.1:9222",
        "-p",
        "22022",
        "localhost",
    ]


def test_build_ssh_tunnel_command_supports_explicit_identity_file() -> None:
    smoke = _load_module()

    command = smoke.build_ssh_tunnel_command(
        "chromebook-user@localhost",
        9333,
        9222,
        22022,
        "/home/host-user/.ssh/osk_chromebook_lab",
    )

    assert command == [
        "ssh",
        "-F",
        "/dev/null",
        "-o",
        "ExitOnForwardFailure=yes",
        "-N",
        "-L",
        "9333:127.0.0.1:9222",
        "-p",
        "22022",
        "-i",
        "/home/host-user/.ssh/osk_chromebook_lab",
        "chromebook-user@localhost",
    ]


def test_dry_run_writes_result_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    smoke = _load_module()
    _set_provenance_env(monkeypatch)
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "join_url": "http://127.0.0.1:8123/join?token=test",
                "operation_name": "Smoke Test",
                "controls": {"wipe_url": "http://127.0.0.1:8123/__smoke/wipe"},
            }
        )
        + "\n"
    )
    artifact_root = tmp_path / "artifacts"

    code = smoke.main(
        [
            "--chromebook-host",
            "lab-book",
            "--smoke-metadata",
            str(metadata_path),
            "--artifact-root",
            str(artifact_root),
            "--dry-run",
            "--timestamp",
            "20260322T190405Z",
        ]
    )

    result_path = artifact_root / "20260322T190405Z" / "result.json"
    payload = json.loads(result_path.read_text())

    assert code == 0
    assert payload["status"] == "dry_run"
    assert payload["chromebook_host"] == "lab-book"
    assert payload["ssh_target"] == "lab-book"
    assert payload["ssh_port"] is None
    assert payload["ssh_identity"] is None
    assert payload["result_path"] == str(result_path)
    assert payload["launch_preflight"] is None
    assert payload["smoke_metadata"]["join_url"] == "http://127.0.0.1:8123/join?token=test"
    assert payload["steps"] == []
    assert payload["provenance"] == {
        "artifact_version": 1,
        "completed_at_utc": payload["provenance"]["completed_at_utc"],
        "device_id": "lab-book",
        "git_branch": "justinredmondsmith-collab/feat/chromebook-lab-gate",
        "git_commit_subject": "feat(chromebook): Add lab gate",
        "git_sha": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
        "invocation": None,
        "run_label": "20260322T190405Z",
        "runner_hostname": "lab-host",
        "started_at_utc": "2026-03-22T19:04:05+00:00",
        "trigger": "test",
        "worktree_dirty": False,
    }


def test_dry_run_with_missing_metadata_fails_cleanly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    smoke = _load_module()
    missing_path = tmp_path / "missing.json"

    code = smoke.main(
        [
            "--chromebook-host",
            "lab-book",
            "--smoke-metadata",
            str(missing_path),
            "--dry-run",
        ]
    )

    err = capsys.readouterr().err

    assert code == 1
    assert str(missing_path) in err


def test_non_dry_run_writes_failure_result_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    smoke = _load_module()
    _set_provenance_env(monkeypatch)
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "join_url": "http://192.168.1.10:8123/join?token=test",
                "operation_name": "Smoke Test",
                "controls": {"wipe_url": "http://192.168.1.10:8123/__smoke/wipe"},
            }
        )
        + "\n"
    )
    artifact_root = tmp_path / "artifacts"

    @contextmanager
    def fake_tunnel(*_args, **_kwargs):
        yield

    monkeypatch.setattr(smoke, "choose_local_port", lambda: 9333)
    monkeypatch.setattr(smoke, "managed_ssh_tunnel", fake_tunnel)
    monkeypatch.setattr(
        smoke,
        "fetch_cdp_version",
        lambda *_args, **_kwargs: {"Browser": "Chrome/146"},
    )

    def fail_flow(*_args, **_kwargs):
        raise RuntimeError("smoke flow failed")

    monkeypatch.setattr(smoke, "run_smoke_flow", fail_flow)

    code = smoke.main(
        [
            "--chromebook-host",
            "lab-book",
            "--ssh-target",
            "chromebook-user@192.0.2.25",
            "--smoke-metadata",
            str(metadata_path),
            "--artifact-root",
            str(artifact_root),
            "--timestamp",
            "20260322T190405Z",
        ]
    )

    result_path = artifact_root / "20260322T190405Z" / "result.json"
    payload = json.loads(result_path.read_text())

    assert code == 1
    assert payload["status"] == "failed"
    assert payload["ssh_port"] is None
    assert payload["ssh_identity"] is None
    assert payload["local_debug_port"] == 9333
    assert payload["cdp_version"]["Browser"] == "Chrome/146"
    assert payload["failure"]["message"] == "smoke flow failed"
    assert payload["result_path"] == str(result_path)
    assert payload["provenance"]["trigger"] == "test"
    assert payload["provenance"]["runner_hostname"] == "lab-host"


def test_non_dry_run_preserves_partial_steps_and_summary_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    smoke = _load_module()
    _set_provenance_env(monkeypatch)
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "join_url": "http://192.168.1.10:8123/join?token=test",
                "operation_name": "Smoke Test",
                "controls": {"wipe_url": "http://192.168.1.10:8123/__smoke/wipe"},
            }
        )
        + "\n"
    )
    artifact_root = tmp_path / "artifacts"

    @contextmanager
    def fake_tunnel(*_args, **_kwargs):
        yield

    monkeypatch.setattr(smoke, "choose_local_port", lambda: 9333)
    monkeypatch.setattr(smoke, "managed_ssh_tunnel", fake_tunnel)
    monkeypatch.setattr(
        smoke,
        "fetch_cdp_version",
        lambda *_args, **_kwargs: {"Browser": "Chrome/146"},
    )

    state = smoke.SmokeRunState(
        steps=[
            {
                "name": "join-loaded",
                "status": "passed",
                "screenshot": "01-join-loaded.png",
                "detail": {"url": "http://192.168.1.10:8123/join?token=test"},
            }
        ],
        console_events=[{"type": "warning", "text": "late console event"}],
        network_failures=[{"url": "http://example.test", "method": "GET", "failure": "net::ERR"}],
        page_errors=["runtime exploded"],
        display_name="Chromebook Smoke 123",
        member_id="member-123",
        operation_name="Smoke Test",
    )

    def fail_flow(*_args, **_kwargs):
        try:
            raise RuntimeError("checkpoint failed")
        except RuntimeError as exc:
            raise smoke.SmokeRunFailed(str(exc), state) from exc

    monkeypatch.setattr(smoke, "run_smoke_flow", fail_flow)

    code = smoke.main(
        [
            "--chromebook-host",
            "lab-book",
            "--ssh-target",
            "chromebook-user@192.0.2.25",
            "--smoke-metadata",
            str(metadata_path),
            "--artifact-root",
            str(artifact_root),
            "--timestamp",
            "20260322T190405Z",
        ]
    )

    result_path = artifact_root / "20260322T190405Z" / "result.json"
    payload = json.loads(result_path.read_text())

    assert code == 1
    assert payload["status"] == "failed"
    assert payload["failure"]["message"] == "checkpoint failed"
    assert payload["failure"]["type"] == "RuntimeError"
    assert payload["steps"] == state.steps
    assert payload["summary"] == {
        "display_name": "Chromebook Smoke 123",
        "member_id": "member-123",
        "operation_name": "Smoke Test",
        "console_event_count": 1,
        "network_failure_count": 1,
        "page_error_count": 1,
    }
    assert payload["provenance"]["git_sha"] == "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
