"""Tests for FastAPI server."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from osk.intelligence_service import IngestSubmissionResult
from osk.models import MemberRole, Operation
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
    mgr.mark_disconnected = AsyncMock()
    mgr.touch_member_heartbeat = AsyncMock()
    mgr.update_member_gps = AsyncMock()
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


def test_join_page_invalid_token(client: TestClient, mock_op_manager: MagicMock) -> None:
    mock_op_manager.validate_token.return_value = False
    resp = client.get("/join?token=bad-token")
    assert resp.status_code == 403


def test_coordinator_dashboard_renders_local_shell(client: TestClient) -> None:
    resp = client.get("/coordinator")

    assert resp.status_code == 200
    assert "Osk Coordinator Review" in resp.text
    assert "/static/dashboard.js" in resp.text
    assert resp.headers["cache-control"] == "no-store"
    assert resp.headers["pragma"] == "no-cache"
    assert resp.headers["referrer-policy"] == "no-referrer"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["x-content-type-options"] == "nosniff"
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


def test_dashboard_static_asset_serves(client: TestClient) -> None:
    resp = client.get("/static/dashboard.css")

    assert resp.status_code == 200
    assert "--color-bg" in resp.text


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


def test_websocket_auth_flow(
    client: TestClient, mock_conn_mgr: MagicMock, mock_op_manager: MagicMock
) -> None:
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({"type": "auth", "token": "valid-token", "name": "Jay"})
        message = websocket.receive_json()

    assert message["type"] == "auth_ok"
    assert message["resume_token"]
    assert message["resumed"] is False
    mock_conn_mgr.register.assert_called_once()
    mock_op_manager.add_member.assert_called_once()


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
    assert message["resume_token"] == "resume-secret"
    assert message["resumed"] is True
    mock_op_manager.resume_member.assert_called_once()
