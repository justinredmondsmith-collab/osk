from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import logging
from pathlib import Path
from typing import Sequence

from . import __version__
from .config import OskConfig, load_config, save_config
from .models import EventCategory, EventSeverity, FindingStatus


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _doctor_snapshot() -> tuple[int, dict[str, object]]:
    root = _repo_root()
    checks = [
        ("pyproject.toml", root / "pyproject.toml"),
        ("package", root / "src" / "osk"),
        ("tests", root / "tests"),
        ("design spec", root / "docs" / "specs" / "2026-03-21-osk-design.md"),
        ("phase plans", root / "docs" / "plans"),
    ]

    scaffold_checks: list[dict[str, object]] = []
    for label, path in checks:
        present = path.exists()
        scaffold_checks.append(
            {
                "label": label,
                "path": str(path),
                "present": present,
                "status": "ok" if present else "missing",
            }
        )

    scaffold_ok = all(check["present"] for check in scaffold_checks)

    from .hub import (
        default_storage_manager,
        hotspot_preflight_status,
        hub_status_snapshot,
        installation_issues,
        local_service_mode,
    )

    cfg = load_config()
    issues = installation_issues(cfg, default_storage_manager(cfg))
    _, hub_status = hub_status_snapshot()

    payload = {
        "scaffold": {
            "checks": scaffold_checks,
            "ready": scaffold_ok,
        },
        "install": {
            "issues": issues,
            "ready": not issues,
            "service_mode": local_service_mode(cfg),
        },
        "hotspot": hotspot_preflight_status(cfg),
        "hub": hub_status,
    }
    code = 0 if scaffold_ok and not issues else 1
    return code, payload


def _cmd_doctor(args: argparse.Namespace) -> int:
    code, payload = _doctor_snapshot()
    if args.json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return code

    print("Osk scaffold status")
    for check in payload["scaffold"]["checks"]:
        print(f"- {check['label']}: {check['status']} ({check['path']})")

    if payload["scaffold"]["ready"]:
        print("Scaffold ready for Phase 1 implementation work.")
    else:
        print("Scaffold incomplete. Fix missing paths before continuing.")
        return 1

    print(f"Service mode: {payload['install']['service_mode']}")
    if payload["install"]["issues"]:
        print("Install readiness: missing")
        for issue in payload["install"]["issues"]:
            print(f"- {issue}")
        print("Run `osk install` before starting the hub.")
    else:
        print("Install readiness: ok")

    hotspot = payload["hotspot"]
    print(
        "Hotspot readiness: "
        f"{hotspot['status']} (ssid={hotspot['ssid']}, "
        f"ip={hotspot['ip_address'] or 'unknown'})"
    )
    print(f"Join host: {hotspot['join_host']}")
    if hotspot["warnings"]:
        print("Field network guidance:")
        for warning in hotspot["warnings"]:
            print(f"- {warning}")
    else:
        print("Field network guidance: no blocking hotspot warnings.")
    for action in hotspot["actions"]:
        print(f"- {action}")
    return code


def _cmd_placeholder(args: argparse.Namespace) -> int:
    print(f"'{args.command}' is planned but not implemented yet.")
    print("Use 'osk doctor' for scaffold status and see docs/plans/ for roadmap details.")
    return 1


def _cmd_version(_: argparse.Namespace) -> int:
    print(__version__)
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def _coerce_config_value(cfg: OskConfig, key: str, raw_value: str):
    if key not in cfg.model_fields:
        raise KeyError(key)
    current = getattr(cfg, key)
    target_type = type(current)
    if target_type is bool:
        return raw_value.lower() in {"1", "true", "yes", "on"}
    return target_type(raw_value)


def _cmd_install(_: argparse.Namespace) -> int:
    from .hub import install

    install()
    return 0


