from __future__ import annotations

import importlib.util
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "real_hub_validation.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("real_hub_validation", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _set_provenance_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OSK_SMOKE_GIT_SHA", "feedfacefeedfacefeedfacefeedfacefeedface")
    monkeypatch.setenv(
        "OSK_SMOKE_GIT_BRANCH",
        "justinredmondsmith-collab/docs/plan-8-real-hub-validation",
    )
    monkeypatch.setenv("OSK_SMOKE_GIT_COMMIT_SUBJECT", "docs(plan): Add real-hub validation plan")
    monkeypatch.setenv("OSK_SMOKE_RUNNER_HOSTNAME", "validation-host")
    monkeypatch.setenv("OSK_SMOKE_TRIGGER", "test")
    monkeypatch.setenv("OSK_SMOKE_WORKTREE_DIRTY", "false")
    monkeypatch.setenv("OSK_SMOKE_STARTED_AT_UTC", "2026-03-23T19:04:05+00:00")


def test_parse_args_defaults_scenario_and_accepts_required_inputs() -> None:
    validation = _load_module()

    args = validation.parse_args(
        [
            "--hub-url",
            "https://127.0.0.1:8443",
            "--join-url",
            "https://osk.local/join?token=test",
            "--device-id",
            "chromebook-lab",
            "--dry-run",
        ]
    )

    assert args.hub_url == "https://127.0.0.1:8443"
    assert args.join_url == "https://osk.local/join?token=test"
    assert args.device_id == "chromebook-lab"
    assert args.ssh_target == "chromebook-lab"
    assert args.debug_port == 9222
    assert args.scenario == "baseline"
    assert args.dry_run is True


def test_parse_args_rejects_non_absolute_hub_url() -> None:
    validation = _load_module()

    with pytest.raises(ValueError, match="hub_url"):
        validation.parse_args(
            [
                "--hub-url",
                "/relative",
                "--join-url",
                "https://osk.local/join?token=test",
                "--device-id",
                "chromebook-lab",
            ]
        )


def test_make_artifact_dir_uses_timestamped_run_directory(tmp_path: Path) -> None:
    validation = _load_module()

    artifact_dir = validation.make_artifact_dir(
        tmp_path,
        now=datetime(2026, 3, 23, 19, 4, 5, tzinfo=timezone.utc),
    )

    assert artifact_dir == tmp_path / "20260323T190405Z"


def test_dry_run_writes_real_hub_contract_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    validation = _load_module()
    _set_provenance_env(monkeypatch)
    artifact_root = tmp_path / "artifacts"

    monkeypatch.setattr(
        validation,
        "_collect_local_snapshots",
        lambda repo_root, artifact_dir: {
            "captures": {
                "doctor_snapshot_path": None,
                "members_snapshot_path": None,
                "status_snapshot_path": None,
            },
            "local_snapshots": {
                "doctor": {"available": False, "path": None},
                "members": {"available": False, "path": None},
                "status": {"available": False, "path": None},
            },
        },
    )

    code = validation.main(
        [
            "--hub-url",
            "https://127.0.0.1:8443",
            "--join-url",
            "https://osk.local/join?token=test",
            "--device-id",
            "chromebook-lab",
            "--artifact-root",
            str(artifact_root),
            "--dry-run",
            "--timestamp",
            "20260323T190405Z",
        ]
    )

    result_path = artifact_root / "20260323T190405Z" / "result.json"
    preflight_path = artifact_root / "20260323T190405Z" / "hub-preflight.json"
    payload = json.loads(result_path.read_text())
    preflight = json.loads(preflight_path.read_text())

    assert code == 0
    assert payload["status"] == "dry_run"
    assert payload["execution_mode"] == "contract_only"
    assert payload["scenario"] == "baseline"
    assert payload["hub_url"] == "https://127.0.0.1:8443"
    assert payload["join_url"] == "https://osk.local/join?token=test"
    assert payload["device_id"] == "chromebook-lab"
    assert payload["failure"] is None
    assert payload["captures"] == {
        "audit_slice_path": None,
        "cdp_version_path": None,
        "closure_summary_path": None,
        "doctor_snapshot_path": None,
        "hub_preflight_path": str(preflight_path),
        "members_snapshot_path": None,
        "member_shell_smoke_latest_path": None,
        "member_shell_smoke_result_path": None,
        "operator_session_bootstrap_path": None,
        "status_snapshot_path": None,
        "wipe_readiness_path": None,
    }
    assert [step["id"] for step in payload["steps"]] == [
        "hub_reachable",
        "join_loads",
        "member_session_establishes",
        "disconnect_reconnect_observed",
        "wipe_observed",
        "operator_closure_captured",
    ]
    assert all(step["status"] == "contract_only" for step in payload["steps"])
    assert payload["result_path"] == str(result_path)
    assert preflight["hub_url"] == "https://127.0.0.1:8443"
    assert preflight["join_url"] == "https://osk.local/join?token=test"
    assert preflight["device_id"] == "chromebook-lab"
    assert preflight["scenario"] == "baseline"
    assert preflight["local_snapshots"] == {
        "doctor": {"available": False, "path": None},
        "members": {"available": False, "path": None},
        "status": {"available": False, "path": None},
    }
    assert payload["provenance"] == {
        "artifact_version": 1,
        "completed_at_utc": payload["provenance"]["completed_at_utc"],
        "device_id": "chromebook-lab",
        "git_branch": "justinredmondsmith-collab/docs/plan-8-real-hub-validation",
        "git_commit_subject": "docs(plan): Add real-hub validation plan",
        "git_sha": "feedfacefeedfacefeedfacefeedfacefeedface",
        "invocation": "real_hub_validation.py",
        "run_label": "20260323T190405Z",
        "runner_hostname": "validation-host",
        "started_at_utc": "2026-03-23T19:04:05+00:00",
        "trigger": "manual",
        "worktree_dirty": False,
    }


