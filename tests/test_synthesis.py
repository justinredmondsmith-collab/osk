from __future__ import annotations

from uuid import uuid4

from osk.intelligence_contracts import IntelligenceObservation, ObservationKind
from osk.models import EventCategory, EventSeverity, Member
from osk.synthesis import HeuristicObservationSynthesizer


async def test_heuristic_synthesizer_emits_police_event_and_alert() -> None:
    synthesizer = HeuristicObservationSynthesizer(cooldown_seconds=60)
    member = Member(name="Jay")
    member.latitude = 39.75
    member.longitude = -104.99
    observation = IntelligenceObservation(
        kind=ObservationKind.TRANSCRIPT,
        source_member_id=member.id,
        summary="Police officers advancing north on foot.",
        confidence=0.91,
    )

    decision = await synthesizer.synthesize(observation, source_member=member)

    assert len(decision.events) == 1
    assert decision.events[0].category == EventCategory.POLICE_ACTION
    assert decision.events[0].severity == EventSeverity.WARNING
    assert decision.events[0].latitude == 39.75
    assert len(decision.alerts) == 1
    assert decision.alerts[0].event_id == decision.events[0].id


async def test_heuristic_synthesizer_dedupes_within_cooldown() -> None:
    synthesizer = HeuristicObservationSynthesizer(cooldown_seconds=60)
    observation = IntelligenceObservation(
        kind=ObservationKind.VISION,
        source_member_id=uuid4(),
        summary="Blocked route at the east entrance.",
        confidence=0.88,
    )

    first = await synthesizer.synthesize(observation)
    second = await synthesizer.synthesize(observation)

    assert len(first.events) == 1
    assert second.events == []
    assert second.alerts == []


async def test_heuristic_synthesizer_ignores_low_signal_observations() -> None:
    synthesizer = HeuristicObservationSynthesizer(cooldown_seconds=60)
    observation = IntelligenceObservation(
        kind=ObservationKind.LOCATION,
        source_member_id=uuid4(),
        summary="Cluster forming",
        confidence=0.4,
        details={"cluster_size": 1},
    )

    decision = await synthesizer.synthesize(observation)

    assert decision.events == []
    assert decision.alerts == []
