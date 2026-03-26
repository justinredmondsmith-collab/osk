from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _load_summary(latest_path: Path) -> dict[str, Any]:
    payload = json.loads(latest_path.read_text())
    provenance = payload.get("provenance") or {}
    handoff = payload.get("operator_handoff") or {}
    return {
        "status": payload.get("status") or "",
        "trigger": provenance.get("trigger") or "",
        "branch": provenance.get("git_branch") or "",
        "git_sha": provenance.get("git_sha") or "",
        "artifact_dir": payload.get("artifact_dir") or "",
        "result_path": payload.get("result_path") or "",
        "handoff_path": handoff.get("path") or "",
        "operator_closure_status": handoff.get("operator_closure_status") or "",
        "operator_closure_state": handoff.get("operator_closure_state") or "",
        "wipe_observed_status": handoff.get("wipe_observed_status") or "",
        "follow_up_required": handoff.get("follow_up_required"),
        "unresolved_follow_up_count": handoff.get("unresolved_follow_up_count"),
        "follow_up_summary": handoff.get("follow_up_summary") or "",
        "latest_path": str(latest_path),
    }


def _write_github_output(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        f"status={summary['status']}",
        f"handoff_path={summary['handoff_path']}",
        f"operator_closure_status={summary['operator_closure_status']}",
        f"operator_closure_state={summary['operator_closure_state']}",
        f"wipe_observed_status={summary['wipe_observed_status']}",
        "follow_up_required="
        + ("" if summary["follow_up_required"] is None else str(summary["follow_up_required"])),
        "unresolved_follow_up_count="
        + (
            ""
            if summary["unresolved_follow_up_count"] is None
            else str(summary["unresolved_follow_up_count"])
        ),
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_step_summary(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# Chromebook Real Hub Gate",
        "",
        f"- Status: `{summary['status'] or '<unknown>'}`",
        f"- Trigger: `{summary['trigger'] or '<unknown>'}`",
        f"- Branch: `{summary['branch'] or '<unknown>'}`",
        f"- Git SHA: `{summary['git_sha'] or '<unknown>'}`",
        f"- Run Dir: `{summary['artifact_dir'] or '<unknown>'}`",
        f"- Result: `{summary['result_path'] or '<unknown>'}`",
        f"- Latest: `{summary['latest_path']}`",
    ]
    if summary["handoff_path"]:
        lines.append(f"- Handoff: `{summary['handoff_path']}`")
    if summary["operator_closure_status"] or summary["operator_closure_state"]:
        lines.append(
            "- Closure: "
            f"`{summary['operator_closure_status'] or '<unknown>'}` / "
            f"`{summary['operator_closure_state'] or '<unknown>'}`"
        )
    if summary["wipe_observed_status"]:
        lines.append(f"- Wipe: `{summary['wipe_observed_status']}`")
    if summary["follow_up_required"] is not None:
        lines.append(f"- Follow Up Required: `{summary['follow_up_required']}`")
    if summary["unresolved_follow_up_count"] is not None:
        lines.append(f"- Unresolved Follow Up Count: `{summary['unresolved_follow_up_count']}`")
    if summary["follow_up_summary"]:
        lines.append(f"- Note: {summary['follow_up_summary']}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _annotation(summary: dict[str, Any]) -> tuple[str, str]:
    status = summary["status"]
    closure_state = summary["operator_closure_state"]
    follow_up_required = summary["follow_up_required"]
    handoff_path = summary["handoff_path"]
    suffix = f" Handoff: {handoff_path}" if handoff_path else ""

    if status != "passed":
        return (
            "error",
            "Chromebook real-hub gate failed. Inspect the indexed result and handoff artifacts."
            + suffix,
        )

    open_follow_up_states = {"captured_open_follow_up", "unavailable", "error"}
    if follow_up_required is True or closure_state in open_follow_up_states:
        return (
            "warning",
            "Chromebook real-hub gate completed with open operator follow-up." + suffix,
        )

    return (
        "notice",
        "Chromebook real-hub gate completed without unresolved operator follow-up." + suffix,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Summarize indexed Chromebook real-hub gate results for GitHub Actions."
    )
    parser.add_argument("--latest-path", required=True, help="Path to latest.json")
    parser.add_argument("--github-output", help="Optional GitHub output file path")
    parser.add_argument("--github-step-summary", help="Optional GitHub step summary path")
    parser.add_argument("--annotate-github", action="store_true", help="Emit a workflow annotation")
    parser.add_argument("--json", action="store_true", help="Emit the summary as JSON to stdout")
    args = parser.parse_args(argv)

    summary = _load_summary(Path(args.latest_path))

    if args.github_output:
        _write_github_output(Path(args.github_output), summary)
    if args.github_step_summary:
        _write_step_summary(Path(args.github_step_summary), summary)
    if args.annotate_github:
        level, message = _annotation(summary)
        print(f"::{level}::{message}")
    if args.json:
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
