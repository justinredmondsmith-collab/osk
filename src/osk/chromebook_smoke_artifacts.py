from __future__ import annotations

import json
import os
import socket
import subprocess
from pathlib import Path
from typing import Any, Mapping


def _git_output(repo_root: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return ""
    return completed.stdout.strip()


def _env_flag(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def build_provenance(
    *,
    repo_root: Path,
    run_label: str,
    chromebook_host: str,
    env: Mapping[str, str] | None = None,
    started_at_utc: str | None = None,
    completed_at_utc: str | None = None,
    invocation: str | None = None,
    trigger: str | None = None,
) -> dict[str, Any]:
    environ = os.environ if env is None else env

    git_branch = environ.get("OSK_SMOKE_GIT_BRANCH") or _git_output(
        repo_root,
        "branch",
        "--show-current",
    )
    if not git_branch:
        fallback_branch = _git_output(repo_root, "rev-parse", "--abbrev-ref", "HEAD")
        if fallback_branch and fallback_branch != "HEAD":
            git_branch = fallback_branch

    worktree_dirty = _env_flag(environ.get("OSK_SMOKE_WORKTREE_DIRTY"))
    if worktree_dirty is None:
        worktree_dirty = bool(_git_output(repo_root, "status", "--short"))

    return {
        "artifact_version": 1,
        "run_label": run_label,
        "trigger": trigger or environ.get("OSK_SMOKE_TRIGGER") or "manual",
        "invocation": invocation or environ.get("OSK_SMOKE_INVOCATION") or None,
        "git_sha": (
            environ.get("OSK_SMOKE_GIT_SHA") or _git_output(repo_root, "rev-parse", "HEAD") or None
        ),
        "git_branch": git_branch or None,
        "git_commit_subject": (
            environ.get("OSK_SMOKE_GIT_COMMIT_SUBJECT")
            or _git_output(repo_root, "log", "-1", "--pretty=%s")
            or None
        ),
        "runner_hostname": (
            environ.get("OSK_SMOKE_RUNNER_HOSTNAME")
            or environ.get("HOSTNAME")
            or socket.gethostname()
        ),
        "device_id": environ.get("OSK_SMOKE_DEVICE_ID") or chromebook_host,
        "worktree_dirty": worktree_dirty,
        "started_at_utc": started_at_utc or environ.get("OSK_SMOKE_STARTED_AT_UTC") or None,
        "completed_at_utc": completed_at_utc or None,
    }


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def merge_result_metadata(
    result_path: Path,
    *,
    launch_preflight_path: Path | None = None,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = _load_json(result_path)
    if payload is None:
        raise ValueError(f"Result payload is missing or invalid JSON: {result_path}")

    payload["result_path"] = str(result_path)

    if launch_preflight_path is not None and launch_preflight_path.exists():
        launch_preflight = _load_json(launch_preflight_path)
        if launch_preflight is not None:
            payload["launch_preflight"] = launch_preflight

    if provenance is not None:
        payload["provenance"] = provenance

    result_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def build_run_index_entry(payload: Mapping[str, Any]) -> dict[str, Any]:
    failure = payload.get("failure")
    if not isinstance(failure, dict):
        failure = {}

    captures = payload.get("captures")
    if not isinstance(captures, dict):
        captures = None

    operator_handoff = None
    operator_handoff_path = ""
    if captures is not None:
        operator_handoff_path = str(captures.get("operator_handoff_path") or "").strip()
    if operator_handoff_path:
        handoff_payload = _load_json(Path(operator_handoff_path))
        if isinstance(handoff_payload, dict):
            handoff_summary = handoff_payload.get("summary")
            if not isinstance(handoff_summary, dict):
                handoff_summary = {}
            handoff_closure = handoff_payload.get("closure")
            if not isinstance(handoff_closure, dict):
                handoff_closure = {}
            operator_handoff = {
                "path": operator_handoff_path,
                "status": handoff_payload.get("status"),
                "closure_state": handoff_closure.get("closure_state"),
                "follow_up_required": handoff_closure.get("follow_up_required"),
                "unresolved_follow_up_count": handoff_closure.get("unresolved_follow_up_count"),
                "follow_up_summary": handoff_closure.get("follow_up_summary"),
                "operator_closure_status": handoff_summary.get("operator_closure_status"),
                "operator_closure_state": handoff_summary.get("operator_closure_state"),
                "wipe_observed_status": handoff_summary.get("wipe_observed_status"),
            }

    launch_preflight = payload.get("launch_preflight")
    if not isinstance(launch_preflight, dict):
        launch_preflight = None

    summary = payload.get("summary")
    if not isinstance(summary, dict):
        summary = None

    provenance = payload.get("provenance")
    if not isinstance(provenance, dict):
        provenance = None

    return {
        "run_label": (provenance or {}).get("run_label"),
        "status": payload.get("status"),
        "artifact_dir": payload.get("artifact_dir"),
        "result_path": payload.get("result_path"),
        "chromebook_host": payload.get("chromebook_host"),
        "ssh_target": payload.get("ssh_target"),
        "failure_stage": failure.get("stage"),
        "failure_type": failure.get("type"),
        "failure_message": failure.get("message"),
        "captures": captures,
        "operator_handoff": operator_handoff,
        "launch_preflight": launch_preflight,
        "summary": summary,
        "provenance": provenance,
    }


def write_artifact_indexes(artifact_root: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    entry = build_run_index_entry(payload)
    artifact_root.mkdir(parents=True, exist_ok=True)

    latest_path = artifact_root / "latest.json"
    latest_path.write_text(json.dumps(entry, indent=2, sort_keys=True) + "\n")

    runs_path = artifact_root / "runs.jsonl"
    with runs_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")

    return entry
