from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from osk.connection_manager import ConnectionManager
from osk.models import MemberRole


@pytest.fixture
def mock_ws() -> MagicMock:
    ws = MagicMock()
    ws.send_json = AsyncMock()
    ws.send_bytes = AsyncMock()
    ws.close = AsyncMock()
    return ws


@pytest.fixture
def conn_mgr() -> ConnectionManager:
    return ConnectionManager()


def test_register_connection(conn_mgr: ConnectionManager, mock_ws: MagicMock) -> None:
    member_id = uuid.uuid4()
    conn_mgr.register(member_id, mock_ws, MemberRole.OBSERVER)
    assert member_id in conn_mgr.connections


def test_unregister_connection(conn_mgr: ConnectionManager, mock_ws: MagicMock) -> None:
    member_id = uuid.uuid4()
    conn_mgr.register(member_id, mock_ws, MemberRole.OBSERVER)
    conn_mgr.unregister(member_id)
    assert member_id not in conn_mgr.connections


async def test_send_to_member(conn_mgr: ConnectionManager, mock_ws: MagicMock) -> None:
    member_id = uuid.uuid4()
    conn_mgr.register(member_id, mock_ws, MemberRole.OBSERVER)
    await conn_mgr.send_to(member_id, {"type": "test"})
    mock_ws.send_json.assert_called_once_with({"type": "test"})


async def test_broadcast_all(conn_mgr: ConnectionManager) -> None:
    ws1 = MagicMock(send_json=AsyncMock())
    ws2 = MagicMock(send_json=AsyncMock())
    conn_mgr.register(uuid.uuid4(), ws1, MemberRole.OBSERVER)
    conn_mgr.register(uuid.uuid4(), ws2, MemberRole.SENSOR)
    await conn_mgr.broadcast({"type": "status", "members": 2})
    ws1.send_json.assert_called_once()
    ws2.send_json.assert_called_once()


async def test_broadcast_by_role(conn_mgr: ConnectionManager) -> None:
    ws_obs = MagicMock(send_json=AsyncMock())
    ws_sen = MagicMock(send_json=AsyncMock())
    ws_coord = MagicMock(send_json=AsyncMock())
    conn_mgr.register(uuid.uuid4(), ws_obs, MemberRole.OBSERVER)
    conn_mgr.register(uuid.uuid4(), ws_sen, MemberRole.SENSOR)
    coord_id = uuid.uuid4()
    conn_mgr.register(coord_id, ws_coord, MemberRole.COORDINATOR)
    await conn_mgr.broadcast_to_role(MemberRole.COORDINATOR, {"type": "event", "text": "test"})
    ws_obs.send_json.assert_not_called()
    ws_sen.send_json.assert_not_called()
    ws_coord.send_json.assert_called_once()


async def test_broadcast_alert_filters_by_severity(conn_mgr: ConnectionManager) -> None:
    ws_obs = MagicMock(send_json=AsyncMock())
    ws_sen = MagicMock(send_json=AsyncMock())
    conn_mgr.register(uuid.uuid4(), ws_obs, MemberRole.OBSERVER)
    conn_mgr.register(uuid.uuid4(), ws_sen, MemberRole.SENSOR)
    await conn_mgr.broadcast_alert({"type": "alert", "severity": "advisory", "text": "test"})
    ws_sen.send_json.assert_called_once()
    ws_obs.send_json.assert_not_called()


async def test_broadcast_alert_critical_reaches_all(conn_mgr: ConnectionManager) -> None:
    ws_obs = MagicMock(send_json=AsyncMock())
    ws_sen = MagicMock(send_json=AsyncMock())
    conn_mgr.register(uuid.uuid4(), ws_obs, MemberRole.OBSERVER)
    conn_mgr.register(uuid.uuid4(), ws_sen, MemberRole.SENSOR)
    await conn_mgr.broadcast_alert({"type": "alert", "severity": "critical", "text": "danger"})
    ws_obs.send_json.assert_called_once()
    ws_sen.send_json.assert_called_once()


def test_update_role(conn_mgr: ConnectionManager, mock_ws: MagicMock) -> None:
    member_id = uuid.uuid4()
    conn_mgr.register(member_id, mock_ws, MemberRole.OBSERVER)
    conn_mgr.update_role(member_id, MemberRole.SENSOR)
    assert conn_mgr.roles[member_id] == MemberRole.SENSOR


async def test_disconnect_member(conn_mgr: ConnectionManager, mock_ws: MagicMock) -> None:
    member_id = uuid.uuid4()
    conn_mgr.register(member_id, mock_ws, MemberRole.OBSERVER)
    await conn_mgr.disconnect(member_id)
    mock_ws.close.assert_called_once()
    assert member_id not in conn_mgr.connections


def test_connected_count(conn_mgr: ConnectionManager) -> None:
    conn_mgr.register(uuid.uuid4(), MagicMock(), MemberRole.OBSERVER)
    conn_mgr.register(uuid.uuid4(), MagicMock(), MemberRole.SENSOR)
    assert conn_mgr.connected_count == 2


def test_stale_member_ids(conn_mgr: ConnectionManager, mock_ws: MagicMock) -> None:
    stale_id = uuid.uuid4()
    fresh_id = uuid.uuid4()
    conn_mgr.register(stale_id, mock_ws, MemberRole.OBSERVER)
    conn_mgr.register(fresh_id, MagicMock(), MemberRole.SENSOR)
    conn_mgr.mark_seen(stale_id, seen_at=10.0)
    conn_mgr.mark_seen(fresh_id, seen_at=50.0)

    stale = conn_mgr.stale_member_ids(15.0, now=60.0)

    assert stale == [stale_id]
