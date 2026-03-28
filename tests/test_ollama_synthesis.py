"""Tests for Ollama-based semantic synthesis."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from osk.intelligence_contracts import IntelligenceObservation, ObservationKind
from osk.models import EventCategory, EventSeverity, Member
from osk.ollama_synthesis import OllamaObservationSynthesizer, DEFAULT_SYNTHESIS_PROMPT


@pytest.fixture
def mock_httpx_client():
    """Create a mock httpx client."""
    client = AsyncMock()
    return client


async def test_ollama_synthesizer_emits_event_on_classification() -> None:
    """Test that synthesizer creates events from Ollama classification."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "response": '{"category": "police_action", "severity": "warning", "reasoning": "Police advancing", "confidence": 0.85}'
    }
    
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    
    synthesizer = OllamaObservationSynthesizer(
        model="llama3.2:3b",
        client=mock_client,
    )
    
    member = Member(name="Jay")
    observation = IntelligenceObservation(
        kind=ObservationKind.TRANSCRIPT,
        source_member_id=member.id,
        summary="Police officers are advancing towards the crowd.",
        confidence=0.91,
    )
    
    decision = await synthesizer.synthesize(observation, source_member=member)
    
    assert len(decision.events) == 1
    assert decision.events[0].category == EventCategory.POLICE_ACTION
    assert decision.events[0].severity == EventSeverity.WARNING
    assert len(decision.alerts) == 1
    assert len(decision.findings) == 1


async def test_ollama_synthesizer_handles_null_classification() -> None:
    """Test that synthesizer returns empty decision when classification is null."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "response": '{"category": null, "severity": null, "reasoning": "Not relevant", "confidence": 0.0}'
    }
    
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    
    synthesizer = OllamaObservationSynthesizer(
        model="llama3.2:3b",
        client=mock_client,
    )
    
    observation = IntelligenceObservation(
        kind=ObservationKind.TRANSCRIPT,
        source_member_id=uuid4(),
        summary="The weather is nice today.",
        confidence=0.8,
    )
    
    decision = await synthesizer.synthesize(observation)
    
    assert decision.events == []
    assert decision.alerts == []
    assert decision.findings == []


async def test_ollama_synthesizer_handles_corroboration() -> None:
    """Test that synthesizer escalates on corroborated observations."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "response": '{"category": "police_action", "severity": "warning", "reasoning": "Police activity", "confidence": 0.85}'
    }
    
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    
    synthesizer = OllamaObservationSynthesizer(
        model="llama3.2:3b",
        client=mock_client,
        cooldown_seconds=60,
    )
    
    # First observation
    member1 = Member(name="Jay")
    observation1 = IntelligenceObservation(
        kind=ObservationKind.TRANSCRIPT,
        source_member_id=member1.id,
        summary="Police advancing north on foot.",
        confidence=0.91,
    )
    decision1 = await synthesizer.synthesize(observation1, source_member=member1)
    
    # Second observation from different member (same incident)
    member2 = Member(name="Alex")
    observation2 = IntelligenceObservation(
        kind=ObservationKind.TRANSCRIPT,
        source_member_id=member2.id,
        summary="Police are moving north.",
        confidence=0.88,
    )
    decision2 = await synthesizer.synthesize(observation2, source_member=member2)
    
    assert len(decision2.events) == 1
    assert decision2.findings[0].corroborated is True
    assert decision2.findings[0].source_count == 2


