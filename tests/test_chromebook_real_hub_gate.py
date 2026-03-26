from __future__ import annotations

import json
import os
import subprocess
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "chromebook_real_hub_gate.sh"


def _write_executable(path: Path, content: str) -> Path:
    path.write_text(content)
    path.chmod(0o755)
    return path


def _write_real_hub_wrapper_stub(path: Path) -> Path:
    return _write_executable(
        path,
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail

            artifact_root=""
            args=("$@")
            for ((index = 0; index < ${#args[@]}; index++)); do
              if [[ "${args[index]}" == "--artifact-root" ]]; then
                artifact_root="${args[index + 1]}"
              fi
            done

            if [[ -z "${artifact_root}" ]]; then
              echo "missing --artifact-root in real-hub gate test stub" >&2
              exit 97
            fi

            mkdir -p "${artifact_root}/20260325T210405Z"
            python - <<'PY' "${OSK_TEST_GATE_ENV_PATH:?missing env path}" "${artifact_root}"
            import json
            import os
            import sys
            from pathlib import Path

            env_path = Path(sys.argv[1])
            artifact_root = Path(sys.argv[2])
            payload = {
                "invocation": os.environ.get("OSK_SMOKE_INVOCATION"),
                "trigger": os.environ.get("OSK_SMOKE_TRIGGER"),
                "git_sha": os.environ.get("OSK_SMOKE_GIT_SHA"),
                "git_branch": os.environ.get("OSK_SMOKE_GIT_BRANCH"),
                "git_commit_subject": os.environ.get("OSK_SMOKE_GIT_COMMIT_SUBJECT"),
                "runner_hostname": os.environ.get("OSK_SMOKE_RUNNER_HOSTNAME"),
                "worktree_dirty": os.environ.get("OSK_SMOKE_WORKTREE_DIRTY"),
            }
            env_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\\n")

            latest = {
                "status": "passed",
                "artifact_dir": str(artifact_root / "20260325T210405Z"),
                "result_path": str(artifact_root / "20260325T210405Z" / "result.json"),
                "operator_handoff": {
                    "path": str(artifact_root / "20260325T210405Z" / "operator-handoff.json"),
                    "operator_closure_status": "captured",
                    "operator_closure_state": "captured_open_follow_up",
                    "wipe_observed_status": "captured_from_member_shell_smoke",
                    "follow_up_required": True,
                    "unresolved_follow_up_count": 1,
                    "follow_up_summary": "Resolve 1 unresolved member wipe follow-up item.",
                },
                "provenance": {
                    "trigger": os.environ.get("OSK_SMOKE_TRIGGER"),
                    "git_branch": os.environ.get("OSK_SMOKE_GIT_BRANCH"),
                    "git_sha": os.environ.get("OSK_SMOKE_GIT_SHA"),
                },
            }
            (artifact_root / "latest.json").write_text(
                json.dumps(latest, indent=2, sort_keys=True) + "\\n"
            )
            (artifact_root / "20260325T210405Z" / "result.json").write_text(
                json.dumps({"status": "passed"}, indent=2, sort_keys=True) + "\\n"
            )
            PY
            exit "${OSK_TEST_GATE_WRAPPER_EXIT_CODE:-0}"
            """
        ),
    )


def test_real_hub_gate_rejects_dirty_worktree_without_allow_dirty(tmp_path: Path) -> None:
    wrapper = _write_real_hub_wrapper_stub(tmp_path / "real-hub-wrapper-stub.sh")
    env = os.environ.copy()
    env.update(
        {
            "OSK_REAL_HUB_GATE_WRAPPER": str(wrapper),
            "OSK_GATE_WORKTREE_STATUS": " M dirty-file",
            "OSK_TEST_GATE_ENV_PATH": str(tmp_path / "env.json"),
        }
    )

    result = subprocess.run(
        [
            "bash",
            str(SCRIPT_PATH),
            "--chromebook-host",
            "lab-book",
            "--hub-url",
            "https://127.0.0.1:8443",
            "--join-url",
            "https://osk.local/join?token=test",
            "--artifact-root",
            str(tmp_path / "artifacts"),
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    assert result.returncode == 1
    assert "requires a clean git worktree" in result.stderr
    assert not (tmp_path / "env.json").exists()


def test_real_hub_gate_forwards_provenance_and_prints_indexed_summary(tmp_path: Path) -> None:
    wrapper = _write_real_hub_wrapper_stub(tmp_path / "real-hub-wrapper-stub.sh")
    env = os.environ.copy()
    env.update(
        {
            "OSK_REAL_HUB_GATE_WRAPPER": str(wrapper),
            "OSK_GATE_GIT_SHA": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
            "OSK_GATE_GIT_BRANCH": "justinredmondsmith-collab/docs/dashboard-audit-workflow",
            "OSK_GATE_GIT_COMMIT_SUBJECT": "feat(validation): Add real-hub gate",
            "OSK_GATE_RUNNER_HOSTNAME": "lab-host",
            "OSK_GATE_WORKTREE_STATUS": "",
            "OSK_TEST_GATE_ENV_PATH": str(tmp_path / "env.json"),
        }
    )

    result = subprocess.run(
        [
            "bash",
            str(SCRIPT_PATH),
            "--trigger",
            "workflow_dispatch",
            "--chromebook-host",
            "lab-book",
            "--hub-url",
            "https://127.0.0.1:8443",
            "--join-url",
            "https://osk.local/join?token=test",
            "--artifact-root",
            str(tmp_path / "artifacts"),
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    payload = json.loads((tmp_path / "env.json").read_text())

    assert result.returncode == 0
    assert payload == {
        "git_branch": "justinredmondsmith-collab/docs/dashboard-audit-workflow",
        "git_commit_subject": "feat(validation): Add real-hub gate",
        "git_sha": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
        "invocation": "chromebook_real_hub_gate.sh",
        "runner_hostname": "lab-host",
        "trigger": "workflow_dispatch",
        "worktree_dirty": "false",
    }
    assert "Chromebook real-hub gate:" in result.stdout
    assert "status:     passed" in result.stdout
    assert "trigger:    workflow_dispatch" in result.stdout
    assert "branch:     justinredmondsmith-collab/docs/dashboard-audit-workflow" in result.stdout
    assert "closure:    captured / captured_open_follow_up" in result.stdout
    assert "wipe:       captured_from_member_shell_smoke" in result.stdout
    assert "follow_up:  True" in result.stdout
    assert "unresolved: 1" in result.stdout
