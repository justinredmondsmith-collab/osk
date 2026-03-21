from __future__ import annotations

import pytest

from osk.models import MemberRole, MemberStatus
from osk.operation import OperationManager


@pytest.fixture
def op_manager(mock_db):
    return OperationManager(db=mock_db)


async def test_create_operation(op_manager: OperationManager) -> None:
    op = await op_manager.create("Test Op")
    assert op.name == "Test Op"
    assert op.token is not None
    op_manager.db.insert_operation.assert_called_once()


async def test_add_member(op_manager: OperationManager) -> None:
    op = await op_manager.create("Test Op")
    member = await op_manager.add_member(op.id, "Jay")
    assert member.name == "Jay"
    assert member.role == MemberRole.OBSERVER
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


async def test_mark_member_disconnected(op_manager: OperationManager) -> None:
    op = await op_manager.create("Test Op")
    member = await op_manager.add_member(op.id, "Jay")
    await op_manager.mark_disconnected(member.id)
    assert op_manager.members[member.id].status == MemberStatus.DISCONNECTED
