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

HELPER_ARGS=(
  scripts/chromebook_real_hub_workflow_summary.py
  --latest-path "${LATEST_PATH}"
)

if [[ "${JSON_MODE}" == "1" ]]; then
  HELPER_ARGS+=(--json)
else
  HELPER_ARGS+=(--text)
fi

"${PYTHON_BIN}" "${HELPER_ARGS[@]}"
