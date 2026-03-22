"""Read-only install and wipe drill reports for operator runbooks."""

from __future__ import annotations

import shutil
from pathlib import Path

from osk.config import OskConfig, load_config
from osk.hub import (
    _find_compose_command,
    default_storage_manager,
    hotspot_preflight_status,
    installation_issues,
    local_service_mode,
    read_hub_state,
    uses_local_dev_services,
)
from osk.local_operator import (
    bootstrap_session_path,
    dashboard_bootstrap_path,
    dashboard_session_path,
    operator_session_path,
)


def _compose_report(config: OskConfig) -> tuple[dict[str, object], list[str]]:
    if not uses_local_dev_services(config):
        return (
            {
                "required": False,
                "available": None,
                "command": None,
                "note": "Configured for externally managed services.",
            },
            [],
        )

    try:
        command = _find_compose_command()
    except Exception as exc:
        return (
            {
                "required": True,
                "available": False,
                "command": None,
                "note": str(exc),
            },
            ["missing Compose-compatible runtime for local service mode"],
        )

    return (
        {
            "required": True,
            "available": True,
            "command": " ".join(command),
            "note": None,
        },
        [],
    )


def install_drill_report(config: OskConfig | None = None) -> dict[str, object]:
    cfg = config or load_config()
    storage = default_storage_manager(cfg)
    issues = list(installation_issues(cfg, storage))
    compose, compose_issues = _compose_report(cfg)
    issues.extend(compose_issues)
    hotspot = hotspot_preflight_status(cfg)

    next_steps: list[str] = []
    if any(
        "missing TLS" in issue or "missing encrypted evidence volume" in issue for issue in issues
    ):
        next_steps.append("Run `osk install` to create local TLS assets and evidence storage.")
    if compose_issues:
        next_steps.append(
            "Install docker/podman support or point `database_url` and `ollama_base_url` at "
            "running external services."
        )
    if cfg.transcriber_backend == "whisper" and shutil.which(cfg.ffmpeg_binary) is None:
        next_steps.append(
            f"Install `{cfg.ffmpeg_binary}` or switch `transcriber_backend` away from `whisper`."
        )
    next_steps.extend(str(action) for action in hotspot["actions"])

    return {
        "drill": "install",
        "status": "ready" if not issues else "needs_attention",
        "service_mode": local_service_mode(cfg),
        "install_ready": not issues,
        "issues": issues,
        "compose": compose,
        "hotspot": hotspot,
        "storage": {
            "backend": storage.backend,
            "runtime_path": str(storage.tmpfs_path),
            "evidence_mount_path": str(storage.luks_mount_path),
            "evidence_image_path": str(storage.luks_image_path),
            "evidence_image_exists": storage.luks_image_path.exists(),
        },
        "tls": {
            "cert_path": cfg.tls_cert_path,
            "cert_exists": Path(cfg.tls_cert_path).exists(),
            "key_path": cfg.tls_key_path,
            "key_exists": Path(cfg.tls_key_path).exists(),
        },
        "next_steps": next_steps,
        "read_only": True,
    }


def wipe_drill_report(config: OskConfig | None = None) -> dict[str, object]:
    cfg = config or load_config()
    storage = default_storage_manager(cfg)
    hub_state = read_hub_state()
    hub_running = hub_state is not None

    paths = [
        {
            "label": "runtime_tmpfs",
            "path": str(storage.tmpfs_path),
            "exists": storage.tmpfs_path.exists(),
            "current_behavior": "Unmounted by the host-side emergency wipe primitive.",
        },
        {
            "label": "evidence_mount",
            "path": str(storage.luks_mount_path),
            "exists": storage.luks_mount_path.exists(),
            "current_behavior": "Closed/unmounted by the host-side emergency wipe primitive.",
        },
        {
            "label": "evidence_image",
            "path": str(storage.luks_image_path),
            "exists": storage.luks_image_path.exists(),
            "current_behavior": (
                "Not automatically destroyed by the wipe primitive; use "
                "`osk evidence destroy --yes` for permanent removal."
            ),
        },
        {
            "label": "operator_bootstrap",
            "path": str(bootstrap_session_path()),
            "exists": bootstrap_session_path().exists(),
            "current_behavior": "Cleared on hub shutdown, not by `/api/wipe` alone.",
        },
        {
            "label": "operator_session",
            "path": str(operator_session_path()),
            "exists": operator_session_path().exists(),
            "current_behavior": "Cleared on hub shutdown, not by `/api/wipe` alone.",
        },
        {
            "label": "dashboard_bootstrap",
            "path": str(dashboard_bootstrap_path()),
            "exists": dashboard_bootstrap_path().exists(),
            "current_behavior": "Cleared on hub shutdown, not by `/api/wipe` alone.",
        },
        {
            "label": "dashboard_session",
            "path": str(dashboard_session_path()),
            "exists": dashboard_session_path().exists(),
            "current_behavior": "Cleared on hub shutdown, not by `/api/wipe` alone.",
        },
    ]

    capabilities = [
        {
            "name": "member_broadcast",
            "available": hub_running,
            "details": (
                'The local coordinator admin surface can broadcast `{"type":"wipe"}` to '
                "connected members while the hub is running."
            ),
        },
        {
            "name": "member_browser_clear",
            "available": True,
            "details": (
                "The current member shell clears local browser-managed member state after a live "
                "`wipe` or `op_ended` message."
            ),
        },
        {
            "name": "host_runtime_wipe_primitive",
            "available": True,
            "details": (
                "The host storage layer can revoke the keyring entry, close the evidence mount, "
                "and unmount runtime tmpfs."
            ),
        },
        {
            "name": "preserved_evidence_destroy",
            "available": True,
            "details": (
                "Permanent preserved-evidence removal is a separate `osk evidence destroy` step."
            ),
        },
    ]

    gaps = [
        "No integrated `osk wipe` CLI command is wired yet for the coordinator host.",
        "Disconnected member browsers will not receive a live wipe broadcast until they reconnect.",
        "The preserved evidence image is not removed by the runtime wipe primitive.",
    ]
    if not hub_running:
        gaps.insert(
            0,
            "No running hub state was found, so the live member wipe broadcast "
            "path cannot be exercised here.",
        )

    next_steps = [
        "Export preserved evidence first if you need to retain pinned material before cleanup.",
        "Use the authenticated local coordinator surface to trigger `/api/wipe` "
        "while the hub is running.",
        "Stop the hub to clear local operator/dashboard session files and "
        "runtime state on the host.",
        "Run `osk evidence destroy --yes` only if you want permanent removal "
        "of preserved evidence storage.",
    ]
    if storage.backend == "directory":
        next_steps.append(
            "This machine is using directory-backed development storage, so there is no encrypted "
            "evidence image to shred."
        )

    return {
        "drill": "wipe",
        "status": "partial",
        "hub_running": hub_running,
        "operation_id": hub_state.get("operation_id") if hub_state else None,
        "storage_backend": storage.backend,
        "capabilities": capabilities,
        "paths": paths,
        "gaps": gaps,
        "next_steps": next_steps,
        "read_only": True,
    }
