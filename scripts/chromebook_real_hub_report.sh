#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/chromebook_real_hub_report.sh [options]

Report the latest indexed real-hub validation result.

Options:
  --artifact-root PATH   Artifact root (default: output/chromebook/real-hub-validation)
  --json                 Emit the summarized report as JSON
  -h, --help             Show this help text
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN="${OSK_PYTHON_BIN:-python}"
ARTIFACT_ROOT="${REPO_ROOT}/output/chromebook/real-hub-validation"
JSON_MODE="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --artifact-root)
      ARTIFACT_ROOT="${2:?missing value for --artifact-root}"
      shift 2
      ;;
    --json)
      JSON_MODE="1"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

LATEST_PATH="${ARTIFACT_ROOT}/latest.json"
if [[ ! -f "${LATEST_PATH}" ]]; then
  echo "Real-hub latest artifact not found: ${LATEST_PATH}" >&2
  exit 1
fi

"${PYTHON_BIN}" - <<'PY' "${LATEST_PATH}" "${JSON_MODE}"
from __future__ import annotations

import json
import sys
from pathlib import Path

latest_path = Path(sys.argv[1])
json_mode = sys.argv[2] == "1"
payload = json.loads(latest_path.read_text())
provenance = payload.get("provenance") or {}
handoff = payload.get("operator_handoff") or {}

summary = {
    "status": payload.get("status"),
    "trigger": provenance.get("trigger"),
    "branch": provenance.get("git_branch"),
    "git_sha": provenance.get("git_sha"),
    "run_dir": payload.get("artifact_dir"),
    "result_path": payload.get("result_path"),
    "handoff_path": handoff.get("path"),
    "operator_closure_status": handoff.get("operator_closure_status"),
    "operator_closure_state": handoff.get("operator_closure_state"),
    "wipe_observed_status": handoff.get("wipe_observed_status"),
    "follow_up_required": handoff.get("follow_up_required"),
    "unresolved_follow_up_count": handoff.get("unresolved_follow_up_count"),
    "follow_up_summary": handoff.get("follow_up_summary"),
    "latest_path": str(latest_path),
}

if json_mode:
    print(json.dumps(summary, indent=2, sort_keys=True))
    raise SystemExit(0)

print("Chromebook real-hub report:")
print(f"  status:     {summary['status'] or '<unknown>'}")
print(f"  trigger:    {summary['trigger'] or '<unknown>'}")
print(f"  branch:     {summary['branch'] or '<unknown>'}")
print(f"  git sha:    {summary['git_sha'] or '<unknown>'}")
print(f"  run dir:    {summary['run_dir'] or '<unknown>'}")
print(f"  result:     {summary['result_path'] or '<unknown>'}")
print(f"  latest:     {summary['latest_path']}")
if summary["handoff_path"]:
    print(f"  handoff:    {summary['handoff_path']}")
if summary["operator_closure_status"] or summary["operator_closure_state"]:
    print(
        "  closure:    "
        f"{summary['operator_closure_status'] or '<unknown>'}"
        f" / {summary['operator_closure_state'] or '<unknown>'}"
    )
if summary["wipe_observed_status"]:
    print(f"  wipe:       {summary['wipe_observed_status']}")
if summary["follow_up_required"] is not None:
    print(f"  follow_up:  {summary['follow_up_required']}")
if summary["unresolved_follow_up_count"] is not None:
    print(f"  unresolved: {summary['unresolved_follow_up_count']}")
if summary["follow_up_summary"]:
    print(f"  note:       {summary['follow_up_summary']}")
PY
