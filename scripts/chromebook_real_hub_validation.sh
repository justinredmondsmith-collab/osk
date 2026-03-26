#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/chromebook_real_hub_validation.sh [options]

Prepare and launch the dedicated Chromebook lab browser, capture launch
preflight details, and run the real-hub validation contract runner against a
real Osk hub target.

Options:
  --chromebook-host HOST   Chromebook host or IP (required)
  --hub-url URL            Base URL for the real Osk hub (required)
  --join-url URL           Real join URL for the operation (required)
  --ssh-target TARGET      Optional SSH target. Defaults to --chromebook-host
  --ssh-port PORT          Optional SSH port for the Chromebook control path
  --ssh-identity PATH      Optional SSH private key for the Chromebook control path
  --artifact-root PATH     Artifact root (default: output/chromebook/real-hub-validation)
  --chrome-binary PATH     Chromebook browser command (default: chromium)
  --debug-port PORT        Chromebook remote debugging port (default: 9222)
  --scenario LABEL         Scenario label passed to the runner (default: baseline)
  --keep-browser           Leave the Chromebook lab browser running after the validation finishes
  -h, --help               Show this help text
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN="${OSK_PYTHON_BIN:-python}"
LAB_CONTROL_SCRIPT="${OSK_LAB_CONTROL_SCRIPT:-${SCRIPT_DIR}/chromebook_lab_control.sh}"
VALIDATION_RUNNER="${OSK_REAL_HUB_VALIDATION_RUNNER:-${SCRIPT_DIR}/real_hub_validation.py}"
CHROMEBOOK_HOST=""
HUB_URL=""
JOIN_URL=""
SSH_TARGET=""
SSH_PORT=""
SSH_IDENTITY=""
ARTIFACT_ROOT="${REPO_ROOT}/output/chromebook/real-hub-validation"
CHROME_BINARY="chromium"
DEBUG_PORT="9222"
SCENARIO="baseline"
KEEP_BROWSER="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --chromebook-host)
      CHROMEBOOK_HOST="${2:?missing value for --chromebook-host}"
      shift 2
      ;;
    --hub-url)
      HUB_URL="${2:?missing value for --hub-url}"
      shift 2
      ;;
    --join-url)
      JOIN_URL="${2:?missing value for --join-url}"
      shift 2
      ;;
    --ssh-target)
      SSH_TARGET="${2:?missing value for --ssh-target}"
      shift 2
      ;;
    --ssh-port)
      SSH_PORT="${2:?missing value for --ssh-port}"
      shift 2
      ;;
    --ssh-identity)
      SSH_IDENTITY="${2:?missing value for --ssh-identity}"
      shift 2
      ;;
    --artifact-root)
      ARTIFACT_ROOT="${2:?missing value for --artifact-root}"
      shift 2
      ;;
    --chrome-binary)
      CHROME_BINARY="${2:?missing value for --chrome-binary}"
      shift 2
      ;;
    --debug-port)
      DEBUG_PORT="${2:?missing value for --debug-port}"
      shift 2
      ;;
    --scenario)
      SCENARIO="${2:?missing value for --scenario}"
      shift 2
      ;;
    --keep-browser)
      KEEP_BROWSER="1"
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

if [[ -z "${CHROMEBOOK_HOST}" ]]; then
  echo "--chromebook-host is required" >&2
  exit 1
fi

if [[ -z "${HUB_URL}" ]]; then
  echo "--hub-url is required" >&2
  exit 1
fi

if [[ -z "${JOIN_URL}" ]]; then
  echo "--join-url is required" >&2
  exit 1
fi

if [[ -z "${SSH_TARGET}" ]]; then
  SSH_TARGET="${CHROMEBOOK_HOST}"
fi