def test_non_dry_run_executes_real_hub_browser_flow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    validation = _load_module()
    _set_provenance_env(monkeypatch)
    artifact_root = tmp_path / "artifacts"

    monkeypatch.setattr(
        validation,
        "_collect_local_snapshots",
        lambda repo_root, artifact_dir: {
            "captures": {
                "doctor_snapshot_path": None,
                "members_snapshot_path": None,
                "status_snapshot_path": None,
            },
            "local_snapshots": {
                "doctor": {"available": False, "path": None},
                "members": {"available": False, "path": None},
                "status": {"available": False, "path": None},
            },
        },
    )

    @contextmanager
    def fake_tunnel(*_args, **_kwargs):
        yield

    def fake_run_live_flow(*, local_port: int, args, artifact_dir: Path) -> dict[str, object]:
        console_path = artifact_dir / "console-events.json"
        network_path = artifact_dir / "network-failures.json"
        page_errors_path = artifact_dir / "page-errors.json"
        console_path.write_text("[]\n")
        network_path.write_text("[]\n")
        page_errors_path.write_text("[]\n")
        return {
            "steps": [
                {
                    "id": "hub_reachable",
                    "label": "Hub reachable",
                    "status": "passed",
                    "automated": True,
                    "detail": {"url": args.hub_url, "local_port": local_port},
                },
                {
                    "id": "join_loads",
                    "label": "Join URL loads",
                    "status": "passed",
                    "automated": True,
                },
                {
                    "id": "member_session_establishes",
                    "label": "Member session establishes",
                    "status": "passed",
                    "automated": True,
                    "detail": {"member_id": "member-123"},
                },
                {
                    "id": "disconnect_reconnect_observed",
                    "label": "Disconnect and reconnect behavior observed",
                    "status": "passed",
                    "automated": True,
                },
                {
                    "id": "wipe_observed",
                    "label": "Live wipe observed",
                    "status": "manual_follow_up",
                    "automated": False,
                },
                {
                    "id": "operator_closure_captured",
                    "label": "Operator-side readiness and audit closure captured",
                    "status": "manual_follow_up",
                    "automated": False,
                },
            ],
            "summary": {
                "message": "Real hub join/member runtime path completed.",
                "member_id": "member-123",
                "display_name": "Chromebook Validation",
            },
            "diagnostic_paths": {
                "console_events_path": str(console_path),
                "network_failures_path": str(network_path),
                "page_errors_path": str(page_errors_path),
            },
        }

    monkeypatch.setattr(validation, "choose_local_port", lambda: 9333)
    monkeypatch.setattr(validation, "managed_ssh_tunnel", fake_tunnel)
    monkeypatch.setattr(
        validation,
        "fetch_cdp_version",
        lambda *_args, **_kwargs: {
            "Browser": "Chrome/146",
            "webSocketDebuggerUrl": "ws://127.0.0.1:9333/devtools/browser/test",
        },
    )
    monkeypatch.setattr(validation, "run_live_flow", fake_run_live_flow)
    monkeypatch.setattr(
        validation,
        "_capture_live_wipe_evidence",
        lambda **_kwargs: {
            "captures": {
                "member_shell_smoke_latest_path": str(
                    artifact_root / "member-shell-smoke" / "latest.json"
                ),
                "member_shell_smoke_result_path": str(
                    artifact_root / "member-shell-smoke" / "20260323T180000Z" / "result.json"
                ),
            },
            "step_update": {
                "id": "wipe_observed",
                "status": "passed",
                "automated": True,
                "detail": {
                    "evidence_source": "member_shell_smoke_latest",
                    "member_shell_smoke_run_label": "20260323T180000Z",
                },
            },
            "summary": {
                "wipe_observed_status": "captured_from_member_shell_smoke",
                "wipe_evidence_source": "member_shell_smoke_latest",
                "wipe_evidence_run_label": "20260323T180000Z",
            },
        },
    )

    def fake_capture_operator_closure(*, args, artifact_dir: Path) -> dict[str, object]:
        closure_summary_path = artifact_dir / "closure-summary.json"
        wipe_readiness_path = artifact_dir / "wipe-readiness.json"
        audit_slice_path = artifact_dir / "audit-slice.json"
        closure_summary_path.write_text(
            '{"closure_state":"captured_open_follow_up","unresolved_follow_up_count":1}\n'
        )
        wipe_readiness_path.write_text('{"status":"blocked","follow_up_required":true}\n')
        audit_slice_path.write_text('{"events":[{"action":"wipe_follow_up_verified"}]}\n')
        return {
            "captures": {
                "closure_summary_path": str(closure_summary_path),
                "operator_session_bootstrap_path": str(
                    artifact_dir / "operator-session-bootstrap.json"
                ),
                "wipe_readiness_path": str(wipe_readiness_path),
                "audit_slice_path": str(audit_slice_path),
            },
            "step_update": {
                "id": "operator_closure_captured",
                "status": "passed",
                "automated": True,
                "detail": {
                    "closure_state": "captured_open_follow_up",
                    "wipe_readiness_status": "blocked",
                    "audit_event_count": 1,
                },
            },
            "summary": {
                "operator_closure_status": "captured",
                "operator_closure_state": "captured_open_follow_up",
                "wipe_readiness_status": "blocked",
                "audit_event_count": 1,
            },
        }

    monkeypatch.setattr(validation, "_capture_operator_closure", fake_capture_operator_closure)

    code = validation.main(
        [
            "--hub-url",
            "https://127.0.0.1:8443",
            "--join-url",
            "https://osk.local/join?token=test",
            "--device-id",
            "chromebook-lab",
            "--ssh-target",
            "chromebook-user@192.0.2.25",
            "--artifact-root",
            str(artifact_root),
            "--timestamp",
            "20260323T190405Z",
        ]
    )
    result_path = artifact_root / "20260323T190405Z" / "result.json"
    preflight_path = artifact_root / "20260323T190405Z" / "hub-preflight.json"
    cdp_version_path = artifact_root / "20260323T190405Z" / "cdp-version.json"
    closure_summary_path = artifact_root / "20260323T190405Z" / "closure-summary.json"
    wipe_readiness_path = artifact_root / "20260323T190405Z" / "wipe-readiness.json"
    audit_slice_path = artifact_root / "20260323T190405Z" / "audit-slice.json"
    payload = json.loads(result_path.read_text())
    preflight = json.loads(preflight_path.read_text())
    cdp_version = json.loads(cdp_version_path.read_text())

    assert code == 0
    assert payload["status"] == "passed"
    assert payload["execution_mode"] == "chromebook_cdp"
    assert payload["ssh_target"] == "chromebook-user@192.0.2.25"
    assert payload["debug_port"] == 9222
    assert payload["local_debug_port"] == 9333
    assert payload["cdp_version"]["Browser"] == "Chrome/146"
    assert payload["captures"]["hub_preflight_path"] == str(preflight_path)
    assert payload["captures"]["cdp_version_path"] == str(cdp_version_path)
    assert payload["captures"]["closure_summary_path"] == str(closure_summary_path)
    assert payload["captures"]["operator_session_bootstrap_path"] == str(
        artifact_root / "20260323T190405Z" / "operator-session-bootstrap.json"
    )
    assert payload["captures"]["wipe_readiness_path"] == str(wipe_readiness_path)
    assert payload["captures"]["audit_slice_path"] == str(audit_slice_path)
    assert payload["captures"]["member_shell_smoke_latest_path"] == str(
        artifact_root / "member-shell-smoke" / "latest.json"
    )
    assert payload["captures"]["member_shell_smoke_result_path"] == str(
        artifact_root / "member-shell-smoke" / "20260323T180000Z" / "result.json"
    )
    assert len(payload["steps"]) == 6
    assert [step["status"] for step in payload["steps"]] == [
        "passed",
        "passed",
        "passed",
        "passed",
        "passed",
        "passed",
    ]
    assert payload["summary"]["member_id"] == "member-123"
    assert payload["summary"]["wipe_observed_status"] == "captured_from_member_shell_smoke"
    assert payload["summary"]["operator_closure_status"] == "captured"
    assert payload["summary"]["operator_closure_state"] == "captured_open_follow_up"
    assert payload["failure"] is None
    assert preflight["local_snapshots"]["doctor"]["available"] is False
    assert preflight["local_snapshots"]["members"]["available"] is False
    assert preflight["local_snapshots"]["status"]["available"] is False
    assert cdp_version["webSocketDebuggerUrl"] == "ws://127.0.0.1:9333/devtools/browser/test"


