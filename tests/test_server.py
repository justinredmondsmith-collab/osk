"""Tests for FastAPI server."""

from __future__ import annotations

import datetime as dt
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from osk.config import OskConfig
from osk.intelligence_service import IngestSubmissionResult
from osk.models import MemberRole, MemberStatus, Operation
from osk.server import create_app


@pytest.fixture
def operation() -> Operation:
    return Operation(name="Test Op")


@pytest.fixture
def mock_op_manager(operation: Operation) -> MagicMock:
    member_id = uuid.uuid4()
    mgr = MagicMock()
    mgr.operation = operation
    mgr.validate_token = MagicMock(return_value=True)
    mgr.validate_coordinator_token = MagicMock(
        side_effect=lambda token: token == operation.coordinator_token
    )
    mgr.add_member = AsyncMock(
        return_value=MagicMock(
            id=member_id,
            name="Jay",
            role=MemberRole.OBSERVER,
            reconnect_token="resume-secret",
            model_dump=MagicMock(return_value={"id": str(member_id), "name": "Jay"}),
        )
    )
    mgr.promote_member = AsyncMock()
    mgr.demote_member = AsyncMock()
    mgr.kick_member = AsyncMock()
    mgr.resume_member = AsyncMock()
    mgr.mark_disconnected = AsyncMock()
    mgr.touch_member_heartbeat = AsyncMock()
    mgr.update_member_gps = AsyncMock()
    mgr.update_member_buffer_status = AsyncMock()
    mgr.rotate_token = AsyncMock(return_value="new-token")
    mgr.get_member_list = MagicMock(return_value=[])
    mgr.get_sensor_count = MagicMock(return_value=0)
    mgr.members = {}
    return mgr


@pytest.fixture
def mock_conn_mgr() -> MagicMock:
    mgr = MagicMock()
    mgr.broadcast = AsyncMock()
    mgr.broadcast_alert = AsyncMock()
    mgr.disconnect = AsyncMock()
    mgr.send_to = AsyncMock()
    mgr.register = MagicMock()
    mgr.unregister = MagicMock()
    mgr.update_role = MagicMock()
    mgr.connected_count = 0
    return mgr


@pytest.fixture
def mock_intelligence_service() -> MagicMock:
    service = MagicMock()
    service.snapshot.return_value = {
        "running": True,
        "transcriber": {"backend": "fake"},
        "vision": {"backend": "fake"},
    }
    service.config = SimpleNamespace(
        max_audio_payload_bytes=32,
        max_frame_payload_bytes=64,
    )
    service.submit_audio = AsyncMock(return_value=True)
    service.submit_frame = AsyncMock(return_value=True)
    service.submit_location = AsyncMock(return_value=True)
    return service


@pytest.fixture
def app(
    mock_op_manager: MagicMock,
    mock_conn_mgr: MagicMock,
    mock_db: MagicMock,
    mock_intelligence_service: MagicMock,
):
    app = create_app(
        op_manager=mock_op_manager,
        conn_manager=mock_conn_mgr,
        db=mock_db,
        intelligence_service=mock_intelligence_service,
    )
    app.state.mock_operation = mock_op_manager.operation
    return app


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(
        app,
        headers={"X-Osk-Coordinator-Token": app.state.mock_operation.coordinator_token},
    )


@pytest.fixture
def remote_client(app) -> TestClient:
    return TestClient(
        app,
        client=("10.8.0.15", 50000),
        headers={"X-Osk-Coordinator-Token": app.state.mock_operation.coordinator_token},
    )


@pytest.fixture
def unauthenticated_client(app) -> TestClient:
    return TestClient(app)


@pytest.fixture
def session_client(app) -> TestClient:
    return TestClient(
        app,
        headers={"X-Osk-Operator-Session": "operator-session-token"},
    )


def test_join_page_valid_token(client: TestClient, mock_op_manager: MagicMock) -> None:
    mock_op_manager.validate_token.return_value = True
    resp = client.get("/join?token=valid-token")
    assert resp.status_code == 200
    assert "Continue to member shell" in resp.text
    assert "/manifest.webmanifest" in resp.text
    assert "/static/pwa-runtime.js" in resp.text
    assert "sessionStorage.setItem('osk_token'" not in resp.text
    assert "content-security-policy" in resp.headers


def test_join_page_sets_member_cookie_and_redirects_clean_url(
    unauthenticated_client: TestClient,
    mock_op_manager: MagicMock,
) -> None:
    mock_op_manager.validate_token.return_value = True

    resp = unauthenticated_client.get("/join?token=valid-token", follow_redirects=False)

    assert resp.status_code == 303
    assert resp.headers["location"] == "/join"
    assert "osk_member_join=valid-token" in resp.headers["set-cookie"]


def test_join_page_invalid_token(client: TestClient, mock_op_manager: MagicMock) -> None:
    mock_op_manager.validate_token.return_value = False
    resp = client.get("/join?token=bad-token")
    assert resp.status_code == 403


def test_join_page_without_cookie_renders_rescan_message(
    unauthenticated_client: TestClient,
) -> None:
    resp = unauthenticated_client.get("/join")

    assert resp.status_code == 200
    assert "Scan the coordinator QR code" in resp.text


def test_member_page_without_cookie_renders_runtime_shell(
    unauthenticated_client: TestClient,
) -> None:
    resp = unauthenticated_client.get("/member")

    assert resp.status_code == 200
    assert "Osk Member" in resp.text
    assert "/static/member.js" in resp.text
    assert "/static/pwa-runtime.js" in resp.text
    assert "/static/audio-capture.js" in resp.text
    assert "/static/frame-sampler.js" in resp.text
    assert "/static/observer-media.js" in resp.text
    assert "/static/member-outbox.js" in resp.text
    assert "Share GPS" in resp.text
    assert "Send A Field Note" in resp.text
    assert "Snap Photo + Record Audio Clip" in resp.text
    assert "No queued items in this browser." in resp.text
    assert "Retry queued" in resp.text
    assert "bounded sensor media can queue locally until reconnect" in resp.text
    assert "Live Audio + Key Frames" in resp.text
    assert "Keep moving through reconnects" in resp.text
    assert "Install app" in resp.text
    assert '"gps_interval_moving_seconds": 10' in resp.text
    assert '"audio_chunk_ms": 4000' in resp.text
    assert '"observer_clip_duration_seconds": 10' in resp.text
    assert '"member_outbox_max_items": 12' in resp.text
    assert '"sensor_audio_buffer_limit": 3' in resp.text
    assert '"sensor_frame_buffer_limit": 4' in resp.text
    assert "osk_member_join" not in resp.text
    assert "content-security-policy" in resp.headers


def test_member_page_renders_runtime_shell(
    unauthenticated_client: TestClient,
) -> None:
    unauthenticated_client.cookies.set("osk_member_join", "valid-token")

    resp = unauthenticated_client.get("/member")

    assert resp.status_code == 200
    assert "Osk Member" in resp.text
    assert "/static/member.js" in resp.text
    assert "Live Alerts" in resp.text
    assert "Field Controls" in resp.text
    assert "Mute mic" in resp.text
    assert "Snap photo" in resp.text
    assert "Record clip" in resp.text
    assert "No queued items in this browser." in resp.text
    assert "bounded local buffering" in resp.text
    assert "osk_member_join" not in resp.text
    assert "content-security-policy" in resp.headers


def test_member_session_status_requires_cookie(
    unauthenticated_client: TestClient,
) -> None:
    resp = unauthenticated_client.get("/api/member/session")

    assert resp.status_code == 401
    assert "Rescan the coordinator QR code" in resp.json()["error"]


def test_member_session_status_accepts_cookie(
    unauthenticated_client: TestClient,
) -> None:
    unauthenticated_client.cookies.set("osk_member_join", "valid-token")

    resp = unauthenticated_client.get("/api/member/session")

    assert resp.status_code == 200
    assert resp.json()["authenticated"] is True
    assert resp.json()["join_authenticated"] is True
    assert resp.json()["runtime_authenticated"] is False
    assert resp.json()["operation_name"] == "Test Op"


@patch("osk.server._member_runtime_session_from_request")
def test_member_session_status_accepts_runtime_cookie(
    mock_member_runtime_session_from_request: MagicMock,
    unauthenticated_client: TestClient,
) -> None:
    member_id = uuid.uuid4()
    mock_member_runtime_session_from_request.return_value = {
        "member": SimpleNamespace(
            id=member_id,
            name="Jay",
            role=MemberRole.OBSERVER,
            status=MemberStatus.CONNECTED,
        ),
        "member_id": member_id,
        "reconnect_token": "resume-secret",
        "expires_at": "2026-03-21T19:30:00+00:00",
    }
    unauthenticated_client.cookies.set("osk_member_runtime", "runtime-cookie")

    resp = unauthenticated_client.get("/api/member/session")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["authenticated"] is True
    assert payload["join_authenticated"] is False
    assert payload["runtime_authenticated"] is True
    assert payload["member_id"] == str(member_id)
    assert payload["member_name"] == "Jay"
    assert payload["role"] == "observer"
    assert payload["status"] == "connected"
    assert payload["expires_at"] == "2026-03-21T19:30:00+00:00"


