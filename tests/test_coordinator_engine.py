from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from osk.coordinator_engine import CoordinatorEngine, ROUTE_GAP_KIND
from osk.models import EventCategory, EventSeverity, Member, MemberRole, Operation, SynthesisFinding


def _sensor(name: str, *, stale: bool = False) -> Member:
    member = Member(name=name, role=MemberRole.SENSOR)
    member.last_seen_at = datetime.now(timezone.utc) - (
        timedelta(seconds=120) if stale else timedelta(seconds=5)
    )
    member.last_gps_at = datetime.now(timezone.utc) - timedelta(seconds=10)
    return member


@pytest.mark.asyncio
async def test_process_finding_creates_gap_and_assigns_task() -> None:
    sensor = _sensor("Sensor-1")
    operation_manager = SimpleNamespace(
        operation=Operation(name="Test Op"),
        members={sensor.id: sensor},
    )
    db = MagicMock()
    db.get_active_coordinator_recommendation = AsyncMock(return_value=None)
    db.upsert_open_coordinator_gap = AsyncMock(
        return_value={
            "id": sensor.id,
            "kind": ROUTE_GAP_KIND,
            "title": "Confirm safest exit",
            "summary": "Police advancing north.",
            "requested_route_key": "north_exit",
            "status": "open",
        }
    )
    db.get_coordinator_state = AsyncMock(
        return_value={
            "gaps": [{"id": sensor.id, "kind": ROUTE_GAP_KIND, "status": "open", "requested_route_key": "north_exit", "title": "Confirm safest exit", "summary": "Police advancing north."}],
            "tasks": [],
            "recommendations": [],
            "active_gap": {"id": sensor.id, "kind": ROUTE_GAP_KIND, "status": "open", "requested_route_key": "north_exit", "title": "Confirm safest exit", "summary": "Police advancing north."},
            "active_task": None,
            "active_recommendation": None,
        }
    )
    db.insert_coordinator_task = AsyncMock(
        return_value={
            "id": sensor.id,
            "gap_id": sensor.id,
            "assigned_member_id": sensor.id,
            "status": "open",
            "prompt": "Move to the north side and send a quick update on police presence and crowd movement.",
            "assignment_reason": "Sensor-1 is an active sensor with a recent GPS fix near the field scene.",
            "requested_route_key": "north_exit",
            "requested_location_label": "north side of the intersection",
            "requested_viewpoint": "face north toward the 17th Street corridor",
            "details": {},
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    )
    conn_manager = MagicMock()
    conn_manager.send_to = AsyncMock()
    engine = CoordinatorEngine(
        db=db,
        operation_manager=operation_manager,
        conn_manager=conn_manager,
    )
    finding = SynthesisFinding(
        signature="police_action:north",
        category=EventCategory.POLICE_ACTION,
        severity=EventSeverity.WARNING,
        title="Police Action",
        summary="Police advancing north.",
    )

    await engine.process_finding(finding)

    db.upsert_open_coordinator_gap.assert_awaited_once()
    db.insert_coordinator_task.assert_awaited_once()
    conn_manager.send_to.assert_awaited_once()
    payload = conn_manager.send_to.await_args.args[1]
    assert payload["type"] == "coordinator_task"
    assert payload["requested_route_key"] == "north_exit"


@pytest.mark.asyncio
async def test_refresh_supersedes_stale_task_with_fresher_sensor() -> None:
    stale_sensor = _sensor("Stale Sensor", stale=True)
    fresh_sensor = _sensor("Fresh Sensor")
    gap_id = stale_sensor.id
    stale_task_id = fresh_sensor.id
    operation_manager = SimpleNamespace(
        operation=Operation(name="Test Op"),
        members={stale_sensor.id: stale_sensor, fresh_sensor.id: fresh_sensor},
    )
    db = MagicMock()
    db.get_coordinator_state = AsyncMock(
        return_value={
            "gaps": [{"id": gap_id, "status": "open", "requested_route_key": "north_exit", "title": "Confirm safest exit", "summary": "Need fresh route confirmation."}],
            "tasks": [{"id": stale_task_id, "gap_id": gap_id, "assigned_member_id": stale_sensor.id, "status": "open", "requested_route_key": "north_exit", "prompt": "Old prompt", "assignment_reason": "Old reason", "details": {}, "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)}],
            "recommendations": [],
            "active_gap": {"id": gap_id, "status": "open", "requested_route_key": "north_exit", "title": "Confirm safest exit", "summary": "Need fresh route confirmation."},
            "active_task": {"id": stale_task_id, "gap_id": gap_id, "assigned_member_id": stale_sensor.id, "status": "open", "requested_route_key": "north_exit", "prompt": "Old prompt", "assignment_reason": "Old reason", "details": {}, "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)},
            "active_recommendation": None,
        }
    )
    db.update_coordinator_task_status = AsyncMock(
        return_value={
            "id": stale_task_id,
            "gap_id": gap_id,
            "assigned_member_id": stale_sensor.id,
            "status": "superseded",
            "prompt": "Old prompt",
            "assignment_reason": "Old reason",
            "requested_route_key": "north_exit",
            "requested_location_label": "north side of the intersection",
            "requested_viewpoint": "face north toward the 17th Street corridor",
            "details": {},
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "cancelled_at": datetime.now(timezone.utc),
        }
    )
    db.insert_coordinator_task = AsyncMock(
        return_value={
            "id": fresh_sensor.id,
            "gap_id": gap_id,
            "assigned_member_id": fresh_sensor.id,
            "status": "open",
            "prompt": "Move to the north side and send a quick update on police presence and crowd movement.",
            "assignment_reason": "Fresh Sensor is an active sensor with a recent GPS fix near the field scene.",
            "requested_route_key": "north_exit",
            "requested_location_label": "north side of the intersection",
            "requested_viewpoint": "face north toward the 17th Street corridor",
            "details": {},
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    )
    conn_manager = MagicMock()
    conn_manager.send_to = AsyncMock()
    engine = CoordinatorEngine(
        db=db,
        operation_manager=operation_manager,
        conn_manager=conn_manager,
    )

    await engine.refresh()

    db.update_coordinator_task_status.assert_awaited_once()
    db.insert_coordinator_task.assert_awaited_once()
    assert conn_manager.send_to.await_count == 2


@pytest.mark.asyncio
async def test_process_member_report_completes_task_and_emits_recommendation() -> None:
    sensor = _sensor("Sensor-1")
    event_id = sensor.id
    gap_id = sensor.id
    task_id = Operation(name="Task Ref").id
    operation_manager = SimpleNamespace(
        operation=Operation(name="Test Op"),
        members={sensor.id: sensor},
    )
    db = MagicMock()
    db.get_open_coordinator_task_for_member = AsyncMock(
        return_value={
            "id": task_id,
            "gap_id": gap_id,
            "assigned_member_id": sensor.id,
            "status": "open",
            "prompt": "Move north and send a quick update.",
            "assignment_reason": "Freshest sensor.",
            "requested_route_key": "north_exit",
            "requested_location_label": "north side of the intersection",
            "requested_viewpoint": "face north toward the 17th Street corridor",
            "details": {},
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    )
    db.update_coordinator_task_status = AsyncMock(
        return_value={
            "id": task_id,
            "gap_id": gap_id,
            "assigned_member_id": sensor.id,
            "status": "completed",
            "prompt": "Move north and send a quick update.",
            "assignment_reason": "Freshest sensor.",
            "requested_route_key": "north_exit",
            "requested_location_label": "north side of the intersection",
            "requested_viewpoint": "face north toward the 17th Street corridor",
            "details": {},
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "completed_at": datetime.now(timezone.utc),
        }
    )
    db.update_coordinator_gap_status = AsyncMock(return_value={"id": gap_id, "status": "resolved"})
    db.get_active_coordinator_recommendation = AsyncMock(return_value=None)
    db.insert_coordinator_recommendation = AsyncMock(return_value={"route_key": "north_exit", "status": "emitted"})
    conn_manager = MagicMock()
    conn_manager.send_to = AsyncMock()
    engine = CoordinatorEngine(
        db=db,
        operation_manager=operation_manager,
        conn_manager=conn_manager,
    )

    await engine.process_member_report(
        member_id=sensor.id,
        report_text="North route looks clear and passable.",
        event_id=event_id,
        timestamp=datetime.now(timezone.utc),
    )

    db.update_coordinator_task_status.assert_awaited_once()
    db.update_coordinator_gap_status.assert_awaited_once()
    db.insert_coordinator_recommendation.assert_awaited_once()
