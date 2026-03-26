"""Helpers for summarizing live member wipe readiness."""

from __future__ import annotations

import datetime as dt

HISTORICAL_DRIFT_SECONDS = 60 * 60 * 6


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
        "classification": "verified_current",
        "verified_at": verified_at_iso,
        "required_action": None,
        "resolution_detail": (
            f"Verified after the member's last recorded activity at {verified_at_iso}."
            if verified_at_iso
            else "Verified after the member's last recorded activity."
        ),
    }


def _follow_up_classification(member: dict[str, object]) -> str:
    seconds_since_last_seen = int(member.get("seconds_since_last_seen") or 0)
    if seconds_since_last_seen >= HISTORICAL_DRIFT_SECONDS:
        return "historical_drift"
    return "active_unresolved"


def _historical_follow_up_review(
    member: dict[str, object],
    follow_up_review: dict[str, object] | None,
) -> dict[str, object] | None:
    if not follow_up_review:
        return None
    reviewed_at = _parse_timestamp(follow_up_review.get("reviewed_at"))
    if reviewed_at is None:
        return None
    reviewed_at_iso = _isoformat_utc(reviewed_at)
    required_action = _follow_up_action_for_reason(str(member["reason"]))
    return {
        "historical_reviewed": True,
        "historical_reviewed_at": reviewed_at_iso,
        "resolution_detail": (
            f"Historical drift review recorded at {reviewed_at_iso}. {required_action} "
            "This review does not close the cleanup boundary by itself."
            if reviewed_at_iso
            else (
                "Historical drift review recorded. "
                f"{required_action} This review does not close the cleanup boundary by itself."
            )
        ),
    }


def _retired_historical_follow_up(
    member: dict[str, object],
    follow_up_retirement: dict[str, object] | None,
) -> dict[str, object] | None:
    if not follow_up_retirement:
        return None
    if _follow_up_classification(member) != "historical_drift":
        return None
    retired_at = _parse_timestamp(follow_up_retirement.get("retired_at"))
    if retired_at is None:
        return None
    last_seen_at = _parse_timestamp(member.get("last_seen_at"))
    if last_seen_at is not None and retired_at < last_seen_at:
        return None
    retired_at_iso = _isoformat_utc(retired_at)
    return {
        "retired_at": retired_at_iso,
        "resolution_detail": (
            f"Historical drift retired from current readiness at {retired_at_iso}."
            if retired_at_iso
            else "Historical drift retired from current readiness."
        ),
    }


def summarize_wipe_readiness(
    members: list[dict[str, object]],
    *,
    follow_up_resolutions: dict[str, dict[str, object]] | None = None,
    follow_up_reviews: dict[str, dict[str, object]] | None = None,
    follow_up_retirements: dict[str, dict[str, object]] | None = None,
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
    review_index = follow_up_reviews or {}
    retirement_index = follow_up_retirements or {}
    follow_up = []
    retired_historical_drift_follow_up_count = 0
    for member in at_risk:
        retired = _retired_historical_follow_up(
            member,
            retirement_index.get(str(member.get("id") or "").strip()),
        )
        if retired is not None:
            retired_historical_drift_follow_up_count += 1
            continue
        follow_up_item = {
            **member,
            "resolution": "unresolved",
            "classification": _follow_up_classification(member),
            "required_action": _follow_up_action_for_reason(str(member["reason"])),
            "verified_at": None,
            "historical_reviewed": False,
            "historical_reviewed_at": None,
        }
        resolved = _resolved_follow_up(
            member,
            resolution_index.get(str(member.get("id") or "").strip()),
        )
        if resolved is None:
            follow_up_item["resolution_detail"] = follow_up_item["required_action"]
            if follow_up_item["classification"] == "historical_drift":
                follow_up_item["resolution_detail"] = (
                    f"{follow_up_item['required_action']} This item may be historical drift from "
                    "an older cleanup boundary and still needs explicit operator review."
                )
                review = _historical_follow_up_review(
                    member,
                    review_index.get(str(member.get("id") or "").strip()),
                )
                if review is not None:
                    follow_up_item.update(review)
        else:
            follow_up_item.update(resolved)
        follow_up.append(follow_up_item)

    verified_follow_up_count = sum(1 for item in follow_up if item["resolution"] == "verified")
    unresolved_follow_up_count = len(follow_up) - verified_follow_up_count
    verified_current_follow_up_count = sum(
        1 for item in follow_up if item["classification"] == "verified_current"
    )
    active_unresolved_follow_up_count = sum(
        1 for item in follow_up if item["classification"] == "active_unresolved"
    )
    historical_drift_follow_up_count = sum(
        1 for item in follow_up if item["classification"] == "historical_drift"
    )
    reviewed_historical_drift_follow_up_count = sum(
        1
        for item in follow_up
        if item["classification"] == "historical_drift" and item["historical_reviewed"]
    )
    unreviewed_historical_drift_follow_up_count = (
        historical_drift_follow_up_count - reviewed_historical_drift_follow_up_count
    )
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
        if historical_drift_follow_up_count > 0:
            follow_up_summary += (
                f" {historical_drift_follow_up_count} item"
                f"{'' if historical_drift_follow_up_count == 1 else 's'} may be historical drift."
            )
        if reviewed_historical_drift_follow_up_count > 0:
            follow_up_summary += (
                f" {reviewed_historical_drift_follow_up_count} historical-drift review"
                f"{'' if reviewed_historical_drift_follow_up_count == 1 else 's'} recorded."
            )
        if retired_historical_drift_follow_up_count > 0:
            follow_up_summary += (
                f" {retired_historical_drift_follow_up_count} historical-drift retirement"
                f"{'' if retired_historical_drift_follow_up_count == 1 else 's'} recorded."
            )
    elif verified_follow_up_count > 0:
        follow_up_summary = (
            f"All {verified_follow_up_count} member wipe follow-up item"
            f"{'' if verified_follow_up_count == 1 else 's'} are verified "
            "for the current cleanup boundary."
        )
        if retired_historical_drift_follow_up_count > 0:
            follow_up_summary += (
                f" {retired_historical_drift_follow_up_count} historical-drift item"
                f"{'' if retired_historical_drift_follow_up_count == 1 else 's'} retired "
                "from readiness."
            )
    elif retired_historical_drift_follow_up_count > 0:
        follow_up_summary = (
            "No unresolved member wipe follow-up remains."
            f" {retired_historical_drift_follow_up_count} historical-drift item"
            f"{'' if retired_historical_drift_follow_up_count == 1 else 's'} retired "
            "from readiness."
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
        "verified_current_follow_up_count": verified_current_follow_up_count,
        "active_unresolved_follow_up_count": active_unresolved_follow_up_count,
        "historical_drift_follow_up_count": historical_drift_follow_up_count,
        "reviewed_historical_drift_follow_up_count": reviewed_historical_drift_follow_up_count,
        "unreviewed_historical_drift_follow_up_count": unreviewed_historical_drift_follow_up_count,
        "retired_historical_drift_follow_up_count": retired_historical_drift_follow_up_count,
        "follow_up": follow_up,
    }