def _cmd_wipe(args: argparse.Namespace) -> int:
    from .hub import default_storage_manager, read_hub_state, wipe_hub
    from .local_operator import read_operator_session

    state = read_hub_state()
    operation_id = str(state.get("operation_id")) if state and state.get("operation_id") else None
    session = read_operator_session()
    if (
        state is None
        or not operation_id
        or session is None
        or session.get("operation_id") != operation_id
    ):
        return wipe_hub(
            wait_seconds=args.timeout,
            stop_services=args.services,
            destroy_evidence=args.destroy_evidence,
            json_output=args.json_output,
        )

    if not args.yes:
        storage = default_storage_manager(load_config())
        if args.destroy_evidence:
            prompt = (
                "Trigger wipe broadcast, stop the hub, and permanently destroy preserved "
                f"evidence at {storage.luks_image_path}? [y/N]: "
            )
        else:
            prompt = (
                "Trigger wipe broadcast and stop the hub? Preserved evidence will remain on "
                "disk. [y/N]: "
            )
        confirmation = input(prompt).strip().lower()
        if confirmation not in {"y", "yes"}:
            print("Wipe cancelled.")
            return 1

    return wipe_hub(
        wait_seconds=args.timeout,
        stop_services=args.services,
        destroy_evidence=args.destroy_evidence,
        json_output=args.json_output,
    )


def _cmd_drill(args: argparse.Namespace) -> int:
    from .drills import install_drill_report, wipe_drill_report

    if args.drill_command == "install":
        payload = install_drill_report()
    elif args.drill_command == "wipe":
        payload = wipe_drill_report()
    else:
        print("Unknown drill command.")
        return 1

    if args.json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload["status"] == "ready" else 1

    print(f"{payload['drill'].capitalize()} drill: {payload['status']}")
    print("Read-only: this command does not change host or browser state.")

    if payload["drill"] == "install":
        print(f"service_mode = {payload['service_mode']}")
        print(f"install_ready = {str(payload['install_ready']).lower()}")
        compose = payload["compose"]
        if compose["required"]:
            print(f"compose_available = {str(bool(compose['available'])).lower()}")
            if compose["command"]:
                print(f"compose_command = {compose['command']}")
            elif compose["note"]:
                print(f"compose_note = {compose['note']}")
        else:
            print("compose_required = false")
        hotspot = payload["hotspot"]
        print(
            "hotspot = "
            f"{hotspot['status']} (ssid={hotspot['ssid']}, ip={hotspot['ip_address'] or 'unknown'})"
        )
        print(f"join_host = {hotspot['join_host']}")
        if payload["issues"]:
            print("Issues:")
            for issue in payload["issues"]:
                print(f"- {issue}")
        if hotspot["warnings"]:
            print("Field network guidance:")
            for warning in hotspot["warnings"]:
                print(f"- {warning}")
    else:
        print(f"hub_running = {str(payload['hub_running']).lower()}")
        print(f"storage_backend = {payload['storage_backend']}")
        print("Current capabilities:")
        for capability in payload["capabilities"]:
            availability = "available" if capability["available"] else "not_available"
            print(f"- {capability['name']}: {availability} — {capability['details']}")
        print("Host paths:")
        for path_entry in payload["paths"]:
            exists = "present" if path_entry["exists"] else "missing"
            print(f"- {path_entry['label']}: {exists} ({path_entry['path']})")
            print(f"  current_behavior = {path_entry['current_behavior']}")
        if payload["gaps"]:
            print("Known gaps:")
            for gap in payload["gaps"]:
                print(f"- {gap}")

    if payload["next_steps"]:
        print("Next steps:")
        for step in payload["next_steps"]:
            print(f"- {step}")

    return 0 if payload["status"] == "ready" else 1


def _cmd_start(args: argparse.Namespace) -> int:
    from .hub import run_hub_sync

    return run_hub_sync(args.name)


def _cmd_status(_: argparse.Namespace) -> int:
    from .hub import status_hub

    return status_hub(json_output=_.json_output)


def _cmd_stop(args: argparse.Namespace) -> int:
    from .hub import stop_hub

    return stop_hub(wait_seconds=args.timeout, stop_services=args.services)


def _cmd_config(args: argparse.Namespace) -> int:
    cfg = load_config()
    if args.set:
        key, sep, value = args.set.partition("=")
        if not sep:
            print("Expected config assignment in the form key=value.")
            return 1
        try:
            coerced = _coerce_config_value(cfg, key, value)
        except (KeyError, ValueError, TypeError):
            print(f"Invalid config setting: {args.set}")
            return 1
        cfg = cfg.model_copy(update={key: coerced})
        save_config(cfg)
        print(f"Set {key} = {getattr(cfg, key)}")
        return 0

    for key, value in cfg.model_dump().items():
        print(f"{key} = {value}")
    return 0


