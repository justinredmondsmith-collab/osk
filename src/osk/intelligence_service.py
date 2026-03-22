"""Coordinator-owned service for Phase 2 ingest, persistence, and synthesis."""

from __future__ import annotations

import inspect
import logging
import time
from collections import Counter, deque
from collections.abc import Awaitable, Callable
from datetime import timezone
from typing import Any

from osk.audio_ingest import AudioIngest
from osk.config import OskConfig
from osk.fake_intelligence import FakeLocationAnalyzer, FakeTranscriber, FakeVisionAnalyzer
from osk.frame_ingest import FrameIngest
from osk.intelligence_contracts import (
    AudioChunk,
    FrameSample,
    IntelligenceObservation,
    LocationSample,
    ObservationKind,
)
from osk.intelligence_pipeline import build_observation
from osk.synthesis import HeuristicObservationSynthesizer
from osk.transcriber import TranscriptionWorker, WhisperTranscriber
from osk.vision_engine import OllamaVisionAnalyzer, VisionWorker
from osk.whisper_runtime import WhisperRuntimeManager
from osk.worker_runtime import ProcessingWorkerMetrics

logger = logging.getLogger(__name__)

ObservationSink = Callable[[IntelligenceObservation], Awaitable[None] | None]


def build_transcriber(config: OskConfig):
    if config.transcriber_backend == "fake":
        return FakeTranscriber()
    return WhisperTranscriber(
        runtime_manager=WhisperRuntimeManager(model_size=config.whisper_model)
    )


def build_vision_analyzer(config: OskConfig):
    if config.vision_backend == "fake":
        return FakeVisionAnalyzer()
    return OllamaVisionAnalyzer(
        base_url=config.ollama_base_url,
        model=config.vision_model,
    )


def build_location_analyzer(config: OskConfig):
    return FakeLocationAnalyzer(
        cluster_radius_m=config.location_cluster_radius_m,
        min_cluster_size=config.location_cluster_min_size,
    )


def build_synthesizer(config: OskConfig):
    return HeuristicObservationSynthesizer(
        cooldown_seconds=config.synthesis_cooldown_seconds,
    )


async def _maybe_close(resource: object) -> None:
    close = getattr(resource, "close", None)
    if close is None:
        return
    result = close()
    if inspect.isawaitable(result):
        await result


def _processing_metrics_snapshot(
    metrics: ProcessingWorkerMetrics,
    *,
    running: bool,
) -> dict[str, object]:
    return {
        "processed_items": metrics.processed_items,
        "emitted_observations": metrics.emitted_observations,
        "empty_results": metrics.empty_results,
        "errors": metrics.errors,
        "last_latency_ms": metrics.last_latency_ms,
        "average_latency_ms": metrics.average_latency_ms,
        "last_error": metrics.last_error,
        "running": running,
    }