def test_non_dry_run_records_partial_operator_closure_when_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    validation = _load_module()
    _set_provenance_env(monkeypatch)
    artifact_root = tmp_path / "artifacts"

    monkeypatch.setattr(
        validation,
        "_collect_local_snapshots",
        lambda repo_root, artifact_dir: {
            "captures": {
                "doctor_snapshot_path": None,
                "members_snapshot_path": None,
                "status_snapshot_path": None,
            },
            "local_snapshots": {
                "doctor": {"available": False, "path": None},
                "members": {"available": False, "path": None},
                "status": {"available": False, "path": None},
            },
        },
    )

    @contextmanager
    def fake_tunnel(*_args, **_kwargs):
        yield

    monkeypatch.setattr(validation, "choose_local_port", lambda: 9333)
    monkeypatch.setattr(validation, "managed_ssh_tunnel", fake_tunnel)
    monkeypatch.setattr(
        validation,
        "fetch_cdp_version",
        lambda *_args, **_kwargs: {
            "Browser": "Chrome/146",
            "webSocketDebuggerUrl": "ws://127.0.0.1:9333/devtools/browser/test",
        },
    )
    monkeypatch.setattr(
        validation,
        "run_live_flow",
        lambda **_kwargs: {
            "steps": [
                {
                    "id": "hub_reachable",
                    "status": "passed",
                    "automated": True,
                },
                {
                    "id": "join_loads",
                    "status": "passed",
                    "automated": True,
                },
                {
                    "id": "member_session_establishes",
                    "status": "passed",
                    "automated": True,
                },
                {
                    "id": "disconnect_reconnect_observed",
                    "status": "passed",
                    "automated": True,
                },
                {
                    "id": "wipe_observed",
                    "status": "manual_follow_up",
                    "automated": False,
                },
                {
                    "id": "operator_closure_captured",
                    "status": "manual_follow_up",
                    "automated": False,
                },
            ],
            "summary": {
                "message": "Real hub join/member runtime path completed.",
            },
            "diagnostic_paths": {},
        },
    )
    monkeypatch.setattr(
        validation,
        "_capture_live_wipe_evidence",
        lambda **_kwargs: {
            "captures": {
                "member_shell_smoke_latest_path": None,
                "member_shell_smoke_result_path": None,
            },
            "step_update": {
                "id": "wipe_observed",
                "status": "manual_follow_up",
                "automated": False,
                "detail": {
                    "message": "No member-shell smoke artifact was available for wipe evidence.",
                    "evidence_source": "member_shell_smoke_latest",
                },
            },
            "summary": {
                "wipe_observed_status": "manual_follow_up",
                "wipe_evidence_source": "member_shell_smoke_latest",
            },
        },
    )
    monkeypatch.setattr(
        validation,
        "_capture_operator_closure",
        lambda **_kwargs: {
            "captures": {
                "closure_summary_path": str(
                    artifact_root / "20260323T190405Z" / "closure-summary.json"
                ),
                "operator_session_bootstrap_path": None,
                "wipe_readiness_path": None,
                "audit_slice_path": None,
            },
            "step_update": {
                "id": "operator_closure_captured",
                "status": "manual_follow_up",
                "automated": False,
                "detail": {
                    "message": "Local operator credentials unavailable.",
                    "closure_state": "unavailable",
                },
            },
            "summary": {
                "operator_closure_status": "unavailable",
                "operator_closure_state": "unavailable",
            },
        },
    )

    code = validation.main(
        [
            "--hub-url",
            "https://127.0.0.1:8443",
            "--join-url",
            "https://osk.local/join?token=test",
            "--device-id",
            "chromebook-lab",
            "--artifact-root",
            str(artifact_root),
            "--timestamp",
            "20260323T190405Z",
        ]
    )

    payload = json.loads((artifact_root / "20260323T190405Z" / "result.json").read_text())

    assert code == 0
    assert payload["status"] == "passed"
    assert payload["captures"]["closure_summary_path"] == str(
        artifact_root / "20260323T190405Z" / "closure-summary.json"
    )
    assert payload["captures"]["operator_session_bootstrap_path"] is None
    assert payload["captures"]["wipe_readiness_path"] is None
    assert payload["captures"]["audit_slice_path"] is None
    assert payload["captures"]["member_shell_smoke_latest_path"] is None
    assert payload["captures"]["member_shell_smoke_result_path"] is None
    assert payload["steps"][-1]["id"] == "operator_closure_captured"
    assert payload["steps"][-1]["status"] == "manual_follow_up"
    assert payload["summary"]["wipe_observed_status"] == "manual_follow_up"
    assert payload["summary"]["operator_closure_status"] == "unavailable"
    assert payload["summary"]["operator_closure_state"] == "unavailable"


