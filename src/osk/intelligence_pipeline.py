"""Thin normalization layer for contract-first intelligence processing."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel

from osk.intelligence_contracts import (
    AudioChunk,
    FrameSample,
    IntelligenceObservation,
    LocationAnalyzer,
    LocationSample,
    ObservationKind,
    Transcriber,
    VisionAnalyzer,
)


def build_observation(
    *,
    kind: ObservationKind,
    source_member_id,
    summary: str,
    confidence: float,
    result: BaseModel,
) -> IntelligenceObservation:
    return IntelligenceObservation(
        kind=kind,
        source_member_id=source_member_id,
        summary=summary,
        confidence=confidence,
        details=result.model_dump(mode="json"),
    )


class IntelligencePipeline:
    def __init__(
        self,
        *,
        transcriber: Transcriber,
        vision_analyzer: VisionAnalyzer,
        location_analyzer: LocationAnalyzer,
    ) -> None:
        self.transcriber = transcriber
        self.vision_analyzer = vision_analyzer
        self.location_analyzer = location_analyzer

    async def process_audio(self, chunk: AudioChunk) -> IntelligenceObservation | None:
        transcript = await self.transcriber.transcribe(chunk)
        if transcript is None:
            return None
        return self._observation_from_result(
            kind=ObservationKind.TRANSCRIPT,
            source_member_id=chunk.source.member_id,
            summary=transcript.text,
            confidence=transcript.confidence,
            result=transcript,
        )

    async def process_frame(self, frame: FrameSample) -> IntelligenceObservation | None:
        vision_result = await self.vision_analyzer.analyze(frame)
        if vision_result is None:
            return None
        return self._observation_from_result(
            kind=ObservationKind.VISION,
            source_member_id=frame.source.member_id,
            summary=vision_result.summary,
            confidence=vision_result.confidence,
            result=vision_result,
        )

    async def process_location(
        self,
        sample: LocationSample,
        nearby_samples: Sequence[LocationSample] = (),
    ) -> IntelligenceObservation | None:
        location_result = await self.location_analyzer.analyze(sample, nearby_samples)
        if location_result is None:
            return None
        return self._observation_from_result(
            kind=ObservationKind.LOCATION,
            source_member_id=sample.source.member_id,
            summary=location_result.summary,
            confidence=location_result.risk_score,
            result=location_result,
        )

    def _observation_from_result(
        self,
        *,
        kind: ObservationKind,
        source_member_id,
        summary: str,
        confidence: float,
        result: BaseModel,
    ) -> IntelligenceObservation:
        return build_observation(
            kind=kind,
            source_member_id=source_member_id,
            summary=summary,
            confidence=confidence,
            result=result,
        )
