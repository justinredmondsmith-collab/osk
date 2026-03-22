#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/chromebook_lab_control.sh <prepare|launch|cleanup> [options]

Manage a dedicated Chromebook lab browser session over SSH.

Actions:
  prepare                  Verify reachability, stop the prior lab browser, and reset the lab profile
  launch                   Launch the lab browser with an explicit user-data-dir and debug port
  cleanup                  Stop the prior lab browser session

Options:
  --ssh-target TARGET      SSH host/user target for the Chromebook (required)
  --ssh-port PORT          SSH port for the Chromebook control path
  --ssh-identity PATH      SSH private key used for the Chromebook control path
  --chrome-binary PATH     Chrome binary or command on the Chromebook (default: chromium)
  --profile-dir PATH       Disposable browser profile path (default: /var/tmp/osk-chromebook-lab)
  --debug-port PORT        Remote debugging port (default: 9222)
  --window-size WxH        Browser window size for launch (default: 1440,900)
  --start-url URL          Initial URL for the lab browser (default: about:blank)
  --dry-run                Print the command plan without executing remote commands
  --json                   Emit the dry-run command plan as JSON
  -h, --help               Show this help text
EOF
}

render_command() {
  local out=""
  local arg
  for arg in "$@"; do
    printf -v out '%s%s%q' "${out}" "${out:+ }" "${arg}"
  done
  printf '%s\n' "${out}"
}

fail() {
  echo "${1}" >&2
  exit 1
}

