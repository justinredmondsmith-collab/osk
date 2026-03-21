"""Tests for FastAPI server."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

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
def app(mock_op_manager: MagicMock, mock_conn_mgr: MagicMock, mock_db: MagicMock):
    app = create_app(op_manager=mock_op_manager, conn_manager=mock_conn_mgr, db=mock_db)
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


def test_join_page_valid_token(client: TestClient, mock_op_manager: MagicMock) -> None:
    mock_op_manager.validate_token.return_value = True
    resp = client.get("/join?token=valid-token")
    assert resp.status_code == 200


def test_join_page_invalid_token(client: TestClient, mock_op_manager: MagicMock) -> None:
    mock_op_manager.validate_token.return_value = False
    resp = client.get("/join?token=bad-token")
    assert resp.status_code == 403


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
    assert resp.json()["error"] == "Missing coordinator token"


def test_list_members(client: TestClient) -> None:
    resp = client.get("/api/members")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


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
