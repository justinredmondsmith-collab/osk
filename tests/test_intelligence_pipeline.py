from __future__ import annotations

import uuid

from osk.fake_intelligence import FakeLocationAnalyzer, FakeTranscriber, FakeVisionAnalyzer
from osk.intelligence_contracts import (
    AudioChunk,
    FrameSample,
    IngestPriority,
    IngestSource,
    LocationSample,
    ObservationKind,
)
from osk.intelligence_pipeline import IntelligencePipeline
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


async def test_pipeline_normalizes_audio_results() -> None:
    chunk = AudioChunk(
        source=_source(role=MemberRole.SENSOR, priority=IngestPriority.SENSOR),
        duration_ms=1_000,
    )
    pipeline = IntelligencePipeline(
        transcriber=FakeTranscriber(scripted_text={chunk.chunk_id: "Crowd pushing northbound."}),
        vision_analyzer=FakeVisionAnalyzer(),
        location_analyzer=FakeLocationAnalyzer(),
    )

    observation = await pipeline.process_audio(chunk)

    assert observation is not None
    assert observation.kind == ObservationKind.TRANSCRIPT
    assert observation.summary == "Crowd pushing northbound."
    assert observation.details["adapter"] == "fake-transcriber"
    assert observation.details["chunk_id"] == str(chunk.chunk_id)


async def test_pipeline_skips_dropped_audio_results() -> None:
    chunk = AudioChunk(source=_source(), duration_ms=250)
    pipeline = IntelligencePipeline(
        transcriber=FakeTranscriber(dropped_chunk_ids={chunk.chunk_id}),
        vision_analyzer=FakeVisionAnalyzer(),
        location_analyzer=FakeLocationAnalyzer(),
    )

    observation = await pipeline.process_audio(chunk)

    assert observation is None


async def test_pipeline_normalizes_frame_results() -> None:
    frame = FrameSample(source=_source(role=MemberRole.OBSERVER), width=1280, height=720)
    pipeline = IntelligencePipeline(
        transcriber=FakeTranscriber(),
        vision_analyzer=FakeVisionAnalyzer(
            scripted_results={frame.frame_id: ("Police vehicles in the intersection.", ["vehicle"])}
        ),
        location_analyzer=FakeLocationAnalyzer(),
    )

    observation = await pipeline.process_frame(frame)

    assert observation is not None
    assert observation.kind == ObservationKind.VISION
    assert observation.summary == "Police vehicles in the intersection."
    assert observation.details["tags"] == ["vehicle"]
    assert observation.details["frame_id"] == str(frame.frame_id)


async def test_pipeline_normalizes_location_results() -> None:
    sample = LocationSample(
        source=_source(role=MemberRole.OBSERVER),
        latitude=39.7392,
        longitude=-104.9903,
    )
    nearby = LocationSample(
        source=_source(role=MemberRole.SENSOR),
        latitude=39.7393,
        longitude=-104.9902,
    )
    pipeline = IntelligencePipeline(
        transcriber=FakeTranscriber(),
        vision_analyzer=FakeVisionAnalyzer(),
        location_analyzer=FakeLocationAnalyzer(min_cluster_size=2),
    )

    observation = await pipeline.process_location(sample, [nearby])

    assert observation is not None
    assert observation.kind == ObservationKind.LOCATION
    assert observation.details["cluster_size"] == 2
    assert observation.details["nearby_member_ids"] == [str(nearby.source.member_id)]
