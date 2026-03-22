#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/chromebook_reverse_tunnel.sh <run|preflight|install-user-service|uninstall-user-service|service-status> [options]

Manage a persistent reverse SSH tunnel from a Chromebook Crostini container back
to the host running the Osk repo.

Actions:
  run                     Run the reverse SSH tunnel in the foreground
  preflight               Verify host auth and confirm the host port is free
  install-user-service    Install and enable a systemd --user service for the tunnel
  uninstall-user-service  Disable and remove the systemd --user service
  service-status          Show systemd --user service status

Options:
  --host-target TARGET    Host SSH target for the reverse tunnel
  --identity PATH         SSH private key for the reverse tunnel (default: ~/.ssh/id_ed25519)
  --remote-port PORT      Reverse-tunnel port exposed on the host (default: 22022)
  --local-host HOST       Local host forwarded from the Chromebook side (default: localhost)
  --local-port PORT       Local port forwarded from the Chromebook side (default: 22)
  --service-name NAME     systemd user service name (default: osk-chromebook-reverse-tunnel.service)
  --service-dir PATH      systemd user service directory (default: ~/.config/systemd/user)
  --allow-existing-port   Skip the host-port collision check
  --dry-run               Print the planned command(s) without executing them
  --json                  Emit dry-run output as JSON
  -h, --help              Show this help text
EOF
}

fail() {
  echo "${1}" >&2
  exit 1
}

render_command() {
  local out=""
  local arg
  for arg in "$@"; do
    printf -v out '%s%s%q' "${out}" "${out:+ }" "${arg}"
  done
  printf '%s\n' "${out}"
}

expand_path() {
  local value="$1"
  if [[ "${value}" == "~" ]]; then
    printf '%s\n' "${HOME}"
  elif [[ "${value}" == "~/"* ]]; then
    printf '%s/%s\n' "${HOME}" "${value#"~/"}"
  else
    printf '%s\n' "${value}"
  fi
}

build_ssh_command() {
  printf '%s\n' \
    "ssh" \
    "-F" \
    "/dev/null" \
    "-i" \
    "${IDENTITY_PATH}" \
    "-o" \
    "ExitOnForwardFailure=yes" \
    "-o" \
    "ServerAliveInterval=15" \
    "-o" \
    "ServerAliveCountMax=3" \
    "-o" \
    "StrictHostKeyChecking=accept-new" \
    "-N" \
    "-R" \
    "${REMOTE_PORT}:${LOCAL_HOST}:${LOCAL_PORT}" \
    "${HOST_TARGET}"
}

build_host_ssh_command() {
  printf '%s\n' \
    "ssh" \
    "-F" \
    "/dev/null" \
    "-i" \
    "${IDENTITY_PATH}" \
    "-o" \
    "BatchMode=yes" \
    "-o" \
    "ConnectTimeout=5" \
    "-o" \
    "StrictHostKeyChecking=accept-new" \
    "${HOST_TARGET}"
}

build_run_command() {
  mapfile -t ssh_command < <(build_ssh_command)
  render_command "${ssh_command[@]}"
}

build_host_access_command() {
  mapfile -t ssh_command < <(build_host_ssh_command)
  render_command "${ssh_command[@]}" "true"
}

build_remote_port_probe_command() {
  mapfile -t ssh_command < <(build_host_ssh_command)
  render_command \
    "${ssh_command[@]}" \
    "bash -lc 'cat < /dev/null > /dev/tcp/127.0.0.1/${REMOTE_PORT}'"
}

build_service_unit() {
  local script_path="$1"
  cat <<EOF
[Unit]
Description=Osk Chromebook Reverse Tunnel
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
ExecStart=${script_path} run --host-target ${HOST_TARGET} --identity ${IDENTITY_PATH} --remote-port ${REMOTE_PORT} --local-host ${LOCAL_HOST} --local-port ${LOCAL_PORT}
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF
}

write_service_unit() {
  local script_path="$1"
  mkdir -p "${SERVICE_DIR}"
  build_service_unit "${script_path}" > "${SERVICE_PATH}"
}

verify_host_access() {
  mapfile -t ssh_command < <(build_host_ssh_command)
  if ! "${ssh_command[@]}" "true" >/dev/null 2>&1; then
    fail "Unable to authenticate to ${HOST_TARGET} with ${IDENTITY_PATH}. Verify Chromebook-to-host SSH auth before starting the reverse tunnel."
  fi
}

verify_remote_port_is_free() {
  mapfile -t ssh_command < <(build_host_ssh_command)
  if "${ssh_command[@]}" "bash -lc 'cat < /dev/null > /dev/tcp/127.0.0.1/${REMOTE_PORT}'" >/dev/null 2>&1; then
    fail "Host port ${REMOTE_PORT} on ${HOST_TARGET} is already accepting connections. Stop the existing manual tunnel or choose a different --remote-port, or rerun with --allow-existing-port."
  fi
}

run_preflight() {
  verify_host_access
  if [[ "${ALLOW_EXISTING_PORT}" != "1" ]]; then
    verify_remote_port_is_free
  fi
}

