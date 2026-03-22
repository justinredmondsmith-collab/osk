"""Core Pydantic models for Osk."""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> uuid.UUID:
    return uuid.uuid4()


def _new_token() -> str:
    return secrets.token_urlsafe(32)


class MemberRole(str, Enum):
    OBSERVER = "observer"
    SENSOR = "sensor"
    COORDINATOR = "coordinator"


class MemberStatus(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    KICKED = "kicked"


class StreamType(str, Enum):
    AUDIO = "audio"
    VIDEO = "video"


class StreamStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    ENDED = "ended"


class EventSeverity(str, Enum):
    INFO = "info"
    ADVISORY = "advisory"
    WARNING = "warning"
    CRITICAL = "critical"

    @property
    def level(self) -> int:
        return {
            self.INFO.value: 0,
            self.ADVISORY.value: 1,
            self.WARNING.value: 2,
            self.CRITICAL.value: 3,
        }[self.value]


class EventCategory(str, Enum):
    CROWD_MOVEMENT = "crowd_movement"
    POLICE_ACTION = "police_action"
    BLOCKED_ROUTE = "blocked_route"
    ESCALATION = "escalation"
    MEDICAL = "medical"
    WEATHER = "weather"
    COMMUNITY = "community"
    MANUAL_REPORT = "manual_report"
    MEMBER_BUFFER = "member_buffer"


class FindingStatus(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class MemberBufferStatus(BaseModel):
    pending_count: int = 0
    manual_pending_count: int = 0
    sensor_pending_count: int = 0
    report_pending_count: int = 0
    audio_pending_count: int = 0
    frame_pending_count: int = 0
    in_flight: bool = False
    network: str = "online"
    last_error: str | None = None
    oldest_pending_at: datetime | None = None
    updated_at: datetime = Field(default_factory=_utcnow)


class Operation(BaseModel):
    id: uuid.UUID = Field(default_factory=_new_id)
    name: str
    token: str = Field(default_factory=_new_token)
    coordinator_token: str = Field(default_factory=_new_token)
    started_at: datetime = Field(default_factory=_utcnow)
    stopped_at: datetime | None = None


class Member(BaseModel):
    id: uuid.UUID = Field(default_factory=_new_id)
    name: str
    role: MemberRole = MemberRole.OBSERVER
    status: MemberStatus = MemberStatus.CONNECTED
    reconnect_token: str = Field(default_factory=_new_token, exclude=True)
    latitude: float | None = None
    longitude: float | None = None
    last_gps_at: datetime | None = None
    connected_at: datetime = Field(default_factory=_utcnow)
    last_seen_at: datetime = Field(default_factory=_utcnow)
    buffer_status: MemberBufferStatus = Field(default_factory=MemberBufferStatus)


class Stream(BaseModel):
    id: uuid.UUID = Field(default_factory=_new_id)
    member_id: uuid.UUID
    stream_type: StreamType
    status: StreamStatus = StreamStatus.ACTIVE
    started_at: datetime = Field(default_factory=_utcnow)
    ended_at: datetime | None = None


class Event(BaseModel):
    id: uuid.UUID = Field(default_factory=_new_id)
    severity: EventSeverity
    category: EventCategory
    text: str
    source_member_id: uuid.UUID | None = None
    latitude: float | None = None
    longitude: float | None = None
    timestamp: datetime = Field(default_factory=_utcnow)


class Alert(BaseModel):
    id: uuid.UUID = Field(default_factory=_new_id)
    event_id: uuid.UUID
    severity: EventSeverity
    category: EventCategory
    text: str
    timestamp: datetime = Field(default_factory=_utcnow)


class Pin(BaseModel):
    id: uuid.UUID = Field(default_factory=_new_id)
    event_id: uuid.UUID
    pinned_by: uuid.UUID
    pinned_at: datetime = Field(default_factory=_utcnow)


class SitRep(BaseModel):
    id: uuid.UUID = Field(default_factory=_new_id)
    text: str
    trend: str
    timestamp: datetime = Field(default_factory=_utcnow)


class SynthesisFinding(BaseModel):
    id: uuid.UUID = Field(default_factory=_new_id)
    signature: str
    category: EventCategory
    severity: EventSeverity
    title: str
    summary: str
    status: FindingStatus = FindingStatus.OPEN
    corroborated: bool = False
    source_count: int = 1
    signal_count: int = 1
    observation_count: int = 1
    first_seen_at: datetime = Field(default_factory=_utcnow)
    last_seen_at: datetime = Field(default_factory=_utcnow)
    status_updated_at: datetime = Field(default_factory=_utcnow)
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None
    notes_count: int = 0
    latest_observation_id: uuid.UUID | None = None
    latest_event_id: uuid.UUID | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class FindingNote(BaseModel):
    id: uuid.UUID = Field(default_factory=_new_id)
    operation_id: uuid.UUID
    finding_id: uuid.UUID
    author_type: str = "coordinator"
    text: str
    created_at: datetime = Field(default_factory=_utcnow)


class AuditEvent(BaseModel):
    id: uuid.UUID = Field(default_factory=_new_id)
    operation_id: uuid.UUID
    actor_member_id: uuid.UUID | None = None
    actor_type: str
    action: str
    details: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=_utcnow)
