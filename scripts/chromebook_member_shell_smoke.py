#!/usr/bin/env python3
"""Host-side Chromebook member-shell smoke contract and dry-run entrypoint."""

from __future__ import annotations

import argparse
import contextlib
import json
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import httpx

DEFAULT_ARTIFACT_ROOT = Path("output/chromebook/member-shell-smoke")
DEFAULT_DEBUG_PORT = 9222
DEFAULT_TIMEOUT_SECONDS = 20.0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Drive the mocked Osk member-shell smoke flow on a dedicated Chromebook.",
    )
    parser.add_argument(
        "--chromebook-host",
        required=True,
        help="Host or IP used to identify the dedicated Chromebook lab device.",
    )
    parser.add_argument(
        "--ssh-target",
        default="",
        help="Optional SSH target. Defaults to --chromebook-host when omitted.",
    )
    parser.add_argument(
        "--ssh-port",
        type=int,
        default=0,
        help="Optional SSH port used for the Chromebook control path.",
    )
    parser.add_argument(
        "--ssh-identity",
        default="",
        help="Optional SSH private key used for the Chromebook control path.",
    )
    parser.add_argument(
        "--smoke-metadata",
        required=True,
        help="Path to the JSON metadata written by scripts/member_shell_smoke.py.",
    )
    parser.add_argument(
        "--artifact-root",
        default=str(DEFAULT_ARTIFACT_ROOT),
        help="Root directory for timestamped smoke artifacts.",
    )
    parser.add_argument(
        "--debug-port",
        type=int,
        default=DEFAULT_DEBUG_PORT,
        help="Remote Chrome debugging port for the Chromebook lab browser.",
    )
    parser.add_argument(
        "--local-debug-port",
        type=int,
        default=0,
        help="Optional local forwarded port for the SSH tunnel. Defaults to an ephemeral port.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Timeout for tunnel readiness and browser step waits.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Validate configuration, write a result contract, and exit without "
            "running the browser smoke."
        ),
    )
    parser.add_argument(
        "--timestamp",
        default="",
        help="Optional UTC timestamp label for deterministic artifact directories.",
    )
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    args = build_parser().parse_args(argv)
    if not args.ssh_target:
        args.ssh_target = args.chromebook_host
    return args


def load_smoke_metadata(metadata_path: Path) -> dict[str, Any]:
    payload = json.loads(metadata_path.read_text())
    join_url = str(payload.get("join_url") or "").strip()
    if not join_url:
        raise ValueError("Smoke metadata must include a non-empty join_url.")
    controls = payload.get("controls")
    if not isinstance(controls, dict):
        controls = {}
    return {
        "join_url": join_url,
        "operation_name": str(payload.get("operation_name") or "").strip() or None,
        "controls": controls,
    }


