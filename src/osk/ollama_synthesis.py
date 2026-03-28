"""Ollama-based semantic synthesis for Osk observations."""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from osk.intelligence_contracts import IntelligenceObservation, ObservationKind
from osk.models import (
    Alert,
    Event,
    EventCategory,
    EventSeverity,
    Member,
    SitRep,
    SynthesisFinding,
)
from osk.synthesis import SynthesisDecision

logger = logging.getLogger(__name__)


DEFAULT_SYNTHESIS_PROMPT = """You are an AI assistant analyzing observations from a civilian situational awareness system. Your task is to classify observations into categories and assess severity.

Observation Type: {observation_kind}
Summary: {summary}
Context: {context}

Classify this observation into exactly one category:
- police_action: Police, officers, law enforcement activity
- blocked_route: Barriers, road closures, sealed areas
- medical: Injuries, medical emergencies, bleeding
- escalation: Fights, panic, stampedes, violence
- crowd_movement: Group formations, marches, gathering
- community: General activity, vehicles, crowds without threat

Assess severity:
- critical: Immediate danger, active violence, severe injury
- warning: Potential threat, police advancing, medical needed
- advisory: Notable activity, blocked routes, useful context
- info: General awareness, no immediate concern

Respond in JSON format:
{{
    "category": "category_name",
    "severity": "severity_level",
    "reasoning": "Brief explanation of classification",
    "confidence": 0.85
}}

Use snake_case for category and severity values.

If the observation is not operationally relevant, respond with:
{{
    "category": null,
    "severity": null,
    "reasoning": "Not relevant",
    "confidence": 0.0
}}
"""


@dataclass
class _OllamaIncidentState:
    """Track incident state for corroboration and deduplication."""
    finding_id: uuid.UUID
    category: EventCategory
    first_seen_at: float
    last_seen_at: float
    last_emitted_at: float
    member_ids: set[uuid.UUID] = field(default_factory=set)
    observation_count: int = 1
    latest_summary: str = ""
    severity: EventSeverity = EventSeverity.INFO
    corroboration_emitted: bool = False


