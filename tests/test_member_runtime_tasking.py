from __future__ import annotations

import datetime as dt
import uuid
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from osk.models import MemberRole, Operation
from osk.server import create_app


def _build_app(*, coordinator_engine: MagicMock | None = None):
    operation = Operation(name="Test Op")
    member_id = uuid.uuid4()
    op_manager = MagicMock()
    op_manager.operation = operation
    op_manager.validate_token = MagicMock(return_value=True)
    op_manager.validate_coordinator_token = MagicMock(return_value=True)
    op_manager.add_member = AsyncMock(
        return_value=MagicMock(
            id=member_id,
            name="Jay",
            role=MemberRole.SENSOR,
            reconnect_token="resume-secret",
        )
    )
    op_manager.touch_member_heartbeat = AsyncMock()
    op_manager.update_member_gps = AsyncMock()
    op_manager.update_member_buffer_status = AsyncMock()
    op_manager.mark_disconnected = AsyncMock()
    op_manager.members = {}

    conn_manager = MagicMock()
    conn_manager.register = MagicMock()
    conn_manager.disconnect = AsyncMock()
    conn_manager.unregister = MagicMock()
    conn_manager.mark_seen = MagicMock()
    conn_manager.connections = {}
    conn_manager.connected_count = 0
    conn_manager.send_to = AsyncMock()

    db = MagicMock()
    db.insert_manual_report_once = AsyncMock(
        return_value={
            "duplicate": False,
            "event_id": uuid.uuid4(),
            "text": "North route looks clear.",
            "timestamp": dt.datetime(2026, 3, 28, 8, 0, tzinfo=dt.timezone.utc),
        }
    )
    db.insert_event = AsyncMock()
    db.insert_audit_event = AsyncMock()
    db.get_coordinator_state = AsyncMock(
        return_value={
            "gaps": [],
            "tasks": [],
            "recommendations": [],
            "active_gap": None,
            "active_task": None,
            "active_recommendation": None,
        }
    )

    app = create_app(
        op_manager=op_manager,
        conn_manager=conn_manager,
        db=db,
        intelligence_service=None,
        coordinator_engine=coordinator_engine,
    )
    return app, db, op_manager


def test_websocket_auth_pushes_current_task() -> None:
    coordinator_engine = MagicMock()
    coordinator_engine.push_current_task = AsyncMock()
    app, _, _ = _build_app(coordinator_engine=coordinator_engine)
    client = TestClient(app)

    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({"type": "auth", "token": "valid-token", "name": "Jay"})
        auth_ok = websocket.receive_json()

    assert auth_ok["type"] == "auth_ok"
    coordinator_engine.push_current_task.assert_awaited_once()


def test_websocket_report_invokes_coordinator_engine() -> None:
    coordinator_engine = MagicMock()
    coordinator_engine.push_current_task = AsyncMock()
    coordinator_engine.process_member_report = AsyncMock()
    app, db, _ = _build_app(coordinator_engine=coordinator_engine)
    client = TestClient(app)

    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({"type": "auth", "token": "valid-token", "name": "Jay"})
        websocket.receive_json()
        websocket.send_json(
            {
                "type": "report",
                "report_id": "report-1",
                "text": "North route looks clear.",
            }
        )
        ack = websocket.receive_json()

    assert ack["type"] == "report_ack"
    coordinator_engine.process_member_report.assert_awaited_once()
    _, kwargs = coordinator_engine.process_member_report.await_args
    assert kwargs["report_text"] == "North route looks clear."
    assert kwargs["event_id"] == db.insert_manual_report_once.return_value["event_id"]
