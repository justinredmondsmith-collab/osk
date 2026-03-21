from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from . import __version__


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _cmd_doctor(_: argparse.Namespace) -> int:
    root = _repo_root()
    checks = [
        ("pyproject.toml", root / "pyproject.toml"),
        ("package", root / "src" / "osk"),
        ("tests", root / "tests"),
        ("design spec", root / "docs" / "specs" / "2026-03-21-osk-design.md"),
        ("phase plans", root / "docs" / "plans"),
    ]

    print("Osk scaffold status")
    ok = True
    for label, path in checks:
        present = path.exists()
        ok = ok and present
        status = "ok" if present else "missing"
        print(f"- {label}: {status} ({path})")

    if ok:
        print("Scaffold ready for Phase 1 implementation work.")
        return 0

    print("Scaffold incomplete. Fix missing paths before continuing.")
    return 1


def _cmd_placeholder(args: argparse.Namespace) -> int:
    print(f"'{args.command}' is planned but not implemented yet.")
    print("Use 'osk doctor' for scaffold status and see docs/plans/ for roadmap details.")
    return 1


def _cmd_version(_: argparse.Namespace) -> int:
    print(__version__)
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
    doctor_parser.set_defaults(func=_cmd_doctor)

    for name, help_text in (
        ("start", "Planned operation startup command."),
        ("stop", "Planned operation shutdown command."),
        ("config", "Planned configuration command."),
        ("evidence", "Planned evidence management command."),
    ):
        subparser = subparsers.add_parser(name, help=help_text)
        subparser.set_defaults(func=_cmd_placeholder, command=name)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not hasattr(args, "func"):
        parser.print_help()
        return 0

    return int(args.func(args))