class OllamaObservationSynthesizer:
    """Semantic synthesis using Ollama LLM for contextual understanding."""

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.2:3b",
        prompt_template: str = DEFAULT_SYNTHESIS_PROMPT,
        timeout_seconds: float = 5.0,
        cooldown_seconds: int = 60,
        incident_window_seconds: int = 180,
        client: Any | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.prompt_template = prompt_template
        self.timeout_seconds = timeout_seconds
        self.cooldown_seconds = cooldown_seconds
        self.incident_window_seconds = incident_window_seconds
        self._client = client
        self._owns_client = client is None
        self._incidents: dict[str, _OllamaIncidentState] = {}

    async def synthesize(
        self,
        observation: IntelligenceObservation,
        *,
        source_member: Member | None = None,
    ) -> SynthesisDecision:
        """Synthesize observation using Ollama LLM."""
        now = time.monotonic()
        self._expire_state(now)

        # Get LLM classification
        classification = await self._classify_with_ollama(observation)
        
        if classification is None:
            return SynthesisDecision()

        category = classification["category"]
        severity = classification["severity"]
        confidence = classification.get("confidence", 0.5)

        # Create signature for deduplication
        signature = self._create_signature(observation, category)
        
        incident = self._incidents.get(signature)
        if incident is None:
            # New incident
            incident = _OllamaIncidentState(
                finding_id=uuid.uuid4(),
                category=category,
                first_seen_at=now,
                last_seen_at=now,
                last_emitted_at=now,
                member_ids={observation.source_member_id},
                latest_summary=observation.summary,
                severity=severity,
            )
            self._incidents[signature] = incident
            
            event = self._create_event(observation, category, severity, source_member)
            alerts = self._create_alerts(event)
            finding = self._create_finding(incident, observation)
            
            return SynthesisDecision(
                events=[event],
                alerts=alerts,
                findings=[finding],
            )

        # Update existing incident
        incident.last_seen_at = now
        incident.member_ids.add(observation.source_member_id)
        incident.observation_count += 1
        incident.latest_summary = observation.summary
        
        # Check for corroboration (multiple sources)
        event: Event | None = None
        if len(incident.member_ids) >= 2 and not incident.corroboration_emitted:
            incident.corroboration_emitted = True
            incident.last_emitted_at = now
            severity = self._escalate_severity(severity)
            event = self._create_event(observation, category, severity, source_member)
            
        elif now - incident.last_emitted_at >= self.cooldown_seconds:
            incident.last_emitted_at = now
            event = self._create_event(observation, category, severity, source_member)

        alerts: list[Alert] = []
        if event is not None:
            alerts = self._create_alerts(event)

        finding = self._create_finding(incident, observation)
        
        return SynthesisDecision(
            events=[event] if event else [],
            alerts=alerts,
            findings=[finding],
        )

    def status(self) -> dict[str, object]:
        """Return synthesizer status."""
        return {
            "backend": "ollama",
            "model": self.model,
            "base_url": self.base_url,
            "timeout_seconds": self.timeout_seconds,
            "cooldown_seconds": self.cooldown_seconds,
            "incident_window_seconds": self.incident_window_seconds,
            "active_incidents": len(self._incidents),
        }

    async def close(self) -> None:
        """Close HTTP client if owned."""
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    async def _classify_with_ollama(
        self,
        observation: IntelligenceObservation,
    ) -> dict[str, Any] | None:
        """Send observation to Ollama for classification."""
        prompt = self.prompt_template.format(
            observation_kind=observation.kind.value,
            summary=observation.summary,
            context=self._build_context(observation),
        )

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,  # Low temperature for consistency
                "num_predict": 200,  # Limit response length
            },
        }

        try:
            client = await self._get_client()
            response = await client.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            
            raw_response = data.get("response", "").strip()
            return self._parse_classification(raw_response)
            
        except Exception as exc:
            logger.warning("Ollama classification failed: %s", exc)
            # Fallback to simple keyword classification
            return self._fallback_classify(observation)

    def _parse_classification(self, raw_response: str) -> dict[str, Any] | None:
        """Parse JSON classification from LLM response."""
        # Extract JSON from response (handle markdown code blocks)
        json_str = raw_response
        if "```json" in raw_response:
            json_str = raw_response.split("```json")[1].split("```")[0].strip()
        elif "```" in raw_response:
            json_str = raw_response.split("```")[1].split("```")[0].strip()
        
        try:
            data = json.loads(json_str)
            
            category_str = data.get("category")
            severity_str = data.get("severity")
            
            if category_str is None or severity_str is None:
                return None
            
            category = EventCategory(category_str)
            severity = EventSeverity(severity_str)
            
            return {
                "category": category,
                "severity": severity,
                "confidence": data.get("confidence", 0.5),
                "reasoning": data.get("reasoning", ""),
            }
            
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Failed to parse Ollama response: %s - %s", exc, raw_response[:200])
            return None

    def _fallback_classify(
        self,
        observation: IntelligenceObservation,
    ) -> dict[str, Any] | None:
        """Simple keyword fallback when Ollama is unavailable."""
        summary = observation.summary.lower()
        
        if any(term in summary for term in ("police", "officer")):
            return {
                "category": EventCategory.POLICE_ACTION,
                "severity": EventSeverity.ADVISORY,
                "confidence": 0.6,
            }
        elif any(term in summary for term in ("medical", "injury", "bleeding")):
            return {
                "category": EventCategory.MEDICAL,
                "severity": EventSeverity.WARNING,
                "confidence": 0.7,
            }
        elif any(term in summary for term in ("blocked", "barrier")):
            return {
                "category": EventCategory.BLOCKED_ROUTE,
                "severity": EventSeverity.ADVISORY,
                "confidence": 0.6,
            }
        
        return None

    def _build_context(self, observation: IntelligenceObservation) -> str:
        """Build context string for prompt."""
        context_parts = []
        
        if observation.kind == ObservationKind.TRANSCRIPT:
            context_parts.append("Audio transcription from member device")
        elif observation.kind == ObservationKind.VISION:
            context_parts.append("Visual observation from camera")
        elif observation.kind == ObservationKind.LOCATION:
            context_parts.append("Location/GPS data")
        
        confidence = observation.confidence
        if confidence > 0:
            context_parts.append(f"Confidence: {confidence:.0%}")
        
        return "; ".join(context_parts) if context_parts else "No additional context"

    def _create_signature(
        self,
        observation: IntelligenceObservation,
        category: EventCategory,
    ) -> str:
        """Create deduplication signature."""
        # Include key terms from summary
        summary_lower = observation.summary.lower()
        key_terms = []
        
        # Extract location/direction terms
        for term in ("north", "south", "east", "west", "entrance", "exit"):
            if term in summary_lower:
                key_terms.append(term)
        
        # Extract entity terms
        for term in ("police", "crowd", "vehicle", "barrier", "medical"):
            if term in summary_lower:
                key_terms.append(term)
        
        if key_terms:
            return f"{category.value}:{'-'.join(sorted(key_terms[:3]))}"
        return f"{category.value}:{observation.source_member_id}"

    def _expire_state(self, now: float) -> None:
        """Remove old incidents."""
        cutoff = now - self.incident_window_seconds
        stale = [
            sig for sig, incident in self._incidents.items()
            if incident.last_seen_at < cutoff
        ]
        for sig in stale:
            del self._incidents[sig]

    def _create_event(
        self,
        observation: IntelligenceObservation,
        category: EventCategory,
        severity: EventSeverity,
        source_member: Member | None,
    ) -> Event:
        """Create an Event from observation."""
        return Event(
            id=uuid.uuid4(),
            category=category,
            severity=severity,
            text=observation.summary,
            source_member_id=observation.source_member_id,
            latitude=source_member.latitude if source_member else None,
            longitude=source_member.longitude if source_member else None,
        )

    def _create_alerts(self, event: Event) -> list[Alert]:
        """Create alerts for an event."""
        # Only alert on WARNING and above
        if event.severity.level < EventSeverity.WARNING.level:
            return []
        
        return [Alert(
            id=uuid.uuid4(),
            event_id=event.id,
            severity=event.severity,
            category=event.category,
            text=event.text,
        )]

    def _create_finding(
        self,
        incident: _OllamaIncidentState,
        observation: IntelligenceObservation,
    ) -> SynthesisFinding:
        """Create a SynthesisFinding from incident."""
        severity = (
            self._escalate_severity(incident.severity)
            if incident.corroboration_emitted
            else incident.severity
        )
        
        corroboration_text = ""
        if incident.corroboration_emitted:
            corroboration_text = f" Corroborated by {len(incident.member_ids)} sources."
        
        return SynthesisFinding(
            id=incident.finding_id,
            signature=f"ollama:{incident.category.value}",
            category=incident.category,
            severity=severity,
            title=incident.category.value.replace("_", " ").title(),
            summary=f"{incident.latest_summary}{corroboration_text}",
            corroborated=incident.corroboration_emitted,
            source_count=len(incident.member_ids),
            signal_count=1,  # Simplified for Ollama
            observation_count=incident.observation_count,
            first_seen_at=observation.created_at,  # Simplified
            last_seen_at=observation.created_at,
            latest_observation_id=observation.id,
        )

    def _escalate_severity(self, severity: EventSeverity) -> EventSeverity:
        """Escalate severity for corroborated incidents."""
        escalation = {
            EventSeverity.INFO: EventSeverity.ADVISORY,
            EventSeverity.ADVISORY: EventSeverity.WARNING,
            EventSeverity.WARNING: EventSeverity.CRITICAL,
            EventSeverity.CRITICAL: EventSeverity.CRITICAL,
        }
        return escalation.get(severity, severity)

    async def _get_client(self):
        """Get or create HTTP client."""
        if self._client is not None:
            return self._client
        
        try:
            import httpx
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "httpx is not installed. Install with: pip install httpx"
            ) from exc
        
        self._client = httpx.AsyncClient()
        return self._client
