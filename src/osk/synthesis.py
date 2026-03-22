"""Observation-to-event synthesis contracts and evolving heuristic synthesis."""

from __future__ import annotations

import re
import time
from collections import Counter, deque
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable
from uuid import UUID

from pydantic import BaseModel, Field

from osk.intelligence_contracts import IntelligenceObservation, ObservationKind
from osk.models import Alert, Event, EventCategory, EventSeverity, Member, SitRep


class SynthesisDecision(BaseModel):
    events: list[Event] = Field(default_factory=list)
    alerts: list[Alert] = Field(default_factory=list)
    sitrep: SitRep | None = None


@runtime_checkable
class ObservationSynthesizer(Protocol):
    async def synthesize(
        self,
        observation: IntelligenceObservation,
        *,
        source_member: Member | None = None,
    ) -> SynthesisDecision: ...


@dataclass(slots=True)
class _IncidentState:
    category: EventCategory
    first_seen_at: float
    last_seen_at: float
    last_emitted_at: float
    member_ids: set[UUID] = field(default_factory=set)
    kinds: set[ObservationKind] = field(default_factory=set)
    corroboration_emitted: bool = False
    severity: EventSeverity = EventSeverity.INFO
    latest_summary: str = ""


@dataclass(slots=True)
class _Highlight:
    category: EventCategory
    severity: EventSeverity
    summary: str
    seen_at: float


