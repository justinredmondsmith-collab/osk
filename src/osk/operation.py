"""Operation lifecycle management."""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timezone

from osk.models import Member, MemberBufferStatus, MemberRole, MemberStatus, Operation
from osk.tasking import Task, TaskState, TaskOutcome, TaskType

logger = logging.getLogger(__name__)


class OperationManager:
    def __init__(self, db) -> None:
        self.db = db
        self.operation: Operation | None = None
        self.members: dict[uuid.UUID, Member] = {}
        self.tasks: dict[uuid.UUID, Task] = {}

    def _require_operation(self) -> Operation:
        if self.operation is None:
            raise RuntimeError("No active operation.")
        return self.operation

    def _require_member(self, member_id: uuid.UUID) -> Member:
        try:
            return self.members[member_id]
        except KeyError as exc:
            raise KeyError(f"Unknown member: {member_id}") from exc

    async def create(self, name: str) -> Operation:
        self.operation = Operation(name=name)
        self.members.clear()
        await self.db.insert_operation(
            self.operation.id,
            self.operation.name,
            self.operation.token,
            self.operation.coordinator_token,
            self.operation.started_at,
        )
        await self.db.insert_audit_event(
            self.operation.id,
            "system",
            "operation_created",
            details={"name": self.operation.name},
        )
        logger.info("Created operation %s (%s)", self.operation.name, self.operation.id)
        return self.operation

    async def create_or_resume(self, requested_name: str) -> tuple[Operation, bool]:
        active_operation = await self.db.get_active_operation()
        if active_operation is None:
            return await self.create(requested_name), False

        self.operation = Operation.model_validate(active_operation)
        await self.db.mark_members_disconnected(self.operation.id)
        self.members.clear()

        for row in await self.db.get_members(self.operation.id):
            member_data = dict(row)
            if member_data.get("status") == MemberStatus.CONNECTED.value:
                member_data["status"] = MemberStatus.DISCONNECTED.value
            member = Member.model_validate(member_data)
            self.members[member.id] = member

        await self.db.insert_audit_event(
            self.operation.id,
            "system",
            "operation_resumed",
            details={"requested_name": requested_name, "resumed_name": self.operation.name},
        )

        logger.info(
            "Resumed operation %s (%s); requested start name was %r",
            self.operation.name,
            self.operation.id,
            requested_name,
        )
        return self.operation, True

    def validate_token(self, token: str) -> bool:
        operation = self.operation
        if operation is None:
            return False
        return secrets.compare_digest(operation.token, token)

    def validate_coordinator_token(self, token: str) -> bool:
        operation = self.operation
        if operation is None:
            return False
        return secrets.compare_digest(operation.coordinator_token, token)

    async def rotate_token(self, op_id: uuid.UUID) -> str:
        operation = self._require_operation()
        if operation.id != op_id:
            raise ValueError(f"Operation id mismatch: expected {operation.id}, got {op_id}")

        new_token = secrets.token_urlsafe(32)
        operation.token = new_token
        await self.db.update_operation_token(op_id, new_token)
        logger.info("Rotated token for operation %s", op_id)
        return new_token

    async def stop(self) -> None:
        operation = self._require_operation()
        if operation.stopped_at is not None:
            return

        stopped_at = datetime.now(timezone.utc)
        operation.stopped_at = stopped_at
        await self.db.mark_operation_stopped(operation.id, stopped_at)
        await self.db.insert_audit_event(
            operation.id,
            "system",
            "operation_stopped",
            details={"stopped_at": stopped_at.isoformat()},
        )
        logger.info("Marked operation %s as stopped", operation.id)

    async def add_member(self, operation_id: uuid.UUID, name: str) -> Member:
        operation = self._require_operation()
        if operation.id != operation_id:
            raise ValueError(f"Operation id mismatch: expected {operation.id}, got {operation_id}")

        member = Member(name=name, role=MemberRole.OBSERVER)
        member.last_seen_at = member.connected_at
        self.members[member.id] = member
        await self.db.insert_member(
            member.id,
            operation_id,
            member.name,
            member.role,
            member.reconnect_token,
            member.connected_at,
            member.last_seen_at,
        )
        await self.db.insert_audit_event(
            operation_id,
            "member",
            "member_joined",
            actor_member_id=member.id,
            details={"name": member.name, "role": member.role.value},
        )
        logger.info("Member joined: %s (%s)", member.name, member.id)
        return member

    async def resume_member(
        self,
        operation_id: uuid.UUID,
        member_id: uuid.UUID,
        reconnect_token: str,
    ) -> Member:
        operation = self._require_operation()
        if operation.id != operation_id:
            raise ValueError(f"Operation id mismatch: expected {operation.id}, got {operation_id}")

        member = self._require_member(member_id)
        if member.status == MemberStatus.KICKED:
            raise PermissionError(f"Member {member_id} is kicked and cannot reconnect.")
        if not secrets.compare_digest(member.reconnect_token, reconnect_token):
            raise PermissionError(f"Reconnect token mismatch for member {member_id}.")

        connected_at = datetime.now(timezone.utc)
        member.status = MemberStatus.CONNECTED
        member.connected_at = connected_at
        member.last_seen_at = connected_at
        await self.db.mark_member_connected(member_id, connected_at)
        await self.db.insert_audit_event(
            operation.id,
            "member",
            "member_reconnected",
            actor_member_id=member.id,
            details={"name": member.name, "role": member.role.value},
        )
        logger.info("Member resumed: %s (%s)", member.name, member.id)
        return member

    async def promote_member(self, member_id: uuid.UUID) -> None:
        member = self._require_member(member_id)
        member.role = MemberRole.SENSOR
        await self.db.update_member_role(member_id, MemberRole.SENSOR)

    async def demote_member(self, member_id: uuid.UUID) -> None:
        member = self._require_member(member_id)
        member.role = MemberRole.OBSERVER
        await self.db.update_member_role(member_id, MemberRole.OBSERVER)

    async def kick_member(self, member_id: uuid.UUID) -> None:
        member = self._require_member(member_id)
        member.status = MemberStatus.KICKED
        await self.db.update_member_status(member_id, MemberStatus.KICKED.value)

    async def mark_disconnected(self, member_id: uuid.UUID) -> None:
        member = self._require_member(member_id)
        if member.status == MemberStatus.KICKED:
            return
        if member.status == MemberStatus.DISCONNECTED:
            return
        member.status = MemberStatus.DISCONNECTED
        await self.db.update_member_status(member_id, MemberStatus.DISCONNECTED.value)
        await self.db.insert_audit_event(
            self._require_operation().id,
            "member",
            "member_disconnected",
            actor_member_id=member.id,
            details={"name": member.name, "role": member.role.value},
        )

    async def update_member_gps(self, member_id: uuid.UUID, lat: float, lon: float) -> None:
        member = self._require_member(member_id)
        member.latitude = lat
        member.longitude = lon
        member.last_gps_at = datetime.now(timezone.utc)
        member.last_seen_at = member.last_gps_at
        await self.db.update_member_heartbeat(member_id, member.last_seen_at)
        await self.db.update_member_gps(member_id, lat, lon)

    async def touch_member_heartbeat(self, member_id: uuid.UUID) -> None:
        member = self._require_member(member_id)
        member.last_seen_at = datetime.now(timezone.utc)
        await self.db.update_member_heartbeat(member_id, member.last_seen_at)

    async def update_member_buffer_status(self, member_id: uuid.UUID, payload: dict) -> None:
        member = self._require_member(member_id)
        member.buffer_status = MemberBufferStatus(
            pending_count=max(0, int(payload.get("pending_count") or 0)),
            manual_pending_count=max(0, int(payload.get("manual_pending_count") or 0)),
            sensor_pending_count=max(0, int(payload.get("sensor_pending_count") or 0)),
            report_pending_count=max(0, int(payload.get("report_pending_count") or 0)),
            audio_pending_count=max(0, int(payload.get("audio_pending_count") or 0)),
            frame_pending_count=max(0, int(payload.get("frame_pending_count") or 0)),
            in_flight=bool(payload.get("in_flight")),
            network=(
                "offline"
                if str(payload.get("network") or "").strip().lower() == "offline"
                else "online"
            ),
            last_error=(str(payload.get("last_error") or "").strip() or None),
            oldest_pending_at=payload.get("oldest_pending_at"),
            updated_at=payload.get("updated_at") or datetime.now(timezone.utc),
        )

    def get_sensor_count(self) -> int:
        return sum(
            1
            for member in self.members.values()
            if member.role == MemberRole.SENSOR and member.status == MemberStatus.CONNECTED
        )

    def get_member_list(self) -> list[dict]:
        return [member.model_dump(mode="json") for member in self.members.values()]

    # ---------------------------------------------------------------------
    # Task management (Release 1.2.0)
    # ---------------------------------------------------------------------

    async def create_task(
        self,
        assigner_id: uuid.UUID,
        assignee_id: uuid.UUID,
        task_type: TaskType,
        title: str,
        description: str | None = None,
        target_location: "LocationTarget | None" = None,
        timeout_minutes: int = 15,
        priority: int = 1,
        max_retries: int = 0,
    ) -> Task:
        """Create and assign a new task to a member.
        
        Args:
            assigner_id: Coordinator member ID creating the task
            assignee_id: Member ID to assign the task to
            task_type: Type of task (CONFIRMATION, CHECKPOINT, REPORT, CUSTOM)
            title: Short task title
            description: Optional detailed description
            target_location: Optional geographic target
            timeout_minutes: Deadline from creation (default 15)
            priority: 1=normal, 2=high, 3=urgent
            max_retries: Number of retries allowed on timeout
            
        Returns:
            The created Task object
            
        Raises:
            RuntimeError: If no active operation
            ValueError: If assignee not found
        """
        operation = self._require_operation()
        
        # Validate assignee exists
        if assignee_id not in self.members:
            raise ValueError(f"Assignee {assignee_id} not found")
        
        now = datetime.now(timezone.utc)
        
        task = Task(
            id=uuid.uuid4(),
            operation_id=operation.id,
            assigner_id=assigner_id,
            assignee_id=assignee_id,
            type=task_type,
            title=title,
            description=description,
            target_location=target_location,
            state=TaskState.ASSIGNED,  # Skip PENDING, go straight to ASSIGNED
            created_at=now,
            assigned_at=now,
            timeout_at=now + __import__('datetime').timedelta(minutes=timeout_minutes),
            priority=priority,
            max_retries=max_retries,
        )
        
        # Persist to database
        await self.db.insert_task(
            task_id=task.id,
            operation_id=task.operation_id,
            assigner_id=task.assigner_id,
            assignee_id=task.assignee_id,
            task_type=task.type.value.upper(),
            title=task.title,
            description=task.description,
            target_lat=target_location.lat if target_location else None,
            target_lon=target_location.lon if target_location else None,
            target_radius_meters=target_location.radius_meters if target_location else None,
            state=task.state.value,
            timeout_at=task.timeout_at,
            priority=task.priority,
            max_retries=task.max_retries,
        )
        
        # Add to in-memory store
        self.tasks[task.id] = task
        
        # Log audit event
        await self.db.insert_audit_event(
            operation.id,
            "coordinator",
            "task_created",
            details={
                "task_id": str(task.id),
                "assignee_id": str(assignee_id),
                "assignee_name": self.members[assignee_id].name,
                "type": task_type.value,
                "title": title,
                "priority": priority,
            }
        )
        
        logger.info(
            "Task created: %s (%s) assigned to %s",
            task.id, title, self.members[assignee_id].name
        )
        
        return task

    def get_task(self, task_id: uuid.UUID) -> Task:
        """Get a task by ID.
        
        Args:
            task_id: Task UUID
            
        Returns:
            Task object
            
        Raises:
            ValueError: If task not found
        """
        if task_id not in self.tasks:
            raise ValueError(f"Task {task_id} not found")
        return self.tasks[task_id]

    async def acknowledge_task(self, task_id: uuid.UUID, member_id: uuid.UUID) -> Task:
        """Member acknowledges receipt of assigned task.
        
        Args:
            task_id: Task UUID
            member_id: Member acknowledging (must be assignee)
            
        Returns:
            Updated Task object
            
        Raises:
            ValueError: If task not found or invalid state transition
            PermissionError: If member is not the assignee
        """
        task = self.get_task(task_id)
        
        if task.assignee_id != member_id:
            raise PermissionError("Task not assigned to this member")
        
        task.transition_to(TaskState.ACKNOWLEDGED)
        
        await self.db.update_task_state(task_id, TaskState.ACKNOWLEDGED.value)
        
        await self.db.insert_audit_event(
            task.operation_id,
            "member",
            "task_acknowledged",
            actor_member_id=member_id,
            details={"task_id": str(task_id), "title": task.title},
        )
        
        logger.info("Task acknowledged: %s by member %s", task_id, member_id)
        
        return task

    async def start_task(self, task_id: uuid.UUID, member_id: uuid.UUID) -> Task:
        """Member starts working on acknowledged task.
        
        Args:
            task_id: Task UUID
            member_id: Member starting task (must be assignee)
            
        Returns:
            Updated Task object
        """
        task = self.get_task(task_id)
        
        if task.assignee_id != member_id:
            raise PermissionError("Task not assigned to this member")
        
        task.transition_to(TaskState.IN_PROGRESS)
        
        await self.db.update_task_state(task_id, TaskState.IN_PROGRESS.value)
        
        await self.db.insert_audit_event(
            task.operation_id,
            "member",
            "task_started",
            actor_member_id=member_id,
            details={"task_id": str(task_id), "title": task.title},
        )
        
        logger.info("Task started: %s by member %s", task_id, member_id)
        
        return task

    async def complete_task(
        self,
        task_id: uuid.UUID,
        member_id: uuid.UUID,
        outcome: TaskOutcome,
        notes: str | None = None,
    ) -> Task:
        """Member completes assigned task.
        
        Args:
            task_id: Task UUID
            member_id: Member completing task (must be assignee)
            outcome: Completion outcome (SUCCESS, FAILED, UNABLE)
            notes: Optional completion notes
            
        Returns:
            Updated Task object
        """
        task = self.get_task(task_id)
        
        if task.assignee_id != member_id:
            raise PermissionError("Task not assigned to this member")
        
        task.complete(outcome, notes)
        
        await self.db.update_task_state(
            task_id,
            TaskState.COMPLETED.value,
            outcome=outcome.value,
            outcome_notes=notes,
        )
        
        await self.db.insert_audit_event(
            task.operation_id,
            "member",
            "task_completed",
            actor_member_id=member_id,
            details={
                "task_id": str(task_id),
                "title": task.title,
                "outcome": outcome.value,
            },
        )
        
        logger.info(
            "Task completed: %s with outcome %s by member %s",
            task_id, outcome.value, member_id
        )
        
        return task

    async def process_task_timeouts(self) -> list[Task]:
        """Process tasks that have exceeded their timeout.
        
        Should be called periodically by a background task.
        
        Returns:
            List of tasks that were timed out
        """
        now = datetime.now(timezone.utc)
        overdue_data = await self.db.get_pending_tasks_due_before(now)
        
        timed_out = []
        for task_data in overdue_data:
            task_id = uuid.UUID(str(task_data["id"]))
            
            # Use in-memory task if available, otherwise create from DB
            task = self.tasks.get(task_id)
            if task is None:
                from osk.tasking import Task as TaskClass
                task = TaskClass.from_dict(task_data)
                self.tasks[task_id] = task
            
            if task.can_transition_to(TaskState.TIMEOUT):
                task.transition_to(TaskState.TIMEOUT)
                
                await self.db.update_task_state(
                    task_id,
                    TaskState.TIMEOUT.value,
                    outcome=TaskOutcome.TIMEOUT.value,
                )
                
                await self.db.insert_audit_event(
                    task.operation_id,
                    "system",
                    "task_timeout",
                    details={"task_id": str(task_id), "title": task.title},
                )
                
                timed_out.append(task)
                logger.warning("Task timed out: %s (%s)", task_id, task.title)
        
        return timed_out

    async def cancel_task(
        self,
        task_id: uuid.UUID,
        coordinator_id: uuid.UUID,
        reason: str | None = None,
    ) -> Task:
        """Coordinator cancels a task.
        
        Args:
            task_id: Task UUID
            coordinator_id: Coordinator member ID cancelling the task
            reason: Optional cancellation reason
            
        Returns:
            Updated Task object
        """
        task = self.get_task(task_id)
        
        # Can cancel from most states
        if task.state in (TaskState.COMPLETED, TaskState.CANCELLED):
            raise ValueError(f"Cannot cancel task in state {task.state.value}")
        
        task.transition_to(TaskState.CANCELLED)
        task.outcome = TaskOutcome.CANCELLED
        task.outcome_notes = reason
        
        await self.db.cancel_task(task_id, reason)
        
        await self.db.insert_audit_event(
            task.operation_id,
            "coordinator",
            "task_cancelled",
            actor_member_id=coordinator_id,
            details={"task_id": str(task_id), "title": task.title, "reason": reason},
        )
        
        logger.info("Task cancelled: %s by coordinator %s", task_id, coordinator_id)
        
        return task

    async def retry_task(self, task_id: uuid.UUID, coordinator_id: uuid.UUID) -> Task:
        """Retry a timed-out task.
        
        Args:
            task_id: Task UUID (must be in TIMEOUT state)
            coordinator_id: Coordinator member ID retrying the task
            
        Returns:
            Updated Task object with extended timeout
        """
        task = self.get_task(task_id)
        
        if not task.can_retry():
            raise ValueError(f"Task cannot be retried (retries: {task.retry_count}/{task.max_retries})")
        
        task.mark_retry()
        task.transition_to(TaskState.ASSIGNED)
        
        # Extend timeout
        await self.db.increment_task_retry(task_id)
        await self.db.update_task_state(task_id, TaskState.ASSIGNED.value)
        
        await self.db.insert_audit_event(
            task.operation_id,
            "coordinator",
            "task_retried",
            actor_member_id=coordinator_id,
            details={
                "task_id": str(task_id),
                "title": task.title,
                "retry_count": task.retry_count,
            },
        )
        
        logger.info("Task retried: %s (attempt %d)", task_id, task.retry_count)
        
        return task

    def get_active_tasks(self) -> list[Task]:
        """Get all currently active tasks.
        
        Returns:
            List of tasks in ASSIGNED, ACKNOWLEDGED, or IN_PROGRESS state
        """
        return [t for t in self.tasks.values() if t.is_active()]

    def get_tasks_for_member(self, member_id: uuid.UUID) -> list[Task]:
        """Get all tasks assigned to a specific member.
        
        Args:
            member_id: Member UUID
            
        Returns:
            List of tasks for that member
        """
        return [t for t in self.tasks.values() if t.assignee_id == member_id]
