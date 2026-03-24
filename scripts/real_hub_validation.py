#!/usr/bin/env python3
"""Host-side real-hub validation contract and dry-run entrypoint."""

from __future__ import annotations

import argparse
import contextlib
import ipaddress
import json
import os
import shlex
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urljoin, urlsplit

import httpx

from osk.chromebook_smoke_artifacts import build_provenance

DEFAULT_ARTIFACT_ROOT = Path("output/validation/real-hub")
DEFAULT_SCENARIO = "baseline"
DEFAULT_DEBUG_PORT = 9222
DEFAULT_TIMEOUT_SECONDS = 20.0
ADMIN_TOKEN_HEADER = "X-Osk-Coordinator-Token"
OPERATOR_SESSION_HEADER = "X-Osk-Operator-Session"

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

OUTBOX_EMPTY_JS = """
() => {
  return document.querySelector('#runtime-outbox-count')?.textContent?.trim() === '0';
}
""".strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and record the contract for a real Osk hub validation run.",
    )
    parser.add_argument(
        "--hub-url",
        required=True,
        help="Base URL for the real running Osk hub under validation.",
    )
    parser.add_argument(
        "--join-url",
        required=True,
        help="Join URL for the real operation under validation.",
    )
    parser.add_argument(
        "--device-id",
        required=True,
        help="Stable identifier for the real device used in the validation run.",
    )
    parser.add_argument(
        "--ssh-target",
        default="",
        help="Optional SSH target for the Chromebook control path. Defaults to --device-id.",
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
        "--artifact-root",
        default=str(DEFAULT_ARTIFACT_ROOT),
        help="Root directory for timestamped real-hub validation artifacts.",
    )
    parser.add_argument(
        "--scenario",
        default=DEFAULT_SCENARIO,
        help="Scenario label for the validation run. Defaults to 'baseline'.",
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
        help="Write the contract artifacts without attempting runtime execution.",
    )
    parser.add_argument(
        "--timestamp",
        default="",
        help="Optional UTC timestamp label for deterministic artifact directories.",
    )
    return parser


