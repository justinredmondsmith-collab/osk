#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/chromebook_lab_gate.sh [gate-options] [smoke-options]

Run the real Chromebook member-shell smoke as an operational gate.

Gate options:
  --allow-dirty          Permit running from a dirty git worktree
  --trigger LABEL        Provenance trigger label (default: manual)
  -h, --help             Show this help text

All other arguments are forwarded to scripts/chromebook_member_shell_smoke.sh.
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN="${OSK_PYTHON_BIN:-python}"
SMOKE_WRAPPER="${OSK_CHROMEBOOK_SMOKE_WRAPPER:-${SCRIPT_DIR}/chromebook_member_shell_smoke.sh}"
ALLOW_DIRTY="0"
TRIGGER="${OSK_GATE_TRIGGER:-manual}"
FORWARD_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --allow-dirty)
      ALLOW_DIRTY="1"
      shift
      ;;
    --trigger)
      TRIGGER="${2:?missing value for --trigger}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      FORWARD_ARGS+=("$1")
      shift
      ;;
  esac
done

ARTIFACT_ROOT="${REPO_ROOT}/output/chromebook/member-shell-smoke"
for ((index = 0; index < ${#FORWARD_ARGS[@]}; index++)); do
  if [[ "${FORWARD_ARGS[index]}" == "--artifact-root" ]]; then
    ARTIFACT_ROOT="${FORWARD_ARGS[index + 1]:?missing value for --artifact-root}"
    break
  fi
done

if [[ "${OSK_GATE_WORKTREE_STATUS+x}" == "x" ]]; then
  WORKTREE_STATUS="${OSK_GATE_WORKTREE_STATUS}"
else
  WORKTREE_STATUS="$(git -C "${REPO_ROOT}" status --short 2>/dev/null || true)"
fi
if [[ -n "${WORKTREE_STATUS}" && "${ALLOW_DIRTY}" != "1" ]]; then
  echo "Chromebook lab gate requires a clean git worktree. Commit or stash changes, or rerun with --allow-dirty." >&2
  exit 1
fi

GIT_SHA="${OSK_GATE_GIT_SHA:-$(git -C "${REPO_ROOT}" rev-parse HEAD 2>/dev/null || true)}"
GIT_BRANCH="${OSK_GATE_GIT_BRANCH:-$(git -C "${REPO_ROOT}" branch --show-current 2>/dev/null || true)}"
if [[ -z "${GIT_BRANCH}" ]]; then
  GIT_BRANCH="$(git -C "${REPO_ROOT}" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
fi
GIT_COMMIT_SUBJECT="${OSK_GATE_GIT_COMMIT_SUBJECT:-$(git -C "${REPO_ROOT}" log -1 --pretty=%s 2>/dev/null || true)}"
RUNNER_HOSTNAME="${OSK_GATE_RUNNER_HOSTNAME:-$(hostname)}"

export OSK_SMOKE_TRIGGER="${TRIGGER}"
export OSK_SMOKE_INVOCATION="chromebook_lab_gate.sh"
export OSK_SMOKE_GIT_SHA="${GIT_SHA}"
export OSK_SMOKE_GIT_BRANCH="${GIT_BRANCH}"
export OSK_SMOKE_GIT_COMMIT_SUBJECT="${GIT_COMMIT_SUBJECT}"
export OSK_SMOKE_RUNNER_HOSTNAME="${RUNNER_HOSTNAME}"
if [[ -n "${WORKTREE_STATUS}" ]]; then
  export OSK_SMOKE_WORKTREE_DIRTY="true"
else
  export OSK_SMOKE_WORKTREE_DIRTY="false"
fi

set +e
bash "${SMOKE_WRAPPER}" "${FORWARD_ARGS[@]}"
EXIT_CODE="$?"
set -e

LATEST_PATH="${ARTIFACT_ROOT}/latest.json"
if [[ -f "${LATEST_PATH}" ]]; then
  "${PYTHON_BIN}" - <<'PY' "${LATEST_PATH}"
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
provenance = payload.get("provenance") or {}
print("Chromebook lab gate:")
print(f"  status:     {payload.get('status')}")
print(f"  trigger:    {provenance.get('trigger') or '<unknown>'}")
print(f"  branch:     {provenance.get('git_branch') or '<unknown>'}")
print(f"  git sha:    {provenance.get('git_sha') or '<unknown>'}")
print(f"  run dir:    {payload.get('artifact_dir') or '<unknown>'}")
print(f"  result:     {payload.get('result_path') or '<unknown>'}")
print(f"  latest:     {Path(sys.argv[1])}")
PY
else
  echo "Chromebook lab gate did not produce ${LATEST_PATH}" >&2
fi

exit "${EXIT_CODE}"
