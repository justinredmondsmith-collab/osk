"""Helpers for audit-event filtering."""

from __future__ import annotations

WIPE_FOLLOW_UP_AUDIT_ACTIONS = (
    "wipe_follow_up_verified",
    "wipe_follow_up_reopened",
    "wipe_follow_up_historical_reviewed",
)


def build_audit_action_filter(
    actions: list[str] | None = None,
    *,
    wipe_follow_up_only: bool = False,
) -> list[str] | None:
    merged: list[str] = []
    for action in actions or []:
        normalized = str(action).strip()
        if normalized and normalized not in merged:
            merged.append(normalized)
    if wipe_follow_up_only:
        for action in WIPE_FOLLOW_UP_AUDIT_ACTIONS:
            if action not in merged:
                merged.append(action)
    return merged or None