def test_capture_operator_closure_writes_open_follow_up_summary_and_detail_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    validation = _load_module()

    member_id = "11111111-1111-1111-1111-111111111111"
    detail_path = tmp_path / f"wipe-follow-up-{member_id}.json"
    bootstrap_path = tmp_path / "operator-session-bootstrap.json"

    monkeypatch.setattr(
        validation,
        "_resolve_local_admin_access",
        lambda **_kwargs: {
            "headers": {"X-Test-Auth": "ok"},
            "credential_source": "bootstrap_operator_session",
            "bootstrap_status": "created",
            "bootstrap_message": None,
            "bootstrap_capture_path": str(bootstrap_path),
            "bootstrap_response": {
                "issued_from": "bootstrap",
                "operator_session_active": True,
            },
        },
    )
    monkeypatch.setattr(validation, "_httpx_verify_for_url", lambda _url: True)

    class FakeResponse:
        def __init__(self, payload: object):
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> object:
            return self._payload

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.calls: list[tuple[str, object | None]] = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url: str, params: object | None = None):
            self.calls.append((url, params))
            if url.endswith("/api/coordinator/dashboard-state"):
                return FakeResponse(
                    {
                        "wipe_readiness": {
                            "status": "blocked",
                            "unresolved_follow_up_count": 1,
                            "follow_up_required": True,
                            "active_unresolved_follow_up_count": 0,
                            "historical_drift_follow_up_count": 1,
                            "reviewed_historical_drift_follow_up_count": 1,
                            "unreviewed_historical_drift_follow_up_count": 0,
                            "verified_current_follow_up_count": 0,
                            "follow_up_summary": (
                                "Resolve 1 unresolved member wipe follow-up item before closing "
                                "the cleanup boundary. 1 item may be historical drift. "
                                "1 historical-drift review recorded."
                            ),
                            "follow_up_history_count": 1,
                            "follow_up_history_summary": (
                                "Recent follow-up trail: 1 reviewed."
                            ),
                            "follow_up": [
                                {
                                    "id": member_id,
                                    "name": "Observer One",
                                    "reason": "disconnected",
                                    "classification": "historical_drift",
                                    "historical_reviewed": True,
                                    "historical_reviewed_at": "2026-03-23T08:15:00Z",
                                    "resolution": "unresolved",
                                }
                            ],
                        }
                    }
                )
            if url.endswith("/api/audit"):
                return FakeResponse([{"action": "wipe_follow_up_verified"}])
            if url.endswith(f"/api/coordinator/wipe-follow-up/{member_id}"):
                return FakeResponse(
                    {
                        "member_id": member_id,
                        "member_name": "Observer One",
                        "summary": "Member follow-up still open.",
                        "follow_up": {
                            "id": member_id,
                            "resolution": "unresolved",
                        },
                        "history": [],
                    }
                )
            raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(validation.httpx, "Client", FakeClient)

    result = validation._capture_operator_closure(
        args=SimpleNamespace(hub_url="https://10.0.0.60:8444", timeout_seconds=20.0),
        artifact_dir=tmp_path,
    )

    closure_summary_path = tmp_path / "closure-summary.json"
    wipe_readiness_path = tmp_path / "wipe-readiness.json"
    audit_slice_path = tmp_path / "audit-slice.json"
    payload = json.loads(closure_summary_path.read_text())
    detail = json.loads(detail_path.read_text())

    assert result["captures"]["closure_summary_path"] == str(closure_summary_path)
    assert result["captures"]["operator_session_bootstrap_path"] == str(bootstrap_path)
    assert result["captures"]["wipe_readiness_path"] == str(wipe_readiness_path)
    assert result["captures"]["audit_slice_path"] == str(audit_slice_path)
    assert payload["closure_state"] == "captured_open_follow_up"
    assert payload["credential_source"] == "bootstrap_operator_session"
    assert payload["operator_bootstrap_status"] == "created"
    assert payload["operator_session_bootstrap_path"] == str(bootstrap_path)
    assert payload["unresolved_follow_up_count"] == 1
    assert payload["active_unresolved_follow_up_count"] == 0
    assert payload["historical_drift_follow_up_count"] == 1
    assert payload["reviewed_historical_drift_follow_up_count"] == 1
    assert payload["unreviewed_historical_drift_follow_up_count"] == 0
    assert payload["follow_up_summary"].startswith("Resolve 1 unresolved")
    assert payload["follow_up_history_count"] == 1
    assert payload["follow_up_history_summary"] == "Recent follow-up trail: 1 reviewed."
    assert payload["follow_up_detail_paths"] == {member_id: str(detail_path)}
    assert result["summary"]["operator_closure_state"] == "captured_open_follow_up"
    assert result["summary"]["operator_bootstrap_status"] == "created"
    assert result["step_update"]["detail"]["closure_state"] == "captured_open_follow_up"
    assert result["step_update"]["detail"]["operator_bootstrap_status"] == "created"
    assert detail["member_id"] == member_id
    assert detail["follow_up"]["resolution"] == "unresolved"


