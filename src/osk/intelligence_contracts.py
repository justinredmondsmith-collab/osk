"""Phase 2 intelligence contracts and normalized ingest/result types."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime, timezone
from enum import Enum, IntEnum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from osk.models import MemberRole


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> uuid.UUID:
    return uuid.uuid4()


class IngestPriority(IntEnum):
    BACKGROUND = 0
    OBSERVER = 10
    SENSOR = 20
    URGENT = 30


class ObservationKind(str, Enum):
    TRANSCRIPT = "transcript"
    VISION = "vision"
    LOCATION = "location"


class IngestSource(BaseModel):
    member_id: uuid.UUID
    member_role: MemberRole
    priority: IngestPriority = IngestPriority.OBSERVER
    received_at: datetime = Field(default_factory=_utcnow)


class AudioChunk(BaseModel):
    chunk_id: uuid.UUID = Field(default_factory=_new_id)
    ingest_key: str | None = None
    source: IngestSource
    codec: str = "audio/webm"
    sample_rate_hz: int = 16000
    duration_ms: int = 0
    sequence_no: int = 0
    payload: bytes = Field(default=b"", exclude=True, repr=False)

    @property
    def payload_size_bytes(self) -> int:
        return len(self.payload)


class FrameSample(BaseModel):
    frame_id: uuid.UUID = Field(default_factory=_new_id)
    ingest_key: str | None = None
    source: IngestSource
    content_type: str = "image/jpeg"
    width: int
    height: int
    change_score: float = 0.0
    sequence_no: int = 0
    captured_at: datetime = Field(default_factory=_utcnow)
    payload: bytes = Field(default=b"", exclude=True, repr=False)

    @property
    def payload_size_bytes(self) -> int:
        return len(self.payload)


class LocationSample(BaseModel):
    source: IngestSource
    latitude: float
    longitude: float
    accuracy_m: float = 0.0
    heading_degrees: float | None = None
    speed_mps: float | None = None
    captured_at: datetime = Field(default_factory=_utcnow)


class TranscriptResult(BaseModel):
    adapter: str
    chunk_id: uuid.UUID
    source_member_id: uuid.UUID
    text: str
    language: str = "en"
    confidence: float = 1.0
    started_at: datetime = Field(default_factory=_utcnow)
    ended_at: datetime = Field(default_factory=_utcnow)


class VisionResult(BaseModel):
    adapter: str
    frame_id: uuid.UUID
    source_member_id: uuid.UUID
    summary: str
    tags: list[str] = Field(default_factory=list)
    confidence: float = 1.0
    captured_at: datetime = Field(default_factory=_utcnow)


class LocationResult(BaseModel):
    adapter: str
    source_member_id: uuid.UUID
    summary: str
    cluster_size: int = 1
    nearby_member_ids: list[uuid.UUID] = Field(default_factory=list)
    risk_score: float = 0.0
    captured_at: datetime = Field(default_factory=_utcnow)


class IntelligenceObservation(BaseModel):
    id: uuid.UUID = Field(default_factory=_new_id)
    kind: ObservationKind
    source_member_id: uuid.UUID
    summary: str
    confidence: float = 1.0
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)


@runtime_checkable
class Transcriber(Protocol):
    async def transcribe(self, chunk: AudioChunk) -> TranscriptResult | None: ...


@runtime_checkable
class VisionAnalyzer(Protocol):
    async def analyze(self, frame: FrameSample) -> VisionResult | None: ...


@runtime_checkable
class LocationAnalyzer(Protocol):
    async def analyze(
        self,
        sample: LocationSample,
        nearby_samples: Sequence[LocationSample] = (),
    ) -> LocationResult | None: ...
