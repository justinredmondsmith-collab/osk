from __future__ import annotations

from unittest.mock import patch
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
    assert len(decision.findings) == 1
    assert decision.findings[0].category == EventCategory.POLICE_ACTION
    assert decision.findings[0].latest_event_id == decision.events[0].id
    assert decision.sitrep is None


async def test_heuristic_synthesizer_emits_corroborated_follow_up() -> None:
    synthesizer = HeuristicObservationSynthesizer(cooldown_seconds=60)
    first = IntelligenceObservation(
        kind=ObservationKind.TRANSCRIPT,
        source_member_id=uuid4(),
        summary="Police officers advancing north on foot.",
        confidence=0.91,
    )
    second = IntelligenceObservation(
        kind=ObservationKind.VISION,
        source_member_id=uuid4(),
        summary="Police advancing north at the east entrance.",
        confidence=0.82,
        details={"tags": ["vehicle_description"]},
    )

    first_decision = await synthesizer.synthesize(first)
    second_decision = await synthesizer.synthesize(second)

    assert len(first_decision.events) == 1
    assert len(second_decision.events) == 1
    assert second_decision.events[0].category == EventCategory.POLICE_ACTION
    assert "Corroborated by 2 sources" in second_decision.events[0].text
    assert len(second_decision.alerts) == 1
    assert len(second_decision.findings) == 1
    assert second_decision.findings[0].corroborated is True
    assert second_decision.findings[0].source_count == 2
    assert second_decision.findings[0].signal_count == 2


async def test_heuristic_synthesizer_generates_periodic_sitrep() -> None:
    synthesizer = HeuristicObservationSynthesizer(
        cooldown_seconds=60,
        sitrep_interval_seconds=10,
    )
    first = IntelligenceObservation(
        kind=ObservationKind.TRANSCRIPT,
        source_member_id=uuid4(),
        summary="Police staging near the south exit.",
        confidence=0.82,
    )
    second = IntelligenceObservation(
        kind=ObservationKind.VISION,
        source_member_id=uuid4(),
        summary="Blocked route at the east entrance.",
        confidence=0.88,
    )

    with patch("osk.synthesis.time.monotonic", side_effect=[0.0, 12.0]):
        first_decision = await synthesizer.synthesize(first)
        second_decision = await synthesizer.synthesize(second)

    assert first_decision.sitrep is None
    assert second_decision.sitrep is not None
    assert "Recent updates:" in second_decision.sitrep.text
    assert second_decision.sitrep.trend in {"active", "escalating", "stable"}
    assert len(second_decision.findings) == 1


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
    assert decision.findings == []