def test_capture_operator_closure_writes_detail_artifacts_for_recent_history_members(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    validation = _load_module()

    history_member_id = "22222222-2222-2222-2222-222222222222"
    history_detail_path = tmp_path / f"wipe-follow-up-{history_member_id}.json"

    monkeypatch.setattr(
        validation,
        "_resolve_local_admin_access",
        lambda **_kwargs: {
            "headers": {"X-Test-Auth": "ok"},
            "credential_source": "test_credentials",
            "bootstrap_status": None,
            "bootstrap_message": None,
            "bootstrap_capture_path": None,
            "bootstrap_response": None,
        },
    )
    monkeypatch.setattr(validation, "_httpx_verify_for_url", lambda _url: True)

    class FakeResponse:
        def __init__(self, payload: object):
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> object:
            return self._payload

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.calls: list[tuple[str, object | None]] = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url: str, params: object | None = None):
            self.calls.append((url, params))
            if url.endswith("/api/coordinator/dashboard-state"):
                return FakeResponse(
                    {
                        "wipe_readiness": {
                            "status": "ready",
                            "unresolved_follow_up_count": 0,
                            "follow_up_required": False,
                            "active_unresolved_follow_up_count": 0,
                            "historical_drift_follow_up_count": 0,
                            "reviewed_historical_drift_follow_up_count": 0,
                            "unreviewed_historical_drift_follow_up_count": 0,
                            "verified_current_follow_up_count": 0,
                            "follow_up_summary": "No unresolved member wipe follow-up remains.",
                            "follow_up_history_count": 1,
                            "follow_up_history_summary": "Recent follow-up trail: 1 cleared.",
                            "follow_up": [],
                            "follow_up_history": [
                                {
                                    "member_id": history_member_id,
                                    "member_name": "Observer Trail",
                                    "action": "wipe_follow_up_verified",
                                    "status": "cleared",
                                    "verified_at": "2026-03-23T08:00:00Z",
                                }
                            ],
                        }
                    }
                )
            if url.endswith("/api/audit"):
                return FakeResponse([{"action": "wipe_follow_up_verified"}])
            if url.endswith(f"/api/coordinator/wipe-follow-up/{history_member_id}"):
                return FakeResponse(
                    {
                        "member_id": history_member_id,
                        "member_name": "Observer Trail",
                        "summary": "Verification remains historical context only.",
                        "follow_up": None,
                        "history": [
                            {
                                "member_id": history_member_id,
                                "action": "wipe_follow_up_verified",
                                "status": "cleared",
                            }
                        ],
                    }
                )
            raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(validation.httpx, "Client", FakeClient)

    result = validation._capture_operator_closure(
        args=SimpleNamespace(hub_url="https://10.0.0.60:8444", timeout_seconds=20.0),
        artifact_dir=tmp_path,
    )

    closure_summary_path = tmp_path / "closure-summary.json"
    payload = json.loads(closure_summary_path.read_text())
    detail = json.loads(history_detail_path.read_text())

    assert result["summary"]["operator_closure_state"] == "captured_clear"
    assert payload["closure_state"] == "captured_clear"
    assert payload["follow_up_history_count"] == 1
    assert payload["follow_up_history_summary"] == "Recent follow-up trail: 1 cleared."
    assert payload["follow_up_detail_paths"] == {history_member_id: str(history_detail_path)}
    assert detail["member_id"] == history_member_id
    assert detail["follow_up"] is None
    assert detail["history"][0]["status"] == "cleared"


def test_capture_operator_closure_writes_unavailable_summary_when_credentials_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    validation = _load_module()

    bootstrap_path = tmp_path / "operator-session-bootstrap.json"
    monkeypatch.setattr(
        validation,
        "_resolve_local_admin_access",
        lambda **_kwargs: {
            "headers": None,
            "credential_source": None,
            "bootstrap_status": "failed",
            "bootstrap_message": "No active operator bootstrap is available for this hub instance.",
            "bootstrap_capture_path": str(bootstrap_path),
            "bootstrap_response": None,
        },
    )

    result = validation._capture_operator_closure(
        args=SimpleNamespace(hub_url="https://10.0.0.60:8444", timeout_seconds=20.0),
        artifact_dir=tmp_path,
    )

    closure_summary_path = tmp_path / "closure-summary.json"
    payload = json.loads(closure_summary_path.read_text())

    assert result["captures"]["closure_summary_path"] == str(closure_summary_path)
    assert result["captures"]["operator_session_bootstrap_path"] == str(bootstrap_path)
    assert result["captures"]["wipe_readiness_path"] is None
    assert result["captures"]["audit_slice_path"] is None
    assert payload["closure_state"] == "unavailable"
    assert payload["credential_source"] is None
    assert payload["operator_bootstrap_status"] == "failed"
    assert payload["operator_bootstrap_message"] == (
        "No active operator bootstrap is available for this hub instance."
    )
    assert payload["operator_session_bootstrap_path"] == str(bootstrap_path)
    assert payload["follow_up_detail_paths"] == {}
    assert result["summary"]["operator_closure_state"] == "unavailable"
    assert result["summary"]["operator_bootstrap_status"] == "failed"
    assert result["step_update"]["detail"]["closure_state"] == "unavailable"
    assert result["step_update"]["detail"]["operator_bootstrap_status"] == "failed"