def _cmd_operator_login(args: argparse.Namespace) -> int:
    from .hub import login_operator_session

    return login_operator_session(ttl_minutes=args.ttl_minutes, json_output=args.json_output)


def _cmd_operator_status(args: argparse.Namespace) -> int:
    from .hub import status_operator_session

    return status_operator_session(json_output=args.json_output)


def _cmd_operator_logout(_: argparse.Namespace) -> int:
    from .hub import logout_operator_session

    return logout_operator_session()


def _cmd_audit(args: argparse.Namespace) -> int:
    from .hub import show_audit_events

    return show_audit_events(limit=args.limit, json_output=args.json_output)


def _cmd_logs(args: argparse.Namespace) -> int:
    from .hub import show_runtime_logs

    return show_runtime_logs(tail=args.tail)


def _cmd_dashboard(args: argparse.Namespace) -> int:
    from .hub import show_dashboard_url

    return show_dashboard_url(json_output=args.json_output)


def _cmd_members(args: argparse.Namespace) -> int:
    from .hub import show_members

    return show_members(json_output=args.json_output)


def _cmd_findings(args: argparse.Namespace) -> int:
    from .hub import show_findings

    return show_findings(limit=args.limit, json_output=args.json_output)


def _cmd_review(args: argparse.Namespace) -> int:
    from .hub import show_review_feed

    finding_status = FindingStatus(args.status) if args.status else None
    severity = EventSeverity(args.severity) if args.severity else None
    category = EventCategory(args.category) if args.category else None
    include_types = set(args.include) if args.include else None
    return show_review_feed(
        limit=args.limit,
        include_types=include_types,
        finding_status=finding_status,
        severity=severity,
        category=category,
        json_output=args.json_output,
    )


def _cmd_finding_show(args: argparse.Namespace) -> int:
    from .hub import show_finding

    return show_finding(args.finding_id, json_output=args.json_output)


def _cmd_finding_acknowledge(args: argparse.Namespace) -> int:
    from .hub import acknowledge_finding

    return acknowledge_finding(args.finding_id)


def _cmd_finding_resolve(args: argparse.Namespace) -> int:
    from .hub import resolve_finding

    return resolve_finding(args.finding_id)


def _cmd_finding_reopen(args: argparse.Namespace) -> int:
    from .hub import reopen_finding

    return reopen_finding(args.finding_id)


def _cmd_finding_escalate(args: argparse.Namespace) -> int:
    from .hub import escalate_finding

    return escalate_finding(args.finding_id)


def _cmd_finding_correlations(args: argparse.Namespace) -> int:
    from .hub import show_finding_correlations

    return show_finding_correlations(
        args.finding_id,
        limit=args.limit,
        window_minutes=args.window_minutes,
        json_output=args.json_output,
    )


def _cmd_finding_note(args: argparse.Namespace) -> int:
    from .hub import add_finding_note

    return add_finding_note(args.finding_id, args.text)


def _cmd_rotate_token(_: argparse.Namespace) -> int:
    print("Token rotation requires a running hub and is not wired through the CLI yet.")
    return 1


def _format_bytes(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024.0 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} {unit}"
        value /= 1024.0
    return f"{int(num_bytes)} B"


def _cmd_tiles_status(args: argparse.Namespace) -> int:
    from .tiles import TileCacher

    cfg = load_config()
    status = TileCacher(Path(cfg.map_tile_cache_path)).status()
    if args.json_output:
        print(json.dumps(status, indent=2, sort_keys=True))
        return 0

    zooms = ", ".join(str(zoom) for zoom in status["zoom_levels"]) or "none"
    print(f"cache_root = {status['cache_root']}")
    print(f"tile_count = {status['tile_count']}")
    print(f"size = {_format_bytes(int(status['total_bytes']))} ({status['total_bytes']} bytes)")
    print(f"zoom_levels = {zooms}")
    return 0


