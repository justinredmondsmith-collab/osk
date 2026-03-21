"""Operation lifecycle management."""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timezone

from osk.models import Member, MemberRole, MemberStatus, Operation

logger = logging.getLogger(__name__)


class OperationManager:
    def __init__(self, db) -> None:
        self.db = db
        self.operation: Operation | None = None
        self.members: dict[uuid.UUID, Member] = {}

    def _require_operation(self) -> Operation:
        if self.operation is None:
            raise RuntimeError("No active operation.")
        return self.operation

    def _require_member(self, member_id: uuid.UUID) -> Member:
        try:
            return self.members[member_id]
        except KeyError as exc:
            raise KeyError(f"Unknown member: {member_id}") from exc

    async def create(self, name: str) -> Operation:
        self.operation = Operation(name=name)
        self.members.clear()
        await self.db.insert_operation(
            self.operation.id,
            self.operation.name,
            self.operation.token,
        )
        logger.info("Created operation %s (%s)", self.operation.name, self.operation.id)
        return self.operation

    def validate_token(self, token: str) -> bool:
        operation = self.operation
        if operation is None:
            return False
        return secrets.compare_digest(operation.token, token)

    async def rotate_token(self, op_id: uuid.UUID) -> str:
        operation = self._require_operation()
        if operation.id != op_id:
            raise ValueError(f"Operation id mismatch: expected {operation.id}, got {op_id}")

        new_token = secrets.token_urlsafe(32)
        operation.token = new_token
        await self.db.update_operation_token(op_id, new_token)
        logger.info("Rotated token for operation %s", op_id)
        return new_token

    async def add_member(self, operation_id: uuid.UUID, name: str) -> Member:
        operation = self._require_operation()
        if operation.id != operation_id:
            raise ValueError(f"Operation id mismatch: expected {operation.id}, got {operation_id}")

        member = Member(name=name, role=MemberRole.OBSERVER)
        self.members[member.id] = member
        await self.db.insert_member(member.id, operation_id, member.name, member.role)
        logger.info("Member joined: %s (%s)", member.name, member.id)
        return member

    async def promote_member(self, member_id: uuid.UUID) -> None:
        member = self._require_member(member_id)
        member.role = MemberRole.SENSOR
        await self.db.update_member_role(member_id, MemberRole.SENSOR)

    async def demote_member(self, member_id: uuid.UUID) -> None:
        member = self._require_member(member_id)
        member.role = MemberRole.OBSERVER
        await self.db.update_member_role(member_id, MemberRole.OBSERVER)

    async def kick_member(self, member_id: uuid.UUID) -> None:
        member = self._require_member(member_id)
        member.status = MemberStatus.KICKED
        await self.db.update_member_status(member_id, MemberStatus.KICKED.value)

    async def mark_disconnected(self, member_id: uuid.UUID) -> None:
        member = self._require_member(member_id)
        if member.status == MemberStatus.KICKED:
            return
        member.status = MemberStatus.DISCONNECTED
        await self.db.update_member_status(member_id, MemberStatus.DISCONNECTED.value)

    async def update_member_gps(self, member_id: uuid.UUID, lat: float, lon: float) -> None:
        member = self._require_member(member_id)
        member.latitude = lat
        member.longitude = lon
        member.last_gps_at = datetime.now(timezone.utc)
        await self.db.update_member_gps(member_id, lat, lon)

    def get_sensor_count(self) -> int:
        return sum(
            1
            for member in self.members.values()
            if member.role == MemberRole.SENSOR and member.status == MemberStatus.CONNECTED
        )

    def get_member_list(self) -> list[dict]:
        return [member.model_dump(mode="json") for member in self.members.values()]
