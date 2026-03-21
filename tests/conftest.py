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
    db.update_operation_token = AsyncMock()
    db.insert_member = AsyncMock()
    db.update_member_role = AsyncMock()
    db.update_member_status = AsyncMock()
    db.update_member_gps = AsyncMock()
    db.insert_event = AsyncMock()
    db.insert_alert = AsyncMock()
    db.insert_pin = AsyncMock()
    db.insert_sitrep = AsyncMock()
    db.get_events_since = AsyncMock(return_value=[])
    db.get_latest_sitrep = AsyncMock(return_value=None)
    db.get_members = AsyncMock(return_value=[])
    return db
