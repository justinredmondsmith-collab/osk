from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from osk.audio_ingest import AudioIngest
from osk.fake_intelligence import FakeTranscriber
from osk.intelligence_contracts import AudioChunk, IngestPriority, IngestSource, ObservationKind
from osk.models import MemberRole
from osk.transcriber import TranscriptionWorker


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


async def test_transcription_worker_processes_chunk_and_emits_callback() -> None:
    ingest = AudioIngest(max_queue_size=2)
    chunk = AudioChunk(source=_source(), duration_ms=500)
    observations = []

    async def on_observation(observation) -> None:
        observations.append(observation)

    worker = TranscriptionWorker(
        audio_ingest=ingest,
        transcriber=FakeTranscriber(
            scripted_text={chunk.chunk_id: "Audio contact near north exit."}
        ),
        on_observation=on_observation,
    )

    await ingest.put(chunk)
    processed = await worker.process_next(timeout_seconds=0.05)

    assert processed is True
    assert len(observations) == 1
    assert observations[0].kind == ObservationKind.TRANSCRIPT
    assert observations[0].summary == "Audio contact near north exit."
    assert worker.metrics.processed_items == 1
    assert worker.metrics.emitted_observations == 1
    assert worker.metrics.average_latency_ms is not None


async def test_transcription_worker_tracks_empty_results() -> None:
    ingest = AudioIngest(max_queue_size=2)
    chunk = AudioChunk(source=_source(), duration_ms=500)
    worker = TranscriptionWorker(
        audio_ingest=ingest,
        transcriber=FakeTranscriber(dropped_chunk_ids={chunk.chunk_id}),
    )

    await ingest.put(chunk)
    processed = await worker.process_next(timeout_seconds=0.05)

    assert processed is True
    assert worker.metrics.processed_items == 1
    assert worker.metrics.empty_results == 1
    assert worker.metrics.emitted_observations == 0


async def test_transcription_worker_background_loop_starts_and_stops() -> None:
    ingest = AudioIngest(max_queue_size=2)
    chunk = AudioChunk(source=_source(), duration_ms=250)
    observations = []

    async def on_observation(observation) -> None:
        observations.append(observation)

    worker = TranscriptionWorker(
        audio_ingest=ingest,
        transcriber=FakeTranscriber(
            scripted_text={chunk.chunk_id: "Background worker transcript."}
        ),
        on_observation=on_observation,
        poll_interval_seconds=0.01,
    )

    task = worker.start()
    await ingest.put(chunk)
    await _wait_for(lambda: worker.metrics.emitted_observations == 1)
    await worker.stop()
    await asyncio.wait_for(task, timeout=0.2)

    assert len(observations) == 1
    assert worker.running is False


async def test_transcription_worker_exits_when_queue_is_closed() -> None:
    ingest = AudioIngest(max_queue_size=1)
    worker = TranscriptionWorker(
        audio_ingest=ingest,
        transcriber=FakeTranscriber(),
        poll_interval_seconds=0.01,
    )

    task = worker.start()
    await ingest.stop()
    await asyncio.wait_for(task, timeout=0.2)

    assert worker.running is False


async def test_transcription_worker_records_errors() -> None:
    class FailingTranscriber:
        async def transcribe(self, chunk: AudioChunk):  # pragma: no cover - exercised in test
            raise RuntimeError(f"bad chunk {chunk.chunk_id}")

    ingest = AudioIngest(max_queue_size=2)
    chunk = AudioChunk(source=_source(), duration_ms=300)
    worker = TranscriptionWorker(
        audio_ingest=ingest,
        transcriber=FailingTranscriber(),
    )

    await ingest.put(chunk)
    processed = await worker.process_next(timeout_seconds=0.05)

    assert processed is True
    assert worker.metrics.processed_items == 1
    assert worker.metrics.errors == 1
    assert "bad chunk" in str(worker.metrics.last_error)
