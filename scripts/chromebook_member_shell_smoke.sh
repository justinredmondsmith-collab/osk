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

cleanup() {
  local cleanup_args=(
    "${LAB_CONTROL_ARGS[@]}"
  )

  if [[ "${KEEP_BROWSER}" != "1" ]]; then
    bash "${SCRIPT_DIR}/chromebook_lab_control.sh" cleanup \
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
  PYTHONPATH=src python scripts/member_shell_smoke.py \
    --host "${HOST}" \
    --port "${PORT}" \
    --advertise-host "${ADVERTISE_HOST}" \
    --operation-name "Chromebook Member Smoke" \
    --metadata-path "${METADATA_PATH}" \
    >"${HELPER_LOG}" 2>&1
) &
HELPER_PID="$!"

JOIN_URL=""
for _ in $(seq 1 40); do
  if [[ -f "${METADATA_PATH}" ]]; then
    JOIN_URL="$(python - <<'PY' "${METADATA_PATH}"
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
print(payload.get("join_url", ""))
PY
)"
    if [[ -n "${JOIN_URL}" ]] && curl -sS -I "${JOIN_URL}" >/dev/null; then
      break
    fi
  fi
  sleep 1
done

if [[ -z "${JOIN_URL}" ]]; then
  echo "Failed to resolve join URL from ${METADATA_PATH}" >&2
  cat "${HELPER_LOG}" >&2 || true
  exit 1
fi

bash "${SCRIPT_DIR}/chromebook_lab_control.sh" prepare \
  "${LAB_CONTROL_ARGS[@]}"

bash "${SCRIPT_DIR}/chromebook_lab_control.sh" launch \
  "${LAB_CONTROL_ARGS[@]}" \
  --start-url "about:blank"

python "${SCRIPT_DIR}/chromebook_member_shell_smoke.py" \
  "${PYTHON_SMOKE_ARGS[@]}"

echo
echo "Chromebook smoke artifacts:"
echo "  run dir:    ${RUN_DIR}"
echo "  helper log: ${HELPER_LOG}"
echo "  metadata:   ${METADATA_PATH}"
echo "  result:     ${RUN_DIR}/result.json"
