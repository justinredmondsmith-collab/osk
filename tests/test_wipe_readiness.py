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