def _cmd_tiles_cache(args: argparse.Namespace) -> int:
    from .tiles import TileCacher, parse_bbox, parse_zoom_range

    try:
        bbox = parse_bbox(args.bbox)
        zoom_levels = parse_zoom_range(args.zoom)
    except ValueError as exc:
        print(f"Invalid tile cache input: {exc}")
        return 1

    cfg = load_config()
    cacher = TileCacher(Path(cfg.map_tile_cache_path))
    try:
        stats = asyncio.run(cacher.cache_area(bbox, zoom_levels))
    except Exception as exc:
        print(f"Failed to cache tiles: {exc}")
        return 1

    if args.json_output:
        print(json.dumps(stats, indent=2, sort_keys=True))
        return 0

    print(f"cache_root = {stats['cache_root']}")
    print(f"requested_tiles = {stats['requested_tiles']}")
    print(f"downloaded_tiles = {stats['downloaded_tiles']}")
    print(f"skipped_tiles = {stats['skipped_tiles']}")
    print(f"size = {_format_bytes(int(stats['total_bytes']))} ({stats['total_bytes']} bytes)")
    print(f"zoom_levels = {', '.join(str(zoom) for zoom in stats['zoom_levels'])}")
    return 0


def _hotspot_manager_from_args(args: argparse.Namespace):
    from .hotspot import HotspotManager

    cfg = load_config()
    ssid = getattr(args, "ssid", None) or cfg.hotspot_ssid or "osk-local"
    band = getattr(args, "band", None) or cfg.hotspot_band
    password = getattr(args, "password", None)
    return HotspotManager(ssid=ssid, band=band, password=password)


def _cmd_hotspot_status(args: argparse.Namespace) -> int:
    manager = _hotspot_manager_from_args(args)
    payload = manager.status()
    if args.json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    print(f"available = {payload['available']}")
    print(f"ssid = {payload['ssid']}")
    print(f"band = {payload['band']}")
    print(f"connection_name = {payload['connection_name']}")
    print(f"ip_address = {payload['ip_address'] or 'unknown'}")
    if payload["manual_instructions"]:
        print(payload["manual_instructions"])
    return 0


def _cmd_hotspot_up(args: argparse.Namespace) -> int:
    manager = _hotspot_manager_from_args(args)
    if not manager.is_available():
        print(manager.get_manual_instructions())
        return 1
    if not args.password:
        print("Hotspot password is required for `osk hotspot up`.")
        return 1
    if not manager.start():
        print("Failed to start hotspot.")
        return 1
    print(f"Hotspot started for SSID {manager.ssid}.")
    if ip_address := manager.get_ip():
        print(f"ip_address = {ip_address}")
    return 0


def _cmd_hotspot_down(args: argparse.Namespace) -> int:
    manager = _hotspot_manager_from_args(args)
    if not manager.is_available():
        print("NetworkManager (nmcli) is not available.")
        return 1
    if not manager.stop():
        print("Failed to stop hotspot.")
        return 1
    print(f"Hotspot stopped for SSID {manager.ssid}.")
    return 0


def _cmd_hotspot_instructions(args: argparse.Namespace) -> int:
    manager = _hotspot_manager_from_args(args)
    print(manager.get_manual_instructions())
    return 0


def _evidence_manager():
    from .evidence import EvidenceManager
    from .hub import default_storage_manager

    cfg = load_config()
    return EvidenceManager.from_storage(default_storage_manager(cfg))