def test_resolve_local_admin_access_bootstraps_operator_session_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    validation = _load_module()
    repo_root = tmp_path / "repo"
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()

    state = {"headers_ready": False}

    def fake_local_admin_headers():
        if state["headers_ready"]:
            return {"X-Osk-Operator-Session": "token-123"}, "local_operator_session"
        return None, None

    def fake_bootstrap(*, repo_root: Path, artifact_dir: Path) -> dict[str, object]:
        state["headers_ready"] = True
        return {
            "ok": True,
            "status": "created",
            "message": None,
            "capture_path": str(artifact_dir / "operator-session-bootstrap.json"),
            "response": {"issued_from": "bootstrap"},
        }

    monkeypatch.setattr(validation, "_local_admin_headers", fake_local_admin_headers)
    monkeypatch.setattr(validation, "_bootstrap_local_operator_session", fake_bootstrap)

    result = validation._resolve_local_admin_access(repo_root=repo_root, artifact_dir=artifact_dir)

    assert result["headers"] == {"X-Osk-Operator-Session": "token-123"}
    assert result["credential_source"] == "bootstrap_operator_session"
    assert result["bootstrap_status"] == "created"
    assert result["bootstrap_capture_path"] == str(
        artifact_dir / "operator-session-bootstrap.json"
    )


def test_bootstrap_local_operator_session_writes_attempt_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    validation = _load_module()

    monkeypatch.setattr(
        validation,
        "_run_osk_cli",
        lambda repo_root, cli_args, timeout_seconds=None: SimpleNamespace(
            args=[str(repo_root), *cli_args],
            returncode=0,
            stdout=json.dumps(
                {
                    "bootstrap_consumed": True,
                    "issued_from": "bootstrap",
                    "operator_session_active": True,
                }
            ),
            stderr="",
        ),
    )

    result = validation._bootstrap_local_operator_session(
        repo_root=tmp_path / "repo",
        artifact_dir=tmp_path,
    )

    payload = json.loads((tmp_path / "operator-session-bootstrap.json").read_text())

    assert result["ok"] is True
    assert result["status"] == "created"
    assert result["capture_path"] == str(tmp_path / "operator-session-bootstrap.json")
    assert payload["returncode"] == 0
    assert payload["response"]["issued_from"] == "bootstrap"


def test_capture_live_wipe_evidence_uses_latest_member_shell_smoke_for_same_device(
    tmp_path: Path,
) -> None:
    validation = _load_module()
    repo_root = tmp_path / "repo"
    artifact_root = repo_root / "output" / "chromebook" / "member-shell-smoke"
    run_dir = artifact_root / "20260323T180000Z"
    run_dir.mkdir(parents=True)

    result_path = run_dir / "result.json"
    result_path.write_text(
        json.dumps(
            {
                "status": "passed",
                "chromebook_host": "chromebook-lab",
                "result_path": str(result_path),
                "steps": [
                    {
                        "name": "wipe-clear",
                        "status": "passed",
                        "screenshot": "06-wipe-clear.png",
                        "detail": {"wipe_status_code": 200},
                    }
                ],
                "provenance": {"run_label": "20260323T180000Z"},
            }
        )
        + "\n"
    )
    (artifact_root / "latest.json").write_text(
        json.dumps(
            {
                "status": "passed",
                "chromebook_host": "chromebook-lab",
                "result_path": str(result_path),
                "provenance": {"run_label": "20260323T180000Z"},
            }
        )
        + "\n"
    )

    result = validation._capture_live_wipe_evidence(
        args=SimpleNamespace(
            device_id="chromebook-lab",
            member_shell_artifact_root="output/chromebook/member-shell-smoke",
        ),
        repo_root=repo_root,
    )

    assert result["captures"]["member_shell_smoke_latest_path"] == str(
        artifact_root / "latest.json"
    )
    assert result["captures"]["member_shell_smoke_result_path"] == str(result_path)
    assert result["step_update"]["id"] == "wipe_observed"
    assert result["step_update"]["status"] == "passed"
    assert result["step_update"]["automated"] is True
    assert result["step_update"]["detail"]["member_shell_smoke_run_label"] == "20260323T180000Z"
    assert result["step_update"]["detail"]["wipe_status_code"] == 200
    assert result["summary"]["wipe_observed_status"] == "captured_from_member_shell_smoke"
    assert result["summary"]["wipe_evidence_run_label"] == "20260323T180000Z"


def test_capture_live_wipe_evidence_falls_back_when_smoke_run_does_not_qualify(
    tmp_path: Path,
) -> None:
    validation = _load_module()
    repo_root = tmp_path / "repo"
    artifact_root = repo_root / "output" / "chromebook" / "member-shell-smoke"
    run_dir = artifact_root / "20260323T180000Z"
    run_dir.mkdir(parents=True)

    result_path = run_dir / "result.json"
    result_path.write_text(
        json.dumps(
            {
                "status": "passed",
                "chromebook_host": "other-device",
                "result_path": str(result_path),
                "steps": [{"name": "wipe-clear", "status": "passed"}],
                "provenance": {"run_label": "20260323T180000Z"},
            }
        )
        + "\n"
    )
    (artifact_root / "latest.json").write_text(
        json.dumps(
            {
                "status": "passed",
                "chromebook_host": "other-device",
                "result_path": str(result_path),
                "provenance": {"run_label": "20260323T180000Z"},
            }
        )
        + "\n"
    )

    result = validation._capture_live_wipe_evidence(
        args=SimpleNamespace(
            device_id="chromebook-lab",
            member_shell_artifact_root="output/chromebook/member-shell-smoke",
        ),
        repo_root=repo_root,
    )

    assert result["captures"]["member_shell_smoke_latest_path"] is None
    assert result["captures"]["member_shell_smoke_result_path"] is None
    assert result["step_update"]["id"] == "wipe_observed"
    assert result["step_update"]["status"] == "manual_follow_up"
    assert result["step_update"]["automated"] is False
    assert result["summary"]["wipe_observed_status"] == "manual_follow_up"


