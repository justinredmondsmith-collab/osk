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
            self.operation.coordinator_token,
            self.operation.started_at,
        )
        await self.db.insert_audit_event(
            self.operation.id,
            "system",
            "operation_created",
            details={"name": self.operation.name},
        )
        logger.info("Created operation %s (%s)", self.operation.name, self.operation.id)
        return self.operation

    async def create_or_resume(self, requested_name: str) -> tuple[Operation, bool]:
        active_operation = await self.db.get_active_operation()
        if active_operation is None:
            return await self.create(requested_name), False

        self.operation = Operation.model_validate(active_operation)
        await self.db.mark_members_disconnected(self.operation.id)
        self.members.clear()

        for row in await self.db.get_members(self.operation.id):
            member_data = dict(row)
            if member_data.get("status") == MemberStatus.CONNECTED.value:
                member_data["status"] = MemberStatus.DISCONNECTED.value
            member = Member.model_validate(member_data)
            self.members[member.id] = member

        await self.db.insert_audit_event(
            self.operation.id,
            "system",
            "operation_resumed",
            details={"requested_name": requested_name, "resumed_name": self.operation.name},
        )

        logger.info(
            "Resumed operation %s (%s); requested start name was %r",
            self.operation.name,
            self.operation.id,
            requested_name,
        )
        return self.operation, True

    def validate_token(self, token: str) -> bool:
        operation = self.operation
        if operation is None:
            return False
        return secrets.compare_digest(operation.token, token)

    def validate_coordinator_token(self, token: str) -> bool:
        operation = self.operation
        if operation is None:
            return False
        return secrets.compare_digest(operation.coordinator_token, token)

    async def rotate_token(self, op_id: uuid.UUID) -> str:
        operation = self._require_operation()
        if operation.id != op_id:
            raise ValueError(f"Operation id mismatch: expected {operation.id}, got {op_id}")

        new_token = secrets.token_urlsafe(32)
        operation.token = new_token
        await self.db.update_operation_token(op_id, new_token)
        logger.info("Rotated token for operation %s", op_id)
        return new_token

    async def stop(self) -> None:
        operation = self._require_operation()
        if operation.stopped_at is not None:
            return

        stopped_at = datetime.now(timezone.utc)
        operation.stopped_at = stopped_at
        await self.db.mark_operation_stopped(operation.id, stopped_at)
        await self.db.insert_audit_event(
            operation.id,
            "system",
            "operation_stopped",
            details={"stopped_at": stopped_at.isoformat()},
        )
        logger.info("Marked operation %s as stopped", operation.id)

    async def add_member(self, operation_id: uuid.UUID, name: str) -> Member:
        operation = self._require_operation()
        if operation.id != operation_id:
            raise ValueError(f"Operation id mismatch: expected {operation.id}, got {operation_id}")

        member = Member(name=name, role=MemberRole.OBSERVER)
        member.last_seen_at = member.connected_at
        self.members[member.id] = member
        await self.db.insert_member(
            member.id,
            operation_id,
            member.name,
            member.role,
            member.reconnect_token,
            member.connected_at,
            member.last_seen_at,
        )
        await self.db.insert_audit_event(
            operation_id,
            "member",
            "member_joined",
            actor_member_id=member.id,
            details={"name": member.name, "role": member.role.value},
        )
        logger.info("Member joined: %s (%s)", member.name, member.id)
        return member

    async def resume_member(
        self,
        operation_id: uuid.UUID,
        member_id: uuid.UUID,
        reconnect_token: str,
    ) -> Member:
        operation = self._require_operation()
        if operation.id != operation_id:
            raise ValueError(f"Operation id mismatch: expected {operation.id}, got {operation_id}")

        member = self._require_member(member_id)
        if member.status == MemberStatus.KICKED:
            raise PermissionError(f"Member {member_id} is kicked and cannot reconnect.")
        if not secrets.compare_digest(member.reconnect_token, reconnect_token):
            raise PermissionError(f"Reconnect token mismatch for member {member_id}.")

        connected_at = datetime.now(timezone.utc)
        member.status = MemberStatus.CONNECTED
        member.connected_at = connected_at
        member.last_seen_at = connected_at
        await self.db.mark_member_connected(member_id, connected_at)
        await self.db.insert_audit_event(
            operation.id,
            "member",
            "member_reconnected",
            actor_member_id=member.id,
            details={"name": member.name, "role": member.role.value},
        )
        logger.info("Member resumed: %s (%s)", member.name, member.id)
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
        if member.status == MemberStatus.DISCONNECTED:
            return
        member.status = MemberStatus.DISCONNECTED
        await self.db.update_member_status(member_id, MemberStatus.DISCONNECTED.value)
        await self.db.insert_audit_event(
            self._require_operation().id,
            "member",
            "member_disconnected",
            actor_member_id=member.id,
            details={"name": member.name, "role": member.role.value},
        )

    async def update_member_gps(self, member_id: uuid.UUID, lat: float, lon: float) -> None:
        member = self._require_member(member_id)
        member.latitude = lat
        member.longitude = lon
        member.last_gps_at = datetime.now(timezone.utc)
        member.last_seen_at = member.last_gps_at
        await self.db.update_member_heartbeat(member_id, member.last_seen_at)
        await self.db.update_member_gps(member_id, lat, lon)

    async def touch_member_heartbeat(self, member_id: uuid.UUID) -> None:
        member = self._require_member(member_id)
        member.last_seen_at = datetime.now(timezone.utc)
        await self.db.update_member_heartbeat(member_id, member.last_seen_at)

    def get_sensor_count(self) -> int:
        return sum(
            1
            for member in self.members.values()
            if member.role == MemberRole.SENSOR and member.status == MemberStatus.CONNECTED
        )

    def get_member_list(self) -> list[dict]:
        return [member.model_dump(mode="json") for member in self.members.values()]