def _cmd_evidence(args: argparse.Namespace) -> int:
    manager = _evidence_manager()

    if args.evidence_command == "unlock":
        passphrase = (
            "" if manager.backend == "directory" else getpass.getpass("Evidence passphrase: ")
        )
        try:
            result = manager.unlock(passphrase)
        except Exception as exc:
            print(f"Failed to unlock evidence: {exc}")
            return 1
    elif args.evidence_command == "export":
        try:
            result = manager.export(Path(args.output))
        except Exception as exc:
            print(f"Failed to export evidence: {exc}")
            return 1
    elif args.evidence_command == "destroy":
        if not args.yes:
            target = (
                manager.luks_mount_path
                if manager.backend == "directory"
                else manager.luks_image_path
            )
            confirmation = input(f"Destroy preserved evidence at {target}? [y/N]: ").strip().lower()
            if confirmation not in {"y", "yes"}:
                print("Aborted.")
                return 1
        try:
            result = manager.destroy()
        except Exception as exc:
            print(f"Failed to destroy evidence: {exc}")
            return 1
    else:
        print("Unknown evidence command.")
        return 1

    if args.json_output:
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 1

    if not result.get("ok"):
        print(result.get("error", "Evidence command failed."))
        return 1

    if args.evidence_command == "unlock":
        print(f"mount_path = {result['mount_path']}")
        print(f"item_count = {result['item_count']}")
        for item in result["items"][:20]:
            print(f"- {item['path']} ({item['size_bytes']} bytes)")
        return 0
    if args.evidence_command == "export":
        print(f"output_path = {result['output_path']}")
        print(f"file_count = {result['file_count']}")
        print(f"size = {_format_bytes(int(result['total_bytes']))} ({result['total_bytes']} bytes)")
        return 0

    print(f"destroyed_path = {result['destroyed_path']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="osk",
        description="Osk development scaffold and CLI entrypoint.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command")

    version_parser = subparsers.add_parser("version", help="Print the package version.")
    version_parser.set_defaults(func=_cmd_version)

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Report whether the local Phase 1 scaffold is present.",
    )
    doctor_parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    doctor_parser.set_defaults(func=_cmd_doctor)

    install_parser = subparsers.add_parser(
        "install", help="Install local prerequisites and assets."
    )
    install_parser.set_defaults(func=_cmd_install)

    wipe_parser = subparsers.add_parser(
        "wipe",
        help="Broadcast a wipe to members and stop the local hub.",
    )
    wipe_parser.add_argument(
        "--services",
        action="store_true",
        help="Also stop local Compose-managed services after the hub stops.",
    )
    wipe_parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Seconds to wait for the hub to stop cleanly.",
    )
    wipe_parser.add_argument(
        "--destroy-evidence",
        action="store_true",
        help="Also permanently remove preserved evidence after the hub stops.",
    )
    wipe_parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the interactive confirmation prompt.",
    )
    wipe_parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    wipe_parser.set_defaults(func=_cmd_wipe)

    drill_parser = subparsers.add_parser(
        "drill",
        help="Run a read-only install or wipe drill report.",
    )
    drill_sub = drill_parser.add_subparsers(dest="drill_command")

    drill_install = drill_sub.add_parser(
        "install",
        help="Report install/start readiness and operator next steps.",
    )
    drill_install.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    drill_install.set_defaults(func=_cmd_drill)

    drill_wipe = drill_sub.add_parser(
        "wipe",
        help="Report the current wipe boundary and cleanup runbook.",
    )
    drill_wipe.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    drill_wipe.set_defaults(func=_cmd_drill)

    start_parser = subparsers.add_parser("start", help="Start an operation.")
    start_parser.add_argument("name", help="Operation name")
    start_parser.set_defaults(func=_cmd_start)

    status_parser = subparsers.add_parser("status", help="Report hub runtime status.")
    status_parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Emit machine-readable JSON status output.",
    )
    status_parser.set_defaults(func=_cmd_status)

    stop_parser = subparsers.add_parser("stop", help="Stop the current operation.")
    stop_parser.add_argument(
        "--services",
        action="store_true",
        help="Also stop local Compose-managed services used by the current phase.",
    )
    stop_parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Seconds to wait for the hub process to exit cleanly.",
    )
    stop_parser.set_defaults(func=_cmd_stop)

    config_parser = subparsers.add_parser("config", help="View or set configuration.")
    config_parser.add_argument(
        "--set", dest="set", help="Set a config value in the form key=value."
    )
    config_parser.set_defaults(func=_cmd_config)

    operator_parser = subparsers.add_parser("operator", help="Manage local operator sessions.")
    operator_sub = operator_parser.add_subparsers(dest="operator_command")

    operator_login = operator_sub.add_parser(
        "login", help="Create or refresh a local operator session."
    )
    operator_login.add_argument(
        "--ttl-minutes",
        type=int,
        default=None,
        help="Override the configured operator session TTL.",
    )
    operator_login.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    operator_login.set_defaults(func=_cmd_operator_login)

    operator_status = operator_sub.add_parser("status", help="Show local operator session status.")
    operator_status.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    operator_status.set_defaults(func=_cmd_operator_status)

    operator_logout = operator_sub.add_parser("logout", help="Remove the local operator session.")
    operator_logout.set_defaults(func=_cmd_operator_logout)

    audit_parser = subparsers.add_parser("audit", help="Show recent audit events from the hub.")
    audit_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of audit events to display.",
    )
    audit_parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    audit_parser.set_defaults(func=_cmd_audit)

    logs_parser = subparsers.add_parser("logs", help="Show recent hub runtime logs.")
    logs_parser.add_argument(
        "--tail",
        type=int,
        default=100,
        help="Number of log lines to display.",
    )
    logs_parser.set_defaults(func=_cmd_logs)

    dashboard_parser = subparsers.add_parser(
        "dashboard",
        help="Print the local coordinator dashboard URL.",
    )
    dashboard_parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    dashboard_parser.set_defaults(func=_cmd_dashboard)

    members_parser = subparsers.add_parser("members", help="Show current operation members.")
    members_parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    members_parser.set_defaults(func=_cmd_members)

    findings_parser = subparsers.add_parser(
        "findings",
        help="Show reviewable synthesis findings from the hub.",
    )
    findings_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of findings to display.",
    )
    findings_parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    findings_parser.set_defaults(func=_cmd_findings)

    review_parser = subparsers.add_parser(
        "review",
        help="Show the mixed coordinator review feed.",
    )
    review_parser.add_argument(
        "--limit",
        type=int,
        default=25,
        help="Maximum number of review items to display.",
    )
    review_parser.add_argument(
        "--include",
        action="append",
        choices=("finding", "event", "sitrep"),
        help="Review item type to include. Repeat to include multiple types.",
    )
    review_parser.add_argument(
        "--status",
        choices=tuple(status.value for status in FindingStatus),
        help="Filter findings in the review feed by status.",
    )
    review_parser.add_argument(
        "--severity",
        choices=tuple(severity.value for severity in EventSeverity),
        help="Filter findings and events in the review feed by severity.",
    )
    review_parser.add_argument(
        "--category",
        choices=tuple(category.value for category in EventCategory),
        help="Filter findings and events in the review feed by category.",
    )
    review_parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    review_parser.set_defaults(func=_cmd_review)

    finding_parser = subparsers.add_parser("finding", help="Review or triage one finding.")
    finding_sub = finding_parser.add_subparsers(dest="finding_command")

    finding_show = finding_sub.add_parser("show", help="Show one finding with context.")
    finding_show.add_argument("finding_id", help="Finding identifier")
    finding_show.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    finding_show.set_defaults(func=_cmd_finding_show)

    finding_ack = finding_sub.add_parser("acknowledge", help="Acknowledge one finding.")
    finding_ack.add_argument("finding_id", help="Finding identifier")
    finding_ack.set_defaults(func=_cmd_finding_acknowledge)

    finding_resolve = finding_sub.add_parser("resolve", help="Resolve one finding.")
    finding_resolve.add_argument("finding_id", help="Finding identifier")
    finding_resolve.set_defaults(func=_cmd_finding_resolve)

    finding_reopen = finding_sub.add_parser("reopen", help="Reopen one finding.")
    finding_reopen.add_argument("finding_id", help="Finding identifier")
    finding_reopen.set_defaults(func=_cmd_finding_reopen)

    finding_escalate = finding_sub.add_parser("escalate", help="Escalate one finding.")
    finding_escalate.add_argument("finding_id", help="Finding identifier")
    finding_escalate.set_defaults(func=_cmd_finding_escalate)

    finding_correlations = finding_sub.add_parser(
        "correlations",
        help="Show events and findings correlated to one finding.",
    )
    finding_correlations.add_argument("finding_id", help="Finding identifier")
    finding_correlations.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of related findings/events to display.",
    )
    finding_correlations.add_argument(
        "--window-minutes",
        type=int,
        default=30,
        help="Correlation window around the finding lifecycle.",
    )
    finding_correlations.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    finding_correlations.set_defaults(func=_cmd_finding_correlations)

    finding_note = finding_sub.add_parser("note", help="Attach a note to one finding.")
    finding_note.add_argument("finding_id", help="Finding identifier")
    finding_note.add_argument("text", help="Note text")
    finding_note.set_defaults(func=_cmd_finding_note)

    rotate_parser = subparsers.add_parser("rotate-token", help="Rotate the operation token.")
    rotate_parser.set_defaults(func=_cmd_rotate_token)

    tiles_parser = subparsers.add_parser("tiles", help="Inspect or populate the tile cache.")
    tiles_sub = tiles_parser.add_subparsers(dest="tiles_command")

    tiles_status = tiles_sub.add_parser("status", help="Show local cached tile status.")
    tiles_status.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    tiles_status.set_defaults(func=_cmd_tiles_status)

    tiles_cache = tiles_sub.add_parser("cache", help="Download tiles for a bbox and zoom range.")
    tiles_cache.add_argument(
        "--bbox",
        required=True,
        help="Bounding box in south,west,north,east order.",
    )
    tiles_cache.add_argument(
        "--zoom",
        required=True,
        help="Single zoom, inclusive range, or comma list (for example: 13-15 or 14,16).",
    )
    tiles_cache.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    tiles_cache.set_defaults(func=_cmd_tiles_cache)

    hotspot_parser = subparsers.add_parser(
        "hotspot",
        help="Inspect or control a local NetworkManager hotspot.",
    )
    hotspot_sub = hotspot_parser.add_subparsers(dest="hotspot_command")

    hotspot_status = hotspot_sub.add_parser("status", help="Show hotspot availability and IP.")
    hotspot_status.add_argument("--ssid", help="Override the configured hotspot SSID.")
    hotspot_status.add_argument("--band", help="Override the configured hotspot band.")
    hotspot_status.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    hotspot_status.set_defaults(func=_cmd_hotspot_status)

    hotspot_up = hotspot_sub.add_parser("up", help="Start a local hotspot via nmcli.")
    hotspot_up.add_argument("--ssid", help="Override the configured hotspot SSID.")
    hotspot_up.add_argument("--band", help="Override the configured hotspot band.")
    hotspot_up.add_argument(
        "--password",
        required=True,
        help="Passphrase to use when creating the hotspot.",
    )
    hotspot_up.set_defaults(func=_cmd_hotspot_up)

    hotspot_down = hotspot_sub.add_parser("down", help="Stop the local hotspot via nmcli.")
    hotspot_down.add_argument("--ssid", help="Override the configured hotspot SSID.")
    hotspot_down.add_argument("--band", help="Override the configured hotspot band.")
    hotspot_down.set_defaults(func=_cmd_hotspot_down)

    hotspot_instructions = hotspot_sub.add_parser(
        "instructions",
        help="Print manual hotspot setup instructions.",
    )
    hotspot_instructions.add_argument("--ssid", help="Override the configured hotspot SSID.")
    hotspot_instructions.add_argument("--band", help="Override the configured hotspot band.")
    hotspot_instructions.add_argument(
        "--password",
        help="Optional passphrase hint to include in the instructions.",
    )
    hotspot_instructions.set_defaults(func=_cmd_hotspot_instructions)

    evidence_parser = subparsers.add_parser("evidence", help="Manage pinned evidence.")
    evidence_sub = evidence_parser.add_subparsers(dest="evidence_command")

    evidence_unlock = evidence_sub.add_parser("unlock", help="Unlock and view pinned evidence.")
    evidence_unlock.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    evidence_unlock.set_defaults(func=_cmd_evidence)

    evidence_export = evidence_sub.add_parser("export", help="Export pinned evidence.")
    evidence_export.add_argument(
        "--output",
        default="osk-evidence-export.zip",
        help="Zip path for the exported evidence bundle.",
    )
    evidence_export.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    evidence_export.set_defaults(func=_cmd_evidence)

    evidence_destroy = evidence_sub.add_parser("destroy", help="Destroy preserved evidence.")
    evidence_destroy.add_argument(
        "--yes",
        action="store_true",
        help="Skip the interactive confirmation prompt.",
    )
    evidence_destroy.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    evidence_destroy.set_defaults(func=_cmd_evidence)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    parser = build_parser()
    args = parse_args(argv)

    if not hasattr(args, "func"):
        parser.print_help()
        return 0

    return int(args.func(args))