@patch("osk.server._issue_member_runtime_token")
@patch("osk.server._decode_member_runtime_token")
def test_member_runtime_session_exchange_sets_runtime_cookie(
    mock_decode_member_runtime_token: MagicMock,
    mock_issue_member_runtime_token: MagicMock,
    unauthenticated_client: TestClient,
    operation: Operation,
) -> None:
    member_id = uuid.uuid4()
    member = SimpleNamespace(
        id=member_id,
        name="Jay",
        role=MemberRole.OBSERVER,
        status=MemberStatus.CONNECTED,
    )
    mock_decode_member_runtime_token.return_value = {
        "member": member,
        "member_id": member_id,
        "reconnect_token": "resume-secret",
        "expires_at": "2026-03-21T18:05:00+00:00",
    }
    mock_issue_member_runtime_token.return_value = {
        "token": "runtime-cookie-token",
        "operation_id": str(operation.id),
        "member_id": str(member_id),
        "expires_at": "2026-03-21T22:00:00+00:00",
    }
    unauthenticated_client.cookies.set("osk_member_join", "valid-token")

    resp = unauthenticated_client.post(
        "/api/member/runtime-session",
        json={"member_session_code": "bootstrap-code"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["authenticated"] is True
    assert payload["join_authenticated"] is False
    assert payload["runtime_authenticated"] is True
    assert payload["member_id"] == str(member_id)
    assert payload["member_name"] == "Jay"
    assert payload["expires_at"] == "2026-03-21T22:00:00+00:00"
    set_cookie_headers = resp.headers.get_list("set-cookie")
    assert any("osk_member_runtime=runtime-cookie-token" in header for header in set_cookie_headers)
    assert any("osk_member_join=" in header for header in set_cookie_headers)
    args, kwargs = mock_decode_member_runtime_token.call_args
    assert args[1] == "bootstrap-code"
    assert kwargs["expected_purpose"] == "member_bootstrap"


def test_member_session_delete_clears_cookie(
    unauthenticated_client: TestClient,
) -> None:
    unauthenticated_client.cookies.set("osk_member_join", "valid-token")
    unauthenticated_client.cookies.set("osk_member_runtime", "runtime-cookie")

    resp = unauthenticated_client.delete("/api/member/session")

    assert resp.status_code == 200
    assert resp.json()["cleared"] is True
    set_cookie_headers = resp.headers.get_list("set-cookie")
    assert any("osk_member_join=" in header for header in set_cookie_headers)
    assert any("osk_member_runtime=" in header for header in set_cookie_headers)


def test_coordinator_dashboard_renders_local_shell(client: TestClient) -> None:
    resp = client.get("/coordinator")

    assert resp.status_code == 200
    assert "Osk Coordinator Review" in resp.text
    assert "Audit Trail" in resp.text
    assert "/static/dashboard.js" in resp.text
    assert "/api/audit" in resp.text
    assert "/api/coordinator/dashboard-state" in resp.text
    assert "/api/coordinator/dashboard-stream" in resp.text
    assert resp.headers["cache-control"] == "no-store"
    assert resp.headers["pragma"] == "no-cache"
    assert resp.headers["referrer-policy"] == "no-referrer"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert "content-security-policy" in resp.headers
    assert client.headers["X-Osk-Coordinator-Token"] not in resp.text


def test_coordinator_dashboard_allows_local_shell_without_credentials(
    unauthenticated_client: TestClient,
) -> None:
    resp = unauthenticated_client.get("/coordinator")

    assert resp.status_code == 200
    assert "Local review shell for findings, events, and SitReps." in resp.text


def test_coordinator_dashboard_rejects_remote_client(
    remote_client: TestClient,
) -> None:
    resp = remote_client.get("/coordinator")

    assert resp.status_code == 403
    assert resp.json()["error"] == "Local coordinator access only"


def test_dashboard_session_status_requires_code(
    unauthenticated_client: TestClient,
) -> None:
    resp = unauthenticated_client.get("/api/operator/dashboard-session")

    assert resp.status_code == 401
    assert "Run `osk dashboard`" in resp.json()["error"]


@patch("osk.server.read_dashboard_session")
@patch("osk.server.validate_dashboard_session", return_value=True)
def test_dashboard_session_status_accepts_cookie(
    mock_validate_dashboard_session: MagicMock,
    mock_read_dashboard_session: MagicMock,
    unauthenticated_client: TestClient,
    operation: Operation,
) -> None:
    mock_read_dashboard_session.return_value = {
        "operation_id": str(operation.id),
        "token": "dashboard-cookie-token",
        "expires_at": "2026-03-21T19:30:00+00:00",
    }
    unauthenticated_client.cookies.set("osk_dashboard_session", "dashboard-cookie-token")

    resp = unauthenticated_client.get("/api/operator/dashboard-session")

    assert resp.status_code == 200
    assert resp.json()["authenticated"] is True
    mock_validate_dashboard_session.assert_called_once_with(
        "dashboard-cookie-token",
        str(operation.id),
    )


@patch("osk.server.create_dashboard_session")
@patch("osk.server.consume_dashboard_bootstrap_code", return_value=True)
def test_dashboard_session_exchange_sets_cookie(
    mock_consume_dashboard_bootstrap_code: MagicMock,
    mock_create_dashboard_session: MagicMock,
    unauthenticated_client: TestClient,
    mock_db: MagicMock,
    operation: Operation,
) -> None:
    mock_create_dashboard_session.return_value = {
        "operation_id": str(operation.id),
        "token": "dashboard-cookie-token",
        "expires_at": "2026-03-21T19:30:00+00:00",
    }

    resp = unauthenticated_client.post(
        "/api/operator/dashboard-session",
        json={"dashboard_code": "one-time-code"},
    )

    assert resp.status_code == 200
    assert resp.json()["authenticated"] is True
    assert "osk_dashboard_session=dashboard-cookie-token" in resp.headers["set-cookie"]
    mock_consume_dashboard_bootstrap_code.assert_called_once_with(
        str(operation.id),
        "one-time-code",
    )
    mock_db.insert_audit_event.assert_awaited_once()


@patch("osk.server.load_config")
def test_coordinator_dashboard_state_returns_snapshot(
    mock_load_config: MagicMock,
    client: TestClient,
    mock_db: MagicMock,
    mock_op_manager: MagicMock,
    tmp_path,
) -> None:
    tile_root = tmp_path / "tiles"
    cached_tile = tile_root / "14" / "3271" / "6234.png"
    cached_tile.parent.mkdir(parents=True, exist_ok=True)
    cached_tile.write_bytes(b"png")
    mock_load_config.return_value = OskConfig(map_tile_cache_path=str(tile_root))
    member_id = uuid.uuid4()
    timestamp = dt.datetime.now(dt.timezone.utc)
    mock_op_manager.get_member_list.return_value = [
        {
            "id": str(member_id),
            "name": "Field Sensor",
            "role": "sensor",
            "connected_at": timestamp,
            "last_seen_at": timestamp,
            "status": "connected",
            "last_gps_at": timestamp,
            "latitude": 39.7392,
            "longitude": -104.9903,
            "buffer_status": {
                "pending_count": 3,
                "manual_pending_count": 1,
                "sensor_pending_count": 2,
                "report_pending_count": 1,
                "audio_pending_count": 1,
                "frame_pending_count": 1,
                "in_flight": False,
                "network": "offline",
                "last_error": "Retry pending.",
                "oldest_pending_at": timestamp.isoformat(),
                "updated_at": timestamp.isoformat(),
            },
        }
    ]
    mock_db.get_latest_sitrep.return_value = {"text": "Situation steady.", "trend": "stable"}
    mock_db.get_review_feed.return_value = [
        {
            "type": "finding",
            "id": str(uuid.uuid4()),
            "timestamp": "2026-03-21T19:45:00Z",
            "title": "Police Action",
            "summary": "Police advancing east.",
            "severity": "warning",
        }
    ]

    resp = client.get("/api/coordinator/dashboard-state?include=finding&limit=10")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["operation_status"]["name"] == "Test Op"
    assert payload["member_summary"]["fresh"] == 1
    assert payload["member_summary"]["buffered_members"] == 1
    assert payload["member_summary"]["buffered_items"] == 3
    assert payload["wipe_readiness"]["status"] == "ready"
    assert payload["wipe_readiness"]["ready"] is True
    assert payload["members"][0]["name"] == "Field Sensor"
    assert payload["members"][0]["buffer_status"]["pending_count"] == 3
    assert payload["members"][0]["buffer_status"]["network"] == "offline"
    assert payload["members"][0]["buffer_pressure"] == "buffered"
    assert payload["buffer_history"]["trend"] == "steady"
    assert payload["buffer_history"]["window_points"] == 1
    assert payload["buffer_history"]["points"][0]["buffered_items"] == 3
    assert payload["latest_sitrep"]["text"] == "Situation steady."
    assert payload["map"]["available"] is True
    assert payload["map"]["available_zooms"] == [14]
    assert payload["map"]["tile_template"] == "/tiles/{z}/{x}/{y}.png"
    _, kwargs = mock_db.get_review_feed.await_args
    assert kwargs["include_types"] == {"finding"}
    assert kwargs["limit"] == 10


def test_coordinator_dashboard_state_surfaces_wipe_readiness_risk(
    client: TestClient,
    mock_db: MagicMock,
    mock_op_manager: MagicMock,
    mock_intelligence_service: MagicMock,
) -> None:
    current = dt.datetime.now(dt.timezone.utc)
    stale_seen = current - dt.timedelta(seconds=180)
    disconnected_seen = current - dt.timedelta(seconds=420)
    sensor_id = uuid.uuid4()
    mock_db.get_latest_sitrep.return_value = None
    mock_db.get_review_feed.return_value = []
    mock_intelligence_service.snapshot.return_value = {"running": True}
    mock_db.get_audit_events.return_value = [
        {
            "action": "wipe_follow_up_verified",
            "actor_type": "coordinator",
            "timestamp": current - dt.timedelta(seconds=60),
            "details": {"member_id": str(sensor_id)},
        }
    ]
    mock_op_manager.get_member_list.return_value = [
        {
            "id": str(uuid.uuid4()),
            "name": "Observer One",
            "role": "observer",
            "connected_at": current,
            "last_seen_at": stale_seen,
            "status": "connected",
            "last_gps_at": None,
            "latitude": None,
            "longitude": None,
            "buffer_status": {},
        },
        {
            "id": str(sensor_id),
            "name": "Sensor Two",
            "role": "sensor",
            "connected_at": current,
            "last_seen_at": disconnected_seen,
            "status": "disconnected",
            "last_gps_at": None,
            "latitude": None,
            "longitude": None,
            "buffer_status": {},
        },
    ]

    with patch(
        "osk.server.load_config",
        return_value=OskConfig(member_heartbeat_timeout_seconds=60),
    ):
        resp = client.get("/api/coordinator/dashboard-state")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["wipe_readiness"]["status"] == "blocked"
    assert payload["wipe_readiness"]["ready"] is False
    assert payload["wipe_readiness"]["stale_members"] == 1
    assert payload["wipe_readiness"]["disconnected_members"] == 1
    assert payload["wipe_readiness"]["at_risk_members"] == 2
    assert payload["wipe_readiness"]["at_risk"][0]["name"] == "Sensor Two"
    assert payload["wipe_readiness"]["follow_up_required"] is True
    assert payload["wipe_readiness"]["follow_up_count"] == 2
    assert payload["wipe_readiness"]["unresolved_follow_up_count"] == 1
    assert payload["wipe_readiness"]["verified_follow_up_count"] == 1
    assert payload["wipe_readiness"]["verified_current_follow_up_count"] == 1
    assert payload["wipe_readiness"]["active_unresolved_follow_up_count"] == 1
    assert payload["wipe_readiness"]["historical_drift_follow_up_count"] == 0
    assert payload["wipe_readiness"]["follow_up_summary"].startswith("Resolve 1 unresolved")
    assert payload["wipe_readiness"]["follow_up"][0]["name"] == "Sensor Two"
    assert payload["wipe_readiness"]["follow_up"][0]["resolution"] == "verified"
    assert payload["wipe_readiness"]["follow_up"][0]["classification"] == "verified_current"
    assert payload["wipe_readiness"]["follow_up"][0]["verified_at"] is not None
    assert payload["wipe_readiness"]["follow_up_history_count"] == 1
    assert payload["wipe_readiness"]["follow_up_history_summary"].startswith(
        "Recent follow-up trail:"
    )
    assert payload["wipe_readiness"]["follow_up_history"][0]["member_name"] == "Sensor Two"
    assert payload["wipe_readiness"]["follow_up_history"][0]["status"] == "current"
    assert payload["wipe_readiness"]["follow_up_history"][0]["verified_at"] is not None


def test_coordinator_dashboard_state_marks_reopened_follow_up_history(
    client: TestClient,
    mock_db: MagicMock,
    mock_op_manager: MagicMock,
    mock_intelligence_service: MagicMock,
) -> None:
    current = dt.datetime.now(dt.timezone.utc)
    stale_seen = current - dt.timedelta(seconds=180)
    member_id = uuid.uuid4()
    mock_db.get_latest_sitrep.return_value = None
    mock_db.get_review_feed.return_value = []
    mock_intelligence_service.snapshot.return_value = {"running": True}
    mock_db.get_audit_events.return_value = [
        {
            "action": "wipe_follow_up_verified",
            "actor_type": "coordinator",
            "timestamp": current - dt.timedelta(seconds=420),
            "details": {
                "member_id": str(member_id),
                "member_name": "Observer One",
                "reason": "stale",
                "last_seen_at": (current - dt.timedelta(seconds=540)).isoformat(),
            },
        }
    ]
    mock_op_manager.get_member_list.return_value = [
        {
            "id": str(member_id),
            "name": "Observer One",
            "role": "observer",
            "connected_at": current,
            "last_seen_at": stale_seen,
            "status": "connected",
            "last_gps_at": None,
            "latitude": None,
            "longitude": None,
            "buffer_status": {},
        },
    ]

    with patch(
        "osk.server.load_config",
        return_value=OskConfig(member_heartbeat_timeout_seconds=60),
    ):
        resp = client.get("/api/coordinator/dashboard-state")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["wipe_readiness"]["follow_up_required"] is True
    assert payload["wipe_readiness"]["follow_up"][0]["resolution"] == "unresolved"
    assert payload["wipe_readiness"]["follow_up"][0]["classification"] == "active_unresolved"
    assert payload["wipe_readiness"]["follow_up_history_count"] == 1
    assert payload["wipe_readiness"]["follow_up_history"][0]["member_name"] == "Observer One"
    assert payload["wipe_readiness"]["follow_up_history"][0]["status"] == "reopened"
    assert "Reopened" in payload["wipe_readiness"]["follow_up_history"][0]["status_detail"]


def test_coordinator_dashboard_state_uses_reopen_audit_details_in_follow_up_history(
    client: TestClient,
    mock_db: MagicMock,
    mock_op_manager: MagicMock,
    mock_intelligence_service: MagicMock,
) -> None:
    current = dt.datetime(2026, 3, 23, 3, 12, tzinfo=dt.timezone.utc)
    stale_seen = dt.datetime(2026, 3, 23, 3, 8, tzinfo=dt.timezone.utc)
    verified_at = dt.datetime(2026, 3, 23, 3, 0, tzinfo=dt.timezone.utc)
    member_id = uuid.uuid4()
    mock_db.get_latest_sitrep.return_value = None
    mock_db.get_review_feed.return_value = []
    mock_intelligence_service.snapshot.return_value = {"running": True}
    mock_db.get_audit_events.return_value = [
        {
            "action": "wipe_follow_up_reopened",
            "actor_type": "member",
            "timestamp": stale_seen,
            "details": {
                "member_id": str(member_id),
                "member_name": "Observer One",
                "activity_kind": "resume",
                "last_seen_at": stale_seen.isoformat().replace("+00:00", "Z"),
            },
        },
        {
            "action": "wipe_follow_up_verified",
            "actor_type": "coordinator",
            "timestamp": verified_at,
            "details": {
                "member_id": str(member_id),
                "member_name": "Observer One",
                "reason": "stale",
                "last_seen_at": "2026-03-23T02:54:00Z",
            },
        },
    ]
    mock_op_manager.get_member_list.return_value = [
        {
            "id": str(member_id),
            "name": "Observer One",
            "role": "observer",
            "connected_at": current,
            "last_seen_at": stale_seen,
            "status": "connected",
            "last_gps_at": None,
            "latitude": None,
            "longitude": None,
            "buffer_status": {},
        },
    ]

    with patch(
        "osk.server.load_config",
        return_value=OskConfig(member_heartbeat_timeout_seconds=60),
    ):
        resp = client.get("/api/coordinator/dashboard-state")

    assert resp.status_code == 200
    payload = resp.json()
    item = payload["wipe_readiness"]["follow_up_history"][0]
    assert item["status"] == "reopened"
    assert item["reopened_at"] == "2026-03-23T03:08:00Z"
    assert item["reopened_activity_kind"] == "resume"
    assert "resume" in item["status_detail"]
    assert "2026-03-23T03:08:00Z" in item["status_detail"]


def test_coordinator_dashboard_state_preserves_reopen_details_after_clear(
    client: TestClient,
    mock_db: MagicMock,
    mock_op_manager: MagicMock,
    mock_intelligence_service: MagicMock,
) -> None:
    reopened_at = dt.datetime(2026, 3, 23, 3, 5, tzinfo=dt.timezone.utc)
    verified_at = dt.datetime(2026, 3, 23, 3, 0, tzinfo=dt.timezone.utc)
    member_id = uuid.uuid4()
    mock_db.get_latest_sitrep.return_value = None
    mock_db.get_review_feed.return_value = []
    mock_intelligence_service.snapshot.return_value = {"running": True}
    mock_db.get_audit_events.return_value = [
        {
            "action": "wipe_follow_up_reopened",
            "actor_type": "member",
            "timestamp": reopened_at,
            "details": {
                "member_id": str(member_id),
                "member_name": "Observer One",
                "activity_kind": "message",
                "last_seen_at": reopened_at.isoformat().replace("+00:00", "Z"),
            },
        },
        {
            "action": "wipe_follow_up_verified",
            "actor_type": "coordinator",
            "timestamp": verified_at,
            "details": {
                "member_id": str(member_id),
                "member_name": "Observer One",
                "reason": "disconnected",
                "last_seen_at": "2026-03-23T02:51:00Z",
            },
        },
    ]
    mock_op_manager.get_member_list.return_value = []

    with patch(
        "osk.server.load_config",
        return_value=OskConfig(member_heartbeat_timeout_seconds=60),
    ):
        resp = client.get("/api/coordinator/dashboard-state")

    assert resp.status_code == 200
    payload = resp.json()
    item = payload["wipe_readiness"]["follow_up_history"][0]
    assert item["status"] == "cleared"
    assert item["reopened_at"] == "2026-03-23T03:05:00Z"
    assert item["reopened_activity_kind"] == "message"
    assert "message" in item["status_detail"]
    assert "2026-03-23T03:05:00Z" in item["status_detail"]


def test_verify_wipe_follow_up_records_audit_and_returns_closed_item(
    client: TestClient,
    mock_db: MagicMock,
    mock_op_manager: MagicMock,
) -> None:
    current = dt.datetime.now(dt.timezone.utc)
    disconnected_seen = current - dt.timedelta(seconds=420)
    member_id = uuid.uuid4()
    mock_op_manager.get_member_list.return_value = [
        {
            "id": str(member_id),
            "name": "Sensor Two",
            "role": "sensor",
            "connected_at": current,
            "last_seen_at": disconnected_seen,
            "status": "disconnected",
            "last_gps_at": None,
            "latitude": None,
            "longitude": None,
            "buffer_status": {},
        },
    ]
    mock_db.get_audit_events.return_value = []

    with patch(
        "osk.server.load_config",
        return_value=OskConfig(member_heartbeat_timeout_seconds=60),
    ):
        resp = client.post(f"/api/coordinator/wipe-follow-up/{member_id}/verify")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "verified"
    assert payload["member_id"] == str(member_id)
    assert payload["follow_up"]["resolution"] == "verified"
    assert payload["follow_up"]["verified_at"] is not None
    assert payload["wipe_readiness"]["follow_up_required"] is False
    assert payload["wipe_readiness"]["verified_follow_up_count"] == 1
    assert payload["wipe_readiness"]["follow_up_history_count"] == 1
    assert payload["wipe_readiness"]["follow_up_history"][0]["member_id"] == str(member_id)
    assert payload["wipe_readiness"]["follow_up_history"][0]["status"] == "current"
    mock_db.insert_audit_event.assert_awaited_once()
    assert mock_db.insert_audit_event.await_args.args[2] == "wipe_follow_up_verified"
    audit_details = mock_db.insert_audit_event.await_args.kwargs["details"]
    assert audit_details["member_id"] == str(member_id)
    assert audit_details["reason"] == "disconnected"
    assert audit_details["last_seen_at"] is not None


def test_review_historical_drift_follow_up_records_audit_and_returns_reviewed_item(
    client: TestClient,
    mock_db: MagicMock,
    mock_op_manager: MagicMock,
) -> None:
    current = dt.datetime.now(dt.timezone.utc)
    disconnected_seen = current - dt.timedelta(hours=8)
    member_id = uuid.uuid4()
    mock_op_manager.get_member_list.return_value = [
        {
            "id": str(member_id),
            "name": "Observer Two",
            "role": "observer",
            "connected_at": current,
            "last_seen_at": disconnected_seen,
            "status": "disconnected",
            "last_gps_at": None,
            "latitude": None,
            "longitude": None,
            "buffer_status": {},
        },
    ]
    mock_db.get_audit_events.return_value = []

    with patch(
        "osk.server.load_config",
        return_value=OskConfig(member_heartbeat_timeout_seconds=60),
    ):
        resp = client.post(f"/api/coordinator/wipe-follow-up/{member_id}/review")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "reviewed"
    assert payload["member_id"] == str(member_id)
    assert payload["follow_up"]["resolution"] == "unresolved"
    assert payload["follow_up"]["classification"] == "historical_drift"
    assert payload["follow_up"]["historical_reviewed"] is True
    assert payload["follow_up"]["historical_reviewed_at"] is not None
    assert payload["wipe_readiness"]["follow_up_required"] is True
    assert payload["wipe_readiness"]["reviewed_historical_drift_follow_up_count"] == 1
    assert payload["wipe_readiness"]["unreviewed_historical_drift_follow_up_count"] == 0
    mock_db.insert_audit_event.assert_awaited_once()
    assert mock_db.insert_audit_event.await_args.args[2] == "wipe_follow_up_historical_reviewed"
    audit_details = mock_db.insert_audit_event.await_args.kwargs["details"]
    assert audit_details["member_id"] == str(member_id)
    assert audit_details["classification"] == "historical_drift"


def test_retire_historical_drift_follow_up_records_audit_and_clears_item(
    client: TestClient,
    mock_db: MagicMock,
    mock_op_manager: MagicMock,
) -> None:
    current = dt.datetime.now(dt.timezone.utc)
    disconnected_seen = current - dt.timedelta(hours=8)
    member_id = uuid.uuid4()
    mock_op_manager.get_member_list.return_value = [
        {
            "id": str(member_id),
            "name": "Observer Retired",
            "role": "observer",
            "connected_at": current,
            "last_seen_at": disconnected_seen,
            "status": "disconnected",
            "last_gps_at": None,
            "latitude": None,
            "longitude": None,
            "buffer_status": {},
        },
    ]
    mock_db.get_audit_events.return_value = []

    with patch(
        "osk.server.load_config",
        return_value=OskConfig(member_heartbeat_timeout_seconds=60),
    ):
        resp = client.post(f"/api/coordinator/wipe-follow-up/{member_id}/retire")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "retired"
    assert payload["member_id"] == str(member_id)
    assert payload["follow_up"] is None
    assert payload["wipe_readiness"]["follow_up_required"] is False
    assert payload["wipe_readiness"]["historical_drift_follow_up_count"] == 0
    assert payload["wipe_readiness"]["retired_historical_drift_follow_up_count"] == 1
    assert payload["wipe_readiness"]["follow_up_history_count"] == 1
    assert payload["wipe_readiness"]["follow_up_history"][0]["status"] == "retired"
    mock_db.insert_audit_event.assert_awaited_once()
    assert mock_db.insert_audit_event.await_args.args[2] == "wipe_follow_up_historical_retired"
    audit_details = mock_db.insert_audit_event.await_args.kwargs["details"]
    assert audit_details["member_id"] == str(member_id)
    assert audit_details["classification"] == "historical_drift"


def test_coordinator_dashboard_state_includes_reviewed_historical_drift_history(
    client: TestClient,
    mock_db: MagicMock,
    mock_op_manager: MagicMock,
    mock_intelligence_service: MagicMock,
) -> None:
    current = dt.datetime(2026, 3, 23, 8, 12, tzinfo=dt.timezone.utc)
    historical_seen = dt.datetime(2026, 3, 23, 0, 8, tzinfo=dt.timezone.utc)
    reviewed_at = dt.datetime(2026, 3, 23, 8, 0, tzinfo=dt.timezone.utc)
    member_id = uuid.uuid4()
    mock_db.get_latest_sitrep.return_value = None
    mock_db.get_review_feed.return_value = []
    mock_intelligence_service.snapshot.return_value = {"running": True}
    mock_db.get_audit_events.return_value = [
        {
            "action": "wipe_follow_up_historical_reviewed",
            "actor_type": "coordinator",
            "timestamp": reviewed_at,
            "details": {
                "member_id": str(member_id),
                "member_name": "Observer Two",
                "reason": "disconnected",
                "classification": "historical_drift",
                "last_seen_at": historical_seen.isoformat().replace("+00:00", "Z"),
            },
        }
    ]
    mock_op_manager.get_member_list.return_value = [
        {
            "id": str(member_id),
            "name": "Observer Two",
            "role": "observer",
            "connected_at": current,
            "last_seen_at": historical_seen,
            "status": "disconnected",
            "last_gps_at": None,
            "latitude": None,
            "longitude": None,
            "buffer_status": {},
        }
    ]

    with patch(
        "osk.server.load_config",
        return_value=OskConfig(member_heartbeat_timeout_seconds=60),
    ):
        resp = client.get("/api/coordinator/dashboard-state")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["wipe_readiness"]["follow_up_history_count"] == 1
    assert payload["wipe_readiness"]["follow_up_history_summary"].startswith(
        "Recent follow-up trail:"
    )
    item = payload["wipe_readiness"]["follow_up_history"][0]
    assert item["member_id"] == str(member_id)
    assert item["action"] == "wipe_follow_up_historical_reviewed"
    assert item["status"] == "reviewed"
    assert item["reviewed_at"] == "2026-03-23T08:00:00Z"
    assert "did not close" in item["status_detail"]


def test_review_historical_drift_follow_up_rejects_active_item(
    client: TestClient,
    mock_db: MagicMock,
    mock_op_manager: MagicMock,
) -> None:
    current = dt.datetime.now(dt.timezone.utc)
    disconnected_seen = current - dt.timedelta(minutes=7)
    member_id = uuid.uuid4()
    mock_op_manager.get_member_list.return_value = [
        {
            "id": str(member_id),
            "name": "Sensor Two",
            "role": "sensor",
            "connected_at": current,
            "last_seen_at": disconnected_seen,
            "status": "disconnected",
            "last_gps_at": None,
            "latitude": None,
            "longitude": None,
            "buffer_status": {},
        },
    ]
    mock_db.get_audit_events.return_value = []

    with patch(
        "osk.server.load_config",
        return_value=OskConfig(member_heartbeat_timeout_seconds=60),
    ):
        resp = client.post(f"/api/coordinator/wipe-follow-up/{member_id}/review")

    assert resp.status_code == 409
    assert (
        resp.json()["error"]
        == "Historical drift review is only available for historical drift items"
    )
    mock_db.insert_audit_event.assert_not_awaited()


def test_retire_historical_drift_follow_up_rejects_active_item(
    client: TestClient,
    mock_db: MagicMock,
    mock_op_manager: MagicMock,
) -> None:
    current = dt.datetime.now(dt.timezone.utc)
    disconnected_seen = current - dt.timedelta(minutes=7)
    member_id = uuid.uuid4()
    mock_op_manager.get_member_list.return_value = [
        {
            "id": str(member_id),
            "name": "Sensor Two",
            "role": "sensor",
            "connected_at": current,
            "last_seen_at": disconnected_seen,
            "status": "disconnected",
            "last_gps_at": None,
            "latitude": None,
            "longitude": None,
            "buffer_status": {},
        },
    ]
    mock_db.get_audit_events.return_value = []

    with patch(
        "osk.server.load_config",
        return_value=OskConfig(member_heartbeat_timeout_seconds=60),
    ):
        resp = client.post(f"/api/coordinator/wipe-follow-up/{member_id}/retire")

    assert resp.status_code == 409
    assert (
        resp.json()["error"]
        == "Historical drift retirement is only available for historical drift items"
    )
    mock_db.insert_audit_event.assert_not_awaited()


def test_get_wipe_follow_up_detail_returns_current_item_and_history(
    client: TestClient,
    mock_db: MagicMock,
    mock_op_manager: MagicMock,
) -> None:
    current = dt.datetime(2026, 3, 23, 3, 12, tzinfo=dt.timezone.utc)
    stale_seen = dt.datetime(2026, 3, 23, 3, 8, tzinfo=dt.timezone.utc)
    verified_at = dt.datetime(2026, 3, 23, 3, 0, tzinfo=dt.timezone.utc)
    member_id = uuid.uuid4()
    mock_op_manager.get_member_list.return_value = [
        {
            "id": str(member_id),
            "name": "Observer One",
            "role": "observer",
            "connected_at": current,
            "last_seen_at": stale_seen,
            "status": "connected",
            "last_gps_at": None,
            "latitude": None,
            "longitude": None,
            "buffer_status": {},
        },
    ]
    mock_db.get_audit_events.return_value = [
        {
            "action": "wipe_follow_up_reopened",
            "actor_type": "member",
            "timestamp": stale_seen,
            "details": {
                "member_id": str(member_id),
                "member_name": "Observer One",
                "activity_kind": "resume",
                "last_seen_at": stale_seen.isoformat().replace("+00:00", "Z"),
            },
        },
        {
            "action": "wipe_follow_up_verified",
            "actor_type": "coordinator",
            "timestamp": verified_at,
            "details": {
                "member_id": str(member_id),
                "member_name": "Observer One",
                "reason": "stale",
                "last_seen_at": "2026-03-23T02:54:00Z",
            },
        },
    ]

    with patch(
        "osk.server.load_config",
        return_value=OskConfig(member_heartbeat_timeout_seconds=60),
    ):
        resp = client.get(f"/api/coordinator/wipe-follow-up/{member_id}")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["member_id"] == str(member_id)
    assert payload["member_name"] == "Observer One"
    assert payload["reason"] == "stale"
    assert payload["follow_up"] is not None
    assert payload["follow_up"]["id"] == str(member_id)
    assert payload["follow_up"]["resolution"] == "unresolved"
    assert payload["history_count"] == 1
    assert payload["history"][0]["member_id"] == str(member_id)
    assert payload["history"][0]["status"] == "reopened"
    assert payload["history"][0]["reopened_activity_kind"] == "resume"


def test_get_wipe_follow_up_detail_includes_historical_review_marker(
    client: TestClient,
    mock_db: MagicMock,
    mock_op_manager: MagicMock,
) -> None:
    current = dt.datetime(2026, 3, 23, 8, 12, tzinfo=dt.timezone.utc)
    historical_seen = dt.datetime(2026, 3, 23, 0, 8, tzinfo=dt.timezone.utc)
    reviewed_at = dt.datetime(2026, 3, 23, 8, 0, tzinfo=dt.timezone.utc)
    member_id = uuid.uuid4()
    mock_op_manager.get_member_list.return_value = [
        {
            "id": str(member_id),
            "name": "Observer One",
            "role": "observer",
            "connected_at": current,
            "last_seen_at": historical_seen,
            "status": "disconnected",
            "last_gps_at": None,
            "latitude": None,
            "longitude": None,
            "buffer_status": {},
        },
    ]
    mock_db.get_audit_events.return_value = [
        {
            "action": "wipe_follow_up_historical_reviewed",
            "actor_type": "coordinator",
            "timestamp": reviewed_at,
            "details": {
                "member_id": str(member_id),
                "member_name": "Observer One",
                "reason": "disconnected",
                "classification": "historical_drift",
                "last_seen_at": historical_seen.isoformat().replace("+00:00", "Z"),
            },
        }
    ]

    with patch(
        "osk.server.load_config",
        return_value=OskConfig(member_heartbeat_timeout_seconds=60),
    ):
        resp = client.get(f"/api/coordinator/wipe-follow-up/{member_id}")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["follow_up"] is not None
    assert payload["follow_up"]["classification"] == "historical_drift"
    assert payload["follow_up"]["historical_reviewed"] is True
    assert payload["follow_up"]["historical_reviewed_at"] == "2026-03-23T08:00:00Z"
    assert payload["history_count"] == 1
    assert payload["history"][0]["action"] == "wipe_follow_up_historical_reviewed"
    assert payload["history"][0]["status"] == "reviewed"
    assert payload["history"][0]["reviewed_at"] == "2026-03-23T08:00:00Z"
    assert "review" in payload["summary"].lower()


def test_get_wipe_follow_up_detail_includes_historical_retirement_marker(
    client: TestClient,
    mock_db: MagicMock,
    mock_op_manager: MagicMock,
) -> None:
    current = dt.datetime(2026, 3, 23, 8, 12, tzinfo=dt.timezone.utc)
    historical_seen = dt.datetime(2026, 3, 23, 0, 8, tzinfo=dt.timezone.utc)
    retired_at = dt.datetime(2026, 3, 23, 8, 5, tzinfo=dt.timezone.utc)
    member_id = uuid.uuid4()
    mock_op_manager.get_member_list.return_value = [
        {
            "id": str(member_id),
            "name": "Observer Retired",
            "role": "observer",
            "connected_at": current,
            "last_seen_at": historical_seen,
            "status": "disconnected",
            "last_gps_at": None,
            "latitude": None,
            "longitude": None,
            "buffer_status": {},
        },
    ]
    mock_db.get_audit_events.return_value = [
        {
            "action": "wipe_follow_up_historical_retired",
            "actor_type": "coordinator",
            "timestamp": retired_at,
            "details": {
                "member_id": str(member_id),
                "member_name": "Observer Retired",
                "reason": "disconnected",
                "classification": "historical_drift",
                "last_seen_at": historical_seen.isoformat().replace("+00:00", "Z"),
            },
        }
    ]

    with patch(
        "osk.server.load_config",
        return_value=OskConfig(member_heartbeat_timeout_seconds=60),
    ):
        resp = client.get(f"/api/coordinator/wipe-follow-up/{member_id}")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["follow_up"] is None
    assert payload["history_count"] == 1
    assert payload["history"][0]["action"] == "wipe_follow_up_historical_retired"
    assert payload["history"][0]["status"] == "retired"
    assert payload["history"][0]["retired_at"] == "2026-03-23T08:05:00Z"
    assert "retirement" in payload["summary"].lower()


def test_get_wipe_follow_up_detail_returns_cleared_member_history(
    client: TestClient,
    mock_db: MagicMock,
    mock_op_manager: MagicMock,
) -> None:
    reopened_at = dt.datetime(2026, 3, 23, 3, 5, tzinfo=dt.timezone.utc)
    verified_at = dt.datetime(2026, 3, 23, 3, 0, tzinfo=dt.timezone.utc)
    member_id = uuid.uuid4()
    mock_op_manager.get_member_list.return_value = []
    mock_db.get_audit_events.return_value = [
        {
            "action": "wipe_follow_up_reopened",
            "actor_type": "member",
            "timestamp": reopened_at,
            "details": {
                "member_id": str(member_id),
                "member_name": "Observer One",
                "activity_kind": "message",
                "last_seen_at": reopened_at.isoformat().replace("+00:00", "Z"),
            },
        },
        {
            "action": "wipe_follow_up_verified",
            "actor_type": "coordinator",
            "timestamp": verified_at,
            "details": {
                "member_id": str(member_id),
                "member_name": "Observer One",
                "reason": "disconnected",
                "last_seen_at": "2026-03-23T02:51:00Z",
            },
        },
    ]

    with patch(
        "osk.server.load_config",
        return_value=OskConfig(member_heartbeat_timeout_seconds=60),
    ):
        resp = client.get(f"/api/coordinator/wipe-follow-up/{member_id}")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["member_id"] == str(member_id)
    assert payload["member_name"] == "Observer One"
    assert payload["reason"] == "disconnected"
    assert payload["follow_up"] is None
    assert payload["history_count"] == 1
    assert payload["history"][0]["status"] == "cleared"
    assert payload["history"][0]["reopened_activity_kind"] == "message"
    assert payload["history"][0]["reopened_at"] == "2026-03-23T03:05:00Z"


def test_get_wipe_follow_up_detail_rejects_unknown_member(
    client: TestClient,
    mock_db: MagicMock,
    mock_op_manager: MagicMock,
) -> None:
    member_id = uuid.uuid4()
    mock_op_manager.get_member_list.return_value = []
    mock_db.get_audit_events.return_value = []

    with patch(
        "osk.server.load_config",
        return_value=OskConfig(member_heartbeat_timeout_seconds=60),
    ):
        resp = client.get(f"/api/coordinator/wipe-follow-up/{member_id}")

    assert resp.status_code == 404
    assert resp.json() == {"error": "Wipe follow-up item not found"}


def test_coordinator_dashboard_state_tracks_buffer_history_window(
    client: TestClient,
    mock_db: MagicMock,
    mock_op_manager: MagicMock,
    mock_intelligence_service: MagicMock,
) -> None:
    member_id = uuid.uuid4()
    timestamp = dt.datetime.now(dt.timezone.utc)
    mock_db.get_latest_sitrep.return_value = None
    mock_db.get_review_feed.return_value = []
    mock_intelligence_service.snapshot.return_value = {
        "running": True,
        "audio_ingest": {"queue_size": 1},
        "frame_ingest": {"queue_size": 0},
    }
    mock_op_manager.get_member_list.return_value = [
        {
            "id": str(member_id),
            "name": "Observer One",
            "role": "observer",
            "connected_at": timestamp,
            "last_seen_at": timestamp,
            "status": "connected",
            "last_gps_at": None,
            "latitude": None,
            "longitude": None,
            "buffer_status": {
                "pending_count": 1,
                "manual_pending_count": 1,
                "sensor_pending_count": 0,
                "report_pending_count": 1,
                "audio_pending_count": 0,
                "frame_pending_count": 0,
                "in_flight": False,
                "network": "offline",
                "last_error": None,
                "oldest_pending_at": timestamp.isoformat(),
                "updated_at": timestamp.isoformat(),
            },
        }
    ]

    first = client.get("/api/coordinator/dashboard-state")
    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["buffer_history"]["window_points"] == 1
    assert first_payload["buffer_history"]["points"][0]["audio_queue_size"] == 1

    mock_intelligence_service.snapshot.return_value = {
        "running": True,
        "audio_ingest": {"queue_size": 2},
        "frame_ingest": {"queue_size": 1},
    }
    mock_op_manager.get_member_list.return_value = [
        {
            "id": str(member_id),
            "name": "Observer One",
            "role": "observer",
            "connected_at": timestamp,
            "last_seen_at": timestamp,
            "status": "connected",
            "last_gps_at": None,
            "latitude": None,
            "longitude": None,
            "buffer_status": {
                "pending_count": 4,
                "manual_pending_count": 3,
                "sensor_pending_count": 1,
                "report_pending_count": 2,
                "audio_pending_count": 1,
                "frame_pending_count": 0,
                "in_flight": True,
                "network": "offline",
                "last_error": "Upload retry pending.",
                "oldest_pending_at": timestamp.isoformat(),
                "updated_at": timestamp.isoformat(),
            },
        }
    ]

    second = client.get("/api/coordinator/dashboard-state")
    assert second.status_code == 200
    second_payload = second.json()
    assert second_payload["buffer_history"]["window_points"] == 2
    assert second_payload["buffer_history"]["trend"] == "rising"
    assert second_payload["buffer_history"]["current_buffered_items"] == 4
    assert second_payload["buffer_history"]["peak_buffered_items"] == 4
    assert second_payload["buffer_history"]["change_items"] == 3
    assert [point["buffered_items"] for point in second_payload["buffer_history"]["points"]] == [
        1,
        4,
    ]
    assert second_payload["buffer_history"]["points"][-1]["audio_queue_size"] == 2
    assert second_payload["buffer_history"]["points"][-1]["frame_queue_size"] == 1


def test_coordinator_dashboard_state_emits_sustained_buffer_signal(
    client: TestClient,
    mock_db: MagicMock,
    mock_op_manager: MagicMock,
    mock_intelligence_service: MagicMock,
) -> None:
    member_id = uuid.uuid4()
    timestamp = dt.datetime.now(dt.timezone.utc)
    mock_db.get_latest_sitrep.return_value = None
    mock_db.get_review_feed.return_value = []
    mock_intelligence_service.snapshot.return_value = {
        "running": True,
        "audio_ingest": {"queue_size": 2},
        "frame_ingest": {"queue_size": 1},
    }

    member_row = {
        "id": str(member_id),
        "name": "Sensor One",
        "role": "sensor",
        "connected_at": timestamp,
        "last_seen_at": timestamp,
        "status": "connected",
        "last_gps_at": timestamp,
        "latitude": 39.7392,
        "longitude": -104.9903,
        "buffer_status": {
            "pending_count": 4,
            "manual_pending_count": 1,
            "sensor_pending_count": 3,
            "report_pending_count": 1,
            "audio_pending_count": 2,
            "frame_pending_count": 1,
            "in_flight": True,
            "network": "offline",
            "last_error": "Upload retry pending.",
            "oldest_pending_at": timestamp.isoformat(),
            "updated_at": timestamp.isoformat(),
        },
    }
    mock_op_manager.get_member_list.return_value = [member_row]

    first = client.get("/api/coordinator/dashboard-state")
    second = client.get("/api/coordinator/dashboard-state")
    third = client.get("/api/coordinator/dashboard-state")

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 200
    third_payload = third.json()
    assert third_payload["buffer_signal"] is not None
    assert third_payload["buffer_signal"]["signal_kind"] == "member_buffer_sustained"
    assert third_payload["buffer_signal"]["severity"] == "warning"
    assert third_payload["buffer_signal"]["category"] == "member_buffer"
    assert third_payload["review_feed"][0]["type"] == "signal"
    assert third_payload["review_feed"][0]["signal_kind"] == "member_buffer_sustained"

    fourth = client.get("/api/coordinator/dashboard-state")
    assert fourth.status_code == 200
    fourth_payload = fourth.json()
    assert (
        fourth_payload["buffer_signal"]["signal_id"] == third_payload["buffer_signal"]["signal_id"]
    )
    assert (
        fourth_payload["buffer_signal"]["timestamp"] == third_payload["buffer_signal"]["timestamp"]
    )


def test_acknowledge_dashboard_signal(
    client: TestClient,
    mock_db: MagicMock,
    mock_op_manager: MagicMock,
    mock_intelligence_service: MagicMock,
) -> None:
    member_id = uuid.uuid4()
    timestamp = dt.datetime.now(dt.timezone.utc)
    mock_db.get_latest_sitrep.return_value = None
    mock_db.get_review_feed.return_value = []
    mock_intelligence_service.snapshot.return_value = {
        "running": True,
        "audio_ingest": {"queue_size": 2},
        "frame_ingest": {"queue_size": 1},
    }
    mock_op_manager.get_member_list.return_value = [
        {
            "id": str(member_id),
            "name": "Sensor One",
            "role": "sensor",
            "connected_at": timestamp,
            "last_seen_at": timestamp,
            "status": "connected",
            "last_gps_at": timestamp,
            "latitude": 39.7392,
            "longitude": -104.9903,
            "buffer_status": {
                "pending_count": 4,
                "manual_pending_count": 1,
                "sensor_pending_count": 3,
                "report_pending_count": 1,
                "audio_pending_count": 2,
                "frame_pending_count": 1,
                "in_flight": True,
                "network": "offline",
                "last_error": "Upload retry pending.",
                "oldest_pending_at": timestamp.isoformat(),
                "updated_at": timestamp.isoformat(),
            },
        }
    ]

    client.get("/api/coordinator/dashboard-state")
    client.get("/api/coordinator/dashboard-state")
    client.get("/api/coordinator/dashboard-state")
    mock_db.insert_audit_event.reset_mock()

    resp = client.post("/api/coordinator/signals/member_buffer_sustained/acknowledge")

    assert resp.status_code == 200
    assert resp.json()["status"] == "acknowledged"
    assert "signature" not in resp.json()
    mock_db.insert_audit_event.assert_awaited_once()

    next_snapshot = client.get("/api/coordinator/dashboard-state")
    assert next_snapshot.status_code == 200
    payload = next_snapshot.json()
    assert payload["buffer_signal"]["status"] == "acknowledged"
    assert payload["review_feed"][0]["type"] == "signal"
    assert payload["review_feed"][0]["status"] == "acknowledged"


def test_snooze_dashboard_signal_hides_feed_item(
    client: TestClient,
    mock_db: MagicMock,
    mock_op_manager: MagicMock,
    mock_intelligence_service: MagicMock,
) -> None:
    member_id = uuid.uuid4()
    timestamp = dt.datetime.now(dt.timezone.utc)
    mock_db.get_latest_sitrep.return_value = None
    mock_db.get_review_feed.return_value = []
    mock_intelligence_service.snapshot.return_value = {
        "running": True,
        "audio_ingest": {"queue_size": 2},
        "frame_ingest": {"queue_size": 1},
    }
    mock_op_manager.get_member_list.return_value = [
        {
            "id": str(member_id),
            "name": "Sensor One",
            "role": "sensor",
            "connected_at": timestamp,
            "last_seen_at": timestamp,
            "status": "connected",
            "last_gps_at": timestamp,
            "latitude": 39.7392,
            "longitude": -104.9903,
            "buffer_status": {
                "pending_count": 4,
                "manual_pending_count": 1,
                "sensor_pending_count": 3,
                "report_pending_count": 1,
                "audio_pending_count": 2,
                "frame_pending_count": 1,
                "in_flight": True,
                "network": "offline",
                "last_error": "Upload retry pending.",
                "oldest_pending_at": timestamp.isoformat(),
                "updated_at": timestamp.isoformat(),
            },
        }
    ]

    client.get("/api/coordinator/dashboard-state")
    client.get("/api/coordinator/dashboard-state")
    client.get("/api/coordinator/dashboard-state")
    mock_db.insert_audit_event.reset_mock()

    resp = client.post(
        "/api/coordinator/signals/member_buffer_sustained/snooze",
        json={"minutes": 5},
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "snoozed"
    assert resp.json()["snoozed_until"]
    mock_db.insert_audit_event.assert_awaited_once()

    next_snapshot = client.get("/api/coordinator/dashboard-state")
    assert next_snapshot.status_code == 200
    payload = next_snapshot.json()
    assert payload["buffer_signal"]["status"] == "snoozed"
    assert not any(item["type"] == "signal" for item in payload["review_feed"])


def test_coordinator_dashboard_state_rejects_unknown_include(
    client: TestClient,
) -> None:
    resp = client.get("/api/coordinator/dashboard-state?include=bogus")

    assert resp.status_code == 400
    assert resp.json()["invalid_types"] == ["bogus"]


def test_dashboard_static_asset_serves(client: TestClient) -> None:
    resp = client.get("/static/dashboard.css")

    assert resp.status_code == 200
    assert "--color-bg" in resp.text


def test_member_static_asset_serves(client: TestClient) -> None:
    resp = client.get("/static/member.css")

    assert resp.status_code == 200
    assert "--member-bg" in resp.text


def test_member_sensor_assets_serve(client: TestClient) -> None:
    audio_resp = client.get("/static/audio-capture.js")
    frame_resp = client.get("/static/frame-sampler.js")
    worker_resp = client.get("/static/sampling-worker.js")
    observer_resp = client.get("/static/observer-media.js")
    outbox_resp = client.get("/static/member-outbox.js")
    pwa_resp = client.get("/static/pwa-runtime.js")

    assert audio_resp.status_code == 200
    assert "createAudioCapture" in audio_resp.text
    assert frame_resp.status_code == 200
    assert "createFrameSampler" in frame_resp.text
    assert worker_resp.status_code == 200
    assert 'type: "frame_score"' in worker_resp.text
    assert observer_resp.status_code == 200
    assert "createObserverMediaCapture" in observer_resp.text
    assert outbox_resp.status_code == 200
    assert "createMemberOutbox" in outbox_resp.text
    assert pwa_resp.status_code == 200
    assert "requestInstall" in pwa_resp.text


def test_member_manifest_serves(client: TestClient) -> None:
    resp = client.get("/manifest.webmanifest")

    assert resp.status_code == 200
    assert "application/manifest+json" in resp.headers["content-type"]
    assert resp.json()["name"] == "Osk Member"
    assert resp.json()["icons"][0]["src"] == "/static/icon.svg"


def test_member_service_worker_serves(client: TestClient) -> None:
    resp = client.get("/sw.js")

    assert resp.status_code == 200
    assert "application/javascript" in resp.headers["content-type"]
    assert resp.headers["service-worker-allowed"] == "/"
    assert "osk-member-v2" in resp.text
    assert "/static/member-outbox.js" in resp.text


@patch("osk.server.load_config")
def test_cached_map_tile_serves_png(
    mock_load_config: MagicMock,
    client: TestClient,
    tmp_path,
) -> None:
    tile_root = tmp_path / "tiles"
    cached_tile = tile_root / "14" / "3271" / "6234.png"
    cached_tile.parent.mkdir(parents=True, exist_ok=True)
    cached_tile.write_bytes(b"tile-bytes")
    mock_load_config.return_value = OskConfig(map_tile_cache_path=str(tile_root))

    resp = client.get("/tiles/14/3271/6234.png")

    assert resp.status_code == 200
    assert resp.content == b"tile-bytes"
    assert resp.headers["content-type"] == "image/png"
    assert resp.headers["x-osk-tile-status"] == "hit"


@patch("osk.server.load_config")
def test_cached_map_tile_returns_404_for_miss(
    mock_load_config: MagicMock,
    client: TestClient,
    tmp_path,
) -> None:
    tile_root = tmp_path / "tiles"
    tile_root.mkdir()
    mock_load_config.return_value = OskConfig(map_tile_cache_path=str(tile_root))

    resp = client.get("/tiles/14/3271/6234.png")

    assert resp.status_code == 404
    assert resp.headers["content-type"] == "image/png"
    assert resp.headers["x-osk-tile-status"] == "miss"


def test_operation_status(client: TestClient) -> None:
    resp = client.get("/api/operation/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Test Op"


def test_operation_status_rejects_remote_client(remote_client: TestClient) -> None:
    resp = remote_client.get("/api/operation/status")
    assert resp.status_code == 403
    assert resp.json()["error"] == "Local coordinator access only"


def test_operation_status_requires_coordinator_token(
    unauthenticated_client: TestClient,
) -> None:
    resp = unauthenticated_client.get("/api/operation/status")
    assert resp.status_code == 401
    assert resp.json()["error"] == "Missing operator credentials"


@patch("osk.server.validate_operator_session", return_value=True)
def test_operation_status_accepts_operator_session(
    mock_validate_operator_session: MagicMock,
    session_client: TestClient,
    operation: Operation,
) -> None:
    resp = session_client.get("/api/operation/status")

    assert resp.status_code == 200
    mock_validate_operator_session.assert_called_once_with(
        "operator-session-token",
        str(operation.id),
    )


@patch("osk.server.validate_dashboard_session", return_value=True)
def test_operation_status_accepts_dashboard_cookie(
    mock_validate_dashboard_session: MagicMock,
    unauthenticated_client: TestClient,
    operation: Operation,
) -> None:
    unauthenticated_client.cookies.set("osk_dashboard_session", "dashboard-cookie-token")

    resp = unauthenticated_client.get("/api/operation/status")

    assert resp.status_code == 200
    mock_validate_dashboard_session.assert_called_once_with(
        "dashboard-cookie-token",
        str(operation.id),
    )


def test_list_members(client: TestClient) -> None:
    resp = client.get("/api/members")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_intelligence_status(client: TestClient, mock_intelligence_service: MagicMock) -> None:
    resp = client.get("/api/intelligence/status")
    assert resp.status_code == 200
    assert resp.json()["running"] is True
    mock_intelligence_service.snapshot.assert_called_once_with()


def test_intelligence_status_rejects_remote_client(remote_client: TestClient) -> None:
    resp = remote_client.get("/api/intelligence/status")
    assert resp.status_code == 403


def test_intelligence_observations(client: TestClient, mock_db: MagicMock) -> None:
    mock_db.get_recent_intelligence_observations.return_value = [{"summary": "Police moving east."}]

    resp = client.get("/api/intelligence/observations?limit=10")

    assert resp.status_code == 200
    assert resp.json() == [{"summary": "Police moving east."}]
    mock_db.get_recent_intelligence_observations.assert_called_once()


def test_intelligence_findings(client: TestClient, mock_db: MagicMock) -> None:
    mock_db.get_synthesis_findings.return_value = [{"title": "Police Action"}]

    resp = client.get(
        "/api/intelligence/findings?limit=10&status=open&severity=warning&category=police_action"
    )

    assert resp.status_code == 200
    assert resp.json() == [{"title": "Police Action"}]
    mock_db.get_synthesis_findings.assert_called_once()
    _, kwargs = mock_db.get_synthesis_findings.await_args
    assert kwargs["limit"] == 10
    assert kwargs["status"].value == "open"
    assert kwargs["severity"].value == "warning"
    assert kwargs["category"].value == "police_action"


def test_intelligence_finding_detail(client: TestClient, mock_db: MagicMock) -> None:
    finding_id = uuid.uuid4()
    mock_db.get_synthesis_finding_detail.return_value = {
        "finding": {"id": str(finding_id), "title": "Police Action"},
        "observations": [],
        "events": [],
        "notes": [],
    }

    resp = client.get(f"/api/intelligence/findings/{finding_id}")

    assert resp.status_code == 200
    assert resp.json()["finding"]["title"] == "Police Action"
    mock_db.get_synthesis_finding_detail.assert_called_once()


def test_acknowledge_intelligence_finding(client: TestClient, mock_db: MagicMock) -> None:
    finding_id = uuid.uuid4()
    mock_db.update_synthesis_finding_status.return_value = {
        "id": str(finding_id),
        "status": "acknowledged",
    }

    resp = client.post(f"/api/intelligence/findings/{finding_id}/acknowledge")

    assert resp.status_code == 200
    assert resp.json()["status"] == "acknowledged"
    mock_db.update_synthesis_finding_status.assert_called_once()


def test_resolve_intelligence_finding(client: TestClient, mock_db: MagicMock) -> None:
    finding_id = uuid.uuid4()
    mock_db.update_synthesis_finding_status.return_value = {
        "id": str(finding_id),
        "status": "resolved",
    }

    resp = client.post(f"/api/intelligence/findings/{finding_id}/resolve")

    assert resp.status_code == 200
    assert resp.json()["status"] == "resolved"


def test_reopen_intelligence_finding(client: TestClient, mock_db: MagicMock) -> None:
    finding_id = uuid.uuid4()
    mock_db.update_synthesis_finding_status.return_value = {
        "id": str(finding_id),
        "status": "open",
    }

    resp = client.post(f"/api/intelligence/findings/{finding_id}/reopen")

    assert resp.status_code == 200
    assert resp.json()["status"] == "open"


def test_escalate_intelligence_finding(client: TestClient, mock_db: MagicMock) -> None:
    finding_id = uuid.uuid4()
    mock_db.escalate_synthesis_finding.return_value = {
        "id": str(finding_id),
        "severity": "critical",
    }

    resp = client.post(f"/api/intelligence/findings/{finding_id}/escalate")

    assert resp.status_code == 200
    assert resp.json()["severity"] == "critical"


def test_intelligence_finding_correlations(client: TestClient, mock_db: MagicMock) -> None:
    finding_id = uuid.uuid4()
    mock_db.get_synthesis_finding_correlations.return_value = {
        "finding": {"id": str(finding_id), "title": "Police Action"},
        "related_findings": [],
        "related_events": [],
        "window_minutes": 30,
    }

    resp = client.get(f"/api/intelligence/findings/{finding_id}/correlations?limit=4")

    assert resp.status_code == 200
    assert resp.json()["finding"]["title"] == "Police Action"
    mock_db.get_synthesis_finding_correlations.assert_called_once()


def test_note_intelligence_finding(client: TestClient, mock_db: MagicMock) -> None:
    finding_id = uuid.uuid4()
    mock_db.get_synthesis_finding.return_value = {"id": str(finding_id)}

    resp = client.post(
        f"/api/intelligence/findings/{finding_id}/notes",
        json={"text": "Watch east entrance for regrouping."},
    )

    assert resp.status_code == 200
    assert resp.json()["finding_id"] == str(finding_id)
    mock_db.insert_synthesis_finding_note.assert_called_once()


def test_intelligence_review_feed(client: TestClient, mock_db: MagicMock) -> None:
    mock_db.get_review_feed.return_value = [
        {"type": "finding", "title": "Police Action"},
        {"type": "sitrep", "summary": "Situation remains tense."},
    ]

    resp = client.get(
        "/api/intelligence/review-feed"
        "?limit=12&include=finding&include=sitrep&finding_status=acknowledged&severity=warning"
    )

    assert resp.status_code == 200
    assert resp.json()[0]["type"] == "finding"
    mock_db.get_review_feed.assert_called_once()


def test_intelligence_review_feed_rejects_unknown_include(client: TestClient) -> None:
    resp = client.get("/api/intelligence/review-feed?include=bogus")

    assert resp.status_code == 400
    assert resp.json()["invalid_types"] == ["bogus"]


def test_intelligence_status_reports_missing_service(
    mock_op_manager: MagicMock,
    mock_conn_mgr: MagicMock,
    mock_db: MagicMock,
) -> None:
    app = create_app(op_manager=mock_op_manager, conn_manager=mock_conn_mgr, db=mock_db)
    client = TestClient(
        app,
        headers={"X-Osk-Coordinator-Token": mock_op_manager.operation.coordinator_token},
    )

    resp = client.get("/api/intelligence/status")

    assert resp.status_code == 503
    assert resp.json()["error"] == "Intelligence service is not configured"


def test_list_audit_events(client: TestClient, mock_db: MagicMock) -> None:
    mock_db.get_audit_events.return_value = [{"action": "operation_created"}]
    resp = client.get("/api/audit?limit=25")
    assert resp.status_code == 200
    assert resp.json() == [{"action": "operation_created"}]
    mock_db.get_audit_events.assert_called_once()


def test_list_audit_events_filters_actions(client: TestClient, mock_db: MagicMock) -> None:
    mock_db.get_audit_events.return_value = [{"action": "wipe_follow_up_verified"}]

    resp = client.get(
        "/api/audit?limit=25&action=operator_session_created&wipe_follow_up_only=true"
    )

    assert resp.status_code == 200
    assert resp.json() == [{"action": "wipe_follow_up_verified"}]
    mock_db.get_audit_events.assert_called_once_with(
        client.app.state.mock_operation.id,
        25,
        actions=[
            "operator_session_created",
            "wipe_follow_up_verified",
            "wipe_follow_up_reopened",
            "wipe_follow_up_historical_reviewed",
            "wipe_follow_up_historical_retired",
        ],
    )


def test_promote_member(
    client: TestClient, mock_op_manager: MagicMock, mock_conn_mgr: MagicMock
) -> None:
    member_id = uuid.uuid4()
    mock_op_manager.members = {member_id: MagicMock(role=MemberRole.OBSERVER)}
    resp = client.post(f"/api/members/{member_id}/promote")
    assert resp.status_code == 200
    mock_op_manager.promote_member.assert_called_once()
    mock_conn_mgr.send_to.assert_called_once()


def test_demote_member(client: TestClient, mock_op_manager: MagicMock) -> None:
    member_id = uuid.uuid4()
    mock_op_manager.members = {member_id: MagicMock(role=MemberRole.SENSOR)}
    resp = client.post(f"/api/members/{member_id}/demote")
    assert resp.status_code == 200
    mock_op_manager.demote_member.assert_called_once()


def test_kick_member(
    client: TestClient, mock_op_manager: MagicMock, mock_conn_mgr: MagicMock
) -> None:
    member_id = uuid.uuid4()
    mock_op_manager.members = {member_id: MagicMock()}
    resp = client.post(f"/api/members/{member_id}/kick")
    assert resp.status_code == 200
    mock_op_manager.kick_member.assert_called_once()
    mock_conn_mgr.disconnect.assert_called_once()


def test_rotate_token(client: TestClient) -> None:
    resp = client.post("/api/rotate-token")
    assert resp.status_code == 200
    assert resp.json()["token"] == "new-token"


def test_rotate_token_rejects_remote_client(remote_client: TestClient) -> None:
    resp = remote_client.post("/api/rotate-token")
    assert resp.status_code == 403


def test_pin_event(client: TestClient, mock_db: MagicMock) -> None:
    event_id = uuid.uuid4()
    resp = client.post(f"/api/pin/{event_id}", json={"member_id": str(uuid.uuid4())})
    assert resp.status_code == 200
    mock_db.insert_pin.assert_called_once()


def test_report(client: TestClient, mock_db: MagicMock) -> None:
    resp = client.post(
        "/api/report", json={"member_id": str(uuid.uuid4()), "text": "Suspicious activity"}
    )
    assert resp.status_code == 200
    mock_db.insert_event.assert_called_once()


def test_websocket_submits_audio_frame_and_location_to_intelligence_service(
    client: TestClient,
    mock_intelligence_service: MagicMock,
) -> None:
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({"type": "auth", "token": "valid-token", "name": "Jay"})
        auth_ok = websocket.receive_json()

        websocket.send_json(
            {
                "type": "audio_meta",
                "codec": "audio/raw",
                "sample_rate_hz": 16000,
                "duration_ms": 250,
                "sequence_no": 7,
                "chunk_id": "client-chunk-7",
            }
        )
        websocket.send_bytes(b"\x00\x01\x02\x03")
        audio_ack = websocket.receive_json()

        websocket.send_json(
            {
                "type": "frame_meta",
                "content_type": "image/jpeg",
                "width": 640,
                "height": 360,
                "change_score": 0.8,
                "sequence_no": 9,
                "frame_id": "client-frame-9",
            }
        )
        websocket.send_bytes(b"jpeg-payload")
        frame_ack = websocket.receive_json()

        websocket.send_json(
            {
                "type": "gps",
                "lat": 39.75,
                "lon": -104.99,
                "accuracy_m": 6.0,
            }
        )

    assert auth_ok["type"] == "auth_ok"
    assert audio_ack["type"] == "audio_ack"
    assert audio_ack["accepted"] is True
    assert frame_ack["type"] == "frame_ack"
    assert frame_ack["accepted"] is True
    mock_intelligence_service.submit_audio.assert_awaited_once()
    mock_intelligence_service.submit_frame.assert_awaited_once()
    mock_intelligence_service.submit_location.assert_awaited_once()
    submitted_chunk = mock_intelligence_service.submit_audio.await_args.args[0]
    submitted_frame = mock_intelligence_service.submit_frame.await_args.args[0]
    submitted_location = mock_intelligence_service.submit_location.await_args.args[0]
    assert submitted_chunk.codec == "audio/raw"
    assert submitted_chunk.payload == b"\x00\x01\x02\x03"
    assert submitted_chunk.ingest_key == "client-chunk-7"
    assert submitted_frame.width == 640
    assert submitted_frame.payload == b"jpeg-payload"
    assert submitted_frame.ingest_key == "client-frame-9"
    assert submitted_location.latitude == 39.75
    assert submitted_location.longitude == -104.99


def test_websocket_rejects_oversized_audio_payload(
    client: TestClient,
    mock_intelligence_service: MagicMock,
) -> None:
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({"type": "auth", "token": "valid-token", "name": "Jay"})
        websocket.receive_json()
        websocket.send_json(
            {
                "type": "audio_meta",
                "codec": "audio/raw",
                "sample_rate_hz": 16000,
                "duration_ms": 250,
            }
        )
        websocket.send_bytes(b"x" * 33)
        audio_ack = websocket.receive_json()

    assert audio_ack["type"] == "audio_ack"
    assert audio_ack["accepted"] is False
    assert audio_ack["reason"] == "audio payload too large"
    mock_intelligence_service.submit_audio.assert_not_awaited()


def test_websocket_audio_duplicate_ack(
    client: TestClient, mock_intelligence_service: MagicMock
) -> None:
    mock_intelligence_service.submit_audio.side_effect = [
        IngestSubmissionResult(accepted=True),
        IngestSubmissionResult(accepted=True, duplicate=True),
    ]

    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({"type": "auth", "token": "valid-token", "name": "Jay"})
        websocket.receive_json()
        websocket.send_json(
            {
                "type": "audio_chunk",
                "codec": "audio/raw",
                "sample_rate_hz": 16000,
                "duration_ms": 250,
                "chunk_id": "client-chunk-1",
                "payload_b64": "AAEC",
            }
        )
        first_ack = websocket.receive_json()
        websocket.send_json(
            {
                "type": "audio_chunk",
                "codec": "audio/raw",
                "sample_rate_hz": 16000,
                "duration_ms": 250,
                "chunk_id": "client-chunk-1",
                "payload_b64": "AAEC",
            }
        )
        second_ack = websocket.receive_json()

    assert first_ack["accepted"] is True
    assert first_ack.get("duplicate") is None
    assert second_ack["accepted"] is True
    assert second_ack["duplicate"] is True
    assert second_ack["ingest_key"] == "client-chunk-1"


def test_wipe_rejects_remote_client(remote_client: TestClient) -> None:
    resp = remote_client.post("/api/wipe")
    assert resp.status_code == 403


def test_wipe_returns_and_records_coverage(
    client: TestClient,
    mock_db: MagicMock,
    mock_conn_mgr: MagicMock,
    mock_op_manager: MagicMock,
) -> None:
    current = dt.datetime.now(dt.timezone.utc)
    stale_seen = current - dt.timedelta(seconds=180)
    disconnected_seen = current - dt.timedelta(seconds=420)
    mock_conn_mgr.connected_count = 1
    mock_db.get_audit_events.return_value = []
    mock_op_manager.get_member_list.return_value = [
        {
            "id": str(uuid.uuid4()),
            "name": "Observer One",
            "role": "observer",
            "connected_at": current,
            "last_seen_at": stale_seen,
            "status": "connected",
            "last_gps_at": None,
            "latitude": None,
            "longitude": None,
            "buffer_status": {},
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Sensor Two",
            "role": "sensor",
            "connected_at": current,
            "last_seen_at": disconnected_seen,
            "status": "disconnected",
            "last_gps_at": None,
            "latitude": None,
            "longitude": None,
            "buffer_status": {},
        },
    ]

    with patch(
        "osk.server.load_config",
        return_value=OskConfig(member_heartbeat_timeout_seconds=60),
    ):
        resp = client.post("/api/wipe")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "wipe_initiated"
    assert payload["broadcast_target_count"] == 1
    assert payload["wipe_readiness"]["status"] == "blocked"
    assert payload["wipe_readiness"]["stale_members"] == 1
    assert payload["wipe_readiness"]["disconnected_members"] == 1
    assert payload["wipe_readiness"]["follow_up_required"] is True
    assert payload["wipe_readiness"]["follow_up_count"] == 2
    assert payload["wipe_readiness"]["follow_up"][0]["name"] == "Sensor Two"
    assert payload["wipe_readiness"]["follow_up"][0]["resolution"] == "unresolved"
    mock_conn_mgr.broadcast.assert_awaited_once_with({"type": "wipe"})
    mock_db.insert_audit_event.assert_awaited_once()
    audit_details = mock_db.insert_audit_event.await_args.kwargs["details"]
    assert audit_details["broadcast_target_count"] == 1
    assert audit_details["wipe_readiness"]["at_risk"][0]["name"] == "Sensor Two"
    assert audit_details["wipe_readiness"]["follow_up"][0]["required_action"].startswith(
        "Reconnect this member browser and confirm wipe"
    )


def test_wipe_returns_decorated_follow_up_history(
    client: TestClient,
    mock_db: MagicMock,
    mock_conn_mgr: MagicMock,
    mock_op_manager: MagicMock,
) -> None:
    current = dt.datetime(2026, 3, 23, 8, 12, tzinfo=dt.timezone.utc)
    historical_seen = dt.datetime(2026, 3, 23, 0, 8, tzinfo=dt.timezone.utc)
    member_id = uuid.uuid4()
    mock_conn_mgr.connected_count = 1
    mock_op_manager.get_member_list.return_value = [
        {
            "id": str(member_id),
            "name": "Observer Trail",
            "role": "observer",
            "connected_at": current,
            "last_seen_at": historical_seen,
            "status": "disconnected",
            "last_gps_at": None,
            "latitude": None,
            "longitude": None,
            "buffer_status": {},
        }
    ]
    mock_db.get_audit_events.return_value = [
        {
            "action": "wipe_follow_up_historical_reviewed",
            "actor_type": "coordinator",
            "timestamp": dt.datetime(2026, 3, 23, 8, 0, tzinfo=dt.timezone.utc),
            "details": {
                "member_id": str(member_id),
                "member_name": "Observer Trail",
                "reason": "disconnected",
                "classification": "historical_drift",
                "last_seen_at": historical_seen.isoformat().replace("+00:00", "Z"),
            },
        }
    ]

    with patch(
        "osk.server.load_config",
        return_value=OskConfig(member_heartbeat_timeout_seconds=60),
    ):
        resp = client.post("/api/wipe")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["wipe_readiness"]["follow_up_history_count"] == 1
    assert payload["wipe_readiness"]["follow_up_history_summary"].startswith(
        "Recent follow-up trail:"
    )
    assert (
        payload["wipe_readiness"]["follow_up_history"][0]["action"]
        == "wipe_follow_up_historical_reviewed"
    )


def test_wipe_excludes_retired_historical_drift_from_current_follow_up(
    client: TestClient,
    mock_db: MagicMock,
    mock_conn_mgr: MagicMock,
    mock_op_manager: MagicMock,
) -> None:
    current = dt.datetime(2026, 3, 23, 8, 12, tzinfo=dt.timezone.utc)
    historical_seen = dt.datetime(2026, 3, 23, 0, 8, tzinfo=dt.timezone.utc)
    member_id = uuid.uuid4()
    mock_conn_mgr.connected_count = 0
    mock_op_manager.get_member_list.return_value = [
        {
            "id": str(member_id),
            "name": "Observer Retired",
            "role": "observer",
            "connected_at": current,
            "last_seen_at": historical_seen,
            "status": "disconnected",
            "last_gps_at": None,
            "latitude": None,
            "longitude": None,
            "buffer_status": {},
        }
    ]
    mock_db.get_audit_events.return_value = [
        {
            "action": "wipe_follow_up_historical_retired",
            "actor_type": "coordinator",
            "timestamp": dt.datetime(2026, 3, 23, 8, 5, tzinfo=dt.timezone.utc),
            "details": {
                "member_id": str(member_id),
                "member_name": "Observer Retired",
                "reason": "disconnected",
                "classification": "historical_drift",
                "last_seen_at": historical_seen.isoformat().replace("+00:00", "Z"),
            },
        }
    ]

    with patch(
        "osk.server.load_config",
        return_value=OskConfig(member_heartbeat_timeout_seconds=60),
    ):
        resp = client.post("/api/wipe")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["wipe_readiness"]["follow_up_required"] is False
    assert payload["wipe_readiness"]["follow_up_count"] == 0
    assert payload["wipe_readiness"]["historical_drift_follow_up_count"] == 0
    assert payload["wipe_readiness"]["retired_historical_drift_follow_up_count"] == 1
    assert payload["wipe_readiness"]["follow_up_history"][0]["status"] == "retired"


def test_websocket_auth_flow(
    client: TestClient, mock_conn_mgr: MagicMock, mock_op_manager: MagicMock
) -> None:
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({"type": "auth", "token": "valid-token", "name": "Jay"})
        message = websocket.receive_json()

    assert message["type"] == "auth_ok"
    assert message["member_session_code"]
    assert message["member_session_expires_at"]
    assert "resume_token" not in message
    assert message["resumed"] is False
    mock_conn_mgr.register.assert_called_once()
    mock_op_manager.add_member.assert_called_once()


def test_websocket_auth_flow_accepts_member_cookie(
    unauthenticated_client: TestClient,
    mock_conn_mgr: MagicMock,
    mock_op_manager: MagicMock,
) -> None:
    unauthenticated_client.cookies.set("osk_member_join", "valid-token")

    with unauthenticated_client.websocket_connect("/ws") as websocket:
        websocket.send_json({"type": "auth", "name": "Jay"})
        message = websocket.receive_json()

    assert message["type"] == "auth_ok"
    assert message["member_session_code"]
    mock_conn_mgr.register.assert_called_once()
    mock_op_manager.add_member.assert_called_once()


@patch("osk.server._member_runtime_session_from_websocket")
def test_websocket_auth_flow_accepts_member_runtime_cookie(
    mock_member_runtime_session_from_websocket: MagicMock,
    unauthenticated_client: TestClient,
    mock_conn_mgr: MagicMock,
    mock_op_manager: MagicMock,
) -> None:
    member_id = uuid.uuid4()
    resumed_member = MagicMock(
        id=member_id,
        name="Jay",
        role=MemberRole.OBSERVER,
        reconnect_token="resume-secret",
    )
    mock_member_runtime_session_from_websocket.return_value = {
        "member": resumed_member,
        "member_id": member_id,
        "reconnect_token": "resume-secret",
        "expires_at": "2026-03-21T19:30:00+00:00",
    }
    mock_op_manager.resume_member = AsyncMock(return_value=resumed_member)
    unauthenticated_client.cookies.set("osk_member_runtime", "runtime-cookie")

    with unauthenticated_client.websocket_connect("/ws") as websocket:
        websocket.send_json({"type": "auth", "name": "Jay"})
        message = websocket.receive_json()

    assert message["type"] == "auth_ok"
    assert message["member_id"] == str(member_id)
    assert message["resumed"] is True
    assert message["member_session_code"]
    mock_conn_mgr.register.assert_called_once()
    mock_op_manager.resume_member.assert_called_once_with(
        mock_op_manager.operation.id,
        member_id,
        "resume-secret",
    )


def test_websocket_resume_flow(
    client: TestClient, mock_conn_mgr: MagicMock, mock_op_manager: MagicMock
) -> None:
    member_id = uuid.uuid4()
    resumed_member = MagicMock(
        id=member_id,
        name="Jay",
        role=MemberRole.OBSERVER,
        reconnect_token="resume-secret",
    )
    mock_op_manager.resume_member = AsyncMock(return_value=resumed_member)

    with client.websocket_connect("/ws") as websocket:
        websocket.send_json(
            {
                "type": "auth",
                "token": "valid-token",
                "name": "Jay",
                "resume_member_id": str(member_id),
                "resume_token": "resume-secret",
            }
        )
        message = websocket.receive_json()

    assert message["type"] == "auth_ok"
    assert message["member_id"] == str(member_id)
    assert message["member_session_code"]
    assert "resume_token" not in message
    assert message["resumed"] is True
    mock_op_manager.resume_member.assert_called_once()


def test_websocket_activity_records_wipe_follow_up_reopened_once(
    client: TestClient,
    mock_db: MagicMock,
    mock_op_manager: MagicMock,
) -> None:
    member_id = uuid.uuid4()
    verified_at = dt.datetime(2026, 3, 23, 3, 0, tzinfo=dt.timezone.utc)
    activity_at = dt.datetime(2026, 3, 23, 3, 5, tzinfo=dt.timezone.utc)
    member = MagicMock(
        id=member_id,
        name="Jay",
        role=MemberRole.OBSERVER,
        status=MemberStatus.CONNECTED,
        reconnect_token="resume-secret",
        last_seen_at=verified_at - dt.timedelta(seconds=30),
    )
    mock_op_manager.add_member = AsyncMock(return_value=member)
    mock_op_manager.members = {member_id: member}

    async def touch_heartbeat(member_uuid: uuid.UUID) -> None:
        assert member_uuid == member_id
        member.last_seen_at = activity_at

    mock_op_manager.touch_member_heartbeat = AsyncMock(side_effect=touch_heartbeat)
    mock_db.get_audit_events.return_value = [
        {
            "action": "wipe_follow_up_verified",
            "timestamp": verified_at,
            "details": {
                "member_id": str(member_id),
                "member_name": "Jay",
                "reason": "stale",
            },
        }
    ]

    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({"type": "auth", "token": "valid-token", "name": "Jay"})
        websocket.receive_json()
        websocket.send_json({"type": "buffer_status", "pending_count": 1})
        websocket.send_json({"type": "buffer_status", "pending_count": 2})

    assert mock_db.insert_audit_event.await_count == 1
    assert mock_db.insert_audit_event.await_args.args[2] == "wipe_follow_up_reopened"
    assert mock_db.insert_audit_event.await_args.kwargs["actor_member_id"] == member_id
    details = mock_db.insert_audit_event.await_args.kwargs["details"]
    assert details["member_id"] == str(member_id)
    assert details["activity_kind"] == "message"
    assert details["verified_at"] == "2026-03-23T03:00:00Z"
    assert details["last_seen_at"] == "2026-03-23T03:05:00Z"


def test_websocket_resume_records_wipe_follow_up_reopened(
    client: TestClient,
    mock_db: MagicMock,
    mock_op_manager: MagicMock,
) -> None:
    member_id = uuid.uuid4()
    verified_at = dt.datetime(2026, 3, 23, 3, 0, tzinfo=dt.timezone.utc)
    resumed_at = dt.datetime(2026, 3, 23, 3, 8, tzinfo=dt.timezone.utc)
    resumed_member = MagicMock(
        id=member_id,
        name="Jay",
        role=MemberRole.OBSERVER,
        status=MemberStatus.CONNECTED,
        reconnect_token="resume-secret",
        last_seen_at=resumed_at,
    )
    mock_op_manager.resume_member = AsyncMock(return_value=resumed_member)
    mock_op_manager.members = {member_id: resumed_member}
    mock_db.get_audit_events.return_value = [
        {
            "action": "wipe_follow_up_verified",
            "timestamp": verified_at,
            "details": {
                "member_id": str(member_id),
                "member_name": "Jay",
                "reason": "disconnected",
            },
        }
    ]

    with client.websocket_connect("/ws") as websocket:
        websocket.send_json(
            {
                "type": "auth",
                "token": "valid-token",
                "name": "Jay",
                "resume_member_id": str(member_id),
                "resume_token": "resume-secret",
            }
        )
        message = websocket.receive_json()

    assert message["type"] == "auth_ok"
    assert mock_db.insert_audit_event.await_count == 1
    assert mock_db.insert_audit_event.await_args.args[2] == "wipe_follow_up_reopened"
    details = mock_db.insert_audit_event.await_args.kwargs["details"]
    assert details["member_id"] == str(member_id)
    assert details["activity_kind"] == "resume"
    assert details["verified_at"] == "2026-03-23T03:00:00Z"
    assert details["last_seen_at"] == "2026-03-23T03:08:00Z"


def test_websocket_manual_report_ack(
    client: TestClient,
    mock_db: MagicMock,
) -> None:
    report_timestamp = dt.datetime(2026, 3, 22, 1, 0, tzinfo=dt.timezone.utc)
    mock_db.insert_manual_report_once.return_value = {
        "duplicate": False,
        "event_id": uuid.uuid4(),
        "text": "Need medics at the west gate",
        "timestamp": report_timestamp,
    }
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({"type": "auth", "token": "valid-token", "name": "Jay"})
        websocket.receive_json()
        websocket.send_json(
            {
                "type": "report",
                "report_id": "report-1",
                "text": "Need medics at the west gate",
            }
        )
        ack = websocket.receive_json()

    assert ack["type"] == "report_ack"
    assert ack["accepted"] is True
    assert ack["report_id"] == "report-1"
    assert ack["event_id"]
    assert ack["text"] == "Need medics at the west gate"
    assert ack["timestamp"] == "2026-03-22T01:00:00Z"
    mock_db.insert_manual_report_once.assert_awaited_once()
    mock_db.insert_audit_event.assert_awaited()


def test_websocket_manual_report_duplicate_ack(
    client: TestClient,
    mock_db: MagicMock,
) -> None:
    existing_event_id = uuid.uuid4()
    report_timestamp = dt.datetime(2026, 3, 22, 1, 15, tzinfo=dt.timezone.utc)
    mock_db.insert_manual_report_once.return_value = {
        "duplicate": True,
        "event_id": existing_event_id,
        "text": "Need medics at the west gate",
        "timestamp": report_timestamp,
    }

    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({"type": "auth", "token": "valid-token", "name": "Jay"})
        websocket.receive_json()
        websocket.send_json(
            {
                "type": "report",
                "report_id": "report-1",
                "text": "Need medics at the west gate",
            }
        )
        ack = websocket.receive_json()

    assert ack == {
        "type": "report_ack",
        "accepted": True,
        "duplicate": True,
        "event_id": str(existing_event_id),
        "report_id": "report-1",
        "text": "Need medics at the west gate",
        "timestamp": "2026-03-22T01:15:00Z",
    }
    assert mock_db.insert_event.await_count == 0
    mock_db.insert_manual_report_once.assert_awaited_once()
    assert mock_db.insert_audit_event.await_args.args[2] == "report_replayed_duplicate"


def test_websocket_manual_report_without_report_id_uses_direct_insert(
    client: TestClient,
    mock_db: MagicMock,
) -> None:
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({"type": "auth", "token": "valid-token", "name": "Jay"})
        websocket.receive_json()
        websocket.send_json({"type": "report", "text": "Need medics at the west gate"})
        ack = websocket.receive_json()

    assert ack["type"] == "report_ack"
    assert ack["accepted"] is True
    assert "duplicate" not in ack
    mock_db.insert_event.assert_awaited_once()
    assert mock_db.insert_manual_report_once.await_count == 0


def test_websocket_updates_member_buffer_status(
    client: TestClient,
    mock_op_manager: MagicMock,
) -> None:
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({"type": "auth", "token": "valid-token", "name": "Jay"})
        websocket.receive_json()
        websocket.send_json(
            {
                "type": "buffer_status",
                "pending_count": 4,
                "manual_pending_count": 1,
                "sensor_pending_count": 3,
                "report_pending_count": 1,
                "audio_pending_count": 2,
                "frame_pending_count": 1,
                "in_flight": True,
                "network": "offline",
                "last_error": "Retry pending.",
            }
        )

    args = mock_op_manager.update_member_buffer_status.await_args.args
    assert str(args[1]["pending_count"]) == "4"
    assert args[1]["network"] == "offline"


def test_websocket_manual_report_requires_text(
    client: TestClient,
    mock_db: MagicMock,
) -> None:
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({"type": "auth", "token": "valid-token", "name": "Jay"})
        websocket.receive_json()
        websocket.send_json({"type": "report", "report_id": "report-2", "text": "   "})
        ack = websocket.receive_json()

    assert ack == {
        "type": "report_ack",
        "accepted": False,
        "error": "Report text is required.",
        "report_id": "report-2",
    }
    mock_db.insert_event.assert_not_awaited()
