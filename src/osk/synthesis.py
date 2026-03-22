"""Observation-to-event synthesis contracts and baseline heuristics."""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from osk.intelligence_contracts import IntelligenceObservation, ObservationKind
from osk.models import Alert, Event, EventCategory, EventSeverity, Member


class SynthesisDecision(BaseModel):
    events: list[Event] = Field(default_factory=list)
    alerts: list[Alert] = Field(default_factory=list)


@runtime_checkable
class ObservationSynthesizer(Protocol):
    async def synthesize(
        self,
        observation: IntelligenceObservation,
        *,
        source_member: Member | None = None,
    ) -> SynthesisDecision: ...


class HeuristicObservationSynthesizer:
    """Low-regret placeholder synthesizer for early foundation work."""

    def __init__(self, *, cooldown_seconds: int = 60) -> None:
        self.cooldown_seconds = max(int(cooldown_seconds), 1)
        self._recent_keys: dict[str, float] = {}

    async def synthesize(
        self,
        observation: IntelligenceObservation,
        *,
        source_member: Member | None = None,
    ) -> SynthesisDecision:
        category, severity = self._classify(observation)
        if category is None or severity is None:
            return SynthesisDecision()

        dedupe_key = self._dedupe_key(observation, category)
        now = time.monotonic()
        if now - self._recent_keys.get(dedupe_key, 0.0) < self.cooldown_seconds:
            return SynthesisDecision()
        self._recent_keys[dedupe_key] = now

        latitude = source_member.latitude if source_member else None
        longitude = source_member.longitude if source_member else None
        event = Event(
            severity=severity,
            category=category,
            text=observation.summary,
            source_member_id=observation.source_member_id,
            latitude=latitude,
            longitude=longitude,
            timestamp=observation.created_at,
        )
        alerts: list[Alert] = []
        if severity.level >= EventSeverity.ADVISORY.level:
            alerts.append(
                Alert(
                    event_id=event.id,
                    severity=event.severity,
                    category=event.category,
                    text=event.text,
                    timestamp=event.timestamp,
                )
            )
        return SynthesisDecision(events=[event], alerts=alerts)

    def status(self) -> dict[str, object]:
        return {
            "backend": "heuristic",
            "cooldown_seconds": self.cooldown_seconds,
            "recent_keys": len(self._recent_keys),
        }

    def _classify(
        self,
        observation: IntelligenceObservation,
    ) -> tuple[EventCategory | None, EventSeverity | None]:
        summary = observation.summary.lower()
        tags = [str(tag).lower() for tag in self._coerce_list(observation.details.get("tags"))]

        if observation.kind == ObservationKind.LOCATION:
            cluster_size = int(observation.details.get("cluster_size") or 0)
            if cluster_size >= 4:
                return EventCategory.CROWD_MOVEMENT, EventSeverity.ADVISORY
            if cluster_size >= 2:
                return EventCategory.CROWD_MOVEMENT, EventSeverity.INFO
            return None, None

        if any(term in summary for term in ("police", "officer", "sheriff", "trooper")):
            severity = (
                EventSeverity.WARNING
                if any(term in summary for term in ("charging", "advancing", "riot", "arrest"))
                else EventSeverity.ADVISORY
            )
            return EventCategory.POLICE_ACTION, severity

        if any(term in summary for term in ("blocked", "barrier", "closed", "sealed")):
            return EventCategory.BLOCKED_ROUTE, EventSeverity.ADVISORY

        if any(term in summary for term in ("medic", "medical", "injur", "bleeding")):
            return EventCategory.MEDICAL, EventSeverity.WARNING

        if any(term in summary for term in ("escalat", "panic", "stampede", "fight")):
            return EventCategory.ESCALATION, EventSeverity.WARNING

        if observation.kind == ObservationKind.VISION and any(
            tag in {"vehicle_description", "mounted", "crowd", "vehicle"} for tag in tags
        ):
            return EventCategory.COMMUNITY, EventSeverity.INFO

        return None, None

    def _dedupe_key(self, observation: IntelligenceObservation, category: EventCategory) -> str:
        summary = " ".join(observation.summary.lower().split())
        return f"{category.value}:{observation.kind.value}:{observation.source_member_id}:{summary}"

    def _coerce_list(self, value) -> Sequence[object]:
        if isinstance(value, list):
            return value
        return []
