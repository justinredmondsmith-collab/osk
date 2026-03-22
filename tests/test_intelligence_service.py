from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from osk.config import OskConfig
from osk.intelligence_contracts import (
    AudioChunk,
    FrameSample,
    IngestPriority,
    IngestSource,
    LocationSample,
)
from osk.intelligence_service import IntelligenceService, build_transcriber, build_vision_analyzer
from osk.models import EventCategory, EventSeverity, Member, MemberRole, Operation, SitRep
from osk.synthesis import SynthesisDecision


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
    assert snapshot["location"]["backend"] == "fake"
    assert snapshot["location"]["adapter"] == "fake-location"
    assert snapshot["synthesizer"]["backend"] == "heuristic"
    assert snapshot["audio_ingest"]["accepted_chunks"] == 1
    assert snapshot["frame_ingest"]["accepted_frames"] == 1
    assert snapshot["observation_counts"] == {"transcript": 1, "vision": 1}
    assert len(snapshot["recent_observations"]) == 2
    assert isinstance(snapshot["recent_findings"], list)
    assert len(observed) == 2

    await service.stop()

    stopped = service.snapshot()
    assert stopped["running"] is False
    assert stopped["audio_ingest"]["running"] is False
    assert stopped["frame_ingest"]["running"] is False


def test_build_transcriber_selects_whisper_runtime() -> None:
    config = OskConfig(
        transcriber_backend="whisper",
        whisper_model="medium",
        ffmpeg_binary="ffmpeg-custom",
    )
    with (
        patch("osk.intelligence_service.WhisperRuntimeManager") as mock_runtime_manager,
        patch("osk.intelligence_service.WhisperTranscriber") as mock_transcriber,
        patch("osk.intelligence_service.build_audio_decoder") as mock_decoder,
    ):
        runtime_manager = mock_runtime_manager.return_value
        decoder = mock_decoder.return_value
        built = build_transcriber(config)

    mock_runtime_manager.assert_called_once_with(model_size="medium")
    mock_decoder.assert_called_once_with(ffmpeg_binary="ffmpeg-custom")
    mock_transcriber.assert_called_once_with(runtime_manager=runtime_manager, decoder=decoder)
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


async def test_intelligence_service_persists_and_synthesizes_audio_observations() -> None:
    config = OskConfig(
        transcriber_backend="fake",
        vision_backend="fake",
        location_cluster_min_size=2,
        synthesis_cooldown_seconds=60,
    )
    db = MagicMock()
    db.insert_intelligence_observation = AsyncMock()
    db.insert_event = AsyncMock()
    db.insert_alert = AsyncMock()
    db.upsert_synthesis_finding = AsyncMock()
    db.insert_sitrep = AsyncMock()
    conn_manager = MagicMock()
    conn_manager.broadcast_alert = AsyncMock()
    source_member = Member(name="Sensor", role=MemberRole.SENSOR)
    source_member.latitude = 39.75
    source_member.longitude = -104.99
    operation_manager = SimpleNamespace(
        operation=Operation(name="Test Op"),
        members={source_member.id: source_member},
    )
    service = IntelligenceService(
        config=config,
        db=db,
        operation_manager=operation_manager,
        conn_manager=conn_manager,
        transcriber=MagicMock(),
    )
    chunk = AudioChunk(
        source=IngestSource(
            member_id=source_member.id,
            member_role=source_member.role,
            priority=IngestPriority.SENSOR,
            received_at=datetime.now(timezone.utc),
        ),
        duration_ms=500,
    )
    service.transcriber.transcribe = AsyncMock(
        return_value=SimpleNamespace(
            adapter="fake-transcriber",
            chunk_id=chunk.chunk_id,
            source_member_id=source_member.id,
            text="Police officers advancing north.",
            confidence=0.92,
            started_at=chunk.source.received_at,
            ended_at=chunk.source.received_at,
            model_dump=lambda mode="json": {
                "adapter": "fake-transcriber",
                "chunk_id": str(chunk.chunk_id),
                "source_member_id": str(source_member.id),
                "text": "Police officers advancing north.",
                "confidence": 0.92,
            },
        )
    )

    await service.start()
    await service.submit_audio(chunk)
    await _wait_for(lambda: service.transcription_worker.metrics.emitted_observations == 1)
    await service.stop()

    db.insert_intelligence_observation.assert_awaited_once()
    db.insert_event.assert_awaited_once()
    db.insert_alert.assert_awaited_once()
    db.upsert_synthesis_finding.assert_awaited_once()
    conn_manager.broadcast_alert.assert_awaited_once()
    insert_event_call = db.insert_event.await_args.args
    assert insert_event_call[2] == EventSeverity.WARNING
    assert insert_event_call[3] == EventCategory.POLICE_ACTION
    db.insert_sitrep.assert_not_awaited()


