"""Deterministic coordinator engine for the first guided demo slice."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from osk.models import (
    CoordinatorGap,
    CoordinatorGapStatus,
    CoordinatorRecommendation,
    CoordinatorRecommendationStatus,
    CoordinatorTask,
    CoordinatorTaskStatus,
    EventCategory,
    EventSeverity,
    MemberRole,
    MemberStatus,
    SynthesisFinding,
)

logger = logging.getLogger(__name__)

ROUTE_GAP_KIND = "route_viability_confirmation"

ROUTE_CANDIDATES: dict[str, dict[str, str]] = {
    "north_exit": {
        "title": "North Exit",
        "summary": "Move north to the 17th Street corridor and exit through the open side streets.",
        "location_label": "north side of the intersection",
        "viewpoint": "face north toward the 17th Street corridor",
        "prompt": (
            "Move to the north side and send a quick update on police presence and crowd movement."
        ),
    },
    "east_exit": {
        "title": "East Exit",
        "summary": (
            "Shift east toward the river path and clear the area "
            "using the lower-density side route."
        ),
        "location_label": "east side escape path",
        "viewpoint": "face east toward the river path",
        "prompt": (
            "Move to the east side route and send a quick update "
            "on police presence and crowd movement."
        ),
    },
}

ROUTE_CLEAR_TERMS = ("clear", "open", "passable", "moving", "light", "safe")
ROUTE_BLOCKED_TERMS = (
    "blocked",
    "closed",
    "trapped",
    "tear gas",
    "kettle",
    "kettling",
    "line formed",
    "line is forming",
    "crowded",
    "impassable",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_uuid(value: Any) -> uuid.UUID | None:
    if value is None or isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _isoformat(value: Any) -> str | None:
    if not isinstance(value, datetime):
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class CoordinatorEngine:
    def __init__(
        self,
        *,
        db,
        operation_manager,
        conn_manager,
        heartbeat_timeout_seconds: int = 45,
    ) -> None:
        self.db = db
        self.operation_manager = operation_manager
        self.conn_manager = conn_manager
        self.heartbeat_timeout_seconds = max(int(heartbeat_timeout_seconds), 1)

    async def process_finding(self, finding: SynthesisFinding | dict[str, Any]) -> dict | None:
        operation = getattr(self.operation_manager, "operation", None)
        if operation is None:
            return None
        if isinstance(finding, SynthesisFinding):
            finding_row = finding.model_dump(mode="json")
        else:
            finding_row = dict(finding)
        if not self._finding_requires_coordination(finding_row):
            return None

        active_recommendation = await self.db.get_active_coordinator_recommendation(operation.id)
        if active_recommendation and self._finding_invalidates_recommendation(
            active_recommendation, finding_row
        ):
            await self._invalidate_recommendation(
                active_recommendation,
                reason=(
                    f"New {finding_row.get('category', 'signal')} "
                    f"evidence contradicted the active route."
                ),
                details={"source_finding_id": str(finding_row.get("id") or "")},
            )

        route_key = self._route_from_text(
            f"{finding_row.get('title', '')} {finding_row.get('summary', '')}"
        )
        gap = CoordinatorGap(
            operation_id=operation.id,
            kind=ROUTE_GAP_KIND,
            title="Confirm safest exit",
            summary=str(
                finding_row.get("summary")
                or "New evidence changed route confidence. Request a fresh field update."
            ),
            severity=EventSeverity(str(finding_row.get("severity") or EventSeverity.WARNING.value)),
            requested_route_key=route_key or "north_exit",
            source_finding_id=_to_uuid(finding_row.get("id")),
            details={
                "trigger": "finding",
                "source_category": finding_row.get("category"),
                "source_title": finding_row.get("title"),
            },
        )
        stored_gap = await self.db.upsert_open_coordinator_gap(operation.id, gap)
        await self.refresh()
        return stored_gap

    async def process_member_report(
        self,
        *,
        member_id: uuid.UUID,
        report_text: str,
        event_id: uuid.UUID,
        timestamp: datetime,
    ) -> dict | None:
        operation = getattr(self.operation_manager, "operation", None)
        if operation is None:
            return None

        open_task = await self.db.get_open_coordinator_task_for_member(operation.id, member_id)
        if open_task is None:
            active_recommendation = await self.db.get_active_coordinator_recommendation(
                operation.id
            )
            if active_recommendation and self._text_invalidates_route(
                report_text, str(active_recommendation.get("route_key") or "")
            ):
                await self._invalidate_recommendation(
                    active_recommendation,
                    reason="Late field report contradicted the active recommendation.",
                    details={"event_id": str(event_id)},
                )
                gap = CoordinatorGap(
                    operation_id=operation.id,
                    kind=ROUTE_GAP_KIND,
                    title="Reconfirm safest exit",
                    summary=(
                        "A late field report contradicted the active route. "
                        "Request a new confirmation."
                    ),
                    requested_route_key="north_exit",
                    details={"trigger": "late_report", "event_id": str(event_id)},
                )
                await self.db.upsert_open_coordinator_gap(operation.id, gap)
                await self.refresh()
            return None

        requested_route_key = str(open_task.get("requested_route_key") or "north_exit")
        assessment = self._classify_report_text(report_text)
        updated_task = await self.db.update_coordinator_task_status(
            operation.id,
            _to_uuid(open_task["id"]),
            status=CoordinatorTaskStatus.COMPLETED,
            changed_at=timestamp,
            details={
                **dict(open_task.get("details") or {}),
                "completion_event_id": str(event_id),
                "report_assessment": assessment,
                "report_text": report_text,
            },
            completion_event_id=event_id,
        )
        if updated_task is not None:
            await self._push_task(updated_task)

        if assessment == "unknown":
            await self.refresh()
            return updated_task

        gap_status = await self.db.update_coordinator_gap_status(
            operation.id,
            _to_uuid(open_task["gap_id"]),
            status=CoordinatorGapStatus.RESOLVED,
            changed_at=timestamp,
            details={
                "resolution": assessment,
                "resolved_by_member_id": str(member_id),
                "completion_event_id": str(event_id),
            },
        )
        if assessment == "clear":
            await self._emit_recommendation(
                route_key=requested_route_key,
                gap_id=_to_uuid(open_task["gap_id"]),
                supporting_task_id=_to_uuid(open_task["id"]),
                emitted_at=timestamp,
                rationale="Field update confirmed the requested route remains viable.",
            )
            return gap_status

        active_recommendation = await self.db.get_active_coordinator_recommendation(operation.id)
        if active_recommendation and (
            str(active_recommendation.get("route_key") or "") == requested_route_key
        ):
            await self._invalidate_recommendation(
                active_recommendation,
                reason="Field update marked the active route as blocked.",
                details={"event_id": str(event_id)},
            )

        alternate_route = self._alternate_route(requested_route_key)
        if alternate_route is not None:
            await self._emit_recommendation(
                route_key=alternate_route,
                gap_id=_to_uuid(open_task["gap_id"]),
                supporting_task_id=_to_uuid(open_task["id"]),
                emitted_at=timestamp,
                rationale=(
                    "Field update blocked the requested route, so the "
                    "alternate scripted route is now preferred."
                ),
            )
        else:
            gap = CoordinatorGap(
                operation_id=operation.id,
                kind=ROUTE_GAP_KIND,
                title="Route no longer viable",
                summary=(
                    "The last confirmed route was blocked. Request a fresh evacuation assessment."
                ),
                requested_route_key="north_exit",
                details={"trigger": "route_blocked", "event_id": str(event_id)},
            )
            await self.db.upsert_open_coordinator_gap(operation.id, gap)
            await self.refresh()
        return gap_status

    async def refresh(self) -> dict[str, Any] | None:
        operation = getattr(self.operation_manager, "operation", None)
        if operation is None:
            return None
        state = await self.db.get_coordinator_state(operation.id, limit=10)
        active_gap = state.get("active_gap")
        active_task = state.get("active_task")
        if active_task is not None:
            assigned_member_id = _to_uuid(active_task.get("assigned_member_id"))
            if assigned_member_id is not None and self._eligible_sensor_by_id(assigned_member_id):
                return state
            replacement = self._pick_best_sensor(exclude_member_id=assigned_member_id)
            if replacement is None:
                cancelled = await self.db.update_coordinator_task_status(
                    operation.id,
                    _to_uuid(active_task["id"]),
                    status=CoordinatorTaskStatus.CANCELLED,
                    changed_at=_utcnow(),
                    details={
                        **dict(active_task.get("details") or {}),
                        "cancellation_reason": (
                            "No eligible sensor was available for the open task."
                        ),
                    },
                )
                if cancelled is not None:
                    await self._push_task(cancelled)
                return state

            new_task = self._build_task(active_gap, replacement)
            superseded = await self.db.update_coordinator_task_status(
                operation.id,
                _to_uuid(active_task["id"]),
                status=CoordinatorTaskStatus.SUPERSEDED,
                changed_at=new_task.created_at,
                details={
                    **dict(active_task.get("details") or {}),
                    "supersession_reason": "Assigned member went stale or disconnected.",
                },
                superseded_by_task_id=new_task.id,
            )
            if superseded is not None:
                await self._push_task(superseded)
            stored_task = await self.db.insert_coordinator_task(operation.id, new_task)
            await self._push_task(stored_task)
            return state

        if active_gap is None:
            return state
        assignee = self._pick_best_sensor()
        if assignee is None:
            return state
        new_task = self._build_task(active_gap, assignee)
        stored_task = await self.db.insert_coordinator_task(operation.id, new_task)
        await self._push_task(stored_task)
        return state

    async def push_current_task(self, member_id: uuid.UUID) -> dict | None:
        operation = getattr(self.operation_manager, "operation", None)
        if operation is None:
            return None
        task = await self.db.get_open_coordinator_task_for_member(operation.id, member_id)
        if task is None:
            return None
        await self._push_task(task)
        return task

    def _build_task(self, gap_row: dict[str, Any] | None, member) -> CoordinatorTask:
        operation = getattr(self.operation_manager, "operation", None)
        if operation is None or gap_row is None:
            raise RuntimeError("CoordinatorEngine requires an active operation and gap")
        route_key = str(gap_row.get("requested_route_key") or "north_exit")
        route = ROUTE_CANDIDATES.get(route_key, ROUTE_CANDIDATES["north_exit"])
        created_at = _utcnow()
        return CoordinatorTask(
            operation_id=operation.id,
            gap_id=_to_uuid(gap_row["id"]),
            assigned_member_id=member.id,
            prompt=route["prompt"],
            assignment_reason=self._assignment_reason(member),
            requested_route_key=route_key,
            requested_location_label=route["location_label"],
            requested_viewpoint=route["viewpoint"],
            created_at=created_at,
            updated_at=created_at,
            details={
                "gap_title": gap_row.get("title"),
                "gap_summary": gap_row.get("summary"),
                "assigned_member_name": getattr(member, "name", "Sensor"),
            },
        )

    def _assignment_reason(self, member) -> str:
        if getattr(member, "last_gps_at", None):
            return f"{member.name} is an active sensor with a recent GPS fix near the field scene."
        return f"{member.name} is the freshest connected sensor available for route confirmation."

    def _eligible_sensor_by_id(self, member_id: uuid.UUID):
        member = getattr(self.operation_manager, "members", {}).get(member_id)
        if member is None:
            return None
        if getattr(member, "role", None) != MemberRole.SENSOR:
            return None
        if getattr(member, "status", None) == MemberStatus.DISCONNECTED:
            return None
        last_seen_at = getattr(member, "last_seen_at", None)
        if not isinstance(last_seen_at, datetime):
            return member
        max_age = self.heartbeat_timeout_seconds * 2
        if (_utcnow() - last_seen_at).total_seconds() > max_age:
            return None
        return member

    def _pick_best_sensor(self, exclude_member_id: uuid.UUID | None = None):
        eligible = []
        for member in getattr(self.operation_manager, "members", {}).values():
            if exclude_member_id is not None and getattr(member, "id", None) == exclude_member_id:
                continue
            if self._eligible_sensor_by_id(getattr(member, "id", None)) is None:
                continue
            eligible.append(member)
        if not eligible:
            return None
        eligible.sort(
            key=lambda member: (
                0 if getattr(member, "last_gps_at", None) else 1,
                -(
                    getattr(member, "last_seen_at", None).timestamp()
                    if isinstance(getattr(member, "last_seen_at", None), datetime)
                    else 0
                ),
            )
        )
        return eligible[0]

    async def _emit_recommendation(
        self,
        *,
        route_key: str,
        gap_id: uuid.UUID | None,
        supporting_task_id: uuid.UUID | None,
        emitted_at: datetime,
        rationale: str,
    ) -> dict:
        operation = getattr(self.operation_manager, "operation", None)
        if operation is None:
            raise RuntimeError("No active operation")
        active = await self.db.get_active_coordinator_recommendation(operation.id)
        if active is not None:
            if str(active.get("route_key") or "") == route_key:
                return active
            await self._invalidate_recommendation(
                active,
                reason="A newer route recommendation superseded the previous call.",
                details={"next_route_key": route_key},
            )
        route = ROUTE_CANDIDATES.get(route_key, ROUTE_CANDIDATES["north_exit"])
        recommendation = CoordinatorRecommendation(
            operation_id=operation.id,
            gap_id=gap_id,
            route_key=route_key,
            status=CoordinatorRecommendationStatus.EMITTED,
            title=f"Use {route['title']}",
            summary=route["summary"],
            rationale=rationale,
            supporting_task_id=supporting_task_id,
            details={"location_label": route["location_label"], "viewpoint": route["viewpoint"]},
            created_at=emitted_at,
            updated_at=emitted_at,
            emitted_at=emitted_at,
        )
        return await self.db.insert_coordinator_recommendation(operation.id, recommendation)

    async def _invalidate_recommendation(
        self,
        recommendation_row: dict[str, Any],
        *,
        reason: str,
        details: dict[str, Any] | None = None,
    ) -> dict | None:
        operation = getattr(self.operation_manager, "operation", None)
        if operation is None:
            return None
        recommendation_id = _to_uuid(recommendation_row.get("id"))
        if recommendation_id is None:
            return None
        return await self.db.invalidate_coordinator_recommendation(
            operation.id,
            recommendation_id,
            changed_at=_utcnow(),
            reason=reason,
            details=details,
        )

    async def _push_task(self, task_row: dict[str, Any]) -> None:
        member_id = _to_uuid(task_row.get("assigned_member_id"))
        if member_id is None:
            return
        route_key = str(task_row.get("requested_route_key") or "north_exit")
        route = ROUTE_CANDIDATES.get(route_key, ROUTE_CANDIDATES["north_exit"])
        payload = {
            "type": "coordinator_task",
            "task_id": str(task_row.get("id")),
            "gap_id": str(task_row.get("gap_id")),
            "status": str(task_row.get("status") or CoordinatorTaskStatus.OPEN.value),
            "prompt": task_row.get("prompt") or route["prompt"],
            "assignment_reason": task_row.get("assignment_reason") or "",
            "requested_route_key": route_key,
            "requested_route_title": route["title"],
            "requested_location_label": task_row.get("requested_location_label")
            or route["location_label"],
            "requested_viewpoint": task_row.get("requested_viewpoint") or route["viewpoint"],
            "details": task_row.get("details") or {},
            "created_at": _isoformat(task_row.get("created_at")),
            "updated_at": _isoformat(task_row.get("updated_at")),
            "completed_at": _isoformat(task_row.get("completed_at")),
            "cancelled_at": _isoformat(task_row.get("cancelled_at")),
        }
        try:
            await self.conn_manager.send_to(member_id, payload)
        except Exception:
            logger.exception(
                "Failed to push coordinator task %s to member %s",
                task_row.get("id"),
                member_id,
            )

    def _finding_requires_coordination(self, finding_row: dict[str, Any]) -> bool:
        category = str(finding_row.get("category") or "")
        return category in {
            EventCategory.BLOCKED_ROUTE.value,
            EventCategory.POLICE_ACTION.value,
            EventCategory.ESCALATION.value,
        }

    def _finding_invalidates_recommendation(
        self,
        recommendation_row: dict[str, Any],
        finding_row: dict[str, Any],
    ) -> bool:
        route_key = str(recommendation_row.get("route_key") or "")
        category = str(finding_row.get("category") or "")
        if category != EventCategory.BLOCKED_ROUTE.value:
            return False
        text = f"{finding_row.get('title', '')} {finding_row.get('summary', '')}"
        inferred_route = self._route_from_text(text)
        return inferred_route is None or inferred_route == route_key

    def _text_invalidates_route(self, report_text: str, route_key: str) -> bool:
        if self._classify_report_text(report_text) != "blocked":
            return False
        inferred_route = self._route_from_text(report_text)
        return inferred_route is None or inferred_route == route_key

    def _classify_report_text(self, report_text: str) -> str:
        text = report_text.lower()
        if any(term in text for term in ROUTE_BLOCKED_TERMS):
            return "blocked"
        if any(term in text for term in ROUTE_CLEAR_TERMS):
            return "clear"
        return "unknown"

    def _route_from_text(self, text: str) -> str | None:
        normalized = text.lower()
        if any(term in normalized for term in ("east", "river", "waterfront")):
            return "east_exit"
        if any(term in normalized for term in ("north", "17th", "corridor")):
            return "north_exit"
        return None

    def _alternate_route(self, route_key: str) -> str | None:
        if route_key == "north_exit":
            return "east_exit"
        if route_key == "east_exit":
            return None
        return "east_exit"
