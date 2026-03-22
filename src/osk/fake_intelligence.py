"""Deterministic fake adapters for contract-first Phase 2 development."""

from __future__ import annotations

import math
import uuid
from collections.abc import Iterable, Mapping, Sequence
from datetime import timedelta

from osk.intelligence_contracts import (
    AudioChunk,
    FrameSample,
    IngestPriority,
    LocationResult,
    LocationSample,
    TranscriptResult,
    VisionResult,
)


def _priority_confidence_boost(priority: IngestPriority) -> float:
    return {
        IngestPriority.BACKGROUND: 0.00,
        IngestPriority.OBSERVER: 0.08,
        IngestPriority.SENSOR: 0.14,
        IngestPriority.URGENT: 0.18,
    }[priority]


def _distance_meters(
    left_latitude: float,
    left_longitude: float,
    right_latitude: float,
    right_longitude: float,
) -> float:
    earth_radius_m = 6_371_000.0
    lat1 = math.radians(left_latitude)
    lon1 = math.radians(left_longitude)
    lat2 = math.radians(right_latitude)
    lon2 = math.radians(right_longitude)
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return earth_radius_m * c


class FakeTranscriber:
    def __init__(
        self,
        scripted_text: Mapping[uuid.UUID, str] | None = None,
        *,
        dropped_chunk_ids: Iterable[uuid.UUID] = (),
    ) -> None:
        self._scripted_text = dict(scripted_text or {})
        self._dropped_chunk_ids = {uuid.UUID(str(chunk_id)) for chunk_id in dropped_chunk_ids}

    def status(self) -> dict[str, object]:
        return {
            "adapter": "fake-transcriber",
            "scripted_chunks": len(self._scripted_text),
            "dropped_chunks": len(self._dropped_chunk_ids),
        }

    async def transcribe(self, chunk: AudioChunk) -> TranscriptResult | None:
        if chunk.chunk_id in self._dropped_chunk_ids:
            return None

        text = self._scripted_text.get(chunk.chunk_id)
        if text is None:
            text = (
                f"Simulated {chunk.source.member_role.value} audio transcript "
                f"for {chunk.duration_ms}ms of {chunk.codec}."
            )

        ended_at = chunk.source.received_at
        started_at = ended_at - timedelta(milliseconds=max(chunk.duration_ms, 0))
        confidence = min(0.99, 0.72 + _priority_confidence_boost(chunk.source.priority))
        return TranscriptResult(
            adapter="fake-transcriber",
            chunk_id=chunk.chunk_id,
            source_member_id=chunk.source.member_id,
            text=text,
            confidence=confidence,
            started_at=started_at,
            ended_at=ended_at,
        )


class FakeVisionAnalyzer:
    def __init__(
        self,
        scripted_results: Mapping[uuid.UUID, tuple[str, Sequence[str]]] | None = None,
        *,
        dropped_frame_ids: Iterable[uuid.UUID] = (),
    ) -> None:
        self._scripted_results = {
            uuid.UUID(str(frame_id)): (summary, list(tags))
            for frame_id, (summary, tags) in (scripted_results or {}).items()
        }
        self._dropped_frame_ids = {uuid.UUID(str(frame_id)) for frame_id in dropped_frame_ids}

    def status(self) -> dict[str, object]:
        return {
            "adapter": "fake-vision",
            "scripted_frames": len(self._scripted_results),
            "dropped_frames": len(self._dropped_frame_ids),
        }

    async def analyze(self, frame: FrameSample) -> VisionResult | None:
        if frame.frame_id in self._dropped_frame_ids:
            return None

        scripted = self._scripted_results.get(frame.frame_id)
        if scripted is None:
            orientation = "wide" if frame.width >= frame.height else "portrait"
            summary = (
                f"Simulated frame analysis for a {frame.source.member_role.value} "
                f"{orientation} sample at {frame.width}x{frame.height}."
            )
            tags = [
                "simulated",
                frame.content_type.split("/")[-1],
                orientation,
                frame.source.member_role.value,
            ]
        else:
            summary, tags = scripted

        confidence = min(0.97, 0.68 + _priority_confidence_boost(frame.source.priority))
        return VisionResult(
            adapter="fake-vision",
            frame_id=frame.frame_id,
            source_member_id=frame.source.member_id,
            summary=summary,
            tags=list(tags),
            confidence=confidence,
            captured_at=frame.captured_at,
        )


class FakeLocationAnalyzer:
    def __init__(
        self,
        *,
        cluster_radius_m: float = 150.0,
        min_cluster_size: int = 3,
    ) -> None:
        self.cluster_radius_m = cluster_radius_m
        self.min_cluster_size = max(min_cluster_size, 2)

    async def analyze(
        self,
        sample: LocationSample,
        nearby_samples: Sequence[LocationSample] = (),
    ) -> LocationResult | None:
        nearby_member_ids: list[uuid.UUID] = []
        for nearby in nearby_samples:
            if nearby.source.member_id == sample.source.member_id:
                continue
            distance_m = _distance_meters(
                sample.latitude,
                sample.longitude,
                nearby.latitude,
                nearby.longitude,
            )
            if distance_m <= self.cluster_radius_m:
                nearby_member_ids.append(nearby.source.member_id)

        cluster_size = 1 + len(nearby_member_ids)
        if cluster_size >= self.min_cluster_size:
            summary = f"Simulated cluster of {cluster_size} nearby members detected."
        else:
            summary = "Simulated location update received."

        risk_score = min(
            1.0,
            0.15 * cluster_size + _priority_confidence_boost(sample.source.priority),
        )
        return LocationResult(
            adapter="fake-location",
            source_member_id=sample.source.member_id,
            summary=summary,
            cluster_size=cluster_size,
            nearby_member_ids=nearby_member_ids,
            risk_score=risk_score,
            captured_at=sample.captured_at,
        )
