from __future__ import annotations

import asyncio
import subprocess
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from osk.audio_ingest import AudioIngest
from osk.fake_intelligence import FakeTranscriber
from osk.intelligence_contracts import AudioChunk, IngestPriority, IngestSource, ObservationKind
from osk.models import MemberRole
from osk.transcriber import (
    TranscriptionWorker,
    WhisperTranscriber,
    collapse_repetition_loops,
    decode_audio_chunk,
    normalize_uncertain_tokens,
)


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


def test_normalize_uncertain_tokens_rewrites_placeholder_runs() -> None:
    assert normalize_uncertain_tokens("he said __ something") == "he said [inaudible] something"


def test_collapse_repetition_loops_reduces_obvious_loops() -> None:
    collapsed, changed = collapse_repetition_loops("go go go go go go go go go go go go")
    assert changed is True
    assert collapsed.count("go") < 12


async def test_whisper_transcriber_returns_normalized_result() -> None:
    class MockRuntimeManager:
        def __init__(self) -> None:
            self.calls = 0

        def transcribe_sync(self, audio, **kwargs):
            del audio
            self.calls += 1
            segments = [
                SimpleNamespace(text="crowd __ moving east", avg_logprob=-0.1),
            ]
            info = SimpleNamespace(language="en", language_probability=0.88)
            return segments, info

    chunk = AudioChunk(
        source=_source(),
        duration_ms=500,
        codec="audio/webm",
        payload=b"ignored",
    )
    transcriber = WhisperTranscriber(
        runtime_manager=MockRuntimeManager(),
        decoder=lambda _: object(),
    )

    result = await transcriber.transcribe(chunk)

    assert result is not None
    assert result.adapter == "whisper-local"
    assert result.text == "crowd [inaudible] moving east"
    assert result.language == "en"
    assert 0.0 <= result.confidence <= 1.0


async def test_whisper_transcriber_drops_duplicate_segments() -> None:
    class MockRuntimeManager:
        def transcribe_sync(self, audio, **kwargs):
            del audio, kwargs
            segments = [
                SimpleNamespace(text="stay together", avg_logprob=-0.2),
                SimpleNamespace(text="stay together", avg_logprob=-0.2),
                SimpleNamespace(text="stay together", avg_logprob=-0.2),
            ]
            info = SimpleNamespace(language="en", language_probability=0.8)
            return segments, info

    chunk = AudioChunk(source=_source(), duration_ms=300, codec="audio/webm", payload=b"payload")
    transcriber = WhisperTranscriber(
        runtime_manager=MockRuntimeManager(),
        decoder=lambda _: object(),
    )

    result = await transcriber.transcribe(chunk)

    assert result is not None
    assert result.text == "stay together stay together"


def test_decode_audio_chunk_uses_ffmpeg_for_compressed_codecs() -> None:
    import numpy as np

    chunk = AudioChunk(
        source=_source(),
        codec="audio/webm;codecs=opus",
        sample_rate_hz=16_000,
        payload=b"webm-bytes",
    )
    pcm = np.array([0.1, -0.2, 0.3], dtype=np.float32).tobytes()

    with (
        patch("osk.transcriber.shutil.which", return_value="/usr/bin/ffmpeg"),
        patch(
            "osk.transcriber.subprocess.run",
            return_value=SimpleNamespace(stdout=pcm, stderr=b""),
        ) as mock_run,
    ):
        audio = decode_audio_chunk(chunk)

    assert np.allclose(audio, np.array([0.1, -0.2, 0.3], dtype=np.float32))
    assert mock_run.call_args.kwargs["input"] == b"webm-bytes"


def test_decode_audio_chunk_requires_ffmpeg_for_compressed_audio() -> None:
    chunk = AudioChunk(
        source=_source(),
        codec="audio/ogg",
        sample_rate_hz=16_000,
        payload=b"ogg-bytes",
    )

    with patch("osk.transcriber.shutil.which", return_value=None):
        try:
            decode_audio_chunk(chunk)
        except RuntimeError as exc:
            assert "ffmpeg" in str(exc)
        else:  # pragma: no cover - assertion guard
            raise AssertionError("Expected RuntimeError when ffmpeg is missing.")


def test_decode_audio_chunk_reports_ffmpeg_decode_failure() -> None:
    chunk = AudioChunk(
        source=_source(),
        codec="audio/mp4",
        sample_rate_hz=16_000,
        payload=b"mp4-bytes",
    )
    error = subprocess.CalledProcessError(
        returncode=1,
        cmd=["ffmpeg"],
        stderr=b"invalid data found",
    )

    with (
        patch("osk.transcriber.shutil.which", return_value="/usr/bin/ffmpeg"),
        patch("osk.transcriber.subprocess.run", side_effect=error),
    ):
        try:
            decode_audio_chunk(chunk)
        except ValueError as exc:
            assert "invalid data found" in str(exc)
        else:  # pragma: no cover - assertion guard
            raise AssertionError("Expected ValueError for ffmpeg decode failure.")
