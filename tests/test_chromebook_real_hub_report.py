from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "chromebook_real_hub_report.sh"


def _write_latest(artifact_root: Path, payload: dict[str, object]) -> Path:
    artifact_root.mkdir(parents=True, exist_ok=True)
    latest_path = artifact_root / "latest.json"
    latest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return latest_path


def test_report_prints_indexed_operator_handoff_summary(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    _write_latest(
        artifact_root,
        {
            "status": "passed",
            "artifact_dir": str(artifact_root / "20260325T210000Z"),
            "result_path": str(artifact_root / "20260325T210000Z" / "result.json"),
            "operator_handoff": {
                "path": str(artifact_root / "20260325T210000Z" / "operator-handoff.json"),
                "operator_closure_status": "captured",
                "operator_closure_state": "captured_open_follow_up",
                "wipe_observed_status": "captured_from_member_shell_smoke",
                "follow_up_required": True,
                "unresolved_follow_up_count": 1,
                "follow_up_summary": "Resolve 1 unresolved member wipe follow-up item.",
            },
            "provenance": {
                "trigger": "workflow_dispatch",
                "git_branch": "justinredmondsmith-collab/docs/dashboard-audit-workflow",
                "git_sha": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
            },
        },
    )

    result = subprocess.run(
        [
            "bash",
            str(SCRIPT_PATH),
            "--artifact-root",
            str(artifact_root),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Chromebook real-hub report:" in result.stdout
    assert "status:     passed" in result.stdout
    assert "trigger:    workflow_dispatch" in result.stdout
    assert "closure:    captured / captured_open_follow_up" in result.stdout
    assert "wipe:       captured_from_member_shell_smoke" in result.stdout
    assert "follow_up:  True" in result.stdout
    assert "unresolved: 1" in result.stdout
    assert "Resolve 1 unresolved member wipe follow-up item." in result.stdout


def test_report_json_mode_handles_missing_handoff_summary(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    _write_latest(
        artifact_root,
        {
            "status": "failed",
            "artifact_dir": str(artifact_root / "20260325T210500Z"),
            "result_path": str(artifact_root / "20260325T210500Z" / "result.json"),
            "operator_handoff": None,
            "provenance": {
                "trigger": "manual",
                "git_branch": "branch-name",
                "git_sha": "feedfacefeedfacefeedfacefeedfacefeedface",
            },
        },
    )

    result = subprocess.run(
        [
            "bash",
            str(SCRIPT_PATH),
            "--artifact-root",
            str(artifact_root),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    payload = json.loads(result.stdout)

    assert result.returncode == 0
    assert payload["status"] == "failed"
    assert payload["trigger"] == "manual"
    assert payload["handoff_path"] is None
    assert payload["operator_closure_status"] is None
    assert payload["unresolved_follow_up_count"] is None
