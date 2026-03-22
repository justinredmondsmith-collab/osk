"""Coordinator-owned service for Phase 2 ingest workers and adapter selection."""

from __future__ import annotations

import inspect
import logging
from collections import Counter, deque
from collections.abc import Awaitable, Callable
from typing import Any

from osk.audio_ingest import AudioIngest
from osk.config import OskConfig
from osk.fake_intelligence import FakeTranscriber, FakeVisionAnalyzer
from osk.frame_ingest import FrameIngest
from osk.intelligence_contracts import AudioChunk, FrameSample, IntelligenceObservation
from osk.transcriber import TranscriptionWorker, WhisperTranscriber
from osk.vision_engine import OllamaVisionAnalyzer, VisionWorker
from osk.whisper_runtime import WhisperRuntimeManager

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


async def _maybe_close(resource: object) -> None:
    close = getattr(resource, "close", None)
    if close is None:
        return
    result = close()
    if inspect.isawaitable(result):
        await result


def _worker_metrics_snapshot(worker) -> dict[str, object]:
    metrics = worker.metrics
    return {
        "processed_items": metrics.processed_items,
        "emitted_observations": metrics.emitted_observations,
        "empty_results": metrics.empty_results,
        "errors": metrics.errors,
        "last_latency_ms": metrics.last_latency_ms,
        "average_latency_ms": metrics.average_latency_ms,
        "last_error": metrics.last_error,
        "running": worker.running,
    }


class IntelligenceService:
    def __init__(
        self,
        *,
        config: OskConfig,
        observation_sink: ObservationSink | None = None,
        transcriber=None,
        vision_analyzer=None,
        audio_ingest: AudioIngest | None = None,
        frame_ingest: FrameIngest | None = None,
    ) -> None:
        self.config = config
        self.observation_sink = observation_sink
        self.transcriber = transcriber or build_transcriber(config)
        self.vision_analyzer = vision_analyzer or build_vision_analyzer(config)
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
        self._started = False
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
            "Started intelligence service with transcriber=%s vision=%s",
            self.config.transcriber_backend,
            self.config.vision_backend,
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
        self._started = False
        logger.info("Stopped intelligence service")

    async def submit_audio(self, chunk: AudioChunk) -> bool:
        return await self.audio_ingest.put(chunk)

    async def submit_frame(self, frame: FrameSample) -> bool:
        return await self.frame_ingest.put(frame)

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
                "transcription": _worker_metrics_snapshot(self.transcription_worker),
                "vision": _worker_metrics_snapshot(self.vision_worker),
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
        if self.observation_sink is None:
            return
        result = self.observation_sink(observation)
        if inspect.isawaitable(result):
            await result

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
