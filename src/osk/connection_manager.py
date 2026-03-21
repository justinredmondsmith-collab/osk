"""WebSocket connection management with role-based broadcasting."""

from __future__ import annotations

import logging
import time
import uuid

from osk.models import EventSeverity, MemberRole

logger = logging.getLogger(__name__)

ALERT_THRESHOLDS: dict[MemberRole, int] = {
    MemberRole.COORDINATOR: EventSeverity.INFO.level,
    MemberRole.SENSOR: EventSeverity.ADVISORY.level,
    MemberRole.OBSERVER: EventSeverity.CRITICAL.level,
}


class ConnectionManager:
    def __init__(self) -> None:
        self.connections: dict[uuid.UUID, object] = {}
        self.last_seen_monotonic: dict[uuid.UUID, float] = {}
        self.roles: dict[uuid.UUID, MemberRole] = {}

    def register(self, member_id: uuid.UUID, websocket, role: MemberRole) -> None:
        self.connections[member_id] = websocket
        self.mark_seen(member_id)
        self.roles[member_id] = role
        logger.info("Registered connection for %s (%s)", member_id, role.value)

    def unregister(self, member_id: uuid.UUID) -> None:
        self.connections.pop(member_id, None)
        self.last_seen_monotonic.pop(member_id, None)
        self.roles.pop(member_id, None)

    def update_role(self, member_id: uuid.UUID, role: MemberRole) -> None:
        if member_id in self.connections:
            self.roles[member_id] = role

    def mark_seen(self, member_id: uuid.UUID, seen_at: float | None = None) -> None:
        if member_id in self.connections:
            self.last_seen_monotonic[member_id] = (
                seen_at if seen_at is not None else time.monotonic()
            )

    def stale_member_ids(
        self,
        timeout_seconds: float,
        *,
        now: float | None = None,
    ) -> list[uuid.UUID]:
        current_time = now if now is not None else time.monotonic()
        stale: list[uuid.UUID] = []
        for member_id in self.connections:
            last_seen = self.last_seen_monotonic.get(member_id)
            if last_seen is None:
                continue
            if current_time - last_seen >= timeout_seconds:
                stale.append(member_id)
        return stale

    @property
    def connected_count(self) -> int:
        return len(self.connections)

    async def send_to(self, member_id: uuid.UUID, message: dict) -> None:
        websocket = self.connections.get(member_id)
        if websocket is None:
            return
        try:
            await websocket.send_json(message)
        except Exception:
            logger.warning("Failed to send message to %s; dropping connection", member_id)
            self.unregister(member_id)

    async def broadcast(self, message: dict) -> None:
        dead: list[uuid.UUID] = []
        for member_id, websocket in self.connections.items():
            try:
                await websocket.send_json(message)
            except Exception:
                dead.append(member_id)
        for member_id in dead:
            self.unregister(member_id)

    async def broadcast_to_role(self, role: MemberRole, message: dict) -> None:
        dead: list[uuid.UUID] = []
        for member_id, websocket in self.connections.items():
            if self.roles.get(member_id) != role:
                continue
            try:
                await websocket.send_json(message)
            except Exception:
                dead.append(member_id)
        for member_id in dead:
            self.unregister(member_id)

    async def broadcast_alert(self, alert_message: dict) -> None:
        severity_level = EventSeverity(alert_message.get("severity", "info")).level
        dead: list[uuid.UUID] = []
        for member_id, websocket in self.connections.items():
            role = self.roles.get(member_id, MemberRole.OBSERVER)
            if severity_level < ALERT_THRESHOLDS[role]:
                continue
            try:
                await websocket.send_json(alert_message)
            except Exception:
                dead.append(member_id)
        for member_id in dead:
            self.unregister(member_id)

    async def disconnect(self, member_id: uuid.UUID) -> None:
        websocket = self.connections.get(member_id)
        if websocket is not None:
            try:
                await websocket.close()
            except Exception:
                logger.warning("Failed to close websocket cleanly for %s", member_id)
        self.unregister(member_id)
