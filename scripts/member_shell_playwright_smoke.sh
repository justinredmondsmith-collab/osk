#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/member_shell_playwright_smoke.sh [options]

Start the disposable member-shell smoke helper, then drive a real browser through
/join -> /member with Playwright CLI. This script is intended for environments
where localhost is reachable from the browser session.

Options:
  --host HOST              Bind host for the helper server (default: 127.0.0.1)
  --port PORT              Bind port for the helper server (default: 8123)
  --advertise-host HOST    Hostname/IP embedded in the QR/join URL (default: 127.0.0.1)
  --session NAME           Playwright CLI session name (default: osk-member-shell-smoke)
  --headed                 Open the browser headed instead of headless
  --keep-server            Leave the helper server running after the smoke completes
  -h, --help               Show this help text
EOF
}

HOST="127.0.0.1"
PORT="8123"
ADVERTISE_HOST="127.0.0.1"
SESSION_NAME="osk-member-shell-smoke"
HEADED="0"
KEEP_SERVER="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      HOST="${2:?missing value for --host}"
      shift 2
      ;;
    --port)
      PORT="${2:?missing value for --port}"
      shift 2
      ;;
    --advertise-host)
      ADVERTISE_HOST="${2:?missing value for --advertise-host}"
      shift 2
      ;;
    --session)
      SESSION_NAME="${2:?missing value for --session}"
      shift 2
      ;;
    --headed)
      HEADED="1"
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

if ! command -v npx >/dev/null 2>&1; then
  echo "npx is required on PATH for Playwright CLI." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PWCLI=""
for candidate in \
  "${CODEX_HOME:-}/skills/playwright/scripts/playwright_cli.sh" \
  "${HOME}/.codex/skills/playwright/scripts/playwright_cli.sh" \
  "/var/home/${USER}/.codex/skills/playwright/scripts/playwright_cli.sh"
do
  if [[ -n "${candidate}" && -f "${candidate}" ]]; then
    PWCLI="${candidate}"
    break
  fi
done

if [[ -z "${PWCLI}" ]]; then
  echo "Playwright CLI wrapper not found in CODEX_HOME or standard skill locations." >&2
  exit 1
fi

OUTPUT_DIR="${REPO_ROOT}/output/playwright/member-shell-smoke"
mkdir -p "${OUTPUT_DIR}"
METADATA_PATH="${OUTPUT_DIR}/metadata.json"
HELPER_LOG="${OUTPUT_DIR}/helper.log"
RESULT_PATH="${OUTPUT_DIR}/result.json"

HELPER_PID=""
cleanup() {
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
    --operation-name "Playwright Member Smoke" \
    --metadata-path "${METADATA_PATH}" \
    >"${HELPER_LOG}" 2>&1
) &
HELPER_PID="$!"

JOIN_URL=""
WIPE_URL=""
PROMOTE_LATEST_URL=""
for _ in $(seq 1 40); do
  if [[ -f "${METADATA_PATH}" ]]; then
    JOIN_URL="$(python - <<'PY' "${METADATA_PATH}"
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
print(payload["join_url"])
PY
)"
    WIPE_URL="$(python - <<'PY' "${METADATA_PATH}"
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
print(payload.get("controls", {}).get("wipe_url", ""))
PY
)"
    PROMOTE_LATEST_URL="$(python - <<'PY' "${METADATA_PATH}"
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
print(payload.get("controls", {}).get("promote_latest_url", ""))
PY
)"
    if curl -sS -I "${JOIN_URL}" >/dev/null; then
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

if ! curl -sS -I "${JOIN_URL}" >/dev/null; then
  echo "Smoke helper did not become reachable at ${JOIN_URL}" >&2
  cat "${HELPER_LOG}" >&2 || true
  exit 1
fi

if [[ -z "${WIPE_URL}" ]]; then
  echo "Smoke helper metadata did not expose a wipe control URL." >&2
  cat "${METADATA_PATH}" >&2 || true
  exit 1
fi

if [[ -z "${PROMOTE_LATEST_URL}" ]]; then
  echo "Smoke helper metadata did not expose a promote-latest control URL." >&2
  cat "${METADATA_PATH}" >&2 || true
  exit 1
fi

PROMOTE_LATEST_URL_JSON="$(python - <<'PY' "${PROMOTE_LATEST_URL}"
import json
import sys

print(json.dumps(sys.argv[1]))
PY
)"

