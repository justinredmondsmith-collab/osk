from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from osk.fake_intelligence import FakeLocationAnalyzer, FakeTranscriber, FakeVisionAnalyzer
from osk.frame_ingest import FrameIngest
from osk.intelligence_contracts import (
    FrameSample,
    IngestPriority,
    IngestSource,
    ObservationKind,
)
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


def _frame(
    *,
    member_role: MemberRole,
    priority: IngestPriority,
    member_id=None,
    captured_at: datetime | None = None,
    change_score: float = 0.1,
    payload: bytes = b"jpeg",
    width: int = 1280,
    height: int = 720,
) -> FrameSample:
    source = _source(
        member_role=member_role,
        priority=priority,
        member_id=member_id,
        received_at=captured_at,
    )
    return FrameSample(
        source=source,
        width=width,
        height=height,
        change_score=change_score,
        captured_at=captured_at or datetime.now(timezone.utc),
        payload=payload,
    )


async def test_frame_ingest_returns_high_change_frames_first() -> None:
    ingest = FrameIngest(max_queue_size=4)
    baseline = _frame(
        member_role=MemberRole.OBSERVER,
        priority=IngestPriority.OBSERVER,
        change_score=0.2,
    )
    high_change = _frame(
        member_role=MemberRole.SENSOR,
        priority=IngestPriority.SENSOR,
        change_score=0.9,
    )

    assert await ingest.put(baseline) is True
    assert await ingest.put(high_change) is True

    first = await ingest.get()
    second = await ingest.get()

    assert first == high_change
    assert second == baseline


async def test_frame_ingest_deduplicates_low_change_near_identical_frames() -> None:
    ingest = FrameIngest(dedupe_window_seconds=2.0, dedupe_change_threshold=0.2)
    member_id = uuid4()
    started_at = datetime(2026, 3, 21, 12, 0, tzinfo=timezone.utc)
    first = _frame(
        member_role=MemberRole.SENSOR,
        priority=IngestPriority.SENSOR,
        member_id=member_id,
        captured_at=started_at,
        change_score=0.1,
        payload=b"same-frame",
    )
    duplicate = _frame(
        member_role=MemberRole.SENSOR,
        priority=IngestPriority.SENSOR,
        member_id=member_id,
        captured_at=started_at + timedelta(seconds=1),
        change_score=0.1,
        payload=b"same-frame",
    )

    assert await ingest.put(first) is True
    assert await ingest.put(duplicate) is False

    assert ingest.qsize() == 1
    assert ingest.duplicate_frames == 1


async def test_frame_ingest_enforces_per_member_depth_with_better_frame_replacement() -> None:
    ingest = FrameIngest(max_queue_size=5, max_queue_depth_per_member=2)
    member_id = uuid4()
    early = _frame(
        member_role=MemberRole.SENSOR,
        priority=IngestPriority.SENSOR,
        member_id=member_id,
        change_score=0.2,
        payload=b"early",
    )
    mid = _frame(
        member_role=MemberRole.SENSOR,
        priority=IngestPriority.SENSOR,
        member_id=member_id,
        change_score=0.5,
        payload=b"mid",
    )
    late = _frame(
        member_role=MemberRole.SENSOR,
        priority=IngestPriority.SENSOR,
        member_id=member_id,
        change_score=0.9,
        payload=b"late",
    )

    assert await ingest.put(early) is True
    assert await ingest.put(mid) is True
    assert await ingest.put(late) is True

    first = await ingest.get()
    second = await ingest.get()

    assert first == late
    assert second == mid
    assert ingest.evicted_frames == 1


async def test_frame_ingest_rate_limits_observers() -> None:
    ingest = FrameIngest(observer_min_interval_seconds=2.0)
    member_id = uuid4()
    started_at = datetime(2026, 3, 21, 12, 0, tzinfo=timezone.utc)
    first = _frame(
        member_role=MemberRole.OBSERVER,
        priority=IngestPriority.OBSERVER,
        member_id=member_id,
        captured_at=started_at,
        change_score=0.4,
        payload=b"observer-one",
    )
    second = _frame(
        member_role=MemberRole.OBSERVER,
        priority=IngestPriority.OBSERVER,
        member_id=member_id,
        captured_at=started_at + timedelta(seconds=1),
        change_score=0.8,
        payload=b"observer-two",
    )

    assert await ingest.put(first) is True
    assert await ingest.put(second) is False
    assert ingest.rate_limited_frames == 1
    assert ingest.qsize() == 1


async def test_frame_ingest_stop_drains_then_returns_none() -> None:
    ingest = FrameIngest(max_queue_size=2)
    frame = _frame(
        member_role=MemberRole.SENSOR,
        priority=IngestPriority.SENSOR,
        change_score=0.8,
        payload=b"sensor-frame",
    )

    await ingest.put(frame)
    await ingest.stop()

    assert await ingest.get() == frame
    assert await ingest.get() is None


async def test_frame_ingest_feeds_pipeline() -> None:
    ingest = FrameIngest(max_queue_size=2)
    frame = _frame(
        member_role=MemberRole.SENSOR,
        priority=IngestPriority.SENSOR,
        change_score=0.95,
        payload=b"vision",
    )
    pipeline = IntelligencePipeline(
        transcriber=FakeTranscriber(),
        vision_analyzer=FakeVisionAnalyzer(
            scripted_results={frame.frame_id: ("Police van near the east curb.", ["vehicle"])}
        ),
        location_analyzer=FakeLocationAnalyzer(),
    )

    await ingest.put(frame)
    queued = await ingest.get()
    observation = await pipeline.process_frame(queued)

    assert observation is not None
    assert observation.kind == ObservationKind.VISION
    assert observation.summary == "Police van near the east curb."
