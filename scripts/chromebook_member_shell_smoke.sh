#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/chromebook_member_shell_smoke.sh [options]

Start the mocked member-shell smoke helper on the host, prepare and launch the
dedicated Chromebook lab browser, then drive the real Chromebook browser over
an SSH-tunnelled CDP session.

Options:
  --chromebook-host HOST   Chromebook host or IP (required)
  --ssh-target TARGET      Optional SSH target. Defaults to --chromebook-host
  --ssh-port PORT          Optional SSH port for the Chromebook control path
  --ssh-identity PATH      Optional SSH private key for the Chromebook control path
  --advertise-host HOST    Host/IP the Chromebook can use to reach the smoke helper (required)
  --host HOST              Bind host for the smoke helper (default: 0.0.0.0)
  --port PORT              Bind port for the smoke helper (default: 8123)
  --artifact-root PATH     Artifact root (default: output/chromebook/member-shell-smoke)
  --chrome-binary PATH     Chromebook browser command (default: chromium)
  --debug-port PORT        Chromebook remote debugging port (default: 9222)
  --keep-browser           Leave the Chromebook lab browser running after the smoke finishes
  --keep-server            Leave the smoke helper running after the smoke finishes
  -h, --help               Show this help text
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN="${OSK_PYTHON_BIN:-python}"
CURL_BIN="${OSK_CURL_BIN:-curl}"
LAB_CONTROL_SCRIPT="${OSK_LAB_CONTROL_SCRIPT:-${SCRIPT_DIR}/chromebook_lab_control.sh}"
CDP_RUNNER_SCRIPT="${OSK_CDP_RUNNER_SCRIPT:-${SCRIPT_DIR}/chromebook_member_shell_smoke.py}"
MEMBER_SMOKE_SCRIPT="${OSK_MEMBER_SMOKE_SCRIPT:-scripts/member_shell_smoke.py}"
HELPER_READY_ATTEMPTS="${OSK_HELPER_READY_ATTEMPTS:-40}"
HELPER_READY_SLEEP_SECONDS="${OSK_HELPER_READY_SLEEP_SECONDS:-1}"
CHROMEBOOK_HOST=""
SSH_TARGET=""
SSH_PORT=""
SSH_IDENTITY=""
ADVERTISE_HOST=""
HOST="0.0.0.0"
PORT="8123"
ARTIFACT_ROOT="${REPO_ROOT}/output/chromebook/member-shell-smoke"
CHROME_BINARY="chromium"
DEBUG_PORT="9222"
KEEP_BROWSER="0"
KEEP_SERVER="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --chromebook-host)
      CHROMEBOOK_HOST="${2:?missing value for --chromebook-host}"
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
    --advertise-host)
      ADVERTISE_HOST="${2:?missing value for --advertise-host}"
      shift 2
      ;;
    --host)
      HOST="${2:?missing value for --host}"
      shift 2
      ;;
    --port)
      PORT="${2:?missing value for --port}"
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
    --keep-browser)
      KEEP_BROWSER="1"
      shift
      ;;
    --keep-server)
      KEEP_SERVER="1"
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

if [[ -z "${ADVERTISE_HOST}" ]]; then
  echo "--advertise-host is required" >&2
  exit 1
fi

if [[ -z "${SSH_TARGET}" ]]; then
  SSH_TARGET="${CHROMEBOOK_HOST}"
fi

RUN_LABEL="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="${ARTIFACT_ROOT}/${RUN_LABEL}"
mkdir -p "${RUN_DIR}"
METADATA_PATH="${RUN_DIR}/metadata.json"
HELPER_LOG="${RUN_DIR}/helper.log"
HELPER_PID=""
RESULT_PATH="${RUN_DIR}/result.json"
PREFLIGHT_RAW_PATH="${RUN_DIR}/launch-preflight.txt"
PREFLIGHT_JSON_PATH="${RUN_DIR}/launch-preflight.json"
LAB_CONTROL_ARGS=(
  --ssh-target "${SSH_TARGET}"
  --chrome-binary "${CHROME_BINARY}"
  --debug-port "${DEBUG_PORT}"
)
PYTHON_SMOKE_ARGS=(
  --chromebook-host "${CHROMEBOOK_HOST}"
  --ssh-target "${SSH_TARGET}"
  --smoke-metadata "${METADATA_PATH}"
  --artifact-root "${ARTIFACT_ROOT}"
  --debug-port "${DEBUG_PORT}"
  --timestamp "${RUN_LABEL}"
)

if [[ -n "${SSH_PORT}" ]]; then
  LAB_CONTROL_ARGS+=(--ssh-port "${SSH_PORT}")
  PYTHON_SMOKE_ARGS+=(--ssh-port "${SSH_PORT}")
fi

if [[ -n "${SSH_IDENTITY}" ]]; then
  LAB_CONTROL_ARGS+=(--ssh-identity "${SSH_IDENTITY}")
  PYTHON_SMOKE_ARGS+=(--ssh-identity "${SSH_IDENTITY}")
fi

