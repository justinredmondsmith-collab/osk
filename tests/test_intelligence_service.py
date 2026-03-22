from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

from osk.config import OskConfig
from osk.intelligence_contracts import AudioChunk, FrameSample, IngestPriority, IngestSource
from osk.intelligence_service import IntelligenceService, build_transcriber, build_vision_analyzer
from osk.models import MemberRole


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


async def test_intelligence_service_processes_audio_and_frames() -> None:
    config = OskConfig(
        transcriber_backend="fake",
        vision_backend="fake",
        intelligence_recent_observation_limit=4,
    )
    observed = []
    service = IntelligenceService(config=config, observation_sink=observed.append)
    chunk = AudioChunk(source=_source(), duration_ms=400)
    frame = FrameSample(
        source=_source(),
        width=1280,
        height=720,
        change_score=0.8,
        payload=b"frame-jpeg",
    )

    await service.start()
    await service.submit_audio(chunk)
    await service.submit_frame(frame)
    await _wait_for(
        lambda: (
            service.transcription_worker.metrics.emitted_observations == 1
            and service.vision_worker.metrics.emitted_observations == 1
        )
    )

    snapshot = service.snapshot()
    assert snapshot["running"] is True
    assert snapshot["transcriber"]["backend"] == "fake"
    assert snapshot["transcriber"]["adapter"] == "fake-transcriber"
    assert snapshot["vision"]["backend"] == "fake"
    assert snapshot["vision"]["adapter"] == "fake-vision"
    assert snapshot["audio_ingest"]["accepted_chunks"] == 1
    assert snapshot["frame_ingest"]["accepted_frames"] == 1
    assert snapshot["observation_counts"] == {"transcript": 1, "vision": 1}
    assert len(snapshot["recent_observations"]) == 2
    assert len(observed) == 2

    await service.stop()

    stopped = service.snapshot()
    assert stopped["running"] is False
    assert stopped["audio_ingest"]["running"] is False
    assert stopped["frame_ingest"]["running"] is False


def test_build_transcriber_selects_whisper_runtime() -> None:
    config = OskConfig(transcriber_backend="whisper", whisper_model="medium")
    with (
        patch("osk.intelligence_service.WhisperRuntimeManager") as mock_runtime_manager,
        patch("osk.intelligence_service.WhisperTranscriber") as mock_transcriber,
    ):
        runtime_manager = mock_runtime_manager.return_value
        built = build_transcriber(config)

    mock_runtime_manager.assert_called_once_with(model_size="medium")
    mock_transcriber.assert_called_once_with(runtime_manager=runtime_manager)
    assert built is mock_transcriber.return_value


def test_build_vision_analyzer_selects_ollama_runtime() -> None:
    config = OskConfig(
        vision_backend="ollama",
        vision_model="llava:test",
        ollama_base_url="http://ollama.internal:11434",
    )
    with patch("osk.intelligence_service.OllamaVisionAnalyzer") as mock_analyzer:
        built = build_vision_analyzer(config)

    mock_analyzer.assert_called_once_with(
        base_url="http://ollama.internal:11434",
        model="llava:test",
    )
    assert built is mock_analyzer.return_value


async def test_intelligence_service_stop_closes_owned_vision_adapter() -> None:
    config = OskConfig()
    vision_analyzer = MagicMock()
    vision_analyzer.close = MagicMock(return_value=None)
    service = IntelligenceService(config=config, vision_analyzer=vision_analyzer)

    await service.start()
    await service.stop()

    vision_analyzer.close.assert_called_once_with()