ensure_safe_profile_dir() {
  case "${PROFILE_DIR}" in
    /var/tmp/osk-chromebook-lab|/var/tmp/osk-chromebook-lab/*|/tmp/osk-chromebook-lab|/tmp/osk-chromebook-lab/*)
      ;;
    *)
      fail "Refusing to operate on unsafe profile dir: ${PROFILE_DIR}"
      ;;
  esac
}

build_check_chrome_remote() {
  local remote
  printf -v remote \
    'set -euo pipefail; if [ -x %q ]; then exit 0; fi; command -v %q >/dev/null 2>&1' \
    "${CHROME_BINARY}" \
    "${CHROME_BINARY}"
  printf '%s\n' "${remote}"
}

build_kill_lab_browser_remote() {
  local remote
  printf -v remote \
    'set -euo pipefail; if [ -f %q ]; then kill "$(cat %q)" >/dev/null 2>&1 || true; rm -f %q; fi; resolved_bin="$(readlink -f "$(command -v %q)")"; if [ -n "$resolved_bin" ]; then pkill -u "$(id -un)" -f "^${resolved_bin} .*--user-data-dir=%q" >/dev/null 2>&1 || true; fi' \
    "${PID_FILE}" \
    "${PID_FILE}" \
    "${PID_FILE}" \
    "${CHROME_BINARY}" \
    "${PROFILE_DIR}"
  printf '%s\n' "${remote}"
}

build_reset_profile_remote() {
  local remote
  printf -v remote \
    'set -euo pipefail; rm -rf -- %q; mkdir -p -- %q' \
    "${PROFILE_DIR}" \
    "${PROFILE_DIR}"
  printf '%s\n' "${remote}"
}

build_launch_remote() {
  local remote
  printf -v remote \
    'set -euo pipefail; mkdir -p -- %q; nohup %q --user-data-dir=%q --remote-debugging-port=%q --no-first-run --no-default-browser-check --disable-sync --disable-background-networking --window-size=%q %q >%q 2>&1 </dev/null & echo $! > %q' \
    "${PROFILE_DIR}" \
    "${CHROME_BINARY}" \
    "${PROFILE_DIR}" \
    "${DEBUG_PORT}" \
    "${WINDOW_SIZE}" \
    "${START_URL}" \
    "${BROWSER_LOG}" \
    "${PID_FILE}"
  printf '%s\n' "${remote}"
}

run_remote() {
  local remote_script="$1"
  "${SSH_PREFIX[@]}" "${SSH_TARGET}" "${remote_script}"
}

emit_json_plan() {
  python - "$ACTION" "$SSH_TARGET" "$SSH_PORT" "$SSH_IDENTITY" "$PROFILE_DIR" "$DEBUG_PORT" "$CHROME_BINARY" "${SSH_PREFIX[@]}" -- "$@" <<'PY'
import json
import sys

action, ssh_target, ssh_port, ssh_identity, profile_dir, debug_port, chrome_binary, *rest = sys.argv[1:]
separator_index = rest.index("--")
ssh_prefix = rest[:separator_index]
pairs = rest[separator_index + 1 :]
steps = []
for index in range(0, len(pairs), 2):
    steps.append({"name": pairs[index], "command": pairs[index + 1]})

print(
    json.dumps(
        {
            "action": action,
            "ssh_target": ssh_target,
            "ssh_port": int(ssh_port) if ssh_port else None,
            "ssh_identity": ssh_identity or None,
            "profile_dir": profile_dir,
            "debug_port": int(debug_port),
            "chrome_binary": chrome_binary,
            "ssh_prefix": ssh_prefix,
            "steps": steps,
        },
        indent=2,
        sort_keys=True,
    )
)
PY
}

emit_plan() {
  if [[ "${JSON_OUTPUT}" == "1" ]]; then
    emit_json_plan "$@"
  else
    local index
    for ((index = 1; index <= $#; index += 2)); do
      printf '%s: %s\n' "${!index}" "${!((index + 1))}"
    done
  fi
}

ACTION="${1:-}"
if [[ -z "${ACTION}" || "${ACTION}" == -* ]]; then
  usage >&2
  exit 1
fi
shift

SSH_TARGET=""
SSH_PORT=""
SSH_IDENTITY=""
CHROME_BINARY="chromium"
PROFILE_DIR="/var/tmp/osk-chromebook-lab"
DEBUG_PORT="9222"
WINDOW_SIZE="1440,900"
START_URL="about:blank"
DRY_RUN="0"
JSON_OUTPUT="0"
SSH_PREFIX=("ssh" "-F" "/dev/null")

while [[ $# -gt 0 ]]; do
  case "$1" in
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
    --chrome-binary)
      CHROME_BINARY="${2:?missing value for --chrome-binary}"
      shift 2
      ;;
    --profile-dir)
      PROFILE_DIR="${2:?missing value for --profile-dir}"
      shift 2
      ;;
    --debug-port)
      DEBUG_PORT="${2:?missing value for --debug-port}"
      shift 2
      ;;
    --window-size)
      WINDOW_SIZE="${2:?missing value for --window-size}"
      shift 2
      ;;
    --start-url)
      START_URL="${2:?missing value for --start-url}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN="1"
      shift
      ;;
    --json)
      JSON_OUTPUT="1"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "Unknown argument: $1"
      ;;
  esac
done

if [[ -z "${SSH_TARGET}" ]]; then
  fail "--ssh-target is required"
fi

ensure_safe_profile_dir
PID_FILE="${PROFILE_DIR}.pid"
BROWSER_LOG="${PROFILE_DIR}/browser.log"

if [[ -n "${SSH_PORT}" ]]; then
  SSH_PREFIX+=("-p" "${SSH_PORT}")
fi

if [[ -n "${SSH_IDENTITY}" ]]; then
  SSH_PREFIX+=("-i" "${SSH_IDENTITY}")
fi

check_ssh_cmd="$(render_command "${SSH_PREFIX[@]}" "${SSH_TARGET}" true)"
check_chrome_remote="$(build_check_chrome_remote)"
check_chrome_cmd="$(render_command "${SSH_PREFIX[@]}" "${SSH_TARGET}" "${check_chrome_remote}")"
kill_remote="$(build_kill_lab_browser_remote)"
kill_cmd="$(render_command "${SSH_PREFIX[@]}" "${SSH_TARGET}" "${kill_remote}")"
reset_remote="$(build_reset_profile_remote)"
reset_cmd="$(render_command "${SSH_PREFIX[@]}" "${SSH_TARGET}" "${reset_remote}")"
launch_remote="$(build_launch_remote)"
launch_cmd="$(render_command "${SSH_PREFIX[@]}" "${SSH_TARGET}" "${launch_remote}")"

case "${ACTION}" in
  prepare)
    if [[ "${DRY_RUN}" == "1" ]]; then
      emit_plan \
        check_ssh "${check_ssh_cmd}" \
        check_chrome "${check_chrome_cmd}" \
        kill_lab_browser "${kill_cmd}" \
        reset_profile "${reset_cmd}"
      exit 0
    fi
    "${SSH_PREFIX[@]}" "${SSH_TARGET}" true
    run_remote "${check_chrome_remote}"
    run_remote "${kill_remote}"
    run_remote "${reset_remote}"
    ;;
  launch)
    if [[ "${DRY_RUN}" == "1" ]]; then
      emit_plan launch_lab_browser "${launch_cmd}"
      exit 0
    fi
    run_remote "${launch_remote}"
    ;;
  cleanup)
    if [[ "${DRY_RUN}" == "1" ]]; then
      emit_plan kill_lab_browser "${kill_cmd}"
      exit 0
    fi
    run_remote "${kill_remote}"
    ;;
  *)
    usage >&2
    exit 1
    ;;
esac