class IntelligenceService:
    def __init__(
        self,
        *,
        config: OskConfig,
        observation_sink: ObservationSink | None = None,
        db=None,
        operation_manager=None,
        conn_manager=None,
        synthesizer=None,
        transcriber=None,
        vision_analyzer=None,
        location_analyzer=None,
        audio_ingest: AudioIngest | None = None,
        frame_ingest: FrameIngest | None = None,
    ) -> None:
        self.config = config
        self.db = db
        self.operation_manager = operation_manager
        self.conn_manager = conn_manager
        self.observation_sink = observation_sink
        self.synthesizer = synthesizer or build_synthesizer(config)
        self.transcriber = transcriber or build_transcriber(config)
        self.vision_analyzer = vision_analyzer or build_vision_analyzer(config)
        self.location_analyzer = location_analyzer or build_location_analyzer(config)
        self.audio_ingest = audio_ingest or AudioIngest(max_queue_size=config.audio_queue_size)
        self.frame_ingest = frame_ingest or FrameIngest(
            max_queue_size=config.frame_queue_size,
            max_queue_depth_per_member=config.frame_queue_depth_per_member,
            dedupe_change_threshold=config.frame_change_threshold,
        )
        self._recent_observations: deque[IntelligenceObservation] = deque(
            maxlen=max(1, config.intelligence_recent_observation_limit)
        )
        self._observation_counts: Counter[str] = Counter()
        self._recent_location_samples: dict[Any, LocationSample] = {}
        self._started = False
        self.location_metrics = ProcessingWorkerMetrics()
        self.transcription_worker = TranscriptionWorker(
            audio_ingest=self.audio_ingest,
            transcriber=self.transcriber,
            on_observation=self._handle_observation,
        )
        self.vision_worker = VisionWorker(
            frame_ingest=self.frame_ingest,
            vision_analyzer=self.vision_analyzer,
            on_observation=self._handle_observation,
        )

    @property
    def running(self) -> bool:
        return self._started and (self.transcription_worker.running or self.vision_worker.running)

    async def start(self) -> None:
        if self._started:
            return
        self.audio_ingest.start()
        self.frame_ingest.start()
        self.transcription_worker.start()
        self.vision_worker.start()
        self._started = True
        logger.info(
            "Started intelligence service with transcriber=%s vision=%s location=%s",
            self.config.transcriber_backend,
            self.config.vision_backend,
            self.config.location_backend,
        )

    async def stop(self) -> None:
        if not self._started:
            return
        await self.audio_ingest.stop()
        await self.frame_ingest.stop()
        await self.transcription_worker.stop()
        await self.vision_worker.stop()
        await _maybe_close(self.transcriber)
        await _maybe_close(self.vision_analyzer)
        await _maybe_close(self.location_analyzer)
        await _maybe_close(self.synthesizer)
        self._started = False
        logger.info("Stopped intelligence service")

    async def submit_audio(self, chunk: AudioChunk) -> bool:
        return await self.audio_ingest.put(chunk)

    async def submit_frame(self, frame: FrameSample) -> bool:
        return await self.frame_ingest.put(frame)

    async def submit_location(self, sample: LocationSample) -> bool:
        self._recent_location_samples[sample.source.member_id] = sample
        self._prune_location_samples(sample)
        nearby_samples = self._nearby_location_samples(sample)
        started_at = time.perf_counter()
        self.location_metrics.processed_items += 1
        try:
            result = await self.location_analyzer.analyze(sample, nearby_samples)
            if result is None:
                self.location_metrics.empty_results += 1
                return False

            observation = build_observation(
                kind=ObservationKind.LOCATION,
                source_member_id=sample.source.member_id,
                summary=result.summary,
                confidence=result.risk_score,
                result=result,
            )
            await self._handle_observation(observation)
            self.location_metrics.emitted_observations += 1
            self.location_metrics.last_error = None
            return True
        except Exception as exc:
            self.location_metrics.errors += 1
            self.location_metrics.last_error = str(exc)
            logger.exception("Location processing failed for member %s", sample.source.member_id)
            return False
        finally:
            self.location_metrics.record_latency(started_at)

    def snapshot(self) -> dict[str, object]:
        return {
            "running": self.running,
            "transcriber": self._adapter_snapshot(
                self.transcriber,
                backend=self.config.transcriber_backend,
            ),
            "vision": self._adapter_snapshot(
                self.vision_analyzer,
                backend=self.config.vision_backend,
            ),
            "location": self._adapter_snapshot(
                self.location_analyzer,
                backend=self.config.location_backend,
            ),
            "synthesizer": self._adapter_snapshot(
                self.synthesizer,
                backend=self.config.synthesis_backend,
            ),
            "audio_ingest": {
                "accepted_chunks": self.audio_ingest.accepted_chunks,
                "evicted_chunks": self.audio_ingest.evicted_chunks,
                "rejected_chunks": self.audio_ingest.rejected_chunks,
                "queue_size": self.audio_ingest.qsize(),
                "running": self.audio_ingest.is_running,
            },
            "frame_ingest": {
                "accepted_frames": self.frame_ingest.accepted_frames,
                "duplicate_frames": self.frame_ingest.duplicate_frames,
                "evicted_frames": self.frame_ingest.evicted_frames,
                "rate_limited_frames": self.frame_ingest.rate_limited_frames,
                "rejected_frames": self.frame_ingest.rejected_frames,
                "queue_size": self.frame_ingest.qsize(),
                "running": self.frame_ingest.is_running,
            },
            "workers": {
                "transcription": _processing_metrics_snapshot(
                    self.transcription_worker.metrics,
                    running=self.transcription_worker.running,
                ),
                "vision": _processing_metrics_snapshot(
                    self.vision_worker.metrics,
                    running=self.vision_worker.running,
                ),
                "location": _processing_metrics_snapshot(
                    self.location_metrics,
                    running=self._started,
                ),
            },
            "observation_counts": dict(self._observation_counts),
            "recent_observations": [
                {
                    "id": str(observation.id),
                    "kind": observation.kind.value,
                    "source_member_id": str(observation.source_member_id),
                    "summary": observation.summary,
                    "confidence": observation.confidence,
                    "created_at": observation.created_at.isoformat().replace("+00:00", "Z"),
                }
                for observation in list(self._recent_observations)
            ],
        }

    async def _handle_observation(self, observation: IntelligenceObservation) -> None:
        self._recent_observations.append(observation)
        self._observation_counts[observation.kind.value] += 1
        await self._persist_observation(observation)
        await self._synthesize_observation(observation)
        if self.observation_sink is None:
            return
        result = self.observation_sink(observation)
        if inspect.isawaitable(result):
            await result

    async def _persist_observation(self, observation: IntelligenceObservation) -> None:
        operation = getattr(self.operation_manager, "operation", None)
        if self.db is None or operation is None:
            return
        await self.db.insert_intelligence_observation(operation.id, observation)

    async def _synthesize_observation(self, observation: IntelligenceObservation) -> None:
        operation = getattr(self.operation_manager, "operation", None)
        if self.db is None or operation is None or self.synthesizer is None:
            return
        source_member = None
        if self.operation_manager is not None:
            source_member = self.operation_manager.members.get(observation.source_member_id)
        decision = await self.synthesizer.synthesize(
            observation,
            source_member=source_member,
        )
        for event in decision.events:
            await self.db.insert_event(
                event.id,
                operation.id,
                event.severity,
                event.category,
                event.text,
                event.source_member_id,
                event.latitude,
                event.longitude,
            )
        event_lookup = {event.id: event for event in decision.events}
        for alert in decision.alerts:
            await self.db.insert_alert(
                alert.id,
                alert.event_id,
                alert.severity,
                alert.category,
                alert.text,
            )
            if self.conn_manager is not None:
                event = event_lookup.get(alert.event_id)
                await self.conn_manager.broadcast_alert(
                    self._alert_payload(alert, event),
                )

    def _nearby_location_samples(self, sample: LocationSample) -> list[LocationSample]:
        nearby: list[LocationSample] = []
        for member_id, candidate in self._recent_location_samples.items():
            if member_id == sample.source.member_id:
                continue
            if abs((sample.captured_at - candidate.captured_at).total_seconds()) > (
                self.config.location_sample_ttl_seconds
            ):
                continue
            nearby.append(candidate)
        return nearby

    def _prune_location_samples(self, sample: LocationSample) -> None:
        cutoff = sample.captured_at.timestamp() - self.config.location_sample_ttl_seconds
        stale_member_ids = [
            member_id
            for member_id, candidate in self._recent_location_samples.items()
            if candidate.captured_at.timestamp() < cutoff
        ]
        for member_id in stale_member_ids:
            self._recent_location_samples.pop(member_id, None)

    def _alert_payload(self, alert, event) -> dict[str, object]:
        payload: dict[str, object] = {
            "type": "alert",
            "alert_id": str(alert.id),
            "event_id": str(alert.event_id),
            "severity": alert.severity.value,
            "category": alert.category.value,
            "text": alert.text,
            "timestamp": alert.timestamp.astimezone(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
        }
        if event is not None:
            payload["source_member_id"] = (
                str(event.source_member_id) if event.source_member_id else None
            )
            payload["latitude"] = event.latitude
            payload["longitude"] = event.longitude
        return payload

    def _adapter_snapshot(self, adapter: object, *, backend: str) -> dict[str, Any]:
        status = getattr(adapter, "status", None)
        if callable(status):
            payload = status()
            if isinstance(payload, dict):
                return {"backend": backend, **payload}
        return {
            "backend": backend,
            "class": adapter.__class__.__name__,
        }
