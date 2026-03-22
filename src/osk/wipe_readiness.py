"""Helpers for summarizing live member wipe readiness."""

from __future__ import annotations


def summarize_wipe_readiness(members: list[dict[str, object]]) -> dict[str, object]:
    fresh_members = 0
    stale_members = 0
    disconnected_members = 0
    considered_members = 0
    at_risk: list[dict[str, object]] = []

    for member in members:
        status = str(member.get("status") or "unknown")
        heartbeat_state = str(member.get("heartbeat_state") or "unknown")
        if status == "kicked":
            continue
        considered_members += 1

        risk_reason = None
        if status == "disconnected" or heartbeat_state == "disconnected":
            disconnected_members += 1
            risk_reason = "disconnected"
        elif heartbeat_state == "stale":
            stale_members += 1
            risk_reason = "stale"
        else:
            fresh_members += 1

        if risk_reason is not None:
            at_risk.append(
                {
                    "id": member.get("id"),
                    "name": member.get("name"),
                    "role": member.get("role"),
                    "status": status,
                    "heartbeat_state": heartbeat_state,
                    "seconds_since_last_seen": int(member.get("seconds_since_last_seen") or 0),
                    "last_seen_at": member.get("last_seen_at"),
                    "reason": risk_reason,
                }
            )

    at_risk.sort(
        key=lambda member: (
            0 if member["reason"] == "disconnected" else 1,
            -int(member["seconds_since_last_seen"] or 0),
            str(member["name"] or ""),
        )
    )

    at_risk_members = len(at_risk)
    if considered_members == 0:
        status = "idle"
        summary = "No member browsers are currently joined."
        ready = True
    elif disconnected_members > 0:
        status = "blocked"
        summary = (
            f"{at_risk_members} member browsers may miss a live wipe "
            f"({disconnected_members} disconnected, {stale_members} stale)."
        )
        ready = False
    elif stale_members > 0:
        status = "degraded"
        summary = (
            f"{stale_members} member browsers are stale and may miss a live wipe "
            "if they do not recover."
        )
        ready = False
    else:
        status = "ready"
        summary = f"All {fresh_members} current member browsers are reachable for a live wipe."
        ready = True

    return {
        "status": status,
        "ready": ready,
        "reachable_members": fresh_members,
        "stale_members": stale_members,
        "disconnected_members": disconnected_members,
        "at_risk_members": at_risk_members,
        "members_considered": considered_members,
        "summary": summary,
        "at_risk": at_risk,
    }