def test_restart_scenario_records_resume_step_and_hardening_tasks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    validation = _load_module()
    _set_provenance_env(monkeypatch)
    artifact_root = tmp_path / "artifacts"
    tunnel_state = {"active": False}

    monkeypatch.setattr(
        validation,
        "_collect_local_snapshots",
        lambda repo_root, artifact_dir: {
            "captures": {
                "doctor_snapshot_path": None,
                "members_snapshot_path": None,
                "status_snapshot_path": None,
            },
            "local_snapshots": {
                "doctor": {"available": False, "path": None},
                "members": {"available": False, "path": None},
                "status": {"available": False, "path": None},
            },
        },
    )

    @contextmanager
    def fake_tunnel(*_args, **_kwargs):
        tunnel_state["active"] = True
        try:
            yield
        finally:
            tunnel_state["active"] = False

    monkeypatch.setattr(validation, "choose_local_port", lambda: 9333)
    monkeypatch.setattr(validation, "managed_ssh_tunnel", fake_tunnel)
    monkeypatch.setattr(
        validation,
        "fetch_cdp_version",
        lambda *_args, **_kwargs: {
            "Browser": "Chrome/146",
            "webSocketDebuggerUrl": "ws://127.0.0.1:9333/devtools/browser/test",
        },
    )
    monkeypatch.setattr(
        validation,
        "run_live_flow",
        lambda **_kwargs: {
            "steps": [
                {"id": "hub_reachable", "status": "passed", "automated": True},
                {"id": "join_loads", "status": "passed", "automated": True},
                {"id": "member_session_establishes", "status": "passed", "automated": True},
                {
                    "id": "disconnect_reconnect_observed",
                    "status": "passed",
                    "automated": True,
                },
                {"id": "wipe_observed", "status": "manual_follow_up", "automated": False},
                {
                    "id": "operator_closure_captured",
                    "status": "manual_follow_up",
                    "automated": False,
                },
            ],
            "summary": {"message": "baseline complete"},
            "diagnostic_paths": {},
        },
    )
    monkeypatch.setattr(
        validation,
        "_capture_operator_closure",
        lambda **_kwargs: {
            "captures": {
                "closure_summary_path": str(
                    artifact_root / "20260323T190405Z" / "closure-summary.json"
                ),
                "operator_session_bootstrap_path": None,
                "wipe_readiness_path": None,
                "audit_slice_path": None,
            },
            "step_update": {
                "id": "operator_closure_captured",
                "status": "manual_follow_up",
                "automated": False,
                "detail": {
                    "message": "Local operator credentials unavailable.",
                    "closure_state": "unavailable",
                },
            },
            "summary": {
                "operator_closure_status": "unavailable",
                "operator_closure_state": "unavailable",
            },
        },
    )
    monkeypatch.setattr(
        validation,
        "_capture_live_wipe_evidence",
        lambda **_kwargs: {
            "captures": {
                "member_shell_smoke_latest_path": None,
                "member_shell_smoke_result_path": None,
            },
            "step_update": {
                "id": "wipe_observed",
                "status": "manual_follow_up",
                "automated": False,
                "detail": {
                    "message": "No member-shell smoke artifact was available for wipe evidence.",
                    "evidence_source": "member_shell_smoke_latest",
                },
            },
            "summary": {
                "wipe_observed_status": "manual_follow_up",
                "wipe_evidence_source": "member_shell_smoke_latest",
            },
        },
    )
    def fake_restart_resume_check(**_kwargs):
        assert tunnel_state["active"] is True
        return {
            "step_update": {
                "id": "hub_restart_resume_observed",
                "status": "failed_hardening_task",
                "automated": True,
                "detail": {
                    "message": "Outbox did not drain after hub restart.",
                    "hardening_task": "Investigate replay across hub restart.",
                },
            },
            "summary": {
                "hardening_tasks": [
                    "Investigate replay across hub restart.",
                ],
                "restart_resume_status": "failed_hardening_task",
            },
        }

    monkeypatch.setattr(validation, "_run_restart_resume_check", fake_restart_resume_check)

    code = validation.main(
        [
            "--hub-url",
            "https://127.0.0.1:8443",
            "--join-url",
            "https://osk.local/join?token=test",
            "--device-id",
            "chromebook-lab",
            "--artifact-root",
            str(artifact_root),
            "--scenario",
            "restart",
            "--timestamp",
            "20260323T190405Z",
        ]
    )

    payload = json.loads((artifact_root / "20260323T190405Z" / "result.json").read_text())

    assert code == 0
    assert payload["status"] == "failed_hardening_task"
    assert payload["scenario"] == "restart"
    assert [step["id"] for step in payload["steps"]] == [
        "hub_reachable",
        "join_loads",
        "member_session_establishes",
        "disconnect_reconnect_observed",
        "wipe_observed",
        "operator_closure_captured",
        "hub_restart_resume_observed",
    ]
    assert payload["steps"][-1]["status"] == "failed_hardening_task"
    assert payload["summary"]["restart_resume_status"] == "failed_hardening_task"
    assert payload["summary"]["hardening_tasks"] == [
        "Investigate replay across hub restart.",
    ]