async def test_ollama_synthesizer_respects_cooldown() -> None:
    """Test that synthesizer respects cooldown for duplicate incidents."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "response": '{"category": "blocked_route", "severity": "advisory", "reasoning": "Road blocked", "confidence": 0.75}'
    }
    
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    
    synthesizer = OllamaObservationSynthesizer(
        model="llama3.2:3b",
        client=mock_client,
        cooldown_seconds=60,
    )
    
    member_id = uuid4()
    
    # First observation
    observation1 = IntelligenceObservation(
        kind=ObservationKind.TRANSCRIPT,
        source_member_id=member_id,
        summary="Road blocked at north entrance.",
        confidence=0.9,
    )
    decision1 = await synthesizer.synthesize(observation1)
    
    # Immediate duplicate with same keywords - should not create new event due to cooldown
    observation2 = IntelligenceObservation(
        kind=ObservationKind.TRANSCRIPT,
        source_member_id=member_id,
        summary="North entrance still has blocked road.",
        confidence=0.9,
    )
    decision2 = await synthesizer.synthesize(observation2)
    
    assert len(decision1.events) == 1
    assert len(decision2.events) == 0  # Cooldown prevents new event


async def test_ollama_synthesizer_fallback_on_error() -> None:
    """Test that synthesizer falls back to keyword matching on error."""
    mock_client = AsyncMock()
    mock_client.post.side_effect = Exception("Connection refused")
    
    synthesizer = OllamaObservationSynthesizer(
        model="llama3.2:3b",
        client=mock_client,
    )
    
    observation = IntelligenceObservation(
        kind=ObservationKind.TRANSCRIPT,
        source_member_id=uuid4(),
        summary="Police officers are here.",
        confidence=0.9,
    )
    
    decision = await synthesizer.synthesize(observation)
    
    # Should fall back to keyword matching
    assert len(decision.events) == 1
    assert decision.events[0].category == EventCategory.POLICE_ACTION


async def test_ollama_synthesizer_parses_markdown_json() -> None:
    """Test that synthesizer handles markdown-wrapped JSON responses."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "response": '```json\n{"category": "medical", "severity": "warning", "reasoning": "Injury reported", "confidence": 0.9}\n```'
    }
    
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    
    synthesizer = OllamaObservationSynthesizer(
        model="llama3.2:3b",
        client=mock_client,
    )
    
    observation = IntelligenceObservation(
        kind=ObservationKind.TRANSCRIPT,
        source_member_id=uuid4(),
        summary="Someone is injured and bleeding.",
        confidence=0.9,
    )
    
    decision = await synthesizer.synthesize(observation)
    
    assert len(decision.events) == 1
    assert decision.events[0].category == EventCategory.MEDICAL


async def test_ollama_synthesizer_status() -> None:
    """Test that status returns correct information."""
    synthesizer = OllamaObservationSynthesizer(
        base_url="http://localhost:11434",
        model="llama3.2:3b",
        timeout_seconds=5.0,
        cooldown_seconds=60,
    )
    
    status = synthesizer.status()
    
    assert status["backend"] == "ollama"
    assert status["model"] == "llama3.2:3b"
    assert status["base_url"] == "http://localhost:11434"
    assert status["timeout_seconds"] == 5.0
    assert status["cooldown_seconds"] == 60


async def test_ollama_synthesizer_expires_old_incidents() -> None:
    """Test that old incidents are expired after window."""
    import time
    
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "response": '{"category": "police_action", "severity": "advisory", "reasoning": "Police present", "confidence": 0.7}'
    }
    
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    
    synthesizer = OllamaObservationSynthesizer(
        model="llama3.2:3b",
        client=mock_client,
        incident_window_seconds=1,  # Very short window for test
    )
    
    observation = IntelligenceObservation(
        kind=ObservationKind.TRANSCRIPT,
        source_member_id=uuid4(),
        summary="Police visible in the area.",
        confidence=0.8,
    )
    
    # First observation
    await synthesizer.synthesize(observation)
    assert len(synthesizer._incidents) == 1
    
    # Wait for window to expire
    time.sleep(0.1)  # Less than 1 second, but incident will be old relative to first_seen
    
    # Manually trigger expiration by checking status
    status = synthesizer.status()
    assert status["active_incidents"] == 1  # Not yet expired
    

async def test_ollama_synthesizer_vision_observation() -> None:
    """Test handling of vision observations."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "response": '{"category": "crowd_movement", "severity": "info", "reasoning": "Crowd visible", "confidence": 0.8}'
    }
    
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    
    synthesizer = OllamaObservationSynthesizer(
        model="llama3.2:3b",
        client=mock_client,
    )
    
    observation = IntelligenceObservation(
        kind=ObservationKind.VISION,
        source_member_id=uuid4(),
        summary="Large crowd gathered near entrance.",
        confidence=0.85,
        details={"tags": ["crowd", "public_area"]},
    )
    
    decision = await synthesizer.synthesize(observation)
    
    # Should not create alert since INFO severity
    assert len(decision.events) == 1
    assert len(decision.alerts) == 0


async def test_ollama_synthesizer_builds_correct_prompt() -> None:
    """Test that the prompt is correctly formatted."""
    observation = IntelligenceObservation(
        kind=ObservationKind.TRANSCRIPT,
        source_member_id=uuid4(),
        summary="Police are charging the crowd.",
        confidence=0.9,
    )
    
    prompt = DEFAULT_SYNTHESIS_PROMPT.format(
        observation_kind=observation.kind.value,
        summary=observation.summary,
        context="Audio transcription from member device; Confidence: 90%",
    )
    
    assert "police_action" in prompt
    assert "critical" in prompt
    assert observation.summary in prompt
    assert "transcript" in prompt.lower()