def _normalized_url(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    parsed = urlsplit(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{field_name} must be an absolute http:// or https:// URL.")
    return normalized


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    args = build_parser().parse_args(argv)
    args.hub_url = _normalized_url(args.hub_url, field_name="hub_url")
    args.join_url = _normalized_url(args.join_url, field_name="join_url")
    args.device_id = args.device_id.strip()
    if not args.device_id:
        raise ValueError("device_id must be a non-empty string.")
    args.ssh_target = args.ssh_target.strip() or args.device_id
    args.scenario = args.scenario.strip() or DEFAULT_SCENARIO
    return args


def timestamp_label(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    return current.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def make_artifact_dir(root: Path, *, now: datetime | None = None, label: str | None = None) -> Path:
    artifact_dir = root / (label or timestamp_label(now))
    artifact_dir.mkdir(parents=True, exist_ok=True)
    return artifact_dir


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _slugify(label: str) -> str:
    return "".join(char.lower() if char.isalnum() else "-" for char in label).strip("-")


def _baseline_steps() -> list[dict[str, Any]]:
    return [
        {
            "id": "hub_reachable",
            "label": "Hub reachable",
            "status": "contract_only",
            "automated": False,
        },
        {
            "id": "join_loads",
            "label": "Join URL loads",
            "status": "contract_only",
            "automated": False,
        },
        {
            "id": "member_session_establishes",
            "label": "Member session establishes",
            "status": "contract_only",
            "automated": False,
        },
        {
            "id": "disconnect_reconnect_observed",
            "label": "Disconnect and reconnect behavior observed",
            "status": "contract_only",
            "automated": False,
        },
        {
            "id": "wipe_observed",
            "label": "Live wipe observed",
            "status": "contract_only",
            "automated": False,
        },
        {
            "id": "operator_closure_captured",
            "label": "Operator-side readiness and audit closure captured",
            "status": "contract_only",
            "automated": False,
        },
    ]


def _steps_for_scenario(scenario: str) -> list[dict[str, Any]]:
    steps = [dict(step) for step in _baseline_steps()]
    if scenario == "restart":
        steps.append(
            {
                "id": "hub_restart_resume_observed",
                "label": "Hub restart and session resume observed",
                "status": "contract_only",
                "automated": False,
            }
        )
    return steps


def _merge_step_updates(
    step_updates: list[dict[str, Any]],
    *,
    scenario: str = DEFAULT_SCENARIO,
) -> list[dict[str, Any]]:
    merged = _steps_for_scenario(scenario)
    by_id = {step["id"]: step for step in merged}
    for update in step_updates:
        step_id = str(update.get("id") or "").strip()
        if not step_id or step_id not in by_id:
            continue
        by_id[step_id].update(update)
    return merged


def _merge_summary(
    base_summary: dict[str, Any] | None,
    updates: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(base_summary or {})
    merged.update(updates or {})
    return merged


def _finalize_payload_status(
    payload: dict[str, Any],
    *,
    default_status: str,
) -> None:
    status = default_status
    for step in payload.get("steps") or []:
        if str((step or {}).get("status") or "").strip() == "failed_hardening_task":
            status = "failed_hardening_task"
            break
    payload["status"] = status


def _osk_cli_environment(repo_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    pythonpath_parts = [str(repo_root / "src")]
    existing_pythonpath = env.get("PYTHONPATH", "").strip()
    if existing_pythonpath:
        pythonpath_parts.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    return env


def _run_osk_cli(
    repo_root: Path,
    cli_args: list[str],
    *,
    timeout_seconds: float | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "osk", *cli_args],
        cwd=repo_root,
        env=_osk_cli_environment(repo_root),
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_seconds,
    )


def _write_completed_process(path: Path, process: subprocess.CompletedProcess[str]) -> None:
    _write_json(
        path,
        {
            "args": process.args,
            "returncode": process.returncode,
            "stdout": process.stdout,
            "stderr": process.stderr,
        },
    )


def _wait_for_hub_status(
    repo_root: Path,
    expected_statuses: set[str],
    *,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_snapshot: dict[str, Any] | None = None
    last_error: str | None = None
    while time.monotonic() < deadline:
        completed = _run_osk_cli(repo_root, ["status", "--json"], timeout_seconds=5.0)
        try:
            snapshot = json.loads(completed.stdout or "{}")
            if isinstance(snapshot, dict):
                last_snapshot = snapshot
                if str(snapshot.get("status") or "").strip() in expected_statuses:
                    return snapshot
        except json.JSONDecodeError as exc:
            last_error = str(exc)
        time.sleep(0.5)
    detail = last_error or (last_snapshot or {}).get("status") or "unknown"
    raise RuntimeError(
        "Hub status did not reach "
        f"{sorted(expected_statuses)} within {timeout_seconds:.1f}s: {detail}"
    )


def _perform_restart_cycle(
    *,
    args: argparse.Namespace,
    artifact_dir: Path,
    live_result: dict[str, Any] | None,
) -> dict[str, Any]:
    operation_name = str(
        ((live_result or {}).get("summary") or {}).get("operation_name") or ""
    ).strip()
    if not operation_name:
        return {
            "status": "manual_follow_up",
            "detail": {
                "message": "Restart validation needs the live operation name from the baseline run."
            },
        }

    repo_root = Path(__file__).resolve().parents[1]
    timeout_seconds = max(args.timeout_seconds, 10.0)
    restart_command = str(os.environ.get("OSK_REAL_HUB_RESTART_COMMAND") or "").strip()
    if restart_command:
        command = shlex.split(restart_command)
        if not command:
            return {
                "status": "manual_follow_up",
                "detail": {"message": "Configured restart command was empty after parsing."},
            }
        command_path = artifact_dir / "restart-command.json"
        command_result_path = artifact_dir / "restart-command-result.json"
        _write_json(
            command_path,
            {
                "captured_at_utc": datetime.now(timezone.utc).isoformat(),
                "command": command,
                "operation_name": operation_name,
                "scenario": args.scenario,
            },
        )
        completed = subprocess.run(
            command,
            cwd=repo_root,
            env=_osk_cli_environment(repo_root),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds + 10.0,
        )
        _write_completed_process(command_result_path, completed)
        if completed.returncode != 0:
            return {
                "status": "failed_hardening_task",
                "detail": {
                    "message": completed.stderr.strip()
                    or completed.stdout.strip()
                    or "Restart command failed.",
                    "hardening_task": "Stabilize configured hub restart automation.",
                    "restart_command_path": str(command_path),
                    "restart_command_result_path": str(command_result_path),
                },
            }
        snapshot = _wait_for_hub_status(
            repo_root,
            {"running"},
            timeout_seconds=timeout_seconds,
        )
        return {
            "status": "restarted",
            "detail": {
                "operation_name": operation_name,
                "hub_status": snapshot.get("status"),
                "pid": snapshot.get("pid"),
                "restart_command_path": str(command_path),
                "restart_command_result_path": str(command_result_path),
            },
        }

    stop_result_path = artifact_dir / "restart-stop.json"
    stop_result = _run_osk_cli(
        repo_root,
        ["stop", "--restart", "--timeout", f"{timeout_seconds:.1f}"],
        timeout_seconds=timeout_seconds + 10.0,
    )
    _write_completed_process(stop_result_path, stop_result)
    if stop_result.returncode != 0:
        return {
            "status": "failed_hardening_task",
            "detail": {
                "message": stop_result.stderr.strip()
                or stop_result.stdout.strip()
                or "Hub stop command failed.",
                "hardening_task": "Stabilize host-side hub restart control.",
                "restart_stop_path": str(stop_result_path),
            },
        }

    _wait_for_hub_status(repo_root, {"stopped"}, timeout_seconds=timeout_seconds)

    start_stdout_path = artifact_dir / "restart-start.stdout.log"
    start_stderr_path = artifact_dir / "restart-start.stderr.log"
    with start_stdout_path.open("w", encoding="utf-8") as stdout, start_stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr:
        process = subprocess.Popen(
            [sys.executable, "-m", "osk", "start", operation_name],
            cwd=repo_root,
            env=_osk_cli_environment(repo_root),
            stdout=stdout,
            stderr=stderr,
            text=True,
        )

    deadline = time.monotonic() + timeout_seconds
    last_status: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        completed = _run_osk_cli(repo_root, ["status", "--json"], timeout_seconds=5.0)
        try:
            snapshot = json.loads(completed.stdout or "{}")
        except json.JSONDecodeError:
            snapshot = {}
        if isinstance(snapshot, dict):
            last_status = snapshot
            if str(snapshot.get("status") or "").strip() == "running":
                return {
                    "status": "restarted",
                    "detail": {
                        "operation_name": operation_name,
                        "hub_status": snapshot.get("status"),
                        "pid": snapshot.get("pid"),
                        "restart_stop_path": str(stop_result_path),
                        "restart_start_stdout_path": str(start_stdout_path),
                        "restart_start_stderr_path": str(start_stderr_path),
                    },
                }
        if process.poll() is not None:
            break
        time.sleep(0.5)

    return {
        "status": "failed_hardening_task",
        "detail": {
            "message": "Hub did not report running after restart.",
            "hardening_task": "Stabilize host-side hub restart control.",
            "restart_stop_path": str(stop_result_path),
            "restart_start_stdout_path": str(start_stdout_path),
            "restart_start_stderr_path": str(start_stderr_path),
            "hub_status": (last_status or {}).get("status"),
            "start_returncode": process.poll(),
        },
    }


def _probe_restart_resume_over_cdp(
    *,
    args: argparse.Namespace,
    artifact_dir: Path,
    local_debug_port: int,
    expected_member_id: str,
    expected_operation_name: str | None,
) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - exercised in real runtime only
        raise RuntimeError(
            "Playwright is not installed in this environment. Install dev dependencies first."
        ) from exc

    def current_probe(page: Any) -> dict[str, Any]:
        body_text = (page.locator("body").text_content() or "").strip()
        probe = {
            "captured_at_utc": datetime.now(timezone.utc).isoformat(),
            "url": page.url,
            "title": page.title(),
            "member_id": (page.locator("#runtime-member-id").text_content() or "").strip()
            if page.locator("#runtime-member-id").count()
            else "",
            "session_state": (page.locator("#runtime-session-state").text_content() or "").strip()
            if page.locator("#runtime-session-state").count()
            else "",
            "connection_state": (
                page.locator("#runtime-connection-state").text_content() or ""
            ).strip()
            if page.locator("#runtime-connection-state").count()
            else "",
            "operation_name": (
                page.locator("#runtime-operation-name").text_content() or ""
            ).strip()
            if page.locator("#runtime-operation-name").count()
            else "",
            "outbox_count": (page.locator("#runtime-outbox-count").text_content() or "").strip()
            if page.locator("#runtime-outbox-count").count()
            else "",
            "has_report_form": bool(page.locator("#runtime-report-form").count()),
            "body_excerpt": body_text[:240],
        }
        probe["session_cleared"] = (
            "Operation ended" in body_text
            or "Local session cleared" in body_text
            or "rescan the QR code" in body_text.lower()
        )
        probe["resume_detected"] = (
            probe["member_id"] == expected_member_id
            and probe["has_report_form"]
            and probe["outbox_count"] == "0"
            and probe["operation_name"] == (expected_operation_name or probe["operation_name"])
        )
        return probe

    timeout_seconds = max(args.timeout_seconds, 15.0)
    probe_path = artifact_dir / "restart-resume-probe.json"
    screenshot_path = artifact_dir / "restart-resume-probe.png"
    last_probe: dict[str, Any] | None = None

    with sync_playwright() as playwright:
        browser = None
        try:
            browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{local_debug_port}")
            page = None
            for context in browser.contexts:
                for candidate in context.pages:
                    if candidate.url.endswith("/member") or candidate.url.endswith("/join"):
                        page = candidate
                        break
                if page is not None:
                    break
            if page is None:
                return {
                    "status": "failed_hardening_task",
                    "detail": {
                        "message": (
                            "No existing member browser tab was available for "
                            "restart probing."
                        ),
                        "hardening_task": (
                            "Preserve the member browser session so restart validation can "
                            "probe reconnect behavior without a fresh join."
                        ),
                    },
                }

            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline:
                last_probe = current_probe(page)
                if last_probe["resume_detected"]:
                    page.screenshot(path=str(screenshot_path))
                    _write_json(probe_path, last_probe)
                    return {
                        "status": "passed",
                        "detail": {
                            "message": "Member runtime resumed over the existing browser session.",
                            "restart_resume_probe_path": str(probe_path),
                            "restart_resume_screenshot_path": str(screenshot_path),
                            "member_id": last_probe["member_id"],
                            "outbox_count": last_probe["outbox_count"],
                        },
                    }
                if last_probe["session_cleared"]:
                    page.screenshot(path=str(screenshot_path))
                    _write_json(probe_path, last_probe)
                    return {
                        "status": "failed_hardening_task",
                        "detail": {
                            "message": (
                                "Member browser session was cleared when the hub stopped, so "
                                "restart replay could not resume over the existing session."
                            ),
                            "hardening_task": (
                                "Preserve member runtime sessions across coordinator restarts so "
                                "queued replay can resume without rescanning the QR code."
                            ),
                            "restart_resume_probe_path": str(probe_path),
                            "restart_resume_screenshot_path": str(screenshot_path),
                        },
                    }
                time.sleep(0.5)
        finally:
            if last_probe is not None and not probe_path.exists():
                _write_json(probe_path, last_probe)
            if browser is not None:
                with contextlib.suppress(Exception):
                    browser.close()

    return {
        "status": "failed_hardening_task",
        "detail": {
            "message": "Member runtime did not resume over the existing browser session in time.",
            "hardening_task": (
                "Stabilize member reconnect and queued replay across coordinator restarts."
            ),
            "restart_resume_probe_path": str(probe_path),
            "restart_resume_screenshot_path": str(screenshot_path),
        },
    }


def _run_restart_resume_check(
    *,
    args: argparse.Namespace,
    artifact_dir: Path,
    local_debug_port: int,
    cdp_version: dict[str, Any] | None,
    live_result: dict[str, Any] | None,
) -> dict[str, Any]:
    baseline_summary = (live_result or {}).get("summary") or {}
    expected_member_id = str(baseline_summary.get("member_id") or "").strip()
    expected_operation_name = str(baseline_summary.get("operation_name") or "").strip()
    if not expected_member_id or not expected_operation_name:
        return {
            "step_update": {
                "id": "hub_restart_resume_observed",
                "status": "manual_follow_up",
                "automated": False,
                "detail": {
                    "message": (
                        "Restart validation needs baseline member_id and operation_name "
                        "metadata from the live run."
                    )
                },
            },
            "summary": {"restart_resume_status": "manual_follow_up"},
        }

    restart_result = _perform_restart_cycle(
        args=args,
        artifact_dir=artifact_dir,
        live_result=live_result,
    )
    if restart_result["status"] == "manual_follow_up":
        return {
            "step_update": {
                "id": "hub_restart_resume_observed",
                "status": "manual_follow_up",
                "automated": False,
                "detail": restart_result["detail"],
            },
            "summary": {"restart_resume_status": "manual_follow_up"},
        }
    if restart_result["status"] != "restarted":
        hardening_task = str(
            (restart_result.get("detail") or {}).get("hardening_task")
            or "Stabilize host-side hub restart control."
        )
        return {
            "step_update": {
                "id": "hub_restart_resume_observed",
                "status": "failed_hardening_task",
                "automated": True,
                "detail": restart_result["detail"],
            },
            "summary": {
                "restart_resume_status": "failed_hardening_task",
                "hardening_tasks": [hardening_task],
            },
        }

    resume_probe = _probe_restart_resume_over_cdp(
        args=args,
        artifact_dir=artifact_dir,
        local_debug_port=local_debug_port,
        expected_member_id=expected_member_id,
        expected_operation_name=expected_operation_name,
    )
    if resume_probe["status"] == "passed":
        return {
            "step_update": {
                "id": "hub_restart_resume_observed",
                "status": "passed",
                "automated": True,
                "detail": _merge_summary(restart_result["detail"], resume_probe["detail"]),
            },
            "summary": {
                "restart_resume_status": "passed",
            },
        }

    hardening_task = str(
        (resume_probe.get("detail") or {}).get("hardening_task")
        or "Stabilize member reconnect across coordinator restarts."
    )
    return {
        "step_update": {
            "id": "hub_restart_resume_observed",
            "status": "failed_hardening_task",
            "automated": True,
            "detail": _merge_summary(restart_result["detail"], resume_probe["detail"]),
        },
        "summary": {
            "restart_resume_status": "failed_hardening_task",
            "hardening_tasks": [hardening_task],
        },
    }


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
        build_ssh_tunnel_command(ssh_target, local_port, remote_port, ssh_port, ssh_identity),
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


def _capture_local_snapshot(
    repo_root: Path,
    artifact_dir: Path,
    *,
    name: str,
    cli_args: list[str],
) -> tuple[str | None, dict[str, Any]]:
    output_path = artifact_dir / f"{name}.json"
    command = [sys.executable, "-m", "osk", *cli_args]
    env = os.environ.copy()
    pythonpath_parts = [str(repo_root / "src")]
    existing_pythonpath = env.get("PYTHONPATH", "").strip()
    if existing_pythonpath:
        pythonpath_parts.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)

    try:
        completed = subprocess.run(
            command,
            cwd=repo_root,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        return None, {"available": False, "path": None, "error": str(exc)}

    if completed.returncode != 0:
        error = (
            completed.stderr.strip()
            or completed.stdout.strip()
            or f"exit {completed.returncode}"
        )
        return None, {"available": False, "path": None, "error": error}

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None, {"available": False, "path": None, "error": "Invalid JSON snapshot output."}

    _write_json(output_path, payload)
    return str(output_path), {"available": True, "path": str(output_path)}


def _collect_local_snapshots(repo_root: Path, artifact_dir: Path) -> dict[str, Any]:
    doctor_path, doctor_meta = _capture_local_snapshot(
        repo_root,
        artifact_dir,
        name="doctor",
        cli_args=["doctor", "--json"],
    )
    status_path, status_meta = _capture_local_snapshot(
        repo_root,
        artifact_dir,
        name="status",
        cli_args=["status", "--json"],
    )
    return {
        "captures": {
            "doctor_snapshot_path": doctor_path,
            "status_snapshot_path": status_path,
        },
        "local_snapshots": {
            "doctor": doctor_meta,
            "status": status_meta,
        },
    }


def _write_hub_preflight(
    *,
    artifact_dir: Path,
    args: argparse.Namespace,
    snapshot_info: dict[str, Any],
) -> str:
    preflight_path = artifact_dir / "hub-preflight.json"
    payload = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "execution_mode": "contract_only",
        "scenario": args.scenario,
        "hub_url": args.hub_url,
        "join_url": args.join_url,
        "device_id": args.device_id,
        "local_snapshots": snapshot_info["local_snapshots"],
    }
    _write_json(preflight_path, payload)
    return str(preflight_path)


def _httpx_verify_for_url(url: str) -> bool:
    host = urlsplit(url).hostname
    if host is None:
        return True
    if host == "localhost":
        return False
    try:
        return not ipaddress.ip_address(host).is_loopback
    except ValueError:
        return True


def _local_admin_headers() -> tuple[dict[str, str] | None, str | None]:
    env_admin_token = str(os.environ.get("OSK_REAL_HUB_ADMIN_TOKEN") or "").strip()
    if env_admin_token:
        return {ADMIN_TOKEN_HEADER: env_admin_token}, "env_admin_token"

    env_operator_session = str(
        os.environ.get("OSK_REAL_HUB_OPERATOR_SESSION_TOKEN") or ""
    ).strip()
    if env_operator_session:
        return {OPERATOR_SESSION_HEADER: env_operator_session}, "env_operator_session"

    env_dashboard_session = str(
        os.environ.get("OSK_REAL_HUB_DASHBOARD_SESSION_TOKEN") or ""
    ).strip()
    if env_dashboard_session:
        return {"Authorization": f"Bearer {env_dashboard_session}"}, "env_dashboard_session"

    try:
        from osk.local_operator import read_dashboard_session, read_operator_session
    except ImportError:
        return None, None

    operator_session = read_operator_session()
    operator_token = str((operator_session or {}).get("token") or "").strip()
    if operator_token:
        return {OPERATOR_SESSION_HEADER: operator_token}, "local_operator_session"

    dashboard_session = read_dashboard_session()
    dashboard_token = str((dashboard_session or {}).get("token") or "").strip()
    if dashboard_token:
        return {"Authorization": f"Bearer {dashboard_token}"}, "local_dashboard_session"

    return None, None


def _capture_operator_closure(*, args: argparse.Namespace, artifact_dir: Path) -> dict[str, Any]:
    headers, credential_source = _local_admin_headers()
    if headers is None:
        return {
            "captures": {
                "wipe_readiness_path": None,
                "audit_slice_path": None,
            },
            "step_update": {
                "id": "operator_closure_captured",
                "status": "manual_follow_up",
                "automated": False,
                "detail": {"message": "Local operator credentials unavailable."},
            },
            "summary": {
                "operator_closure_status": "unavailable",
            },
        }

    wipe_readiness_path = artifact_dir / "wipe-readiness.json"
    audit_slice_path = artifact_dir / "audit-slice.json"
    verify = _httpx_verify_for_url(args.hub_url)
    try:
        with httpx.Client(
            headers=headers,
            timeout=max(args.timeout_seconds, 5.0),
            verify=verify,
            follow_redirects=True,
        ) as client:
            dashboard_response = client.get(
                urljoin(args.hub_url, "/api/coordinator/dashboard-state")
            )
            dashboard_response.raise_for_status()
            dashboard_payload = dashboard_response.json()
            wipe_readiness = dashboard_payload.get("wipe_readiness")
            if not isinstance(wipe_readiness, dict):
                raise ValueError("Dashboard state did not include wipe_readiness.")

            audit_response = client.get(
                urljoin(args.hub_url, "/api/audit"),
                params={"wipe_follow_up_only": "true", "limit": "20"},
            )
            audit_response.raise_for_status()
            audit_events = audit_response.json()
            if not isinstance(audit_events, list):
                raise ValueError("Audit slice response was not a list.")
    except Exception as exc:
        return {
            "captures": {
                "wipe_readiness_path": None,
                "audit_slice_path": None,
            },
            "step_update": {
                "id": "operator_closure_captured",
                "status": "manual_follow_up",
                "automated": False,
                "detail": {"message": str(exc)},
            },
            "summary": {
                "operator_closure_status": "error",
            },
        }

    captured_at_utc = datetime.now(timezone.utc).isoformat()
    _write_json(
        wipe_readiness_path,
        {
            "captured_at_utc": captured_at_utc,
            "credential_source": credential_source,
            "wipe_readiness": wipe_readiness,
        },
    )
    _write_json(
        audit_slice_path,
        {
            "captured_at_utc": captured_at_utc,
            "credential_source": credential_source,
            "event_count": len(audit_events),
            "events": audit_events,
        },
    )
    return {
        "captures": {
            "wipe_readiness_path": str(wipe_readiness_path),
            "audit_slice_path": str(audit_slice_path),
        },
        "step_update": {
            "id": "operator_closure_captured",
            "status": "passed",
            "automated": True,
            "detail": {
                "credential_source": credential_source,
                "wipe_readiness_status": wipe_readiness.get("status"),
                "unresolved_follow_up_count": wipe_readiness.get("unresolved_follow_up_count"),
                "audit_event_count": len(audit_events),
            },
        },
        "summary": {
            "operator_closure_status": "captured",
            "wipe_readiness_status": wipe_readiness.get("status"),
            "unresolved_follow_up_count": wipe_readiness.get("unresolved_follow_up_count"),
            "audit_event_count": len(audit_events),
        },
    }


class RealHubRunState:
    def __init__(self) -> None:
        self.step_updates: list[dict[str, Any]] = []
        self.console_events: list[dict[str, str]] = []
        self.network_failures: list[dict[str, str | None]] = []
        self.page_errors: list[str] = []
        self.display_name: str | None = None
        self.member_id: str | None = None
        self.operation_name: str | None = None

    def summary(self) -> dict[str, Any]:
        return {
            "message": "Real hub join/member runtime path completed.",
            "display_name": self.display_name,
            "member_id": self.member_id.strip() if self.member_id else None,
            "operation_name": self.operation_name.strip() if self.operation_name else None,
            "console_event_count": len(self.console_events),
            "network_failure_count": len(self.network_failures),
            "page_error_count": len(self.page_errors),
        }

    def result(self) -> dict[str, Any]:
        return {
            "steps": _merge_step_updates(self.step_updates),
            "summary": self.summary(),
            "diagnostic_paths": {},
        }


class RealHubRunFailed(RuntimeError):
    def __init__(self, message: str, state: RealHubRunState):
        super().__init__(message)
        self.state = state


def write_browser_diagnostics(artifact_dir: Path, state: RealHubRunState) -> dict[str, str]:
    diagnostic_paths = {
        "console_events_path": str(artifact_dir / "console-events.json"),
        "network_failures_path": str(artifact_dir / "network-failures.json"),
        "page_errors_path": str(artifact_dir / "page-errors.json"),
    }
    _write_json(Path(diagnostic_paths["console_events_path"]), state.console_events)
    _write_json(Path(diagnostic_paths["network_failures_path"]), state.network_failures)
    _write_json(Path(diagnostic_paths["page_errors_path"]), state.page_errors)
    return diagnostic_paths


def run_live_flow(
    *,
    local_port: int,
    args: argparse.Namespace,
    artifact_dir: Path,
) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - exercised in real runtime only
        raise RuntimeError(
            "Playwright is not installed in this environment. Install dev dependencies first."
        ) from exc

    state = RealHubRunState()
    state.display_name = f"Chromebook Validation {int(time.time())}"
    timeout_ms = int(args.timeout_seconds * 1000)

    def record_step(page: Any, step_id: str, detail: dict[str, Any] | None = None) -> None:
        screenshot_name = f"{len(state.step_updates) + 1:02d}-{_slugify(step_id)}.png"
        page.screenshot(path=str(artifact_dir / screenshot_name))
        state.step_updates.append(
            {
                "id": step_id,
                "status": "passed",
                "automated": True,
                "detail": detail or {},
                "screenshot": screenshot_name,
            }
        )

    with sync_playwright() as playwright:
        browser = None
        try:
            browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{local_port}")
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.pages[0] if context.pages else context.new_page()

            page.on(
                "console",
                lambda message: state.console_events.append(
                    {"type": message.type, "text": message.text}
                ),
            )
            page.on("pageerror", lambda error: state.page_errors.append(str(error)))
            page.on(
                "requestfailed",
                lambda request: state.network_failures.append(
                    {
                        "url": request.url,
                        "method": request.method,
                        "failure": request.failure,
                    }
                ),
            )

            page.goto(args.join_url, wait_until="networkidle", timeout=timeout_ms)
            record_step(
                page,
                "hub_reachable",
                {"hub_url": args.hub_url, "observed_url": page.url},
            )
            record_step(page, "join_loads", {"join_url": args.join_url, "observed_url": page.url})

            page.locator("#join-display-name").fill(state.display_name)
            page.locator("#join-form").evaluate("(form) => form.requestSubmit()")
            page.wait_for_url("**/member", timeout=timeout_ms)
            page.wait_for_selector("#runtime-report-form", timeout=timeout_ms)
            page.wait_for_function(MEMBER_ID_READY_JS, timeout=timeout_ms)
            state.operation_name = page.locator("#runtime-operation-name").text_content() or ""
            state.member_id = page.locator("#runtime-member-id").text_content() or ""
            record_step(
                page,
                "member_session_establishes",
                {
                    "member_id": state.member_id.strip(),
                    "operation_name": state.operation_name.strip(),
                    "display_name": state.display_name,
                    "url": page.url,
                },
            )

            context.set_offline(True)
            page.locator("#runtime-report-text").fill("Real hub offline validation note")
            page.locator("#runtime-report-form").evaluate("(form) => form.requestSubmit()")
            page.wait_for_function(OUTBOX_HAS_ITEMS_JS, timeout=timeout_ms)
            queued_count = (page.locator("#runtime-outbox-count").text_content() or "0").strip()
            context.set_offline(False)
            page.wait_for_function(OUTBOX_EMPTY_JS, timeout=timeout_ms)
            record_step(page, "disconnect_reconnect_observed", {"queued_count": queued_count})

            state.step_updates.append(
                {
                    "id": "wipe_observed",
                    "status": "manual_follow_up",
                    "automated": False,
                    "detail": {
                        "message": (
                            "Live wipe still requires operator-driven "
                            "validation in this slice."
                        )
                    },
                }
            )
            state.step_updates.append(
                {
                    "id": "operator_closure_captured",
                    "status": "manual_follow_up",
                    "automated": False,
                    "detail": {
                        "message": "Operator-side readiness and audit capture remain manual."
                    },
                }
            )
        except Exception as exc:
            raise RealHubRunFailed(str(exc), state) from exc
        finally:
            diagnostic_paths = write_browser_diagnostics(artifact_dir, state)
            if browser is not None:
                with contextlib.suppress(Exception):
                    browser.close()

    result = state.result()
    result["diagnostic_paths"] = diagnostic_paths
    return result


def _build_result_payload(
    *,
    status: str,
    execution_mode: str,
    args: argparse.Namespace,
    artifact_dir: Path,
    result_path: Path,
    run_label: str,
    capture_paths: dict[str, str | None],
    steps: list[dict[str, Any]] | None = None,
    summary: dict[str, Any] | None = None,
    local_debug_port: int | None = None,
    cdp_version: dict[str, Any] | None = None,
    diagnostic_paths: dict[str, str] | None = None,
    failure: dict[str, str] | None = None,
) -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[1]
    completed_at = datetime.now(timezone.utc).isoformat()
    provenance = build_provenance(
        repo_root=repo_root,
        run_label=run_label,
        chromebook_host=args.device_id,
        completed_at_utc=completed_at,
        invocation="real_hub_validation.py",
        trigger="manual",
    )

    payload: dict[str, Any] = {
        "contract_version": 1,
        "status": status,
        "execution_mode": execution_mode,
        "scenario": args.scenario,
        "hub_url": args.hub_url,
        "join_url": args.join_url,
        "device_id": args.device_id,
        "ssh_target": args.ssh_target,
        "ssh_port": args.ssh_port or None,
        "ssh_identity": args.ssh_identity or None,
        "debug_port": args.debug_port,
        "local_debug_port": local_debug_port,
        "cdp_version": cdp_version,
        "artifact_dir": str(artifact_dir),
        "result_path": str(result_path),
        "captures": {
            "doctor_snapshot_path": capture_paths.get("doctor_snapshot_path"),
            "hub_preflight_path": capture_paths.get("hub_preflight_path"),
            "status_snapshot_path": capture_paths.get("status_snapshot_path"),
            "cdp_version_path": capture_paths.get("cdp_version_path"),
            "audit_slice_path": None,
            "wipe_readiness_path": None,
        },
        "steps": _merge_step_updates(steps, scenario=args.scenario)
        if steps is not None
        else _steps_for_scenario(args.scenario),
        "summary": summary
        or {
            "message": "Real-hub validation contract recorded without runtime execution.",
            "planned_step_count": len(_steps_for_scenario(args.scenario)),
        },
        "diagnostics": diagnostic_paths or {},
        "failure": failure,
        "provenance": provenance,
    }
    return payload


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    artifact_root = Path(args.artifact_root)
    repo_root = Path(__file__).resolve().parents[1]
    run_label = args.timestamp.strip() or timestamp_label()
    artifact_dir = make_artifact_dir(artifact_root, label=run_label)
    result_path = artifact_dir / "result.json"
    snapshot_info = _collect_local_snapshots(repo_root, artifact_dir)
    capture_paths = dict(snapshot_info["captures"])
    capture_paths["hub_preflight_path"] = _write_hub_preflight(
        artifact_dir=artifact_dir,
        args=args,
        snapshot_info=snapshot_info,
    )

    if args.dry_run:
        payload = _build_result_payload(
            status="dry_run",
            execution_mode="contract_only",
            args=args,
            artifact_dir=artifact_dir,
            result_path=result_path,
            run_label=run_label,
            capture_paths=capture_paths,
        )
        _write_json(result_path, payload)
        return 0

    local_debug_port = args.local_debug_port or choose_local_port()
    live_result: dict[str, Any] | None = None
    cdp_version: dict[str, Any] | None = None
    cdp_version_path = artifact_dir / "cdp-version.json"
    try:
        with managed_ssh_tunnel(
            args.ssh_target,
            local_debug_port,
            args.debug_port,
            args.ssh_port or None,
            args.ssh_identity or None,
        ):
            cdp_version = fetch_cdp_version(local_debug_port, args.timeout_seconds)
            _write_json(cdp_version_path, cdp_version)
            capture_paths["cdp_version_path"] = str(cdp_version_path)
            live_result = run_live_flow(
                local_port=local_debug_port,
                args=args,
                artifact_dir=artifact_dir,
            )
            if args.scenario == "restart":
                restart_result = _run_restart_resume_check(
                    args=args,
                    artifact_dir=artifact_dir,
                    local_debug_port=local_debug_port,
                    cdp_version=cdp_version,
                    live_result=live_result,
                )
    except Exception as exc:
        if isinstance(exc, RealHubRunFailed):
            live_result = exc.state.result()
        failure_type = exc.__class__.__name__
        if isinstance(exc, RealHubRunFailed) and exc.__cause__ is not None:
            failure_type = exc.__cause__.__class__.__name__
        payload = _build_result_payload(
            status="failed",
            execution_mode="chromebook_cdp",
            args=args,
            artifact_dir=artifact_dir,
            result_path=result_path,
            run_label=run_label,
            capture_paths=capture_paths,
            steps=(live_result or {}).get("steps"),
            summary=(live_result or {}).get("summary"),
            local_debug_port=local_debug_port,
            cdp_version=cdp_version,
            diagnostic_paths=(live_result or {}).get("diagnostic_paths"),
            failure={
                "stage": "runtime",
                "type": failure_type,
                "message": str(exc),
            },
        )
        _write_json(result_path, payload)
        print(payload["failure"]["message"], file=sys.stderr)
        return 1

    payload = _build_result_payload(
        status="passed",
        execution_mode="chromebook_cdp",
        args=args,
        artifact_dir=artifact_dir,
        result_path=result_path,
        run_label=run_label,
        capture_paths=capture_paths,
        steps=live_result["steps"],
        summary=live_result["summary"],
        local_debug_port=local_debug_port,
        cdp_version=cdp_version,
        diagnostic_paths=live_result.get("diagnostic_paths"),
    )
    operator_closure = _capture_operator_closure(args=args, artifact_dir=artifact_dir)
    payload["captures"]["wipe_readiness_path"] = operator_closure["captures"]["wipe_readiness_path"]
    payload["captures"]["audit_slice_path"] = operator_closure["captures"]["audit_slice_path"]
    payload["steps"] = _merge_step_updates(
        [*payload["steps"], operator_closure["step_update"]],
        scenario=args.scenario,
    )
    payload["summary"] = _merge_summary(payload.get("summary"), operator_closure["summary"])
    if args.scenario == "restart":
        payload["steps"] = _merge_step_updates(
            [*payload["steps"], restart_result["step_update"]],
            scenario=args.scenario,
        )
        payload["summary"] = _merge_summary(payload.get("summary"), restart_result["summary"])
    _finalize_payload_status(payload, default_status="passed")
    _write_json(result_path, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