emit_json_plan() {
  python - "$ACTION" "$HOST_TARGET" "$IDENTITY_PATH" "$REMOTE_PORT" "$LOCAL_HOST" "$LOCAL_PORT" "$SERVICE_NAME" "$SERVICE_DIR" "$SERVICE_PATH" "$RUN_COMMAND" "$HOST_ACCESS_COMMAND" "$PORT_PROBE_COMMAND" "$SCRIPT_PATH" "$ALLOW_EXISTING_PORT" <<'PY'
import json
import sys

(
    action,
    host_target,
    identity_path,
    remote_port,
    local_host,
    local_port,
    service_name,
    service_dir,
    service_path,
    run_command,
    host_access_command,
    port_probe_command,
    script_path,
    allow_existing_port,
) = sys.argv[1:]

payload = {
    "action": action,
    "allow_existing_port": allow_existing_port == "1",
    "host_target": host_target,
    "host_access_command": host_access_command,
    "identity_path": identity_path,
    "local_host": local_host,
    "local_port": int(local_port),
    "port_probe_command": port_probe_command,
    "remote_port": int(remote_port),
    "run_command": run_command,
    "script_path": script_path,
    "service_dir": service_dir,
    "service_name": service_name,
    "service_path": service_path,
}

print(json.dumps(payload, indent=2, sort_keys=True))
PY
}

ACTION="${1:-}"
if [[ -z "${ACTION}" || "${ACTION}" == -* ]]; then
  usage >&2
  exit 1
fi
shift

HOST_TARGET=""
IDENTITY_PATH="~/.ssh/id_ed25519"
REMOTE_PORT="22022"
LOCAL_HOST="localhost"
LOCAL_PORT="22"
SERVICE_NAME="osk-chromebook-reverse-tunnel.service"
SERVICE_DIR="~/.config/systemd/user"
ALLOW_EXISTING_PORT="0"
DRY_RUN="0"
JSON_OUTPUT="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host-target)
      HOST_TARGET="${2:?missing value for --host-target}"
      shift 2
      ;;
    --identity)
      IDENTITY_PATH="${2:?missing value for --identity}"
      shift 2
      ;;
    --remote-port)
      REMOTE_PORT="${2:?missing value for --remote-port}"
      shift 2
      ;;
    --local-host)
      LOCAL_HOST="${2:?missing value for --local-host}"
      shift 2
      ;;
    --local-port)
      LOCAL_PORT="${2:?missing value for --local-port}"
      shift 2
      ;;
    --service-name)
      SERVICE_NAME="${2:?missing value for --service-name}"
      shift 2
      ;;
    --service-dir)
      SERVICE_DIR="${2:?missing value for --service-dir}"
      shift 2
      ;;
    --allow-existing-port)
      ALLOW_EXISTING_PORT="1"
      shift
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

case "${ACTION}" in
  run|preflight|install-user-service|uninstall-user-service|service-status)
    ;;
  *)
    usage >&2
    exit 1
    ;;
esac

HOST_TARGET_REQUIRED="0"
case "${ACTION}" in
  run|preflight|install-user-service)
    HOST_TARGET_REQUIRED="1"
    ;;
esac

if [[ "${HOST_TARGET_REQUIRED}" == "1" ]] && [[ -z "${HOST_TARGET}" ]]; then
  fail "--host-target is required for ${ACTION}"
fi

IDENTITY_PATH="$(expand_path "${IDENTITY_PATH}")"
SERVICE_DIR="$(expand_path "${SERVICE_DIR}")"
SERVICE_PATH="${SERVICE_DIR}/${SERVICE_NAME}"
SCRIPT_PATH="$(readlink -f "$0")"
RUN_COMMAND=""
HOST_ACCESS_COMMAND=""
PORT_PROBE_COMMAND=""

if [[ -n "${HOST_TARGET}" ]]; then
  RUN_COMMAND="$(build_run_command)"
  HOST_ACCESS_COMMAND="$(build_host_access_command)"
  PORT_PROBE_COMMAND="$(build_remote_port_probe_command)"
fi

if [[ "${DRY_RUN}" == "1" ]]; then
  if [[ "${JSON_OUTPUT}" == "1" ]]; then
    emit_json_plan
  else
    printf 'action: %s\n' "${ACTION}"
    if [[ -n "${RUN_COMMAND}" ]]; then
      printf 'run_command: %s\n' "${RUN_COMMAND}"
      printf 'host_access_command: %s\n' "${HOST_ACCESS_COMMAND}"
      if [[ "${ALLOW_EXISTING_PORT}" != "1" ]]; then
        printf 'port_probe_command: %s\n' "${PORT_PROBE_COMMAND}"
      fi
    fi
    if [[ "${ACTION}" == "install-user-service" ]]; then
      printf 'service_path: %s\n' "${SERVICE_PATH}"
    fi
  fi
  exit 0
fi

case "${ACTION}" in
  run)
    run_preflight
    exec ssh \
      -F /dev/null \
      -i "${IDENTITY_PATH}" \
      -o ExitOnForwardFailure=yes \
      -o ServerAliveInterval=15 \
      -o ServerAliveCountMax=3 \
      -o StrictHostKeyChecking=accept-new \
      -N \
      -R "${REMOTE_PORT}:${LOCAL_HOST}:${LOCAL_PORT}" \
      "${HOST_TARGET}"
    ;;
  preflight)
    run_preflight
    printf 'Preflight checks passed for %s on host port %s.\n' "${HOST_TARGET}" "${REMOTE_PORT}"
    ;;
  install-user-service)
    systemctl --user stop "${SERVICE_NAME}" >/dev/null 2>&1 || true
    systemctl --user reset-failed "${SERVICE_NAME}" >/dev/null 2>&1 || true
    run_preflight
    write_service_unit "${SCRIPT_PATH}"
    systemctl --user daemon-reload
    systemctl --user enable --now "${SERVICE_PATH}"
    ;;
  uninstall-user-service)
    systemctl --user disable --now "${SERVICE_NAME}" >/dev/null 2>&1 || true
    rm -f "${SERVICE_PATH}"
    systemctl --user daemon-reload
    ;;
  service-status)
    systemctl --user --no-pager --full status "${SERVICE_NAME}"
    ;;
esac
