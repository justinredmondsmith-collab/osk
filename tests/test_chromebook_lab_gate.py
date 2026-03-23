from __future__ import annotations

import json
import os
import subprocess
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "chromebook_lab_gate.sh"


def _write_executable(path: Path, content: str) -> Path:
    path.write_text(content)
    path.chmod(0o755)
    return path


def _write_smoke_wrapper_stub(path: Path) -> Path:
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
              echo "missing --artifact-root in gate test stub" >&2
              exit 97
            fi

            mkdir -p "${artifact_root}/20260322T190405Z"
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
                "artifact_dir": str(artifact_root / "20260322T190405Z"),
                "result_path": str(artifact_root / "20260322T190405Z" / "result.json"),
                "provenance": {
                    "trigger": os.environ.get("OSK_SMOKE_TRIGGER"),
                    "git_branch": os.environ.get("OSK_SMOKE_GIT_BRANCH"),
                    "git_sha": os.environ.get("OSK_SMOKE_GIT_SHA"),
                },
            }
            (artifact_root / "latest.json").write_text(
                json.dumps(latest, indent=2, sort_keys=True) + "\\n"
            )
            (artifact_root / "20260322T190405Z" / "result.json").write_text(
                json.dumps({"status": "passed"}, indent=2, sort_keys=True) + "\\n"
            )
            PY
            exit "${OSK_TEST_GATE_SMOKE_EXIT_CODE:-0}"
            """
        ),
    )


def test_gate_rejects_dirty_worktree_without_allow_dirty(tmp_path: Path) -> None:
    smoke_wrapper = _write_smoke_wrapper_stub(tmp_path / "smoke-wrapper-stub.sh")
    env = os.environ.copy()
    env.update(
        {
            "OSK_CHROMEBOOK_SMOKE_WRAPPER": str(smoke_wrapper),
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

    assert result.returncode == 1
    assert "requires a clean git worktree" in result.stderr
    assert not (tmp_path / "env.json").exists()


def test_gate_forwards_provenance_and_prints_summary(tmp_path: Path) -> None:
    smoke_wrapper = _write_smoke_wrapper_stub(tmp_path / "smoke-wrapper-stub.sh")
    env = os.environ.copy()
    env.update(
        {
            "OSK_CHROMEBOOK_SMOKE_WRAPPER": str(smoke_wrapper),
            "OSK_GATE_GIT_SHA": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
            "OSK_GATE_GIT_BRANCH": "justinredmondsmith-collab/feat/chromebook-lab-gate",
            "OSK_GATE_GIT_COMMIT_SUBJECT": "feat(chromebook): Add lab gate",
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

    payload = json.loads((tmp_path / "env.json").read_text())

    assert result.returncode == 0
    assert payload == {
        "git_branch": "justinredmondsmith-collab/feat/chromebook-lab-gate",
        "git_commit_subject": "feat(chromebook): Add lab gate",
        "git_sha": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
        "invocation": "chromebook_lab_gate.sh",
        "runner_hostname": "lab-host",
        "trigger": "workflow_dispatch",
        "worktree_dirty": "false",
    }
    assert "Chromebook lab gate:" in result.stdout
    assert "status:     passed" in result.stdout
    assert "trigger:    workflow_dispatch" in result.stdout
    assert "branch:     justinredmondsmith-collab/feat/chromebook-lab-gate" in result.stdout
