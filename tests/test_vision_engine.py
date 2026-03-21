from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from osk.fake_intelligence import FakeVisionAnalyzer
from osk.frame_ingest import FrameIngest
from osk.intelligence_contracts import FrameSample, IngestPriority, IngestSource, ObservationKind
from osk.models import MemberRole
from osk.vision_engine import VisionWorker


def _source(
    *,
    member_role: MemberRole = MemberRole.SENSOR,
    priority: IngestPriority = IngestPriority.SENSOR,
) -> IngestSource:
    return IngestSource(
        member_id=uuid4(),
        member_role=member_role,
        priority=priority,
        received_at=datetime.now(timezone.utc),
    )


async def _wait_for(condition, *, timeout_seconds: float = 0.5) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        if condition():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("Timed out waiting for condition.")


async def test_vision_worker_processes_frame_and_emits_callback() -> None:
    ingest = FrameIngest(max_queue_size=2)
    frame = FrameSample(source=_source(), width=1280, height=720, change_score=0.8)
    observations = []

    async def on_observation(observation) -> None:
        observations.append(observation)

    worker = VisionWorker(
        frame_ingest=ingest,
        vision_analyzer=FakeVisionAnalyzer(
            scripted_results={frame.frame_id: ("Group moving east on foot.", ["group"])}
        ),
        on_observation=on_observation,
    )

    await ingest.put(frame)
    processed = await worker.process_next(timeout_seconds=0.05)

    assert processed is True
    assert len(observations) == 1
    assert observations[0].kind == ObservationKind.VISION
    assert observations[0].summary == "Group moving east on foot."
    assert worker.metrics.processed_items == 1
    assert worker.metrics.emitted_observations == 1
    assert worker.metrics.average_latency_ms is not None


async def test_vision_worker_tracks_empty_results() -> None:
    ingest = FrameIngest(max_queue_size=2)
    frame = FrameSample(source=_source(), width=1280, height=720, change_score=0.6)
    worker = VisionWorker(
        frame_ingest=ingest,
        vision_analyzer=FakeVisionAnalyzer(dropped_frame_ids={frame.frame_id}),
    )

    await ingest.put(frame)
    processed = await worker.process_next(timeout_seconds=0.05)

    assert processed is True
    assert worker.metrics.processed_items == 1
    assert worker.metrics.empty_results == 1
    assert worker.metrics.emitted_observations == 0


async def test_vision_worker_background_loop_starts_and_stops() -> None:
    ingest = FrameIngest(max_queue_size=2)
    frame = FrameSample(source=_source(), width=1280, height=720, change_score=0.9)
    observations = []

    async def on_observation(observation) -> None:
        observations.append(observation)

    worker = VisionWorker(
        frame_ingest=ingest,
        vision_analyzer=FakeVisionAnalyzer(
            scripted_results={
                frame.frame_id: ("Mounted officers near the south curb.", ["mounted"])
            }
        ),
        on_observation=on_observation,
        poll_interval_seconds=0.01,
    )

    task = worker.start()
    await ingest.put(frame)
    await _wait_for(lambda: worker.metrics.emitted_observations == 1)
    await worker.stop()
    await asyncio.wait_for(task, timeout=0.2)

    assert len(observations) == 1
    assert worker.running is False


async def test_vision_worker_exits_when_queue_is_closed() -> None:
    ingest = FrameIngest(max_queue_size=1)
    worker = VisionWorker(
        frame_ingest=ingest,
        vision_analyzer=FakeVisionAnalyzer(),
        poll_interval_seconds=0.01,
    )

    task = worker.start()
    await ingest.stop()
    await asyncio.wait_for(task, timeout=0.2)

    assert worker.running is False


async def test_vision_worker_records_errors() -> None:
    class FailingVisionAnalyzer:
        async def analyze(self, frame: FrameSample):  # pragma: no cover - exercised in test
            raise RuntimeError(f"bad frame {frame.frame_id}")

    ingest = FrameIngest(max_queue_size=2)
    frame = FrameSample(source=_source(), width=1280, height=720, change_score=0.7)
    worker = VisionWorker(
        frame_ingest=ingest,
        vision_analyzer=FailingVisionAnalyzer(),
    )

    await ingest.put(frame)
    processed = await worker.process_next(timeout_seconds=0.05)

    assert processed is True
    assert worker.metrics.processed_items == 1
    assert worker.metrics.errors == 1
    assert "bad frame" in str(worker.metrics.last_error)
