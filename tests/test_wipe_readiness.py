from __future__ import annotations

from osk.wipe_readiness import summarize_wipe_readiness


def test_summarize_wipe_readiness_marks_follow_up_verified() -> None:
    members = [
        {
            "id": "sensor-1",
            "name": "Sensor One",
            "role": "sensor",
            "status": "disconnected",
            "heartbeat_state": "disconnected",
            "seconds_since_last_seen": 420,
            "last_seen_at": "2026-03-23T02:00:00Z",
        }
    ]

    payload = summarize_wipe_readiness(
        members,
        follow_up_resolutions={"sensor-1": {"verified_at": "2026-03-23T02:05:00Z"}},
    )

    assert payload["follow_up_required"] is False
    assert payload["verified_follow_up_count"] == 1
    assert payload["unresolved_follow_up_count"] == 0
    assert payload["follow_up"][0]["resolution"] == "verified"
    assert payload["follow_up"][0]["verified_at"] == "2026-03-23T02:05:00Z"
    assert payload["follow_up"][0]["classification"] == "verified_current"
    assert payload["verified_current_follow_up_count"] == 1
    assert payload["active_unresolved_follow_up_count"] == 0
    assert payload["historical_drift_follow_up_count"] == 0


def test_summarize_wipe_readiness_reopens_follow_up_after_new_activity() -> None:
    members = [
        {
            "id": "sensor-1",
            "name": "Sensor One",
            "role": "sensor",
            "status": "disconnected",
            "heartbeat_state": "disconnected",
            "seconds_since_last_seen": 420,
            "last_seen_at": "2026-03-23T02:10:00Z",
        }
    ]

    payload = summarize_wipe_readiness(
        members,
        follow_up_resolutions={"sensor-1": {"verified_at": "2026-03-23T02:05:00Z"}},
    )

    assert payload["follow_up_required"] is True
    assert payload["verified_follow_up_count"] == 0
    assert payload["unresolved_follow_up_count"] == 1
    assert payload["follow_up"][0]["resolution"] == "unresolved"
    assert payload["follow_up"][0]["verified_at"] is None
    assert payload["follow_up"][0]["classification"] == "active_unresolved"
    assert payload["verified_current_follow_up_count"] == 0
    assert payload["active_unresolved_follow_up_count"] == 1
    assert payload["historical_drift_follow_up_count"] == 0


def test_summarize_wipe_readiness_marks_old_unresolved_follow_up_as_historical_drift() -> None:
    members = [
        {
            "id": "observer-1",
            "name": "Observer One",
            "role": "observer",
            "status": "disconnected",
            "heartbeat_state": "disconnected",
            "seconds_since_last_seen": 60 * 60 * 8,
            "last_seen_at": "2026-03-23T00:00:00Z",
        }
    ]

    payload = summarize_wipe_readiness(members)

    assert payload["follow_up_required"] is True
    assert payload["follow_up"][0]["resolution"] == "unresolved"
    assert payload["follow_up"][0]["classification"] == "historical_drift"
    assert "historical drift" in payload["follow_up"][0]["resolution_detail"].lower()
    assert payload["active_unresolved_follow_up_count"] == 0
    assert payload["historical_drift_follow_up_count"] == 1
    assert payload["follow_up_summary"].startswith("Resolve 1 unresolved")


def test_summarize_wipe_readiness_marks_reviewed_historical_drift_without_resolving() -> None:
    members = [
        {
            "id": "observer-1",
            "name": "Observer One",
            "role": "observer",
            "status": "disconnected",
            "heartbeat_state": "disconnected",
            "seconds_since_last_seen": 60 * 60 * 8,
            "last_seen_at": "2026-03-23T00:00:00Z",
        }
    ]

    payload = summarize_wipe_readiness(
        members,
        follow_up_reviews={"observer-1": {"reviewed_at": "2026-03-23T08:15:00Z"}},
    )

    assert payload["follow_up_required"] is True
    assert payload["follow_up"][0]["resolution"] == "unresolved"
    assert payload["follow_up"][0]["classification"] == "historical_drift"
    assert payload["follow_up"][0]["historical_reviewed"] is True
    assert payload["follow_up"][0]["historical_reviewed_at"] == "2026-03-23T08:15:00Z"
    assert "review" in payload["follow_up"][0]["resolution_detail"].lower()
    assert payload["historical_drift_follow_up_count"] == 1
    assert payload["reviewed_historical_drift_follow_up_count"] == 1
    assert payload["unreviewed_historical_drift_follow_up_count"] == 0
