"""Helpers for summarizing live member wipe readiness."""

from __future__ import annotations

import datetime as dt


def _follow_up_action_for_reason(reason: str) -> str:
    if reason == "disconnected":
        return (
            "Reconnect this member browser and confirm wipe, or record a manual cleanup "
            "verification before closing the cleanup boundary."
        )
    return (
        "Confirm this stale member browser recovers and receives wipe, or record a manual "
        "cleanup verification before closing the cleanup boundary."
    )


def _parse_timestamp(value: object) -> dt.datetime | None:
    if isinstance(value, dt.datetime):
        return value.astimezone(dt.timezone.utc)
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _isoformat_utc(timestamp: dt.datetime | None) -> str | None:
    if timestamp is None:
        return None
    return timestamp.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _resolved_follow_up(
    member: dict[str, object],
    follow_up_resolution: dict[str, object] | None,
) -> dict[str, object] | None:
    if not follow_up_resolution:
        return None
    verified_at = _parse_timestamp(follow_up_resolution.get("verified_at"))
    if verified_at is None:
        return None
    last_seen_at = _parse_timestamp(member.get("last_seen_at"))
    if last_seen_at is not None and verified_at < last_seen_at:
        return None
    verified_at_iso = _isoformat_utc(verified_at)
    return {
        "resolution": "verified",
        "verified_at": verified_at_iso,
        "required_action": None,
        "resolution_detail": (
            f"Verified after the member's last recorded activity at {verified_at_iso}."
            if verified_at_iso
            else "Verified after the member's last recorded activity."
        ),
    }


def summarize_wipe_readiness(
    members: list[dict[str, object]],
    *,
    follow_up_resolutions: dict[str, dict[str, object]] | None = None,
) -> dict[str, object]:
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
    resolution_index = follow_up_resolutions or {}
    follow_up = []
    for member in at_risk:
        follow_up_item = {
            **member,
            "resolution": "unresolved",
            "required_action": _follow_up_action_for_reason(str(member["reason"])),
            "verified_at": None,
        }
        resolved = _resolved_follow_up(
            member,
            resolution_index.get(str(member.get("id") or "").strip()),
        )
        if resolved is None:
            follow_up_item["resolution_detail"] = follow_up_item["required_action"]
        else:
            follow_up_item.update(resolved)
        follow_up.append(follow_up_item)

    verified_follow_up_count = sum(1 for item in follow_up if item["resolution"] == "verified")
    unresolved_follow_up_count = len(follow_up) - verified_follow_up_count
    follow_up_required = unresolved_follow_up_count > 0
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

    if unresolved_follow_up_count > 0:
        follow_up_summary = (
            f"Resolve {unresolved_follow_up_count} unresolved member wipe follow-up item"
            f"{'' if unresolved_follow_up_count == 1 else 's'} before closing the cleanup boundary."
        )
    elif verified_follow_up_count > 0:
        follow_up_summary = (
            f"All {verified_follow_up_count} member wipe follow-up item"
            f"{'' if verified_follow_up_count == 1 else 's'} are verified "
            "for the current cleanup boundary."
        )
    else:
        follow_up_summary = "No unresolved member wipe follow-up remains."

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
        "follow_up_required": follow_up_required,
        "follow_up_summary": follow_up_summary,
        "follow_up_count": len(follow_up),
        "unresolved_follow_up_count": unresolved_follow_up_count,
        "verified_follow_up_count": verified_follow_up_count,
        "follow_up": follow_up,
    }
