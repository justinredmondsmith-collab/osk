from __future__ import annotations

import uuid

from osk.fake_intelligence import FakeLocationAnalyzer, FakeTranscriber, FakeVisionAnalyzer
from osk.intelligence_contracts import (
    AudioChunk,
    FrameSample,
    IngestPriority,
    IngestSource,
    LocationSample,
)
from osk.models import MemberRole


def _source(
    *,
    role: MemberRole = MemberRole.OBSERVER,
    priority: IngestPriority = IngestPriority.OBSERVER,
    member_id: uuid.UUID | None = None,
) -> IngestSource:
    return IngestSource(
        member_id=member_id or uuid.uuid4(),
        member_role=role,
        priority=priority,
    )


async def test_fake_transcriber_uses_scripted_text() -> None:
    chunk = AudioChunk(
        source=_source(role=MemberRole.SENSOR, priority=IngestPriority.SENSOR),
        duration_ms=750,
    )
    adapter = FakeTranscriber(
        scripted_text={chunk.chunk_id: "Police line forming near the west exit."}
    )

    result = await adapter.transcribe(chunk)

    assert result is not None
    assert result.adapter == "fake-transcriber"
    assert result.text == "Police line forming near the west exit."
    assert result.source_member_id == chunk.source.member_id


async def test_fake_vision_analyzer_generates_tags() -> None:
    frame = FrameSample(
        source=_source(role=MemberRole.OBSERVER),
        width=1920,
        height=1080,
    )
    adapter = FakeVisionAnalyzer()

    result = await adapter.analyze(frame)

    assert result is not None
    assert result.adapter == "fake-vision"
    assert "simulated" in result.tags
    assert "wide" in result.tags
    assert result.source_member_id == frame.source.member_id


async def test_fake_location_analyzer_detects_nearby_cluster() -> None:
    sample = LocationSample(
        source=_source(role=MemberRole.OBSERVER),
        latitude=39.7392,
        longitude=-104.9903,
    )
    nearby = LocationSample(
        source=_source(role=MemberRole.SENSOR),
        latitude=39.7394,
        longitude=-104.9902,
    )
    far_away = LocationSample(
        source=_source(role=MemberRole.OBSERVER),
        latitude=39.7492,
        longitude=-104.9803,
    )
    adapter = FakeLocationAnalyzer(min_cluster_size=2)

    result = await adapter.analyze(sample, [nearby, far_away])

    assert result is not None
    assert result.adapter == "fake-location"
    assert result.cluster_size == 2
    assert nearby.source.member_id in result.nearby_member_ids
    assert far_away.source.member_id not in result.nearby_member_ids
    assert "cluster" in result.summary.lower()
