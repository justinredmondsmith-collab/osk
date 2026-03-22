from __future__ import annotations

import argparse
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
        return 1

    print("Install readiness: ok")
    return 0


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


def _cmd_evidence(args: argparse.Namespace) -> int:
    messages = {
        "unlock": "Evidence unlock is not implemented yet.",
        "export": "Evidence export is not implemented yet.",
        "destroy": "Evidence destroy is not implemented yet.",
    }
    print(messages.get(args.evidence_command, "Unknown evidence command."))
    return 1


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

    evidence_parser = subparsers.add_parser("evidence", help="Manage pinned evidence.")
    evidence_sub = evidence_parser.add_subparsers(dest="evidence_command")
    for name, help_text in (
        ("unlock", "Unlock and view pinned evidence."),
        ("export", "Export pinned evidence."),
        ("destroy", "Destroy preserved evidence."),
    ):
        subparser = evidence_sub.add_parser(name, help=help_text)
        subparser.set_defaults(func=_cmd_evidence)

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
