"""Coordinator-owned service for Phase 2 ingest, persistence, and synthesis."""

from __future__ import annotations

import inspect
import logging
import time
from collections import Counter, deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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
from osk.models import SynthesisFinding
from osk.ollama_synthesis import OllamaObservationSynthesizer
from osk.synthesis import HeuristicObservationSynthesizer
from osk.transcriber import TranscriptionWorker, WhisperTranscriber, build_audio_decoder
from osk.vision_engine import OllamaVisionAnalyzer, VisionWorker
from osk.whisper_runtime import WhisperRuntimeManager
from osk.worker_runtime import ProcessingWorkerMetrics

logger = logging.getLogger(__name__)

ObservationSink = Callable[[IntelligenceObservation], Awaitable[None] | None]


@dataclass(slots=True)
class IngestSubmissionResult:
    accepted: bool
    duplicate: bool = False
    reason: str | None = None


def build_transcriber(config: OskConfig):
    if config.transcriber_backend == "fake":
        return FakeTranscriber()
    return WhisperTranscriber(
        runtime_manager=WhisperRuntimeManager(model_size=config.whisper_model),
        decoder=build_audio_decoder(ffmpeg_binary=config.ffmpeg_binary),
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
    if config.synthesis_backend == "ollama":
        return OllamaObservationSynthesizer(
            base_url=config.ollama_base_url,
            model=config.synthesis_model,
            cooldown_seconds=config.synthesis_cooldown_seconds,
        )
    return HeuristicObservationSynthesizer(
        cooldown_seconds=config.synthesis_cooldown_seconds,
        sitrep_interval_seconds=config.sitrep_interval_minutes * 60,
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
        storage=None,
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
        self.storage = storage
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
        self._recent_findings = deque(maxlen=max(1, config.intelligence_recent_observation_limit))
        self._observation_counts: Counter[str] = Counter()
        self._recent_location_samples: dict[Any, LocationSample] = {}
        self._ingest_receipts: dict[tuple[str, object, str], float] = {}
        self._last_ingest_receipt_cleanup_at = 0.0
        self._audio_duplicate_submissions = 0
        self._frame_duplicate_submissions = 0
        self._started = False
        self.location_metrics = ProcessingWorkerMetrics()
        self.transcription_worker = TranscriptionWorker(
            audio_ingest=self.audio_ingest,
            transcriber=self.transcriber,
            on_observation=self._handle_observation,
            on_artifact=self._write_audio_artifact if self.storage else None,
        )
        self.vision_worker = VisionWorker(
            frame_ingest=self.frame_ingest,
            vision_analyzer=self.vision_analyzer,
            on_observation=self._handle_observation,
            on_artifact=self._write_frame_artifact if self.storage else None,
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

    async def submit_audio(self, chunk: AudioChunk) -> IngestSubmissionResult:
        if await self._is_duplicate_ingest(
            kind="audio",
            member_id=chunk.source.member_id,
            ingest_key=chunk.ingest_key,
            item_id=chunk.chunk_id,
            seen_at=chunk.source.received_at,
        ):
            self._audio_duplicate_submissions += 1
            return IngestSubmissionResult(accepted=True, duplicate=True)
        accepted = await self.audio_ingest.put(chunk)
        return IngestSubmissionResult(
            accepted=accepted,
            reason=None if accepted else "audio queue full",
        )

    async def submit_frame(self, frame: FrameSample) -> IngestSubmissionResult:
        if await self._is_duplicate_ingest(
            kind="frame",
            member_id=frame.source.member_id,
            ingest_key=frame.ingest_key,
            item_id=frame.frame_id,
            seen_at=frame.captured_at,
        ):
            self._frame_duplicate_submissions += 1
            return IngestSubmissionResult(accepted=True, duplicate=True)
        accepted = await self.frame_ingest.put(frame)
        return IngestSubmissionResult(
            accepted=accepted,
            reason=None if accepted else "frame queue full",
        )

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
                "duplicate_submissions": self._audio_duplicate_submissions,
                "evicted_chunks": self.audio_ingest.evicted_chunks,
                "rejected_chunks": self.audio_ingest.rejected_chunks,
                "receipt_cache_entries": sum(
                    1 for receipt_key in self._ingest_receipts if receipt_key[0] == "audio"
                ),
                "queue_size": self.audio_ingest.qsize(),
                "running": self.audio_ingest.is_running,
            },
            "frame_ingest": {
                "accepted_frames": self.frame_ingest.accepted_frames,
                "duplicate_submissions": self._frame_duplicate_submissions,
                "duplicate_frames": self.frame_ingest.duplicate_frames,
                "evicted_frames": self.frame_ingest.evicted_frames,
                "rate_limited_frames": self.frame_ingest.rate_limited_frames,
                "rejected_frames": self.frame_ingest.rejected_frames,
                "receipt_cache_entries": sum(
                    1 for receipt_key in self._ingest_receipts if receipt_key[0] == "frame"
                ),
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
            "recent_findings": [
                {
                    "id": str(finding.id),
                    "title": finding.title,
                    "category": finding.category.value,
                    "severity": finding.severity.value,
                    "summary": finding.summary,
                    "corroborated": finding.corroborated,
                    "last_seen_at": finding.last_seen_at.isoformat().replace("+00:00", "Z"),
                }
                for finding in list(self._recent_findings)
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

        # Write to preserved evidence store if available
        if self.storage is not None:
            self._write_observation_to_evidence(operation.id, observation)

    def _write_observation_to_evidence(
        self, operation_id, observation: IntelligenceObservation
    ) -> None:
        """Write observation metadata and any attached artifacts to evidence store."""
        member_id = str(observation.source_member_id)
        observation_id = str(observation.id)

        # Build metadata document
        metadata = {
            "id": observation_id,
            "operation_id": str(operation_id),
            "member_id": member_id,
            "kind": observation.kind.value,
            "summary": observation.summary,
            "confidence": observation.confidence,
            "created_at": observation.created_at.isoformat(),
            "details": observation.details,
        }

        # Write metadata JSON
        self.storage.write_evidence_metadata(operation_id, member_id, metadata)

        # Write artifact data if present in details
        artifact_data = observation.details.get("artifact_data")
        if artifact_data and isinstance(artifact_data, (bytes, str)):
            artifact_type = observation.details.get("artifact_type", "unknown")
            extension = observation.details.get("artifact_extension", "bin")
            if isinstance(artifact_data, str):
                artifact_data = artifact_data.encode("utf-8")
            self.storage.write_evidence_artifact(
                str(operation_id),
                member_id,
                artifact_type,
                artifact_data,
                extension,
            )

    async def _write_audio_artifact(self, chunk, observation_id: str) -> None:
        """Write audio chunk to evidence store as artifact."""
        if self.storage is None:
            return
        operation = getattr(self.operation_manager, "operation", None)
        if operation is None:
            return
        
        member_id = str(chunk.source.member_id)
        
        # Determine extension based on codec
        codec = str(chunk.codec or "audio/unknown").lower()
        if "webm" in codec or "opus" in codec:
            extension = "webm"
        elif "ogg" in codec:
            extension = "ogg"
        elif "wav" in codec or "pcm" in codec:
            extension = "wav"
        else:
            extension = "bin"
        
        try:
            self.storage.write_evidence_artifact(
                str(operation.id),
                member_id,
                "audio",
                chunk.payload,
                extension,
            )
            logger.debug(
                "Wrote audio artifact for observation %s (chunk %s)",
                observation_id,
                chunk.chunk_id,
            )
        except Exception as exc:
            logger.warning("Failed to write audio artifact: %s", exc)

    async def _write_frame_artifact(self, frame, observation_id: str) -> None:
        """Write frame to evidence store as artifact."""
        if self.storage is None:
            return
        operation = getattr(self.operation_manager, "operation", None)
        if operation is None:
            return
        
        member_id = str(frame.source.member_id)
        
        try:
            self.storage.write_evidence_artifact(
                str(operation.id),
                member_id,
                "frames",
                frame.payload,
                "jpg",
            )
            logger.debug(
                "Wrote frame artifact for observation %s (frame %s)",
                observation_id,
                frame.frame_id,
            )
        except Exception as exc:
            logger.warning("Failed to write frame artifact: %s", exc)

    async def _synthesize_observation(self, observation: IntelligenceObservation) -> None:
        operation = getattr(self.operation_manager, "operation", None)
        if self.synthesizer is None:
            return
        source_member = None
        if self.operation_manager is not None:
            source_member = self.operation_manager.members.get(observation.source_member_id)
        decision = await self.synthesizer.synthesize(
            observation,
            source_member=source_member,
        )
        if self.db is None or operation is None:
            self._recent_findings.extend(decision.findings)
            return
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
        for finding in decision.findings:
            persisted = await self.db.upsert_synthesis_finding(operation.id, finding)
            if isinstance(persisted, dict):
                self._recent_findings.append(SynthesisFinding.model_validate(persisted))
            else:
                self._recent_findings.append(finding)
        if decision.sitrep is not None:
            await self.db.insert_sitrep(
                decision.sitrep.id,
                operation.id,
                decision.sitrep.text,
                decision.sitrep.trend,
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

    async def _is_duplicate_ingest(
        self,
        *,
        kind: str,
        member_id,
        ingest_key: str | None,
        item_id,
        seen_at: datetime,
    ) -> bool:
        if not ingest_key:
            return False
        now = time.monotonic()
        self._prune_ingest_receipts(now)
        await self._maybe_prune_durable_ingest_receipts(now)
        receipt_key = (kind, member_id, ingest_key)
        cached_seen_at = self._ingest_receipts.pop(receipt_key, None)
        if cached_seen_at is not None and (
            now - cached_seen_at <= max(int(self.config.ingest_idempotency_window_seconds), 1)
        ):
            self._ingest_receipts[receipt_key] = now
            return True
        operation = getattr(self.operation_manager, "operation", None)
        if self.db is not None and operation is not None:
            duplicate = await self.db.claim_ingest_receipt(
                operation.id,
                kind=kind,
                member_id=member_id,
                ingest_key=ingest_key,
                item_id=item_id,
                seen_at=seen_at,
                window_seconds=int(self.config.ingest_idempotency_window_seconds),
            )
            self._ingest_receipts[receipt_key] = now
            if duplicate:
                return True
        self._ingest_receipts[receipt_key] = now
        cache_limit = max(int(self.config.ingest_idempotency_cache_size), 1)
        while len(self._ingest_receipts) > cache_limit:
            oldest_key = next(iter(self._ingest_receipts))
            self._ingest_receipts.pop(oldest_key, None)
        return False

    def _prune_ingest_receipts(self, now: float) -> None:
        ttl_seconds = max(int(self.config.ingest_idempotency_window_seconds), 1)
        expired_keys = [
            receipt_key
            for receipt_key, seen_at in self._ingest_receipts.items()
            if now - seen_at > ttl_seconds
        ]
        for receipt_key in expired_keys:
            self._ingest_receipts.pop(receipt_key, None)

    async def _maybe_prune_durable_ingest_receipts(self, now: float) -> None:
        interval_seconds = max(int(self.config.ingest_receipt_cleanup_interval_seconds), 1)
        if now - self._last_ingest_receipt_cleanup_at < interval_seconds:
            return
        operation = getattr(self.operation_manager, "operation", None)
        if self.db is None or operation is None:
            self._last_ingest_receipt_cleanup_at = now
            return
        older_than = datetime.now(timezone.utc) - timedelta(
            hours=max(int(self.config.ingest_receipt_retention_hours), 1)
        )
        await self.db.prune_ingest_receipts(operation.id, older_than=older_than)
        self._last_ingest_receipt_cleanup_at = now