RUN_LABEL="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_STARTED_AT_UTC="${OSK_SMOKE_STARTED_AT_UTC:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"
export OSK_SMOKE_STARTED_AT_UTC="${RUN_STARTED_AT_UTC}"
export OSK_SMOKE_TRIGGER="${OSK_SMOKE_TRIGGER:-manual}"
export OSK_SMOKE_INVOCATION="${OSK_SMOKE_INVOCATION:-chromebook_real_hub_validation.sh}"
RUN_DIR="${ARTIFACT_ROOT}/${RUN_LABEL}"
mkdir -p "${RUN_DIR}"
RESULT_PATH="${RUN_DIR}/result.json"
PREFLIGHT_RAW_PATH="${RUN_DIR}/launch-preflight.txt"
PREFLIGHT_JSON_PATH="${RUN_DIR}/launch-preflight.json"

LAB_CONTROL_ARGS=(
  --ssh-target "${SSH_TARGET}"
  --chrome-binary "${CHROME_BINARY}"
  --chrome-flag "--ignore-certificate-errors"
  --chrome-flag "--allow-insecure-localhost"
  --debug-port "${DEBUG_PORT}"
)
RUNNER_ARGS=(
  --hub-url "${HUB_URL}"
  --join-url "${JOIN_URL}"
  --device-id "${CHROMEBOOK_HOST}"
  --ssh-target "${SSH_TARGET}"
  --artifact-root "${ARTIFACT_ROOT}"
  --scenario "${SCENARIO}"
  --debug-port "${DEBUG_PORT}"
  --timestamp "${RUN_LABEL}"
)

if [[ -n "${SSH_PORT}" ]]; then
  LAB_CONTROL_ARGS+=(--ssh-port "${SSH_PORT}")
  RUNNER_ARGS+=(--ssh-port "${SSH_PORT}")
fi

if [[ -n "${SSH_IDENTITY}" ]]; then
  LAB_CONTROL_ARGS+=(--ssh-identity "${SSH_IDENTITY}")
  RUNNER_ARGS+=(--ssh-identity "${SSH_IDENTITY}")
fi

write_failure_result() {
  local stage="$1"
  local message="$2"
  local failure_type="${3:-ShellStageFailure}"

  if [[ -f "${RESULT_PATH}" ]]; then
    return 0
  fi

  (
    cd "${REPO_ROOT}"
    PYTHONPATH=src "${PYTHON_BIN}" - <<'PY' \
      "${RESULT_PATH}" \
      "${RUN_DIR}" \
      "${HUB_URL}" \
      "${JOIN_URL}" \
      "${CHROMEBOOK_HOST}" \
      "${PREFLIGHT_JSON_PATH}" \
      "${SCENARIO}" \
      "${stage}" \
      "${message}" \
      "${failure_type}"
import json
import sys
from pathlib import Path

(
    result_path,
    artifact_dir,
    hub_url,
    join_url,
    device_id,
    preflight_path,
    scenario,
    stage,
    message,
    failure_type,
) = sys.argv[1:]

launch_preflight = None
preflight_file = Path(preflight_path)
if preflight_file.exists():
    try:
        payload = json.loads(preflight_file.read_text())
        launch_preflight = payload if isinstance(payload, dict) else None
    except Exception:
        launch_preflight = None

result_payload = {
    "contract_version": 1,
    "status": "failed",
    "execution_mode": "contract_only",
    "scenario": scenario,
    "hub_url": hub_url,
    "join_url": join_url,
    "device_id": device_id,
    "artifact_dir": artifact_dir,
    "result_path": result_path,
    "captures": {
        "closure_summary_path": None,
        "doctor_snapshot_path": None,
        "hub_preflight_path": None,
        "members_snapshot_path": None,
        "status_snapshot_path": None,
        "cdp_version_path": None,
        "audit_slice_path": None,
        "wipe_readiness_path": None,
    },
    "steps": [],
    "summary": {
        "message": "Chromebook real-hub wrapper failed before browser-driving could begin.",
    },
    "failure": {
        "message": message,
        "type": failure_type,
        "stage": stage,
    },
    "launch_preflight": launch_preflight,
}

Path(result_path).write_text(json.dumps(result_payload, indent=2, sort_keys=True) + "\n")
PY
  )
}

capture_launch_preflight() {
  local preflight_output=""
  local exit_code=0

  set +e
  preflight_output="$(bash "${LAB_CONTROL_SCRIPT}" preflight "${LAB_CONTROL_ARGS[@]}")"
  exit_code="$?"
  set -e

  if [[ "${exit_code}" -ne 0 ]]; then
    write_failure_result \
      "preflight" \
      "Chromebook preflight step failed. (exit ${exit_code})"
    return "${exit_code}"
  fi

  printf '%s\n' "${preflight_output}" > "${PREFLIGHT_RAW_PATH}"
  "${PYTHON_BIN}" - <<'PY' "${PREFLIGHT_RAW_PATH}" "${PREFLIGHT_JSON_PATH}"
import json
import sys
from pathlib import Path

raw_path = Path(sys.argv[1])
json_path = Path(sys.argv[2])
payload = {
    "xdg_runtime_dir": "",
    "wayland_display": "",
    "display": "",
    "dbus_session_bus_address": "",
    "ozone_flag": "",
}
key_map = {
    "XDG_RUNTIME_DIR": "xdg_runtime_dir",
    "WAYLAND_DISPLAY": "wayland_display",
    "DISPLAY": "display",
    "DBUS_SESSION_BUS_ADDRESS": "dbus_session_bus_address",
    "OZONE_FLAG": "ozone_flag",
}

for line in raw_path.read_text().splitlines():
    key, _, value = line.partition("=")
    payload_key = key_map.get(key.strip())
    if payload_key is not None:
        payload[payload_key] = value

json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
PY
}

emit_launch_preflight_summary() {
  if [[ ! -f "${PREFLIGHT_RAW_PATH}" ]]; then
    return 0
  fi

  echo "Chromebook launch preflight:" >&2
  while IFS= read -r line; do
    printf '  %s\n' "${line}" >&2
  done < "${PREFLIGHT_RAW_PATH}"
  printf '  artifact: %s\n' "${PREFLIGHT_JSON_PATH}" >&2
}

sync_result_metadata() {
  if [[ ! -f "${RESULT_PATH}" ]]; then
    return 0
  fi

  (
    cd "${REPO_ROOT}"
    PYTHONPATH=src "${PYTHON_BIN}" - <<'PY' \
      "${RESULT_PATH}" \
      "${ARTIFACT_ROOT}" \
      "${PREFLIGHT_JSON_PATH}" \
      "${CHROMEBOOK_HOST}" \
      "${RUN_LABEL}"
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

from osk.chromebook_smoke_artifacts import (
    build_provenance,
    merge_result_metadata,
    write_artifact_indexes,
)

result_path = Path(sys.argv[1])
artifact_root = Path(sys.argv[2])
preflight_path = Path(sys.argv[3])
chromebook_host = sys.argv[4]
run_label = sys.argv[5]
repo_root = Path.cwd()

provenance = build_provenance(
    repo_root=repo_root,
    run_label=run_label,
    chromebook_host=chromebook_host,
    completed_at_utc=datetime.now(timezone.utc).isoformat(),
)
payload = merge_result_metadata(
    result_path,
    launch_preflight_path=preflight_path,
    provenance=provenance,
)
write_artifact_indexes(artifact_root, payload)
PY
  )
}

run_stage() {
  local stage="$1"
  local description="$2"
  shift 2

  set +e
  "$@"
  local exit_code="$?"
  set -e

  if [[ "${exit_code}" -eq 0 ]]; then
    return 0
  fi

  write_failure_result "${stage}" "${description} (exit ${exit_code})"
  if [[ "${stage}" == "launch" || "${stage}" == "real-hub-runner" ]]; then
    emit_launch_preflight_summary
  fi
  return "${exit_code}"
}

cleanup() {
  if [[ "${KEEP_BROWSER}" != "1" ]]; then
    bash "${LAB_CONTROL_SCRIPT}" cleanup \
      "${LAB_CONTROL_ARGS[@]}" \
      >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

if run_stage \
  "prepare" \
  "Chromebook prepare step failed." \
  bash "${LAB_CONTROL_SCRIPT}" prepare \
  "${LAB_CONTROL_ARGS[@]}"; then
  :
else
  exit_code="$?"
  sync_result_metadata
  exit "${exit_code}"
fi

if capture_launch_preflight; then
  :
else
  exit_code="$?"
  sync_result_metadata
  exit "${exit_code}"
fi

if run_stage \
  "launch" \
  "Chromebook launch step failed." \
  bash "${LAB_CONTROL_SCRIPT}" launch \
  "${LAB_CONTROL_ARGS[@]}" \
  --start-url "about:blank"; then
  :
else
  exit_code="$?"
  sync_result_metadata
  exit "${exit_code}"
fi

if run_stage \
  "real-hub-runner" \
  "Real-hub validation runner failed." \
  "${PYTHON_BIN}" "${VALIDATION_RUNNER}" \
  "${RUNNER_ARGS[@]}"; then
  :
else
  exit_code="$?"
  sync_result_metadata
  exit "${exit_code}"
fi

sync_result_metadata

echo
echo "Chromebook real-hub validation artifacts:"
echo "  run dir:    ${RUN_DIR}"
echo "  result:     ${RUN_DIR}/result.json"
echo "  latest:     ${ARTIFACT_ROOT}/latest.json"
echo "  note:       inspect result.json for scenario-specific restart and wipe follow-up states"
