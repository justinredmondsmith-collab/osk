"""Task management domain models for coordinator-directed operations.

Release: 1.2.0 - Coordinator-Directed Operations
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional
import uuid


class TaskType(Enum):
    """Types of tasks that can be assigned to members."""
    CONFIRMATION = "confirmation"  # Confirm something at a location
    CHECKPOINT = "checkpoint"      # Reach/check a checkpoint
    REPORT = "report"              # Report observations
    CUSTOM = "custom"              # Freeform task


class TaskState(Enum):
    """Task state machine states."""
    PENDING = "pending"           # Created, not yet assigned
    ASSIGNED = "assigned"         # Assigned to member
    ACKNOWLEDGED = "acknowledged" # Member acknowledged receipt
    IN_PROGRESS = "in_progress"   # Member started work
    COMPLETED = "completed"       # Member completed
    TIMEOUT = "timeout"           # Hit deadline without completion
    CANCELLED = "cancelled"       # Coordinator cancelled


class TaskOutcome(Enum):
    """Possible outcomes when a task is completed or times out."""
    SUCCESS = "success"      # Task completed successfully
    FAILED = "failed"        # Attempted but failed
    UNABLE = "unable"        # Could not complete (blocked, prevented, etc.)
    TIMEOUT = "timeout"      # Hit deadline
    CANCELLED = "cancelled"  # Cancelled by coordinator


@dataclass
class LocationTarget:
    """Geographic target for a task."""
    lat: float
    lon: float
    radius_meters: int = 50
    
    def contains(self, lat: float, lon: float) -> bool:
        """Check if coordinates are within target radius using haversine formula.
        
        Args:
            lat: Latitude to check
            lon: Longitude to check
            
        Returns:
            True if point is within radius_meters of target center
        """
        # Earth's radius in meters
        R = 6371000
        
        # Convert to radians
        lat1, lon1 = math.radians(self.lat), math.radians(self.lon)
        lat2, lon2 = math.radians(lat), math.radians(lon)
        
        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = (math.sin(dlat / 2) ** 2 + 
             math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        distance = R * c
        
        return distance <= self.radius_meters
    
    def distance_to(self, lat: float, lon: float) -> float:
        """Calculate distance in meters to given coordinates.
        
        Args:
            lat: Latitude
            lon: Longitude
            
        Returns:
            Distance in meters
        """
        R = 6371000
        lat1, lon1 = math.radians(self.lat), math.radians(self.lon)
        lat2, lon2 = math.radians(lat), math.radians(lon)
        
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = (math.sin(dlat / 2) ** 2 + 
             math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c
    
    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "lat": self.lat,
            "lon": self.lon,
            "radius_meters": self.radius_meters
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> LocationTarget:
        """Create from dictionary."""
        return cls(
            lat=data["lat"],
            lon=data["lon"],
            radius_meters=data.get("radius_meters", 50)
        )


@dataclass
class Task:
    """A coordinator-assigned task for a field member.
    
    Tasks follow a state machine:
        PENDING → ASSIGNED → ACKNOWLEDGED → IN_PROGRESS → COMPLETED
                                              ↓
                                        TIMEOUT/CANCELLED
    """
    id: uuid.UUID
    operation_id: uuid.UUID
    assigner_id: uuid.UUID  # Coordinator who created the task
    assignee_id: uuid.UUID  # Member assigned to complete the task
    
    type: TaskType
    title: str
    description: Optional[str] = None
    
    # Optional geo-target
    target_location: Optional[LocationTarget] = None
    
    # State tracking
    state: TaskState = TaskState.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    assigned_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    timeout_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc) + timedelta(minutes=15))
    
    # Outcome
    outcome: Optional[TaskOutcome] = None
    outcome_notes: Optional[str] = None
    
    # Metadata
    priority: int = 1  # 1=normal, 2=high, 3=urgent
    retry_count: int = 0
    max_retries: int = 0
    
    # Valid state transitions
    _VALID_TRANSITIONS: dict = field(default_factory=lambda: {
        TaskState.PENDING: [TaskState.ASSIGNED, TaskState.CANCELLED],
        TaskState.ASSIGNED: [TaskState.ACKNOWLEDGED, TaskState.TIMEOUT, TaskState.CANCELLED],
        TaskState.ACKNOWLEDGED: [TaskState.IN_PROGRESS, TaskState.TIMEOUT, TaskState.CANCELLED],
        TaskState.IN_PROGRESS: [TaskState.COMPLETED, TaskState.TIMEOUT, TaskState.CANCELLED],
        TaskState.COMPLETED: [],  # Terminal state
        TaskState.TIMEOUT: [TaskState.ASSIGNED],  # For retry
        TaskState.CANCELLED: [],  # Terminal state
    }, repr=False)
    
    def can_transition_to(self, new_state: TaskState) -> bool:
        """Check if transition to new_state is valid.
        
        Args:
            new_state: Desired new state
            
        Returns:
            True if transition is allowed
        """
        valid_states = self._VALID_TRANSITIONS.get(self.state, [])
        
        # Special case: can retry from timeout if retries available
        if self.state == TaskState.TIMEOUT and new_state == TaskState.ASSIGNED:
            return self.retry_count < self.max_retries
        
        return new_state in valid_states
    
    def transition_to(self, new_state: TaskState) -> None:
        """Perform state transition with validation.
        
        Args:
            new_state: State to transition to
            
        Raises:
            ValueError: If transition is not valid
        """
        if not self.can_transition_to(new_state):
            raise ValueError(
                f"Invalid transition from {self.state.value} to {new_state.value}"
            )
        
        old_state = self.state
        self.state = new_state
        
        # Update timestamp based on new state
        now = datetime.now(timezone.utc)
        if new_state == TaskState.ASSIGNED:
            self.assigned_at = now
        elif new_state == TaskState.ACKNOWLEDGED:
            self.acknowledged_at = now
        elif new_state == TaskState.COMPLETED:
            self.completed_at = now
        elif new_state == TaskState.TIMEOUT:
            self.outcome = TaskOutcome.TIMEOUT
    
    def is_terminal(self) -> bool:
        """Check if task is in a terminal state."""
        return self.state in (TaskState.COMPLETED, TaskState.CANCELLED)
    
    def is_active(self) -> bool:
        """Check if task is currently active (assigned to member and in progress)."""
        return self.state in (
            TaskState.ASSIGNED,
            TaskState.ACKNOWLEDGED,
            TaskState.IN_PROGRESS
        )
    
    def time_remaining(self) -> timedelta:
        """Calculate time remaining until timeout.
        
        Returns:
            Timedelta (may be negative if overdue)
        """
        return self.timeout_at - datetime.now(timezone.utc)
    
    def is_overdue(self) -> bool:
        """Check if task has passed its timeout."""
        return datetime.now(timezone.utc) > self.timeout_at
    
    def can_retry(self) -> bool:
        """Check if task can be retried after timeout."""
        return self.state == TaskState.TIMEOUT and self.retry_count < self.max_retries
    
    def mark_retry(self) -> None:
        """Increment retry count and reset for reassignment."""
        self.retry_count += 1
        self.outcome = None
        self.outcome_notes = None
    
    def complete(self, outcome: TaskOutcome, notes: Optional[str] = None) -> None:
        """Mark task as completed with outcome.
        
        Args:
            outcome: The completion outcome
            notes: Optional completion notes
        """
        self.transition_to(TaskState.COMPLETED)
        self.outcome = outcome
        self.outcome_notes = notes
    
    def to_dict(self) -> dict:
        """Serialize task to dictionary for API responses."""
        return {
            "id": str(self.id),
            "operation_id": str(self.operation_id),
            "assigner_id": str(self.assigner_id),
            "assignee_id": str(self.assignee_id),
            "type": self.type.value,
            "title": self.title,
            "description": self.description,
            "target_location": self.target_location.to_dict() if self.target_location else None,
            "state": self.state.value,
            "created_at": self.created_at.isoformat(),
            "assigned_at": self.assigned_at.isoformat() if self.assigned_at else None,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "timeout_at": self.timeout_at.isoformat(),
            "time_remaining_seconds": max(0, int(self.time_remaining().total_seconds())),
            "is_overdue": self.is_overdue(),
            "outcome": self.outcome.value if self.outcome else None,
            "outcome_notes": self.outcome_notes,
            "priority": self.priority,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> Task:
        """Create Task from dictionary (e.g., from database)."""
        target = None
        if data.get("target_lat") is not None:
            target = LocationTarget(
                lat=data["target_lat"],
                lon=data["target_lon"],
                radius_meters=data.get("target_radius_meters", 50)
            )
        
        return cls(
            id=uuid.UUID(data["id"]),
            operation_id=uuid.UUID(data["operation_id"]),
            assigner_id=uuid.UUID(data["assigner_id"]),
            assignee_id=uuid.UUID(data["assignee_id"]),
            type=TaskType(data["type"].lower()),
            title=data["title"],
            description=data.get("description"),
            target_location=target,
            state=TaskState(data["state"].lower()),
            created_at=datetime.fromisoformat(data["created_at"]),
            assigned_at=datetime.fromisoformat(data["assigned_at"]) if data.get("assigned_at") else None,
            acknowledged_at=datetime.fromisoformat(data["acknowledged_at"]) if data.get("acknowledged_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            timeout_at=datetime.fromisoformat(data["timeout_at"]),
            outcome=TaskOutcome(data["outcome"].lower()) if data.get("outcome") else None,
            outcome_notes=data.get("outcome_notes"),
            priority=data.get("priority", 1),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 0),
        )
    
    def __repr__(self) -> str:
        return (
            f"Task({self.id}, {self.type.value}, '{self.title[:30]}...', "
            f"state={self.state.value}, assignee={self.assignee_id})"
        )


class TaskAssignmentError(Exception):
    """Raised when task assignment fails."""
    pass


class TaskStateError(Exception):
    """Raised when an invalid state transition is attempted."""
    pass


class TaskTimeoutError(Exception):
    """Raised when a task operation fails due to timeout."""
    pass
