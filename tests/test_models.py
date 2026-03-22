from __future__ import annotations

import uuid

from osk.models import (
    Alert,
    AuditEvent,
    Event,
    EventCategory,
    EventSeverity,
    Member,
    MemberRole,
    MemberStatus,
    Operation,
    Pin,
    SitRep,
    Stream,
    StreamStatus,
    StreamType,
    SynthesisFinding,
)


def test_operation_defaults() -> None:
    op = Operation(name="Test Op")
    assert op.name == "Test Op"
    assert op.token
    assert op.coordinator_token
    assert op.started_at is not None


def test_member_creation() -> None:
    member = Member(name="Jay", role=MemberRole.OBSERVER)
    assert member.id is not None
    assert member.role == MemberRole.OBSERVER
    assert member.status == MemberStatus.CONNECTED
    assert member.reconnect_token
    assert member.last_seen_at is not None


def test_member_role_values() -> None:
    assert MemberRole.OBSERVER.value == "observer"
    assert MemberRole.SENSOR.value == "sensor"
    assert MemberRole.COORDINATOR.value == "coordinator"


def test_stream_creation() -> None:
    stream = Stream(member_id=uuid.uuid4(), stream_type=StreamType.AUDIO)
    assert stream.status == StreamStatus.ACTIVE


def test_event_creation() -> None:
    event = Event(
        severity=EventSeverity.WARNING,
        category=EventCategory.POLICE_ACTION,
        text="Police forming line on 5th St",
        source_member_id=uuid.uuid4(),
    )
    assert event.id is not None
    assert event.timestamp is not None


def test_event_severity_ordering() -> None:
    assert EventSeverity.INFO.level < EventSeverity.ADVISORY.level
    assert EventSeverity.ADVISORY.level < EventSeverity.WARNING.level
    assert EventSeverity.WARNING.level < EventSeverity.CRITICAL.level


def test_alert_from_event() -> None:
    event_id = uuid.uuid4()
    alert = Alert(
        event_id=event_id,
        severity=EventSeverity.WARNING,
        category=EventCategory.ESCALATION,
        text="Escalation detected near you",
    )
    assert alert.event_id == event_id


def test_pin_creation() -> None:
    pin = Pin(event_id=uuid.uuid4(), pinned_by=uuid.uuid4())
    assert pin.pinned_at is not None


def test_sitrep_creation() -> None:
    sitrep = SitRep(text="Crowd stable, two exits clear", trend="stable")
    assert sitrep.timestamp is not None
    assert sitrep.trend == "stable"


def test_synthesis_finding_creation() -> None:
    finding = SynthesisFinding(
        signature="police_action:movement-north",
        category=EventCategory.POLICE_ACTION,
        severity=EventSeverity.WARNING,
        title="Police Action",
        summary="Police advancing north.",
    )
    assert finding.id is not None
    assert finding.status.value == "open"
    assert finding.observation_count == 1


def test_operation_serialization() -> None:
    operation = Operation(name="Test")
    data = operation.model_dump()
    assert data["name"] == "Test"
    assert "token" in data
    assert "coordinator_token" in data


def test_member_serialization_excludes_reconnect_token() -> None:
    member = Member(name="Jay")
    data = member.model_dump(mode="json")
    assert "reconnect_token" not in data


def test_audit_event_defaults() -> None:
    audit = AuditEvent(operation_id=uuid.uuid4(), actor_type="system", action="started")
    assert audit.id is not None
    assert audit.details == {}


def test_event_serialization() -> None:
    event = Event(
        severity=EventSeverity.CRITICAL,
        category=EventCategory.MEDICAL,
        text="Medical emergency",
        source_member_id=uuid.uuid4(),
    )
    data = event.model_dump(mode="json")
    assert data["severity"] == "critical"
    assert data["category"] == "medical"
