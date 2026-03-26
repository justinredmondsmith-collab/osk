"""Read-only install and wipe drill reports for operator runbooks."""

from __future__ import annotations

import shutil
from pathlib import Path

from osk.config import OskConfig, load_config
from osk.evidence import EvidenceManager
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
    read_operator_session,
)


def _wipe_bundle_report(
    *,
    export_bundle: Path | None,
    manifest_path: Path | None,
    checksum_path: Path | None,
) -> dict[str, object]:
    if export_bundle is None:
        return {
            "provided": False,
            "status": "not_provided",
            "archive_path": None,
            "manifest_path": str(manifest_path) if manifest_path is not None else None,
            "checksum_path": str(checksum_path) if checksum_path is not None else None,
            "verification": None,
            "error": None,
        }

    try:
        verification = EvidenceManager.verify_export_bundle(
            export_bundle,
            manifest_path=manifest_path,
            checksum_path=checksum_path,
        )
    except Exception as exc:
        return {
            "provided": True,
            "status": "failed",
            "archive_path": str(export_bundle),
            "manifest_path": str(manifest_path) if manifest_path is not None else None,
            "checksum_path": str(checksum_path) if checksum_path is not None else None,
            "verification": None,
            "error": str(exc),
        }

    return {
        "provided": True,
        "status": "verified" if verification.get("ok") else "failed",
        "archive_path": str(export_bundle),
        "manifest_path": verification.get("manifest_path"),
        "checksum_path": verification.get("checksum_path"),
        "verification": verification if verification.get("ok") else None,
        "error": None if verification.get("ok") else verification.get("error"),
    }


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


def wipe_drill_report(
    config: OskConfig | None = None,
    *,
    export_bundle: Path | None = None,
    manifest_path: Path | None = None,
    checksum_path: Path | None = None,
) -> dict[str, object]:
    cfg = config or load_config()
    storage = default_storage_manager(cfg)
    hub_state = read_hub_state()
    hub_running = hub_state is not None
    operation_id = (
        str(hub_state.get("operation_id")) if hub_state and hub_state.get("operation_id") else None
    )
    operator_session = read_operator_session()
    operator_session_active = bool(
        operator_session and operation_id and operator_session.get("operation_id") == operation_id
    )

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
            "name": "coordinator_wipe_command",
            "available": hub_running and operator_session_active,
            "details": (
                "The explicit `osk wipe --yes` flow uses the local operator "
                "session to broadcast wipe and then stop the hub."
            ),
        },
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
                "The current member shell clears queued local browser state, current member "
                "cookies, service-worker caches, and the installed member-shell registration "
                "after a live `wipe` or `op_ended` message."
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
        "Disconnected member browsers will not receive a live wipe broadcast until they reconnect.",
        "Browser history and OS-level caches remain outside the app-controlled wipe boundary.",
        "The preserved evidence image is not removed by the runtime wipe primitive.",
    ]
    if not hub_running:
        gaps.insert(
            0,
            "No running hub state was found, so the live member wipe broadcast "
            "path cannot be exercised here.",
        )
    elif not operator_session_active:
        gaps.insert(
            0,
            "No active local operator session is available for this operation, "
            "so `osk wipe` would be blocked until you run `osk operator login`.",
        )

    evidence_bundle = _wipe_bundle_report(
        export_bundle=export_bundle,
        manifest_path=manifest_path,
        checksum_path=checksum_path,
    )

    next_steps = [
        "Export preserved evidence first if you need to retain pinned material before cleanup.",
        "Verify the exported archive before wipe or destroy using "
        "`osk evidence verify --input ...`.",
        "Run `osk wipe --yes` from the coordinator host while a local operator session is active.",
        "Run `osk evidence destroy --yes` only if you want permanent removal "
        "of preserved evidence storage.",
    ]
    if evidence_bundle["provided"]:
        if evidence_bundle["status"] == "verified":
            next_steps.insert(
                1,
                "The supplied evidence bundle verified cleanly; keep the archive, "
                "manifest, and checksum together for handoff.",
            )
        else:
            next_steps.insert(
                1,
                "The supplied evidence bundle did not verify; re-export or repair "
                "that bundle before wipe or destroy.",
            )
    if storage.backend == "directory":
        next_steps.append(
            "This machine is using directory-backed development storage, so there is no encrypted "
            "evidence image to shred."
        )

    closure_interpretation = {
        "active_unresolved": (
            "Current follow-up work tied to the live cleanup boundary and requiring "
            "explicit operator action."
        ),
        "historical_drift": (
            "Older unresolved follow-up that still pollutes readiness and should be reviewed, "
            "but is not silently resolved by age alone."
        ),
        "verified_current": (
            "A manual verification that still closes the current cleanup boundary."
        ),
        "reviewed_historical_drift": (
            "Historical drift that has been inspected and documented for handoff, but still "
            "leaves the cleanup boundary open until separately verified or cleared."
        ),
    }

    return {
        "drill": "wipe",
        "status": "partial",
        "hub_running": hub_running,
        "operation_id": operation_id,
        "operator_session_active": operator_session_active,
        "storage_backend": storage.backend,
        "capabilities": capabilities,
        "paths": paths,
        "evidence_bundle": evidence_bundle,
        "gaps": gaps,
        "next_steps": next_steps,
        "closure_interpretation": closure_interpretation,
        "read_only": True,
    }