SMOKE_CODE=$(cat <<'EOF'
const promoteUrl = __PROMOTE_LATEST_URL__;
const displayName = `Smoke ${Date.now()}`;
await page.waitForLoadState("networkidle");
await page.locator("#join-display-name").fill(displayName);
await Promise.all([
  page.waitForURL("**/member"),
  page.locator("#join-form").evaluate((form) => form.requestSubmit()),
]);
await page.waitForSelector("#runtime-report-form");
await page.waitForFunction(() => {
  const memberId = document.querySelector("#runtime-member-id")?.textContent?.trim();
  return memberId && memberId !== "--";
}, { timeout: 15000 });

const promoteResult = await page.evaluate(async (url) => {
  const response = await fetch(url, { method: "POST" });
  let payload = {};
  try {
    payload = await response.json();
  } catch (error) {
    payload = {};
  }
  return {
    ok: response.ok,
    status: response.status,
    payload,
  };
}, promoteUrl);
if (!promoteResult.ok) {
  throw new Error(`Promote latest failed: ${promoteResult.status} ${JSON.stringify(promoteResult.payload)}`);
}

await page.waitForFunction(() => {
  const role = document.querySelector("#runtime-role")?.textContent?.trim()?.toLowerCase() || "";
  return role.includes("sensor");
}, { timeout: 15000 });
await page.waitForFunction(() => {
  const audioButton = document.querySelector("#runtime-sensor-smoke-audio");
  const frameButton = document.querySelector("#runtime-sensor-smoke-frame");
  const controls = document.querySelector("#runtime-sensor-smoke-actions");
  return Boolean(
    controls &&
    !controls.hidden &&
    audioButton &&
    frameButton &&
    !audioButton.disabled &&
    !frameButton.disabled
  );
}, { timeout: 15000 });

await page.context().setOffline(true);
await page.locator("#runtime-report-text").fill("Playwright offline note");
await page.locator("#runtime-report-form").evaluate((form) => form.requestSubmit());
await page.locator("#runtime-sensor-smoke-audio").click();
await page.locator("#runtime-sensor-smoke-frame").click();
await page.waitForFunction(() => {
  return Number(document.querySelector("#runtime-outbox-count")?.textContent?.trim() || "0") >= 3;
}, { timeout: 10000 });

const queuedCount = document.querySelector("#runtime-outbox-count")?.textContent?.trim() || "0";
const queuedState = document.querySelector("#runtime-outbox-state")?.textContent?.trim() || "";
const sensorState = document.querySelector("#runtime-sensor-state")?.textContent?.trim() || "";
const sensorDetail = document.querySelector("#runtime-sensor-detail")?.textContent?.trim() || "";

await page.context().setOffline(false);
await page.waitForFunction(() => {
  return document.querySelector("#runtime-outbox-count")?.textContent?.trim() === "0";
}, { timeout: 20000 });

await page.reload({ waitUntil: "networkidle" });
await page.waitForSelector("#runtime-report-form");
await page.waitForFunction(() => {
  const memberId = document.querySelector("#runtime-member-id")?.textContent?.trim();
  return memberId && memberId !== "--";
}, { timeout: 15000 });

const operationName = document.querySelector("#runtime-operation-name")?.textContent?.trim() || "";
const connectionLabel = document.querySelector("#runtime-connection-label")?.textContent?.trim() || "";
const reportStatus = document.querySelector("#runtime-report-status")?.textContent?.trim() || "";
const sessionState = document.querySelector("#runtime-session-state")?.textContent?.trim() || "";
const role = document.querySelector("#runtime-role")?.textContent?.trim() || "";

return JSON.stringify({
  url: page.url(),
  displayName,
  operationName,
  role,
  connectionLabel,
  sessionState,
  queuedCount,
  queuedState,
  sensorState,
  sensorDetail,
  reportStatus,
  promotePayload: promoteResult.payload,
});
EOF
)
SMOKE_CODE="${SMOKE_CODE/__PROMOTE_LATEST_URL__/${PROMOTE_LATEST_URL_JSON}}"

WIPE_VERIFY_CODE=$(cat <<'EOF'
await page.waitForFunction(() => {
  return document.body.innerText.includes("Local session cleared");
}, { timeout: 15000 });

return JSON.stringify({
  url: page.url(),
  title: document.title,
  body: document.body.innerText,
});
EOF
)

pushd "${OUTPUT_DIR}" >/dev/null
export PLAYWRIGHT_CLI_SESSION="${SESSION_NAME}"

if [[ "${HEADED}" == "1" ]]; then
  bash "${PWCLI}" --session "${SESSION_NAME}" open "${JOIN_URL}" --headed
else
  bash "${PWCLI}" --session "${SESSION_NAME}" open "${JOIN_URL}"
fi

bash "${PWCLI}" --session "${SESSION_NAME}" run-code "${SMOKE_CODE}" | tee "${RESULT_PATH}"
curl -sS -X POST "${WIPE_URL}" >/dev/null
bash "${PWCLI}" --session "${SESSION_NAME}" run-code "${WIPE_VERIFY_CODE}" | tee -a "${RESULT_PATH}"
bash "${PWCLI}" --session "${SESSION_NAME}" screenshot
bash "${PWCLI}" --session "${SESSION_NAME}" close >/dev/null 2>&1 || true
popd >/dev/null

echo
echo "Smoke artifacts:"
echo "  helper log: ${HELPER_LOG}"
echo "  metadata:   ${METADATA_PATH}"
echo "  result:     ${RESULT_PATH}"
echo "  screenshot: ${OUTPUT_DIR}"
