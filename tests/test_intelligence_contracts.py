from __future__ import annotations

import uuid

from osk.intelligence_contracts import (
    AudioChunk,
    FrameSample,
    IngestPriority,
    IngestSource,
    IntelligenceObservation,
    LocationSample,
    ObservationKind,
)
from osk.models import MemberRole


def test_ingest_priority_ordering() -> None:
    assert IngestPriority.BACKGROUND < IngestPriority.OBSERVER
    assert IngestPriority.OBSERVER < IngestPriority.SENSOR
    assert IngestPriority.SENSOR < IngestPriority.URGENT


def test_audio_chunk_excludes_payload_from_dump() -> None:
    chunk = AudioChunk(
        source=IngestSource(
            member_id=uuid.uuid4(),
            member_role=MemberRole.SENSOR,
            priority=IngestPriority.SENSOR,
        ),
        duration_ms=500,
        payload=b"\x00\x01\x02",
    )

    data = chunk.model_dump(mode="json")
    assert "payload" not in data
    assert chunk.payload_size_bytes == 3


def test_frame_sample_excludes_payload_from_dump() -> None:
    frame = FrameSample(
        source=IngestSource(
            member_id=uuid.uuid4(),
            member_role=MemberRole.OBSERVER,
        ),
        width=1280,
        height=720,
        payload=b"\xff\xd8\xff",
    )

    data = frame.model_dump(mode="json")
    assert "payload" not in data
    assert frame.payload_size_bytes == 3


def test_location_sample_defaults() -> None:
    sample = LocationSample(
        source=IngestSource(
            member_id=uuid.uuid4(),
            member_role=MemberRole.OBSERVER,
        ),
        latitude=39.7392,
        longitude=-104.9903,
    )

    assert sample.accuracy_m == 0.0
    assert sample.captured_at is not None


def test_intelligence_observation_defaults() -> None:
    observation = IntelligenceObservation(
        kind=ObservationKind.TRANSCRIPT,
        source_member_id=uuid.uuid4(),
        summary="Police line forming on the east side.",
        confidence=0.92,
    )

    assert observation.id is not None
    assert observation.created_at is not None
    assert observation.details == {}
