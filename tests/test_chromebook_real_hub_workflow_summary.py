from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "chromebook_real_hub_workflow_summary.py"
WARNING_PREFIX = "::warning::Chromebook real-hub gate completed with open operator follow-up."
NOTICE_PREFIX = (
    "::notice::Chromebook real-hub gate completed without unresolved operator follow-up."
)


def _write_latest(path: Path, *, status: str, handoff: dict | None) -> Path:
    payload = {
        "status": status,
        "artifact_dir": str(path.parent / "20260325T220000Z"),
        "result_path": str(path.parent / "20260325T220000Z" / "result.json"),
        "provenance": {
            "trigger": "workflow_dispatch",
            "git_branch": "justinredmondsmith-collab/docs/dashboard-audit-workflow",
            "git_sha": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
        },
        "operator_handoff": handoff,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path


def test_workflow_summary_writes_warning_for_open_follow_up(tmp_path: Path) -> None:
    latest_path = _write_latest(
        tmp_path / "latest.json",
        status="passed",
        handoff={
            "path": str(tmp_path / "20260325T220000Z" / "operator-handoff.json"),
            "operator_closure_status": "captured",
            "operator_closure_state": "captured_open_follow_up",
            "wipe_observed_status": "captured_from_member_shell_smoke",
            "follow_up_required": True,
            "unresolved_follow_up_count": 1,
            "follow_up_summary": "Resolve 1 unresolved member wipe follow-up item.",
        },
    )
    github_output = tmp_path / "github-output.txt"
    step_summary = tmp_path / "step-summary.md"

    result = subprocess.run(
        [
            "python",
            str(SCRIPT_PATH),
            "--latest-path",
            str(latest_path),
            "--github-output",
            str(github_output),
            "--github-step-summary",
            str(step_summary),
            "--annotate-github",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert WARNING_PREFIX in result.stdout
    output_text = github_output.read_text()
    assert "status=passed" in output_text
    assert "operator_closure_state=captured_open_follow_up" in output_text
    assert "follow_up_required=True" in output_text
    assert "unresolved_follow_up_count=1" in output_text
    summary_text = step_summary.read_text()
    assert "# Chromebook Real Hub Gate" in summary_text
    assert "Closure: `captured` / `captured_open_follow_up`" in summary_text
    assert "Note: Resolve 1 unresolved member wipe follow-up item." in summary_text


def test_workflow_summary_writes_notice_for_clear_pass(tmp_path: Path) -> None:
    latest_path = _write_latest(
        tmp_path / "latest.json",
        status="passed",
        handoff={
            "path": str(tmp_path / "20260325T220000Z" / "operator-handoff.json"),
            "operator_closure_status": "captured",
            "operator_closure_state": "captured_clear",
            "wipe_observed_status": "captured_from_member_shell_smoke",
            "follow_up_required": False,
            "unresolved_follow_up_count": 0,
            "follow_up_summary": "No unresolved member wipe follow-up remains.",
        },
    )

    result = subprocess.run(
        [
            "python",
            str(SCRIPT_PATH),
            "--latest-path",
            str(latest_path),
            "--annotate-github",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert NOTICE_PREFIX in result.stdout
    json_payload = json.loads(result.stdout.split("\n", 1)[1])
    assert json_payload["operator_closure_state"] == "captured_clear"
    assert json_payload["follow_up_required"] is False


def test_workflow_summary_writes_error_for_failed_gate(tmp_path: Path) -> None:
    latest_path = _write_latest(
        tmp_path / "latest.json",
        status="failed",
        handoff=None,
    )

    result = subprocess.run(
        [
            "python",
            str(SCRIPT_PATH),
            "--latest-path",
            str(latest_path),
            "--annotate-github",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "::error::Chromebook real-hub gate failed." in result.stdout