def test_restart_resume_check_records_hardening_task_when_session_clears(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    validation = _load_module()

    monkeypatch.setattr(
        validation,
        "_perform_restart_cycle",
        lambda **_kwargs: {
            "status": "restarted",
            "detail": {
                "operation_name": "Field Test",
                "hub_status": "running",
            },
        },
    )
    monkeypatch.setattr(
        validation,
        "_probe_restart_resume_over_cdp",
        lambda **_kwargs: {
            "status": "failed_hardening_task",
            "detail": {
                "message": "Member browser session was cleared when the hub stopped.",
                "hardening_task": (
                    "Preserve member runtime sessions across coordinator restarts so "
                    "queued replay can resume without rescanning the QR code."
                ),
            },
        },
    )

    result = validation._run_restart_resume_check(
        args=SimpleNamespace(
            scenario="restart",
            timeout_seconds=20.0,
            debug_port=9222,
            hub_url="https://127.0.0.1:8443",
            join_url="https://osk.local/join?token=test",
            device_id="chromebook-lab",
        ),
        artifact_dir=tmp_path,
        local_debug_port=9333,
        cdp_version={"Browser": "Chrome/146"},
        live_result={
            "summary": {
                "member_id": "member-123",
                "operation_name": "Field Test",
            }
        },
    )

    assert result["step_update"]["id"] == "hub_restart_resume_observed"
    assert result["step_update"]["status"] == "failed_hardening_task"
    assert result["summary"]["restart_resume_status"] == "failed_hardening_task"
    assert result["summary"]["hardening_tasks"] == [
        (
            "Preserve member runtime sessions across coordinator restarts so "
            "queued replay can resume without rescanning the QR code."
        )
    ]


def test_restart_resume_check_passes_when_restart_probe_recovers_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    validation = _load_module()

    monkeypatch.setattr(
        validation,
        "_perform_restart_cycle",
        lambda **_kwargs: {
            "status": "restarted",
            "detail": {
                "operation_name": "Field Test",
                "hub_status": "running",
                "pid": 4321,
            },
        },
    )
    monkeypatch.setattr(
        validation,
        "_probe_restart_resume_over_cdp",
        lambda **_kwargs: {
            "status": "passed",
            "detail": {
                "message": "Member runtime resumed over the existing browser session.",
                "member_id": "member-123",
                "outbox_count": "0",
            },
        },
    )

    result = validation._run_restart_resume_check(
        args=SimpleNamespace(
            scenario="restart",
            timeout_seconds=20.0,
            debug_port=9222,
            hub_url="https://127.0.0.1:8443",
            join_url="https://osk.local/join?token=test",
            device_id="chromebook-lab",
        ),
        artifact_dir=tmp_path,
        local_debug_port=9333,
        cdp_version={"Browser": "Chrome/146"},
        live_result={
            "summary": {
                "member_id": "member-123",
                "operation_name": "Field Test",
            }
        },
    )

    assert result["step_update"]["id"] == "hub_restart_resume_observed"
    assert result["step_update"]["status"] == "passed"
    assert result["step_update"]["detail"]["pid"] == 4321
    assert result["step_update"]["detail"]["member_id"] == "member-123"
    assert result["summary"]["restart_resume_status"] == "passed"

def test_dry_run_records_available_local_snapshot_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    validation = _load_module()
    _set_provenance_env(monkeypatch)
    artifact_root = tmp_path / "artifacts"

    def fake_collect_local_snapshots(repo_root: Path, artifact_dir: Path) -> dict[str, object]:
        doctor_path = artifact_dir / "doctor.json"
        members_path = artifact_dir / "members.json"
        status_path = artifact_dir / "status.json"
        doctor_path.write_text('{"status":"ok"}\n')
        members_path.write_text('{"members":[],"wipe_readiness":{"status":"ready"}}\n')
        status_path.write_text('{"running":false}\n')
        return {
            "captures": {
                "doctor_snapshot_path": str(doctor_path),
                "members_snapshot_path": str(members_path),
                "status_snapshot_path": str(status_path),
            },
            "local_snapshots": {
                "doctor": {"available": True, "path": str(doctor_path)},
                "members": {"available": True, "path": str(members_path)},
                "status": {"available": True, "path": str(status_path)},
            },
        }

    monkeypatch.setattr(validation, "_collect_local_snapshots", fake_collect_local_snapshots)

    code = validation.main(
        [
            "--hub-url",
            "https://127.0.0.1:8443",
            "--join-url",
            "https://osk.local/join?token=test",
            "--device-id",
            "chromebook-lab",
            "--artifact-root",
            str(artifact_root),
            "--dry-run",
            "--timestamp",
            "20260323T190405Z",
        ]
    )

    result_path = artifact_root / "20260323T190405Z" / "result.json"
    preflight_path = artifact_root / "20260323T190405Z" / "hub-preflight.json"
    payload = json.loads(result_path.read_text())
    preflight = json.loads(preflight_path.read_text())

    assert code == 0
    assert payload["captures"]["doctor_snapshot_path"] == str(
        artifact_root / "20260323T190405Z" / "doctor.json"
    )
    assert payload["captures"]["members_snapshot_path"] == str(
        artifact_root / "20260323T190405Z" / "members.json"
    )
    assert payload["captures"]["status_snapshot_path"] == str(
        artifact_root / "20260323T190405Z" / "status.json"
    )
    assert payload["captures"]["member_shell_smoke_latest_path"] is None
    assert payload["captures"]["member_shell_smoke_result_path"] is None
    assert preflight["local_snapshots"] == {
        "doctor": {
            "available": True,
            "path": str(artifact_root / "20260323T190405Z" / "doctor.json"),
        },
        "members": {
            "available": True,
            "path": str(artifact_root / "20260323T190405Z" / "members.json"),
        },
        "status": {
            "available": True,
            "path": str(artifact_root / "20260323T190405Z" / "status.json"),
        },
    }