class HeuristicObservationSynthesizer:
    """Stateful heuristic synthesis with dedupe, corroboration, and sitrep output."""

    def __init__(
        self,
        *,
        cooldown_seconds: int = 60,
        incident_window_seconds: int = 180,
        sitrep_interval_seconds: int = 600,
    ) -> None:
        self.cooldown_seconds = max(int(cooldown_seconds), 1)
        self.incident_window_seconds = max(int(incident_window_seconds), self.cooldown_seconds)
        self.sitrep_interval_seconds = max(int(sitrep_interval_seconds), 1)
        self._incidents: dict[str, _IncidentState] = {}
        self._recent_highlights: deque[_Highlight] = deque(maxlen=32)
        self._last_sitrep_at: float | None = None
        self._last_sitrep_text: str | None = None

    async def synthesize(
        self,
        observation: IntelligenceObservation,
        *,
        source_member: Member | None = None,
    ) -> SynthesisDecision:
        now = time.monotonic()
        self._expire_state(now)
        category, severity = self._classify(observation)
        if category is None or severity is None:
            return SynthesisDecision(sitrep=self._maybe_generate_sitrep(now))

        signature = self._dedupe_key(observation, category)
        incident = self._incidents.get(signature)
        if incident is None:
            incident = _IncidentState(
                category=category,
                first_seen_at=now,
                last_seen_at=now,
                last_emitted_at=now,
                member_ids={observation.source_member_id},
                kinds={observation.kind},
                severity=severity,
                latest_summary=observation.summary,
            )
            self._incidents[signature] = incident
            event = self._event_from_observation(
                observation,
                category=category,
                severity=severity,
                source_member=source_member,
            )
            alerts = self._alerts_for_event(event)
            self._record_highlight(event, now)
            return SynthesisDecision(
                events=[event],
                alerts=alerts,
                sitrep=self._maybe_generate_sitrep(now),
            )

        incident.last_seen_at = now
        incident.member_ids.add(observation.source_member_id)
        incident.kinds.add(observation.kind)
        incident.latest_summary = observation.summary
        if severity.level > incident.severity.level:
            incident.severity = severity

        event: Event | None = None
        if len(incident.member_ids) >= 2 and not incident.corroboration_emitted:
            incident.corroboration_emitted = True
            incident.last_emitted_at = now
            event = self._corroborated_event(
                observation,
                category=category,
                severity=self._escalate_severity(incident.severity),
                source_member=source_member,
                source_count=len(incident.member_ids),
                signal_count=len(incident.kinds),
            )
        elif (
            now - incident.last_emitted_at >= self.cooldown_seconds
            and severity.level > EventSeverity.INFO.level
        ):
            incident.last_emitted_at = now
            event = self._event_from_observation(
                observation,
                category=category,
                severity=incident.severity,
                source_member=source_member,
            )

        alerts: list[Alert] = []
        if event is not None:
            alerts = self._alerts_for_event(event)
            self._record_highlight(event, now)

        return SynthesisDecision(
            events=[event] if event is not None else [],
            alerts=alerts,
            sitrep=self._maybe_generate_sitrep(now),
        )

    def status(self) -> dict[str, object]:
        return {
            "backend": "heuristic",
            "cooldown_seconds": self.cooldown_seconds,
            "incident_window_seconds": self.incident_window_seconds,
            "incident_count": len(self._incidents),
            "highlight_count": len(self._recent_highlights),
            "last_sitrep_text": self._last_sitrep_text,
            "sitrep_interval_seconds": self.sitrep_interval_seconds,
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
        summary = observation.summary.lower()
        terms: list[str] = []
        if category == EventCategory.POLICE_ACTION:
            if any(term in summary for term in ("advanc", "charg", "push")):
                terms.append("movement")
            if any(term in summary for term in ("arrest", "detain")):
                terms.append("custody")
            if any(term in summary for term in ("mounted", "horse")):
                terms.append("mounted")
        elif category == EventCategory.BLOCKED_ROUTE:
            terms.append("blocked-route")
        elif category == EventCategory.MEDICAL:
            terms.append("medical")
        elif category == EventCategory.ESCALATION:
            terms.append("escalation")
        elif category == EventCategory.CROWD_MOVEMENT:
            cluster_size = int(observation.details.get("cluster_size") or 0)
            terms.append(f"cluster-{min(cluster_size, 5)}")
        else:
            terms.append(category.value)

        cardinal_terms = [
            direction for direction in ("north", "south", "east", "west") if direction in summary
        ]
        if cardinal_terms:
            terms.append(cardinal_terms[0])
        else:
            direction_terms = [
                direction for direction in ("entrance", "exit", "street") if direction in summary
            ]
            if direction_terms:
                terms.append(direction_terms[0])

        if not terms:
            terms.extend(self._fallback_terms(summary))
        return f"{category.value}:{'-'.join(terms)}"

    def _coerce_list(self, value) -> Sequence[object]:
        if isinstance(value, list):
            return value
        return []

    def _fallback_terms(self, summary: str) -> list[str]:
        words = re.findall(r"[a-z0-9]+", summary)
        stop_words = {
            "the",
            "and",
            "from",
            "with",
            "near",
            "into",
            "onto",
            "that",
            "this",
            "there",
        }
        terms = [word for word in words if len(word) > 3 and word not in stop_words]
        return terms[:3] or ["general"]

    def _event_from_observation(
        self,
        observation: IntelligenceObservation,
        *,
        category: EventCategory,
        severity: EventSeverity,
        source_member: Member | None,
    ) -> Event:
        return Event(
            severity=severity,
            category=category,
            text=observation.summary,
            source_member_id=observation.source_member_id,
            latitude=source_member.latitude if source_member else None,
            longitude=source_member.longitude if source_member else None,
            timestamp=observation.created_at,
        )

    def _corroborated_event(
        self,
        observation: IntelligenceObservation,
        *,
        category: EventCategory,
        severity: EventSeverity,
        source_member: Member | None,
        source_count: int,
        signal_count: int,
    ) -> Event:
        signal_text = "signals" if signal_count != 1 else "signal"
        text = (
            f"{observation.summary} Corroborated by {source_count} sources across "
            f"{signal_count} {signal_text}."
        )
        return Event(
            severity=severity,
            category=category,
            text=text,
            source_member_id=observation.source_member_id,
            latitude=source_member.latitude if source_member else None,
            longitude=source_member.longitude if source_member else None,
            timestamp=observation.created_at,
        )

    def _alerts_for_event(self, event: Event) -> list[Alert]:
        if event.severity.level < EventSeverity.ADVISORY.level:
            return []
        return [
            Alert(
                event_id=event.id,
                severity=event.severity,
                category=event.category,
                text=event.text,
                timestamp=event.timestamp,
            )
        ]

    def _record_highlight(self, event: Event, now: float) -> None:
        self._recent_highlights.append(
            _Highlight(
                category=event.category,
                severity=event.severity,
                summary=event.text,
                seen_at=now,
            )
        )

    def _maybe_generate_sitrep(self, now: float) -> SitRep | None:
        if self._last_sitrep_at is None:
            self._last_sitrep_at = now
            return None
        if now - self._last_sitrep_at < self.sitrep_interval_seconds:
            return None

        highlights = [
            highlight
            for highlight in self._recent_highlights
            if highlight.seen_at >= self._last_sitrep_at
        ]
        if len(highlights) < 2:
            self._last_sitrep_at = now
            return None

        counts = Counter(highlight.category.value for highlight in highlights)
        top_categories = ", ".join(
            f"{category.replace('_', ' ')} x{count}" for category, count in counts.most_common(3)
        )
        latest_summaries = "; ".join(
            dict.fromkeys(highlight.summary for highlight in highlights[-3:])
        )
        trend = self._trend_from_highlights(highlights)
        text = f"Recent updates: {top_categories}. Latest: {latest_summaries}"
        self._last_sitrep_at = now
        self._last_sitrep_text = text
        return SitRep(text=text, trend=trend)

    def _trend_from_highlights(self, highlights: list[_Highlight]) -> str:
        warning_count = sum(
            1 for highlight in highlights if highlight.severity.level >= EventSeverity.WARNING.level
        )
        advisory_count = sum(
            1
            for highlight in highlights
            if highlight.severity.level >= EventSeverity.ADVISORY.level
        )
        if warning_count >= 2:
            return "escalating"
        if advisory_count >= 2:
            return "active"
        return "stable"

    def _expire_state(self, now: float) -> None:
        expired_keys = [
            key
            for key, incident in self._incidents.items()
            if now - incident.last_seen_at > self.incident_window_seconds
        ]
        for key in expired_keys:
            self._incidents.pop(key, None)
        while self._recent_highlights and now - self._recent_highlights[0].seen_at > (
            self.sitrep_interval_seconds * 2
        ):
            self._recent_highlights.popleft()

    def _escalate_severity(self, severity: EventSeverity) -> EventSeverity:
        if severity == EventSeverity.INFO:
            return EventSeverity.ADVISORY
        if severity == EventSeverity.ADVISORY:
            return EventSeverity.WARNING
        return severity