async def test_intelligence_service_processes_location_clusters() -> None:
    config = OskConfig(location_cluster_min_size=2)
    service = IntelligenceService(config=config)
    source = _source(member_role=MemberRole.OBSERVER)
    nearby_source = _source(member_role=MemberRole.SENSOR)
    observed = []
    service.observation_sink = observed.append
    nearby_sample = LocationSample(
        source=nearby_source,
        latitude=39.7393,
        longitude=-104.9902,
    )
    sample = LocationSample(
        source=source,
        latitude=39.7392,
        longitude=-104.9903,
    )

    await service.start()
    accepted_first = await service.submit_location(nearby_sample)
    accepted_second = await service.submit_location(sample)
    await service.stop()

    assert accepted_first is False
    assert accepted_second is True
    assert service.location_metrics.emitted_observations == 1
    assert observed[0].kind.value == "location"
    assert observed[0].details["cluster_size"] == 2


async def test_intelligence_service_persists_sitrep_from_synthesizer() -> None:
    db = MagicMock()
    db.insert_intelligence_observation = AsyncMock()
    db.insert_event = AsyncMock()
    db.insert_alert = AsyncMock()
    db.upsert_synthesis_finding = AsyncMock()
    db.insert_sitrep = AsyncMock()
    source_member = Member(name="Observer", role=MemberRole.OBSERVER)
    operation_manager = SimpleNamespace(
        operation=Operation(name="Test Op"),
        members={source_member.id: source_member},
    )

    class Synthesizer:
        async def synthesize(self, observation, *, source_member=None):
            del observation, source_member
            return SynthesisDecision(
                sitrep=SitRep(
                    id=uuid4(),
                    text="Recent updates: police action x1.",
                    trend="active",
                )
            )

        def status(self) -> dict[str, object]:
            return {"backend": "test"}

    transcriber = MagicMock()
    chunk = AudioChunk(
        source=IngestSource(
            member_id=source_member.id,
            member_role=source_member.role,
            priority=IngestPriority.OBSERVER,
            received_at=datetime.now(timezone.utc),
        ),
        duration_ms=250,
    )
    transcriber.transcribe = AsyncMock(
        return_value=SimpleNamespace(
            adapter="fake-transcriber",
            chunk_id=chunk.chunk_id,
            source_member_id=source_member.id,
            text="Police staging nearby.",
            confidence=0.8,
            started_at=chunk.source.received_at,
            ended_at=chunk.source.received_at,
            model_dump=lambda mode="json": {
                "adapter": "fake-transcriber",
                "chunk_id": str(chunk.chunk_id),
                "source_member_id": str(source_member.id),
                "text": "Police staging nearby.",
                "confidence": 0.8,
            },
        )
    )
    service = IntelligenceService(
        config=OskConfig(),
        db=db,
        operation_manager=operation_manager,
        synthesizer=Synthesizer(),
        transcriber=transcriber,
    )

    await service.start()
    await service.submit_audio(chunk)
    await _wait_for(lambda: service.transcription_worker.metrics.emitted_observations == 1)
    await service.stop()

    db.insert_sitrep.assert_awaited_once()
    db.upsert_synthesis_finding.assert_not_awaited()


async def test_intelligence_service_dedupes_audio_by_ingest_key() -> None:
    config = OskConfig(transcriber_backend="fake")
    service = IntelligenceService(config=config)
    chunk = AudioChunk(
        ingest_key="member-1:chunk-7",
        source=_source(),
        duration_ms=250,
    )

    first = await service.submit_audio(chunk)
    second = await service.submit_audio(chunk)

    assert first.accepted is True
    assert first.duplicate is False
    assert second.accepted is True
    assert second.duplicate is True
    assert service.snapshot()["audio_ingest"]["duplicate_submissions"] == 1