write_failure_result() {
  local stage="$1"
  local message="$2"
  local failure_type="${3:-ShellStageFailure}"

  if [[ -f "${RESULT_PATH}" ]]; then
    return 0
  fi

  "${PYTHON_BIN}" - <<'PY' \
    "${RESULT_PATH}" \
    "${RUN_DIR}" \
    "${CHROMEBOOK_HOST}" \
    "${SSH_TARGET}" \
    "${SSH_PORT}" \
    "${SSH_IDENTITY}" \
    "${DEBUG_PORT}" \
    "${METADATA_PATH}" \
    "${PREFLIGHT_JSON_PATH}" \
    "${stage}" \
    "${message}" \
    "${failure_type}"
import json
import sys
from pathlib import Path

(
    result_path,
    artifact_dir,
    chromebook_host,
    ssh_target,
    ssh_port,
    ssh_identity,
    debug_port,
    metadata_path,
    preflight_path,
    stage,
    message,
    failure_type,
) = sys.argv[1:]

smoke_metadata: dict[str, object] = {}
launch_preflight: dict[str, object] | None = None
metadata_file = Path(metadata_path)
if metadata_file.exists():
    try:
        payload = json.loads(metadata_file.read_text())
        controls = payload.get("controls")
        smoke_metadata = {
            "join_url": str(payload.get("join_url") or "").strip(),
            "operation_name": str(payload.get("operation_name") or "").strip() or None,
            "controls": controls if isinstance(controls, dict) else {},
        }
    except Exception:
        smoke_metadata = {}

preflight_file = Path(preflight_path)
if preflight_file.exists():
    try:
        payload = json.loads(preflight_file.read_text())
        launch_preflight = payload if isinstance(payload, dict) else None
    except Exception:
        launch_preflight = None

result_payload = {
    "status": "failed",
    "chromebook_host": chromebook_host,
    "ssh_target": ssh_target,
    "ssh_port": int(ssh_port) if ssh_port else None,
    "ssh_identity": ssh_identity or None,
    "debug_port": int(debug_port),
    "local_debug_port": None,
    "artifact_dir": artifact_dir,
    "smoke_metadata": smoke_metadata,
    "launch_preflight": launch_preflight,
    "cdp_version": None,
    "steps": [],
    "failure": {
        "message": message,
        "type": failure_type,
        "stage": stage,
    },
}

Path(result_path).write_text(json.dumps(result_payload, indent=2, sort_keys=True) + "\n")
PY
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
  return "${exit_code}"
}

cleanup() {
  local cleanup_args=(
    "${LAB_CONTROL_ARGS[@]}"
  )

  if [[ "${KEEP_BROWSER}" != "1" ]]; then
    bash "${LAB_CONTROL_SCRIPT}" cleanup \
      "${cleanup_args[@]}" \
      >/dev/null 2>&1 || true
  fi

  if [[ "${KEEP_SERVER}" != "1" ]] && [[ -n "${HELPER_PID}" ]]; then
    kill "${HELPER_PID}" >/dev/null 2>&1 || true
    wait "${HELPER_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

(
  cd "${REPO_ROOT}"
  PYTHONPATH=src "${PYTHON_BIN}" "${MEMBER_SMOKE_SCRIPT}" \
    --host "${HOST}" \
    --port "${PORT}" \
    --advertise-host "${ADVERTISE_HOST}" \
    --operation-name "Chromebook Member Smoke" \
    --metadata-path "${METADATA_PATH}" \
    >"${HELPER_LOG}" 2>&1
) &
HELPER_PID="$!"

JOIN_URL=""
HELPER_READY="0"
for _ in $(seq 1 "${HELPER_READY_ATTEMPTS}"); do
  if [[ -f "${METADATA_PATH}" ]]; then
    JOIN_URL="$("${PYTHON_BIN}" - <<'PY' "${METADATA_PATH}"
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
print(payload.get("join_url", ""))
PY
)"
    if [[ -n "${JOIN_URL}" ]] && "${CURL_BIN}" -sS -I "${JOIN_URL}" >/dev/null; then
      HELPER_READY="1"
      break
    fi
  fi
  sleep "${HELPER_READY_SLEEP_SECONDS}"
done

if [[ "${HELPER_READY}" != "1" ]]; then
  write_failure_result \
    "helper-ready" \
    "Smoke helper never became reachable at ${JOIN_URL:-<missing join_url>}."
  if [[ -z "${JOIN_URL}" ]]; then
    echo "Failed to resolve join URL from ${METADATA_PATH}" >&2
  else
    echo "Smoke helper never became reachable at ${JOIN_URL}" >&2
  fi
  cat "${HELPER_LOG}" >&2 || true
  exit 1
fi

run_stage \
  "prepare" \
  "Chromebook prepare step failed." \
  bash "${LAB_CONTROL_SCRIPT}" prepare \
  "${LAB_CONTROL_ARGS[@]}"

capture_launch_preflight

run_stage \
  "launch" \
  "Chromebook launch step failed." \
  bash "${LAB_CONTROL_SCRIPT}" launch \
  "${LAB_CONTROL_ARGS[@]}" \
  --start-url "about:blank"

run_stage \
  "smoke-runner" \
  "Chromebook smoke runner failed." \
  "${PYTHON_BIN}" "${CDP_RUNNER_SCRIPT}" \
  "${PYTHON_SMOKE_ARGS[@]}"

echo
echo "Chromebook smoke artifacts:"
echo "  run dir:    ${RUN_DIR}"
echo "  helper log: ${HELPER_LOG}"
echo "  metadata:   ${METADATA_PATH}"
echo "  result:     ${RUN_DIR}/result.json"
