from __future__ import annotations

import pytest

from osk.models import Member, MemberRole, MemberStatus, Operation
from osk.operation import OperationManager


@pytest.fixture
def op_manager(mock_db):
    return OperationManager(db=mock_db)


async def test_create_operation(op_manager: OperationManager) -> None:
    op = await op_manager.create("Test Op")
    assert op.name == "Test Op"
    assert op.token is not None
    assert op.coordinator_token is not None
    op_manager.db.insert_operation.assert_called_once()


async def test_add_member(op_manager: OperationManager) -> None:
    op = await op_manager.create("Test Op")
    member = await op_manager.add_member(op.id, "Jay")
    assert member.name == "Jay"
    assert member.role == MemberRole.OBSERVER
    assert member.reconnect_token
    assert member.last_seen_at == member.connected_at
    assert member.id in op_manager.members


async def test_promote_member(op_manager: OperationManager) -> None:
    op = await op_manager.create("Test Op")
    member = await op_manager.add_member(op.id, "Jay")
    await op_manager.promote_member(member.id)
    assert op_manager.members[member.id].role == MemberRole.SENSOR
    op_manager.db.update_member_role.assert_called_once()


async def test_demote_member(op_manager: OperationManager) -> None:
    op = await op_manager.create("Test Op")
    member = await op_manager.add_member(op.id, "Jay")
    await op_manager.promote_member(member.id)
    await op_manager.demote_member(member.id)
    assert op_manager.members[member.id].role == MemberRole.OBSERVER


async def test_kick_member(op_manager: OperationManager) -> None:
    op = await op_manager.create("Test Op")
    member = await op_manager.add_member(op.id, "Jay")
    await op_manager.kick_member(member.id)
    assert op_manager.members[member.id].status == MemberStatus.KICKED


async def test_rotate_token(op_manager: OperationManager) -> None:
    op = await op_manager.create("Test Op")
    old_token = op.token
    new_token = await op_manager.rotate_token(op.id)
    assert new_token != old_token
    assert op_manager.operation.token == new_token


async def test_validate_token(op_manager: OperationManager) -> None:
    op = await op_manager.create("Test Op")
    assert op_manager.validate_token(op.token) is True
    assert op_manager.validate_token("wrong-token") is False


async def test_validate_coordinator_token(op_manager: OperationManager) -> None:
    op = await op_manager.create("Test Op")
    assert op_manager.validate_coordinator_token(op.coordinator_token) is True
    assert op_manager.validate_coordinator_token("wrong-token") is False


async def test_get_sensor_count(op_manager: OperationManager) -> None:
    op = await op_manager.create("Test Op")
    await op_manager.add_member(op.id, "Jay")
    member = await op_manager.add_member(op.id, "Mika")
    await op_manager.promote_member(member.id)
    assert op_manager.get_sensor_count() == 1


async def test_update_member_gps(op_manager: OperationManager) -> None:
    op = await op_manager.create("Test Op")
    member = await op_manager.add_member(op.id, "Jay")
    await op_manager.update_member_gps(member.id, 39.75, -104.99)
    assert op_manager.members[member.id].latitude == 39.75
    assert op_manager.members[member.id].longitude == -104.99
    op_manager.db.update_member_heartbeat.assert_awaited_once()


async def test_touch_member_heartbeat(op_manager: OperationManager) -> None:
    op = await op_manager.create("Test Op")
    member = await op_manager.add_member(op.id, "Jay")

    await op_manager.touch_member_heartbeat(member.id)

    assert op_manager.members[member.id].last_seen_at is not None
    op_manager.db.update_member_heartbeat.assert_awaited_once()


async def test_mark_member_disconnected(op_manager: OperationManager) -> None:
    op = await op_manager.create("Test Op")
    member = await op_manager.add_member(op.id, "Jay")
    await op_manager.mark_disconnected(member.id)
    assert op_manager.members[member.id].status == MemberStatus.DISCONNECTED


async def test_resume_member(op_manager: OperationManager) -> None:
    op = await op_manager.create("Test Op")
    member = await op_manager.add_member(op.id, "Jay")
    await op_manager.mark_disconnected(member.id)

    resumed = await op_manager.resume_member(op.id, member.id, member.reconnect_token)

    assert resumed.id == member.id
    assert resumed.status == MemberStatus.CONNECTED
    assert resumed.last_seen_at == resumed.connected_at
    op_manager.db.mark_member_connected.assert_awaited_once()


async def test_resume_member_rejects_wrong_token(op_manager: OperationManager) -> None:
    op = await op_manager.create("Test Op")
    member = await op_manager.add_member(op.id, "Jay")
    with pytest.raises(PermissionError):
        await op_manager.resume_member(op.id, member.id, "wrong-token")


async def test_resume_existing_operation(op_manager: OperationManager) -> None:
    operation = Operation(name="Existing Op")
    resumed_member = Member(name="Jay")
    op_manager.db.get_active_operation.return_value = operation.model_dump()
    op_manager.db.get_members.return_value = [resumed_member.model_dump(mode="json")]

    resumed, did_resume = await op_manager.create_or_resume("New Requested Name")

    assert did_resume is True
    assert resumed.name == "Existing Op"
    assert resumed_member.id in op_manager.members
    op_manager.db.mark_members_disconnected.assert_awaited_once_with(operation.id)


async def test_create_or_resume_creates_new_operation_when_none_active(
    op_manager: OperationManager,
) -> None:
    created, did_resume = await op_manager.create_or_resume("Fresh Op")
    assert did_resume is False
    assert created.name == "Fresh Op"


async def test_stop_operation(op_manager: OperationManager) -> None:
    op = await op_manager.create("Test Op")
    await op_manager.stop()
    assert op.stopped_at is not None
    op_manager.db.mark_operation_stopped.assert_awaited_once()
