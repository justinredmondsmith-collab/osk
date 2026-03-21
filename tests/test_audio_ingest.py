from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from osk.audio_ingest import AudioIngest
from osk.fake_intelligence import FakeLocationAnalyzer, FakeTranscriber, FakeVisionAnalyzer
from osk.intelligence_contracts import AudioChunk, IngestPriority, IngestSource, ObservationKind
from osk.intelligence_pipeline import IntelligencePipeline
from osk.models import MemberRole


def _source(
    *,
    member_role: MemberRole,
    priority: IngestPriority,
    member_id=None,
    received_at: datetime | None = None,
) -> IngestSource:
    return IngestSource(
        member_id=member_id or uuid4(),
        member_role=member_role,
        priority=priority,
        received_at=received_at or datetime.now(timezone.utc),
    )


async def test_audio_ingest_returns_chunks_in_priority_order() -> None:
    ingest = AudioIngest(max_queue_size=4)
    low = AudioChunk(
        source=_source(
            member_role=MemberRole.OBSERVER,
            priority=IngestPriority.OBSERVER,
        )
    )
    high = AudioChunk(
        source=_source(
            member_role=MemberRole.SENSOR,
            priority=IngestPriority.SENSOR,
        )
    )

    assert await ingest.put(low) is True
    assert await ingest.put(high) is True

    first = await ingest.get()
    second = await ingest.get()

    assert first == high
    assert second == low


async def test_audio_ingest_evicts_oldest_low_priority_chunk_when_full() -> None:
    ingest = AudioIngest(max_queue_size=2)
    observer_source = _source(
        member_role=MemberRole.OBSERVER,
        priority=IngestPriority.OBSERVER,
        received_at=datetime(2026, 3, 21, 12, 0, tzinfo=timezone.utc),
    )
    late_observer_source = observer_source.model_copy(
        update={"received_at": observer_source.received_at + timedelta(seconds=1)}
    )
    sensor_source = _source(member_role=MemberRole.SENSOR, priority=IngestPriority.SENSOR)
    early = AudioChunk(source=observer_source, payload=b"\x00")
    late = AudioChunk(source=late_observer_source, payload=b"\x01")
    urgent = AudioChunk(source=sensor_source, payload=b"\x02")

    assert await ingest.put(early) is True
    assert await ingest.put(late) is True
    assert await ingest.put(urgent) is True

    first = await ingest.get()
    second = await ingest.get()

    assert first == urgent
    assert second == late
    assert ingest.evicted_chunks == 1


async def test_audio_ingest_rejects_lower_priority_chunk_when_queue_full() -> None:
    ingest = AudioIngest(max_queue_size=1)
    sensor_chunk = AudioChunk(
        source=_source(member_role=MemberRole.SENSOR, priority=IngestPriority.SENSOR)
    )
    observer_chunk = AudioChunk(
        source=_source(member_role=MemberRole.OBSERVER, priority=IngestPriority.OBSERVER)
    )

    assert await ingest.put(sensor_chunk) is True
    assert await ingest.put(observer_chunk) is False

    first = await ingest.get()
    assert first == sensor_chunk
    assert ingest.rejected_chunks == 1


async def test_audio_ingest_tracks_member_depths() -> None:
    ingest = AudioIngest(max_queue_size=4)
    member_one = uuid4()
    member_two = uuid4()

    await ingest.put(
        AudioChunk(
            source=_source(
                member_role=MemberRole.SENSOR,
                priority=IngestPriority.SENSOR,
                member_id=member_one,
            )
        )
    )
    await ingest.put(
        AudioChunk(
            source=_source(
                member_role=MemberRole.OBSERVER,
                priority=IngestPriority.OBSERVER,
                member_id=member_one,
            )
        )
    )
    await ingest.put(
        AudioChunk(
            source=_source(
                member_role=MemberRole.OBSERVER,
                priority=IngestPriority.OBSERVER,
                member_id=member_two,
            )
        )
    )

    assert ingest.member_depth(member_one) == 2
    assert ingest.member_depth(member_two) == 1
    assert ingest.qsize() == 3


async def test_audio_ingest_stop_drains_then_returns_none() -> None:
    ingest = AudioIngest(max_queue_size=2)
    chunk = AudioChunk(
        source=_source(
            member_role=MemberRole.SENSOR,
            priority=IngestPriority.SENSOR,
        )
    )

    await ingest.put(chunk)
    await ingest.stop()

    assert await ingest.get() == chunk
    assert await ingest.get() is None


async def test_audio_ingest_feeds_pipeline() -> None:
    ingest = AudioIngest(max_queue_size=2)
    chunk = AudioChunk(
        source=_source(member_role=MemberRole.SENSOR, priority=IngestPriority.SENSOR),
        duration_ms=750,
    )
    pipeline = IntelligencePipeline(
        transcriber=FakeTranscriber(scripted_text={chunk.chunk_id: "Crowd moving south."}),
        vision_analyzer=FakeVisionAnalyzer(),
        location_analyzer=FakeLocationAnalyzer(),
    )

    await ingest.put(chunk)
    queued = await ingest.get()
    observation = await pipeline.process_audio(queued)

    assert observation is not None
    assert observation.kind == ObservationKind.TRANSCRIPT
    assert observation.summary == "Crowd moving south."
