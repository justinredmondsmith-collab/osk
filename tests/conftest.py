from __future__ import annotations

import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from osk.models import (  # noqa: E402
    Event,
    EventCategory,
    EventSeverity,
    Member,
    MemberRole,
    Operation,
)


@pytest.fixture
def operation() -> Operation:
    return Operation(name="Test Operation")


@pytest.fixture
def coordinator(operation: Operation) -> Member:
    return Member(name="Coordinator", role=MemberRole.COORDINATOR)


@pytest.fixture
def sensor_member() -> Member:
    return Member(name="Sensor-1", role=MemberRole.SENSOR)


@pytest.fixture
def observer_member() -> Member:
    return Member(name="Observer-1", role=MemberRole.OBSERVER)


@pytest.fixture
def sample_event() -> Event:
    return Event(
        severity=EventSeverity.WARNING,
        category=EventCategory.POLICE_ACTION,
        text="Police staging at 5th and Main",
        source_member_id=uuid.uuid4(),
        latitude=39.75,
        longitude=-104.99,
    )


@pytest.fixture
def mock_db() -> MagicMock:
    db = MagicMock()
    db.connect = AsyncMock()
    db.close = AsyncMock()
    db.insert_operation = AsyncMock()
    db.get_active_operation = AsyncMock(return_value=None)
    db.mark_operation_stopped = AsyncMock()
    db.mark_members_disconnected = AsyncMock()
    db.update_operation_token = AsyncMock()
    db.insert_member = AsyncMock()
    db.update_member_role = AsyncMock()
    db.update_member_status = AsyncMock()
    db.mark_member_connected = AsyncMock()
    db.update_member_heartbeat = AsyncMock()
    db.update_member_gps = AsyncMock()
    db.insert_event = AsyncMock()
    db.insert_alert = AsyncMock()
    db.insert_intelligence_observation = AsyncMock()
    db.upsert_synthesis_finding = AsyncMock()
    db.get_synthesis_finding = AsyncMock(return_value=None)
    db.get_synthesis_finding_detail = AsyncMock(return_value=None)
    db.get_synthesis_finding_notes = AsyncMock(return_value=[])
    db.update_synthesis_finding_status = AsyncMock(return_value=None)
    db.escalate_synthesis_finding = AsyncMock(return_value=None)
    db.insert_synthesis_finding_note = AsyncMock()
    db.claim_ingest_receipt = AsyncMock(return_value=False)
    db.prune_ingest_receipts = AsyncMock()
    db.insert_pin = AsyncMock()
    db.insert_sitrep = AsyncMock()
    db.insert_audit_event = AsyncMock()
    db.get_events_since = AsyncMock(return_value=[])
    db.get_recent_intelligence_observations = AsyncMock(return_value=[])
    db.get_recent_synthesis_findings = AsyncMock(return_value=[])
    db.get_synthesis_findings = AsyncMock(return_value=[])
    db.get_synthesis_finding_correlations = AsyncMock(return_value=None)
    db.get_review_feed = AsyncMock(return_value=[])
    db.get_events = AsyncMock(return_value=[])
    db.get_latest_sitrep = AsyncMock(return_value=None)
    db.get_recent_sitreps = AsyncMock(return_value=[])
    db.get_members = AsyncMock(return_value=[])
    db.get_audit_events = AsyncMock(return_value=[])
    return db
