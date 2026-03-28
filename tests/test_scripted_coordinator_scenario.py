from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from osk.coordinator_engine import ROUTE_GAP_KIND, CoordinatorEngine
from osk.models import EventCategory, EventSeverity, Member, MemberRole, Operation, SynthesisFinding


class InMemoryCoordinatorDb:
    def __init__(self) -> None:
        self.gap = None
        self.task = None
        self.recommendation = None

    async def get_active_coordinator_recommendation(self, operation_id):
        if self.recommendation and self.recommendation["status"] == "emitted":
            return dict(self.recommendation)
        return None

    async def upsert_open_coordinator_gap(self, operation_id, gap):
        if self.gap and self.gap["status"] == "open":
            self.gap.update(
                title=gap.title,
                summary=gap.summary,
                requested_route_key=gap.requested_route_key,
                updated_at=gap.updated_at,
            )
            return dict(self.gap)
        self.gap = gap.model_dump(mode="python")
        return dict(self.gap)

    async def get_coordinator_state(self, operation_id, *, limit=10):
        gaps = [dict(self.gap)] if self.gap else []
        tasks = [dict(self.task)] if self.task else []
        recommendations = [dict(self.recommendation)] if self.recommendation else []
        return {
            "gaps": gaps,
            "tasks": tasks,
            "recommendations": recommendations,
            "active_gap": next((row for row in gaps if row["status"] == "open"), None),
            "active_task": next((row for row in tasks if row["status"] == "open"), None),
            "active_recommendation": next(
                (row for row in recommendations if row["status"] == "emitted"),
                None,
            ),
        }

    async def insert_coordinator_task(self, operation_id, task):
        self.task = task.model_dump(mode="python")
        return dict(self.task)

    async def update_coordinator_task_status(
        self,
        operation_id,
        task_id,
        *,
        status,
        changed_at,
        details=None,
        completion_event_id=None,
        superseded_by_task_id=None,
    ):
        if self.task is None:
            return None
        self.task["status"] = status.value
        self.task["updated_at"] = changed_at
        if details is not None:
            self.task["details"] = details
        if completion_event_id is not None:
            self.task["completion_event_id"] = completion_event_id
        if superseded_by_task_id is not None:
            self.task["superseded_by_task_id"] = superseded_by_task_id
        if status.value == "completed":
            self.task["completed_at"] = changed_at
        if status.value in {"cancelled", "superseded"}:
            self.task["cancelled_at"] = changed_at
        return dict(self.task)

    async def get_open_coordinator_task_for_member(self, operation_id, member_id):
        if (
            self.task
            and self.task["status"] == "open"
            and self.task["assigned_member_id"] == member_id
        ):
            return dict(self.task)
        return None

    async def update_coordinator_gap_status(
        self, operation_id, gap_id, *, status, changed_at, details=None
    ):
        if self.gap is None:
            return None
        self.gap["status"] = status.value
        self.gap["updated_at"] = changed_at
        self.gap["details"] = details or {}
        if status.value == "resolved":
            self.gap["resolved_at"] = changed_at
        return dict(self.gap)

    async def insert_coordinator_recommendation(self, operation_id, recommendation):
        self.recommendation = recommendation.model_dump(mode="python")
        return dict(self.recommendation)

    async def invalidate_coordinator_recommendation(
        self, operation_id, recommendation_id, *, changed_at, reason, details=None
    ):
        if self.recommendation is None:
            return None
        self.recommendation["status"] = "invalidated"
        self.recommendation["updated_at"] = changed_at
        self.recommendation["invalidated_at"] = changed_at
        self.recommendation["invalidated_reason"] = reason
        self.recommendation["details"] = details or {}
        return dict(self.recommendation)


@pytest.mark.asyncio
async def test_scripted_scenario_assigns_then_switches_recommendation() -> None:
    sensor = Member(name="Sensor-1", role=MemberRole.SENSOR)
    sensor.last_seen_at = datetime.now(timezone.utc)
    sensor.last_gps_at = datetime.now(timezone.utc)
    operation_manager = SimpleNamespace(
        operation=Operation(name="Test Op"),
        members={sensor.id: sensor},
    )
    db = InMemoryCoordinatorDb()
    conn_manager = MagicMock()
    conn_manager.send_to = AsyncMock()
    engine = CoordinatorEngine(
        db=db,
        operation_manager=operation_manager,
        conn_manager=conn_manager,
    )

    await engine.process_finding(
        SynthesisFinding(
            signature="police_action:north",
            category=EventCategory.POLICE_ACTION,
            severity=EventSeverity.WARNING,
            title="Police Action",
            summary="Police advancing north.",
        )
    )

    assert db.gap["kind"] == ROUTE_GAP_KIND
    assert db.task["status"] == "open"
    assert db.task["requested_route_key"] == "north_exit"

    await engine.process_member_report(
        member_id=sensor.id,
        report_text="North route blocked by a police line forming.",
        event_id=Operation(name="Event Ref").id,
        timestamp=datetime.now(timezone.utc),
    )

    assert db.task["status"] == "completed"
    assert db.gap["status"] == "resolved"
    assert db.recommendation["route_key"] == "east_exit"
    assert db.recommendation["status"] == "emitted"