def timestamp_label(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    return current.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def make_artifact_dir(root: Path, *, now: datetime | None = None, label: str | None = None) -> Path:
    artifact_dir = root / (label or timestamp_label(now))
    artifact_dir.mkdir(parents=True, exist_ok=True)
    return artifact_dir


def build_ssh_tunnel_command(
    ssh_target: str,
    local_port: int,
    remote_port: int,
    ssh_port: int | None = None,
    ssh_identity: str | None = None,
) -> list[str]:
    command = [
        "ssh",
        "-F",
        "/dev/null",
        "-o",
        "ExitOnForwardFailure=yes",
        "-N",
        "-L",
        f"{local_port}:127.0.0.1:{remote_port}",
    ]
    if ssh_port:
        command.extend(["-p", str(ssh_port)])
    if ssh_identity:
        command.extend(["-i", ssh_identity])
    command.append(ssh_target)
    return command


def choose_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextlib.contextmanager
def managed_ssh_tunnel(
    ssh_target: str,
    local_port: int,
    remote_port: int,
    ssh_port: int | None = None,
    ssh_identity: str | None = None,
) -> Iterator[subprocess.Popen[str]]:
    process = subprocess.Popen(
        build_ssh_tunnel_command(
            ssh_target, local_port, remote_port, ssh_port, ssh_identity
        ),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    time.sleep(0.2)
    if process.poll() is not None:
        stderr = ""
        if process.stderr is not None:
            stderr = process.stderr.read().strip()
        raise RuntimeError(f"SSH tunnel failed to start: {stderr or process.returncode}")
    try:
        yield process
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def fetch_cdp_version(local_port: int, timeout_seconds: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_error: str | None = None
    url = f"http://127.0.0.1:{local_port}/json/version"
    while time.monotonic() < deadline:
        try:
            response = httpx.get(url, timeout=2.0)
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict) and payload.get("webSocketDebuggerUrl"):
                return payload
            last_error = "CDP version response missing webSocketDebuggerUrl"
        except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
            last_error = str(exc)
        time.sleep(0.25)
    raise RuntimeError(f"CDP version endpoint did not become ready: {last_error or url}")


def _slugify(label: str) -> str:
    return "".join(char.lower() if char.isalnum() else "-" for char in label).strip("-")


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


MEMBER_ID_READY_JS = """
() => {
  const value = document.querySelector('#runtime-member-id')?.textContent?.trim();
  return Boolean(value && value !== '--');
}
""".strip()

OUTBOX_HAS_ITEMS_JS = """
() => {
  return Number(
    document.querySelector('#runtime-outbox-count')?.textContent?.trim() || '0'
  ) >= 1;
}
""".strip()


def run_smoke_flow(
    local_port: int,
    smoke_metadata: dict[str, Any],
    artifact_dir: Path,
    timeout_seconds: float,
) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - exercised in real runtime only
        raise RuntimeError(
            "Playwright is not installed in this environment. Install dev dependencies first."
        ) from exc

    console_events: list[dict[str, str]] = []
    network_failures: list[dict[str, str | None]] = []
    page_errors: list[str] = []
    steps: list[dict[str, Any]] = []

    join_url = smoke_metadata["join_url"]
    wipe_url = str(smoke_metadata.get("controls", {}).get("wipe_url") or "").strip()
    if not wipe_url:
        raise RuntimeError("Smoke metadata did not expose a wipe_url control.")

    display_name = f"Chromebook Smoke {int(time.time())}"
    member_id: str | None = None
    operation_name: str | None = None

    def record_step(page, name: str, detail: dict[str, Any] | None = None) -> None:
        screenshot_name = f"{len(steps) + 1:02d}-{_slugify(name)}.png"
        page.screenshot(path=str(artifact_dir / screenshot_name))
        steps.append(
            {
                "name": name,
                "status": "passed",
                "screenshot": screenshot_name,
                "detail": detail or {},
            }
        )

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{local_port}")
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.pages[0] if context.pages else context.new_page()

        page.on(
            "console",
            lambda message: console_events.append(
                {"type": message.type, "text": message.text}
            ),
        )
        page.on(
            "pageerror",
            lambda error: page_errors.append(str(error)),
        )
        page.on(
            "requestfailed",
            lambda request: network_failures.append(
                {
                    "url": request.url,
                    "method": request.method,
                    "failure": request.failure,
                }
            ),
        )

        page.goto(join_url, wait_until="networkidle", timeout=int(timeout_seconds * 1000))
        record_step(page, "join-loaded", {"url": page.url})

        page.locator("#join-display-name").fill(display_name)
        page.locator("#join-form").evaluate("(form) => form.requestSubmit()")
        page.wait_for_url("**/member", timeout=int(timeout_seconds * 1000))
        page.wait_for_selector("#runtime-report-form", timeout=int(timeout_seconds * 1000))
        page.wait_for_function(
            MEMBER_ID_READY_JS,
            timeout=int(timeout_seconds * 1000),
        )
        operation_name = page.locator("#runtime-operation-name").text_content() or ""
        member_id = page.locator("#runtime-member-id").text_content() or ""
        record_step(
            page,
            "member-loaded",
            {
                "url": page.url,
                "display_name": display_name,
                "member_id": member_id.strip(),
                "operation_name": operation_name.strip(),
            },
        )

        context.set_offline(True)
        page.locator("#runtime-report-text").fill("Chromebook offline note")
        page.locator("#runtime-report-form").evaluate("(form) => form.requestSubmit()")
        page.wait_for_function(
            OUTBOX_HAS_ITEMS_JS,
            timeout=int(timeout_seconds * 1000),
        )
        queued_count = page.locator("#runtime-outbox-count").text_content() or "0"
        queued_state = page.locator("#runtime-outbox-state").text_content() or ""
        record_step(
            page,
            "offline-queue",
            {
                "queued_count": queued_count.strip(),
                "queued_state": queued_state.strip(),
            },
        )

        context.set_offline(False)
        page.wait_for_function(
            "() => document.querySelector('#runtime-outbox-count')?.textContent?.trim() === '0'",
            timeout=int(timeout_seconds * 1000),
        )
        record_step(page, "reconnect-drain")

        page.reload(wait_until="networkidle", timeout=int(timeout_seconds * 1000))
        page.wait_for_selector("#runtime-report-form", timeout=int(timeout_seconds * 1000))
        page.wait_for_function(
            MEMBER_ID_READY_JS,
            timeout=int(timeout_seconds * 1000),
        )
        reloaded_member_id = (page.locator("#runtime-member-id").text_content() or "").strip()
        if member_id is None or reloaded_member_id != member_id.strip():
            raise RuntimeError(
                f"Reloaded member session did not resume correctly: {reloaded_member_id!r}"
            )
        record_step(page, "reload-resume", {"member_id": reloaded_member_id})

        response = httpx.post(wipe_url, timeout=5.0)
        response.raise_for_status()
        page.wait_for_function(
            "() => document.body.innerText.includes('Local session cleared')",
            timeout=int(timeout_seconds * 1000),
        )
        record_step(page, "wipe-clear", {"wipe_status_code": response.status_code})

        _write_json(artifact_dir / "console-events.json", console_events)
        _write_json(artifact_dir / "network-failures.json", network_failures)
        _write_json(artifact_dir / "page-errors.json", page_errors)
        browser.close()

    return {
        "steps": steps,
        "display_name": display_name,
        "member_id": member_id.strip() if member_id else None,
        "operation_name": operation_name.strip() if operation_name else None,
        "console_event_count": len(console_events),
        "network_failure_count": len(network_failures),
        "page_error_count": len(page_errors),
    }


def build_result_payload(
    *,
    status: str,
    chromebook_host: str,
    ssh_target: str,
    ssh_port: int,
    ssh_identity: str,
    debug_port: int,
    smoke_metadata: dict[str, Any],
    artifact_dir: Path,
    local_debug_port: int | None = None,
    cdp_version: dict[str, Any] | None = None,
    steps: list[dict[str, Any]] | None = None,
    failure: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "chromebook_host": chromebook_host,
        "ssh_target": ssh_target,
        "ssh_port": ssh_port or None,
        "ssh_identity": ssh_identity or None,
        "debug_port": debug_port,
        "local_debug_port": local_debug_port,
        "artifact_dir": str(artifact_dir),
        "smoke_metadata": smoke_metadata,
        "cdp_version": cdp_version,
        "steps": steps or [],
        "failure": failure,
    }


def write_result(result_path: Path, payload: dict[str, Any]) -> None:
    result_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    metadata_path = Path(args.smoke_metadata).expanduser()
    if not metadata_path.exists():
        print(f"Smoke metadata file does not exist: {metadata_path}", file=sys.stderr)
        return 1

    try:
        smoke_metadata = load_smoke_metadata(metadata_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Failed to load smoke metadata: {exc}", file=sys.stderr)
        return 1

    artifact_root = Path(args.artifact_root).expanduser()
    artifact_dir = make_artifact_dir(artifact_root, label=args.timestamp or None)
    result_path = artifact_dir / "result.json"
    _write_json(artifact_dir / "smoke-metadata.json", smoke_metadata)

    if args.dry_run:
        payload = build_result_payload(
            status="dry_run",
            chromebook_host=args.chromebook_host,
            ssh_target=args.ssh_target,
            ssh_port=args.ssh_port,
            ssh_identity=args.ssh_identity,
            debug_port=args.debug_port,
            smoke_metadata=smoke_metadata,
            artifact_dir=artifact_dir,
        )
        write_result(result_path, payload)
        return 0

    local_debug_port = args.local_debug_port or choose_local_port()
    try:
        with managed_ssh_tunnel(
            args.ssh_target,
            local_debug_port,
            args.debug_port,
            args.ssh_port or None,
            args.ssh_identity or None,
        ):
            cdp_version = fetch_cdp_version(local_debug_port, args.timeout_seconds)
            _write_json(artifact_dir / "cdp-version.json", cdp_version)
            smoke_result = run_smoke_flow(
                local_debug_port,
                smoke_metadata,
                artifact_dir,
                args.timeout_seconds,
            )
    except Exception as exc:
        payload = build_result_payload(
            status="failed",
            chromebook_host=args.chromebook_host,
            ssh_target=args.ssh_target,
            ssh_port=args.ssh_port,
            ssh_identity=args.ssh_identity,
            debug_port=args.debug_port,
            local_debug_port=local_debug_port,
            smoke_metadata=smoke_metadata,
            artifact_dir=artifact_dir,
            cdp_version=locals().get("cdp_version"),
            failure={
                "message": str(exc),
                "type": exc.__class__.__name__,
            },
        )
        write_result(result_path, payload)
        print(f"Chromebook smoke failed: {exc}", file=sys.stderr)
        return 1

    payload = build_result_payload(
        status="passed",
        chromebook_host=args.chromebook_host,
        ssh_target=args.ssh_target,
        ssh_port=args.ssh_port,
        ssh_identity=args.ssh_identity,
        debug_port=args.debug_port,
        local_debug_port=local_debug_port,
        smoke_metadata=smoke_metadata,
        artifact_dir=artifact_dir,
        cdp_version=cdp_version,
        steps=smoke_result["steps"],
    )
    payload["summary"] = {
        "display_name": smoke_result["display_name"],
        "member_id": smoke_result["member_id"],
        "operation_name": smoke_result["operation_name"],
        "console_event_count": smoke_result["console_event_count"],
        "network_failure_count": smoke_result["network_failure_count"],
        "page_error_count": smoke_result["page_error_count"],
    }
    write_result(result_path, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
