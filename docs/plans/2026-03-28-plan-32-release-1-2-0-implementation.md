# Release 1.2.0 Implementation Plan

**Date:** 2026-03-28  
**Target Release:** 1.2.0 "Coordinator-Directed Operations"  
**Estimated Duration:** 12 weeks  
**Status:** Planning Complete → Ready for Implementation

---

## Executive Summary

This document breaks down Release 1.2.0 into specific, actionable tasks with file-level detail. Each workstream includes implementation steps, file modifications, and validation criteria.

---

## Phase Overview

```
Week 1-2:   [DATA MODELS]      Database schema, migrations, core entities
Week 3-4:   [BACKEND API]      REST endpoints, business logic, WebSocket updates
Week 5-6:   [COORDINATOR UI]   Dashboard tasking interface
Week 7-8:   [MEMBER UX]        Task notification and response flow
Week 9-10:  [INTEGRATION]      End-to-end wiring, testing, bug fixes
Week 11-12: [RELEASE]          Documentation, validation evidence, release prep
```

---

## Workstream 1: Tasking Model (Weeks 1-4)

### 1.1 Database Schema & Migrations

**Files to Create:**
- `src/osk/migrations/009_tasks.sql` - Task table and indexes

**Files to Modify:**
- `src/osk/db.py` - Add task CRUD operations
- `src/osk/operation.py` - Task lifecycle methods

**Implementation Details:**

```sql
-- 009_tasks.sql
CREATE TABLE IF NOT EXISTS tasks (
    id UUID PRIMARY KEY,
    operation_id UUID NOT NULL REFERENCES operations(id) ON DELETE CASCADE,
    assigner_id UUID NOT NULL,  -- Coordinator member ID
    assignee_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    
    type VARCHAR(32) NOT NULL CHECK (type IN ('CONFIRMATION', 'CHECKPOINT', 'REPORT', 'CUSTOM')),
    title VARCHAR(200) NOT NULL,
    description TEXT,
    
    -- Location (optional geo-target)
    target_lat DOUBLE PRECISION,
    target_lon DOUBLE PRECISION,
    target_radius_meters INTEGER,
    
    -- State machine
    state VARCHAR(32) NOT NULL DEFAULT 'PENDING' 
        CHECK (state IN ('PENDING', 'ASSIGNED', 'ACKNOWLEDGED', 'IN_PROGRESS', 'COMPLETED', 'TIMEOUT', 'CANCELLED')),
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    assigned_at TIMESTAMP WITH TIME ZONE,
    acknowledged_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    timeout_at TIMESTAMP WITH TIME ZONE NOT NULL,
    
    -- Outcome
    outcome VARCHAR(32) CHECK (outcome IN ('SUCCESS', 'FAILED', 'UNABLE', 'TIMEOUT', 'CANCELLED')),
    outcome_notes TEXT,
    
    -- Metadata
    priority INTEGER DEFAULT 1 CHECK (priority IN (1, 2, 3)),  -- 1=normal, 2=high, 3=urgent
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 0
);

CREATE INDEX idx_tasks_operation ON tasks(operation_id);
CREATE INDEX idx_tasks_assignee ON tasks(assignee_id);
CREATE INDEX idx_tasks_state ON tasks(state);
CREATE INDEX idx_tasks_active ON tasks(assignee_id, state) 
    WHERE state IN ('ASSIGNED', 'ACKNOWLEDGED', 'IN_PROGRESS');
```

**DB.py Additions:**

```python
# In src/osk/db.py

async def insert_task(
    self,
    task_id: uuid.UUID,
    operation_id: uuid.UUID,
    assigner_id: uuid.UUID,
    assignee_id: uuid.UUID,
    task_type: str,
    title: str,
    description: Optional[str],
    target_lat: Optional[float],
    target_lon: Optional[float],
    target_radius: Optional[int],
    timeout_at: datetime,
    priority: int = 1,
) -> None:
    ...

async def get_task(self, task_id: uuid.UUID) -> Optional[Dict]:
    ...

async def get_tasks_for_operation(
    self, 
    operation_id: uuid.UUID,
    states: Optional[List[str]] = None
) -> List[Dict]:
    ...

async def get_tasks_for_member(
    self,
    member_id: uuid.UUID,
    states: Optional[List[str]] = None
) -> List[Dict]:
    ...

async def update_task_state(
    self,
    task_id: uuid.UUID,
    new_state: str,
    outcome: Optional[str] = None,
    notes: Optional[str] = None
) -> None:
    ...

async def get_pending_tasks_due_before(
    self,
    before: datetime
) -> List[Dict]:
    """For timeout processing."""
    ...
```

### 1.2 Core Task Entity

**Files to Create:**
- `src/osk/tasking.py` - Task domain model and state machine

**Implementation:**

```python
# src/osk/tasking.py
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Optional
import uuid

class TaskType(Enum):
    CONFIRMATION = "confirmation"  # Confirm something at location
    CHECKPOINT = "checkpoint"      # Reach/check a checkpoint
    REPORT = "report"              # Report observations
    CUSTOM = "custom"              # Freeform task

class TaskState(Enum):
    PENDING = "pending"           # Created, not yet assigned
    ASSIGNED = "assigned"         # Assigned to member
    ACKNOWLEDGED = "acknowledged" # Member acknowledged receipt
    IN_PROGRESS = "in_progress"   # Member started work
    COMPLETED = "completed"       # Member completed
    TIMEOUT = "timeout"           # Hit deadline without completion
    CANCELLED = "cancelled"       # Coordinator cancelled

class TaskOutcome(Enum):
    SUCCESS = "success"
    FAILED = "failed"
    UNABLE = "unable"      # Couldn't complete (blocked, etc.)
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"

@dataclass
class Task:
    id: uuid.UUID
    operation_id: uuid.UUID
    assigner_id: uuid.UUID
    assignee_id: uuid.UUID
    
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
    
    # Retry handling
    priority: int = 1  # 1=normal, 2=high, 3=urgent
    retry_count: int = 0
    max_retries: int = 0
    
    # State machine transitions
    def can_transition_to(self, new_state: TaskState) -> bool:
        """Validate state transitions."""
        valid_transitions = {
            TaskState.PENDING: [TaskState.ASSIGNED, TaskState.CANCELLED],
            TaskState.ASSIGNED: [TaskState.ACKNOWLEDGED, TaskState.TIMEOUT, TaskState.CANCELLED],
            TaskState.ACKNOWLEDGED: [TaskState.IN_PROGRESS, TaskState.TIMEOUT, TaskState.CANCELLED],
            TaskState.IN_PROGRESS: [TaskState.COMPLETED, TaskState.TIMEOUT, TaskState.CANCELLED],
            TaskState.COMPLETED: [],  # Terminal
            TaskState.TIMEOUT: [TaskState.ASSIGNED] if self.retry_count < self.max_retries else [],
            TaskState.CANCELLED: [],  # Terminal
        }
        return new_state in valid_transitions.get(self.state, [])
    
    def is_terminal(self) -> bool:
        return self.state in (TaskState.COMPLETED, TaskState.CANCELLED)
    
    def is_active(self) -> bool:
        return self.state in (TaskState.ASSIGNED, TaskState.ACKNOWLEDGED, TaskState.IN_PROGRESS)
    
    def time_remaining(self) -> timedelta:
        return self.timeout_at - datetime.now(timezone.utc)
    
    def is_overdue(self) -> bool:
        return datetime.now(timezone.utc) > self.timeout_at

@dataclass
class LocationTarget:
    lat: float
    lon: float
    radius_meters: int = 50
    
    def contains(self, lat: float, lon: float) -> bool:
        """Check if coordinates are within target radius."""
        # Haversine distance calculation
        ...
```

### 1.3 Operation Manager Integration

**Files to Modify:**
- `src/osk/operation.py` - Add task management methods

**Add to OperationManager class:**

```python
# In src/osk/operation.py

from osk.tasking import Task, TaskType, TaskState, TaskOutcome

class OperationManager:
    # ... existing code ...
    
    def __init__(self, ...):
        # ... existing init ...
        self.tasks: Dict[uuid.UUID, Task] = {}
        self._task_timeout_task: Optional[asyncio.Task] = None
    
    async def create_task(
        self,
        assigner_id: uuid.UUID,
        assignee_id: uuid.UUID,
        task_type: TaskType,
        title: str,
        description: Optional[str] = None,
        target_location: Optional[LocationTarget] = None,
        timeout_minutes: int = 15,
        priority: int = 1,
    ) -> Task:
        """Create and assign a new task."""
        operation = self._require_operation()
        
        # Validate assignee exists
        if assignee_id not in self.members:
            raise ValueError(f"Assignee {assignee_id} not found")
        
        task = Task(
            id=uuid.uuid4(),
            operation_id=operation.id,
            assigner_id=assigner_id,
            assignee_id=assignee_id,
            type=task_type,
            title=title,
            description=description,
            target_location=target_location,
            timeout_at=datetime.now(timezone.utc) + timedelta(minutes=timeout_minutes),
            priority=priority,
        )
        
        # Persist to DB
        await self.db.insert_task(...)
        
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
                "type": task_type.value,
                "title": title,
            }
        )
        
        return task
    
    async def acknowledge_task(self, task_id: uuid.UUID, member_id: uuid.UUID) -> Task:
        """Member acknowledges task receipt."""
        task = self._get_task(task_id)
        
        if task.assignee_id != member_id:
            raise PermissionError("Task not assigned to this member")
        
        if not task.can_transition_to(TaskState.ACKNOWLEDGED):
            raise ValueError(f"Cannot acknowledge task in state {task.state}")
        
        task.state = TaskState.ACKNOWLEDGED
        task.acknowledged_at = datetime.now(timezone.utc)
        
        await self.db.update_task_state(task_id, "ACKNOWLEDGED")
        
        # Notify coordinator
        await self._notify_task_update(task)
        
        return task
    
    async def complete_task(
        self,
        task_id: uuid.UUID,
        member_id: uuid.UUID,
        outcome: TaskOutcome,
        notes: Optional[str] = None
    ) -> Task:
        """Member completes task."""
        task = self._get_task(task_id)
        
        if task.assignee_id != member_id:
            raise PermissionError("Task not assigned to this member")
        
        if not task.can_transition_to(TaskState.COMPLETED):
            raise ValueError(f"Cannot complete task in state {task.state}")
        
        task.state = TaskState.COMPLETED
        task.outcome = outcome
        task.outcome_notes = notes
        task.completed_at = datetime.now(timezone.utc)
        
        await self.db.update_task_state(
            task_id,
            "COMPLETED",
            outcome=outcome.value,
            notes=notes
        )
        
        # Notify coordinator
        await self._notify_task_update(task)
        
        # Log audit
        await self.db.insert_audit_event(...)
        
        return task
    
    async def process_timeouts(self) -> List[Task]:
        """Background task to handle timeouts."""
        overdue = await self.db.get_pending_tasks_due_before(datetime.now(timezone.utc))
        
        timed_out = []
        for task_data in overdue:
            task = self.tasks.get(task_data['id'])
            if task and task.can_transition_to(TaskState.TIMEOUT):
                task.state = TaskState.TIMEOUT
                task.outcome = TaskOutcome.TIMEOUT
                await self.db.update_task_state(task.id, "TIMEOUT", outcome="timeout")
                timed_out.append(task)
                await self._notify_task_update(task)
        
        return timed_out
    
    def _get_task(self, task_id: uuid.UUID) -> Task:
        if task_id not in self.tasks:
            raise ValueError(f"Task {task_id} not found")
        return self.tasks[task_id]
    
    async def _notify_task_update(self, task: Task) -> None:
        """Notify relevant parties of task state change."""
        # This will be implemented with WebSocket broadcasts
        pass
```

**Validation Criteria:**
- [ ] Migration applies cleanly
- [ ] Task CRUD operations work
- [ ] State machine enforces valid transitions
- [ ] Timeout processing works
- [ ] Audit events logged

---

## Workstream 2: Backend API (Weeks 3-4)

### 2.1 Task REST Endpoints

**Files to Modify:**
- `src/osk/server.py` - Add task API routes

**Add to server.py:**

```python
# Pydantic models for API
class TaskCreateRequest(BaseModel):
    assignee_id: uuid.UUID
    task_type: str  # "CONFIRMATION", "CHECKPOINT", "REPORT", "CUSTOM"
    title: str
    description: Optional[str] = None
    target_lat: Optional[float] = None
    target_lon: Optional[float] = None
    target_radius_meters: Optional[int] = None
    timeout_minutes: int = Field(default=15, ge=1, le=120)
    priority: int = Field(default=1, ge=1, le=3)

class TaskAcknowledgeRequest(BaseModel):
    pass  # Empty body, just the POST action

class TaskCompleteRequest(BaseModel):
    outcome: str  # "SUCCESS", "FAILED", "UNABLE"
    notes: Optional[str] = None

class TaskResponse(BaseModel):
    id: uuid.UUID
    assignee_id: uuid.UUID
    assignee_name: str
    type: str
    title: str
    description: Optional[str]
    state: str
    created_at: datetime
    timeout_at: datetime
    time_remaining_seconds: int
    outcome: Optional[str]
    outcome_notes: Optional[str]

# In route registration section, add:

@app.post("/api/operator/tasks")
async def create_task(
    request: Request,
    task_req: TaskCreateRequest,
):
    """Coordinator creates a new task."""
    if response := _require_local_admin(request, op_manager):
        return response
    
    operation = op_manager.operation
    if operation is None:
        return JSONResponse({"error": "No active operation"}, status_code=503)
    
    try:
        from osk.tasking import TaskType
        task_type = TaskType(task_req.task_type.lower())
        
        target_location = None
        if task_req.target_lat is not None and task_req.target_lon is not None:
            target_location = LocationTarget(
                lat=task_req.target_lat,
                lon=task_req.target_lon,
                radius_meters=task_req.target_radius_meters or 50
            )
        
        # Get assigner ID from operator session
        operator_session = _decode_operator_token_from_cookie(request, op_manager)
        assigner_id = operator_session["member_id"]
        
        task = await op_manager.create_task(
            assigner_id=assigner_id,
            assignee_id=task_req.assignee_id,
            task_type=task_type,
            title=task_req.title,
            description=task_req.description,
            target_location=target_location,
            timeout_minutes=task_req.timeout_minutes,
            priority=task_req.priority,
        )
        
        # Notify assignee via WebSocket
        await conn_manager.send_to(
            task.assignee_id,
            {
                "type": "task_assigned",
                "task": _task_to_dict(task)
            }
        )
        
        return JSONResponse(_task_to_dict(task), status_code=201)
        
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

@app.get("/api/operator/tasks")
async def list_tasks(
    request: Request,
    state: Optional[str] = None,
    assignee_id: Optional[uuid.UUID] = None,
):
    """List tasks for operation."""
    if response := _require_local_admin(request, op_manager):
        return response
    
    if op_manager.operation is None:
        return JSONResponse({"error": "No active operation"}, status_code=503)
    
    tasks = list(op_manager.tasks.values())
    
    # Filter by state if provided
    if state:
        tasks = [t for t in tasks if t.state.value == state]
    
    # Filter by assignee if provided
    if assignee_id:
        tasks = [t for t in tasks if t.assignee_id == assignee_id]
    
    return JSONResponse([_task_to_dict(t) for t in tasks])

@app.post("/api/member/tasks/{task_id}/acknowledge")
async def acknowledge_task(
    request: Request,
    task_id: uuid.UUID,
):
    """Member acknowledges task assignment."""
    runtime_session = _member_runtime_session_from_request(request)
    if runtime_session is None:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    member_id = runtime_session["member_id"]
    
    try:
        task = await op_manager.acknowledge_task(task_id, member_id)
        return JSONResponse(_task_to_dict(task))
    except (ValueError, PermissionError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)

@app.post("/api/member/tasks/{task_id}/complete")
async def complete_task(
    request: Request,
    task_id: uuid.UUID,
    complete_req: TaskCompleteRequest,
):
    """Member completes task."""
    runtime_session = _member_runtime_session_from_request(request)
    if runtime_session is None:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    member_id = runtime_session["member_id"]
    
    try:
        from osk.tasking import TaskOutcome
        outcome = TaskOutcome(complete_req.outcome.lower())
        
        task = await op_manager.complete_task(
            task_id, member_id, outcome, complete_req.notes
        )
        return JSONResponse(_task_to_dict(task))
    except (ValueError, PermissionError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)

def _task_to_dict(task: Task) -> dict:
    """Serialize task for API response."""
    member = op_manager.members.get(task.assignee_id)
    assignee_name = member.name if member else "Unknown"
    
    time_remaining = task.time_remaining()
    time_remaining_seconds = max(0, int(time_remaining.total_seconds()))
    
    return {
        "id": str(task.id),
        "assignee_id": str(task.assignee_id),
        "assignee_name": assignee_name,
        "type": task.type.value,
        "title": task.title,
        "description": task.description,
        "state": task.state.value,
        "created_at": task.created_at.isoformat(),
        "timeout_at": task.timeout_at.isoformat(),
        "time_remaining_seconds": time_remaining_seconds,
        "outcome": task.outcome.value if task.outcome else None,
        "outcome_notes": task.outcome_notes,
        "is_overdue": task.is_overdue(),
        "priority": task.priority,
    }
```

### 2.2 WebSocket Task Updates

**Files to Modify:**
- `src/osk/server.py` - WebSocket message handlers

**Add WebSocket message types:**

```python
# In websocket message handling section:

async def handle_member_message(member_id: uuid.UUID, data: dict):
    msg_type = data.get("type")
    
    if msg_type == "task_acknowledge":
        task_id = uuid.UUID(data["task_id"])
        task = await op_manager.acknowledge_task(task_id, member_id)
        await ws.send_json({
            "type": "task_updated",
            "task": _task_to_dict(task)
        })
    
    elif msg_type == "task_complete":
        task_id = uuid.UUID(data["task_id"])
        outcome = TaskOutcome(data["outcome"])
        notes = data.get("notes")
        task = await op_manager.complete_task(task_id, member_id, outcome, notes)
        await ws.send_json({
            "type": "task_updated",
            "task": _task_to_dict(task)
        })
    
    # ... existing handlers ...

# Coordinator WebSocket additions:
async def handle_coordinator_message(data: dict):
    msg_type = data.get("type")
    
    if msg_type == "create_task":
        # Create task and broadcast to assignee
        task = await op_manager.create_task(...)
        await conn_manager.send_to(task.assignee_id, {
            "type": "task_assigned",
            "task": _task_to_dict(task)
        })
        # Acknowledge to coordinator
        await ws.send_json({
            "type": "task_created",
            "task": _task_to_dict(task)
        })
```

**Validation Criteria:**
- [ ] Task creation endpoint works
- [ ] Task list endpoint filters correctly
- [ ] Member acknowledge/complete works
- [ ] WebSocket notifications sent
- [ ] Authentication enforced correctly

---

## Workstream 3: Coordinator Dashboard (Weeks 5-6)

### 3.1 Task Assignment Panel

**Files to Modify:**
- `src/osk/templates/coordinator.html` - Add task UI
- `src/osk/static/coordinator.js` - Task management logic
- `src/osk/static/coordinator.css` - Task styling

**HTML Additions:**

```html
<!-- In coordinator.html, add new section -->
<section class="panel task-panel">
    <h2>Task Assignment</h2>
    
    <!-- Create Task Form -->
    <div class="task-create-form" id="task-create-form">
        <select id="task-assignee" required>
            <option value="">Select member...</option>
            <!-- Populated dynamically -->
        </select>
        
        <select id="task-type" required>
            <option value="CONFIRMATION">Confirmation</option>
            <option value="CHECKPOINT">Checkpoint</option>
            <option value="REPORT">Report</option>
            <option value="CUSTOM">Custom</option>
        </select>
        
        <input type="text" id="task-title" placeholder="Task title" required>
        <textarea id="task-description" placeholder="Description"></textarea>
        
        <div class="task-location">
            <label>
                <input type="checkbox" id="task-has-location">
                Add location target
            </label>
            <div id="task-location-fields" class="hidden">
                <input type="number" id="task-lat" placeholder="Latitude" step="any">
                <input type="number" id="task-lon" placeholder="Longitude" step="any">
                <input type="number" id="task-radius" placeholder="Radius (m)" value="50">
            </div>
        </div>
        
        <div class="task-options">
            <label>
                Timeout:
                <select id="task-timeout">
                    <option value="5">5 minutes</option>
                    <option value="15" selected>15 minutes</option>
                    <option value="30">30 minutes</option>
                    <option value="60">1 hour</option>
                </select>
            </label>
            
            <label>
                Priority:
                <select id="task-priority">
                    <option value="1">Normal</option>
                    <option value="2">High</option>
                    <option value="3">Urgent</option>
                </select>
            </label>
        </div>
        
        <button type="button" id="btn-create-task">Assign Task</button>
    </div>
    
    <!-- Active Tasks List -->
    <div class="task-list" id="task-list">
        <h3>Active Tasks</h3>
        <div id="active-tasks-container">
            <p class="empty">No active tasks</p>
        </div>
    </div>
    
    <!-- Task Detail Modal -->
    <div class="modal hidden" id="task-detail-modal">
        <div class="modal-content">
            <h3 id="task-detail-title"></h3>
            <div id="task-detail-content"></div>
            <button type="button" class="btn-close">Close</button>
        </div>
    </div>
</section>
```

**JavaScript Additions:**

```javascript
// In coordinator.js

class TaskManager {
    constructor() {
        this.tasks = new Map();
        this.members = new Map();
        this.init();
    }
    
    init() {
        this.bindEvents();
        this.loadMembers();
        this.loadTasks();
        this.startTaskPolling();
    }
    
    bindEvents() {
        document.getElementById('btn-create-task').addEventListener('click', () => this.createTask());
        document.getElementById('task-has-location').addEventListener('change', (e) => {
            document.getElementById('task-location-fields').classList.toggle('hidden', !e.target.checked);
        });
    }
    
    async loadMembers() {
        const response = await fetch('/api/members', {
            headers: { 'Authorization': `Bearer ${this.getToken()}` }
        });
        const members = await response.json();
        
        const select = document.getElementById('task-assignee');
        select.innerHTML = '<option value="">Select member...</option>';
        
        members.forEach(member => {
            if (member.role === 'sensor' || member.role === 'observer') {
                this.members.set(member.id, member);
                const option = document.createElement('option');
                option.value = member.id;
                option.textContent = member.name;
                select.appendChild(option);
            }
        });
    }
    
    async createTask() {
        const assigneeId = document.getElementById('task-assignee').value;
        const type = document.getElementById('task-type').value;
        const title = document.getElementById('task-title').value;
        const description = document.getElementById('task-description').value;
        const timeoutMinutes = parseInt(document.getElementById('task-timeout').value);
        const priority = parseInt(document.getElementById('task-priority').value);
        
        const body = {
            assignee_id: assigneeId,
            task_type: type,
            title: title,
            description: description,
            timeout_minutes: timeoutMinutes,
            priority: priority
        };
        
        // Add location if specified
        if (document.getElementById('task-has-location').checked) {
            body.target_lat = parseFloat(document.getElementById('task-lat').value);
            body.target_lon = parseFloat(document.getElementById('task-lon').value);
            body.target_radius_meters = parseInt(document.getElementById('task-radius').value);
        }
        
        const response = await fetch('/api/operator/tasks', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${this.getToken()}`
            },
            body: JSON.stringify(body)
        });
        
        if (response.ok) {
            const task = await response.json();
            this.addTask(task);
            this.clearForm();
            this.showNotification('Task assigned successfully');
        } else {
            const error = await response.json();
            this.showError(error.error || 'Failed to create task');
        }
    }
    
    addTask(task) {
        this.tasks.set(task.id, task);
        this.renderTaskList();
    }
    
    renderTaskList() {
        const container = document.getElementById('active-tasks-container');
        const activeTasks = Array.from(this.tasks.values())
            .filter(t => ['assigned', 'acknowledged', 'in_progress'].includes(t.state));
        
        if (activeTasks.length === 0) {
            container.innerHTML = '<p class="empty">No active tasks</p>';
            return;
        }
        
        container.innerHTML = activeTasks.map(task => this.renderTaskCard(task)).join('');
    }
    
    renderTaskCard(task) {
        const priorityClass = ['normal', 'high', 'urgent'][task.priority - 1];
        const stateClass = task.state;
        const isOverdue = task.is_overdue;
        
        return `
            <div class="task-card ${priorityClass} ${stateClass} ${isOverdue ? 'overdue' : ''}" data-task-id="${task.id}">
                <div class="task-header">
                    <span class="task-priority">${['●', '●●', '●●●'][task.priority - 1]}</span>
                    <span class="task-type">${task.type}</span>
                    <span class="task-state">${task.state}</span>
                </div>
                <h4 class="task-title">${this.escapeHtml(task.title)}</h4>
                <p class="task-assignee">To: ${this.escapeHtml(task.assignee_name)}</p>
                <div class="task-meta">
                    <span class="task-timer">⏱️ ${this.formatTimeRemaining(task.time_remaining_seconds)}</span>
                    ${task.is_overdue ? '<span class="overdue-badge">OVERDUE</span>' : ''}
                </div>
            </div>
        `;
    }
    
    formatTimeRemaining(seconds) {
        if (seconds <= 0) return 'Expired';
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins}m ${secs}s`;
    }
    
    startTaskPolling() {
        // Poll for task updates every 5 seconds
        setInterval(() => this.loadTasks(), 5000);
        
        // Also listen for WebSocket updates
        this.ws = new WebSocket(this.getWebSocketUrl());
        this.ws.onmessage = (event) => {
            const msg = JSON.parse(event.data);
            if (msg.type === 'task_updated' || msg.type === 'task_completed') {
                this.updateTask(msg.task);
            }
        };
    }
    
    updateTask(task) {
        this.tasks.set(task.id, task);
        this.renderTaskList();
    }
    
    // Utility methods
    getToken() { /* ... */ }
    getWebSocketUrl() { /* ... */ }
    escapeHtml(text) { /* ... */ }
    showNotification(message) { /* ... */ }
    showError(message) { /* ... */ }
    clearForm() { /* ... */ }
}

// Initialize
const taskManager = new TaskManager();
```

### 3.2 Route Confidence Display

**Add to coordinator dashboard:**

```html
<section class="panel route-panel">
    <h2>Route Confidence</h2>
    
    <!-- Route Assessment Form -->
    <div class="route-assessment-form">
        <input type="text" id="route-origin" placeholder="Origin (lat, lon)">
        <input type="text" id="route-destination" placeholder="Destination (lat, lon)">
        <button type="button" id="btn-assess-route">Assess Route</button>
    </div>
    
    <!-- Route Result -->
    <div id="route-result" class="hidden">
        <div class="confidence-meter">
            <div class="confidence-bar" id="confidence-bar"></div>
            <span class="confidence-value" id="confidence-value"></span>
        </div>
        <div class="route-factors" id="route-factors"></div>
    </div>
    
    <!-- Open Gaps List -->
    <div class="gaps-list">
        <h3>Open Gaps</h3>
        <div id="gaps-container">
            <p class="empty">No open gaps</p>
        </div>
    </div>
</section>
```

**Validation Criteria:**
- [ ] Task creation form works end-to-end
- [ ] Active tasks display updates in real-time
- [ ] Priority and state visual indicators work
- [ ] Overdue tasks highlighted
- [ ] Route assessment UI functional

---

## Workstream 4: Member Task UX (Weeks 7-8)

### 4.1 Task Notification Banner

**Files to Modify:**
- `src/osk/templates/member.html` - Add task UI
- `src/osk/static/member.js` - Task handling
- `src/osk/static/member.css` - Task styling

**HTML Additions:**

```html
<!-- In member.html -->

<!-- Task Notification Banner (shown when task assigned) -->
<div class="task-banner hidden" id="task-banner">
    <div class="task-notification">
        <span class="task-icon">📋</span>
        <span class="task-summary" id="task-summary">New task assigned</span>
        <button type="button" class="btn-view-task" id="btn-view-task">View</button>
    </div>
</div>

<!-- Task Detail Panel (overlays member feed) -->
<div class="task-panel hidden" id="task-panel">
    <div class="task-panel-header">
        <h3 id="task-panel-title"></h3>
        <button type="button" class="btn-close-panel" id="btn-close-panel">×</button>
    </div>
    
    <div class="task-panel-content">
        <div class="task-description" id="task-description"></div>
        
        <div class="task-target-location hidden" id="task-target-location">
            <h4>Target Location</h4>
            <div id="target-map-mini"></div>
            <p class="target-address" id="target-address"></p>
        </div>
        
        <div class="task-timer">
            <span class="timer-label">Time remaining:</span>
            <span class="timer-value" id="task-timer-value"></span>
        </div>
    </div>
    
    <div class="task-panel-actions" id="task-actions">
        <!-- Actions change based on state -->
        <button type="button" class="btn-acknowledge hidden" id="btn-acknowledge">Acknowledge</button>
        <button type="button" class="btn-start hidden" id="btn-start">Start Task</button>
        <button type="button" class="btn-complete hidden" id="btn-complete">Complete</button>
        <button type="button" class="btn-unable hidden" id="btn-unable">Unable to Complete</button>
    </div>
</div>

<!-- Task Completion Modal -->
<div class="modal hidden" id="task-complete-modal">
    <div class="modal-content">
        <h3>Complete Task</h3>
        <p id="complete-task-title"></p>
        
        <div class="outcome-selection">
            <label>
                <input type="radio" name="outcome" value="SUCCESS" checked>
                ✅ Success - Task completed
            </label>
            <label>
                <input type="radio" name="outcome" value="FAILED">
                ❌ Failed - Could not complete
            </label>
            <label>
                <input type="radio" name="outcome" value="UNABLE">
                🚫 Unable - Blocked or prevented
            </label>
        </div>
        
        <textarea id="completion-notes" placeholder="Notes (optional)"></textarea>
        
        <div class="modal-actions">
            <button type="button" class="btn-cancel">Cancel</button>
            <button type="button" class="btn-submit-completion">Submit</button>
        </div>
    </div>
</div>
```

**JavaScript Implementation:**

```javascript
// In member.js

class TaskHandler {
    constructor() {
        this.currentTask = null;
        this.taskTimer = null;
        this.init();
    }
    
    init() {
        this.bindEvents();
        this.loadCurrentTask();
    }
    
    bindEvents() {
        document.getElementById('btn-view-task').addEventListener('click', () => this.showTaskPanel());
        document.getElementById('btn-close-panel').addEventListener('click', () => this.hideTaskPanel());
        document.getElementById('btn-acknowledge').addEventListener('click', () => this.acknowledgeTask());
        document.getElementById('btn-start').addEventListener('click', () => this.startTask());
        document.getElementById('btn-complete').addEventListener('click', () => this.showCompleteModal());
        document.getElementById('btn-unable').addEventListener('click', () => this.markUnable());
        document.getElementById('btn-submit-completion').addEventListener('click', () => this.submitCompletion());
    }
    
    async loadCurrentTask() {
        // Check for assigned tasks on load/reconnect
        const response = await fetch('/api/member/tasks', {
            headers: { 'Authorization': `Bearer ${this.getToken()}` }
        });
        
        if (response.ok) {
            const tasks = await response.json();
            const activeTask = tasks.find(t => ['assigned', 'acknowledged', 'in_progress'].includes(t.state));
            
            if (activeTask) {
                this.setCurrentTask(activeTask);
            }
        }
    }
    
    setCurrentTask(task) {
        this.currentTask = task;
        this.showTaskNotification();
        this.updateTaskPanel();
        this.startTaskTimer();
    }
    
    showTaskNotification() {
        const banner = document.getElementById('task-banner');
        const summary = document.getElementById('task-summary');
        
        summary.textContent = `New task: ${this.currentTask.title}`;
        banner.classList.remove('hidden');
        
        // Auto-show after short delay
        setTimeout(() => this.showTaskPanel(), 2000);
    }
    
    showTaskPanel() {
        const panel = document.getElementById('task-panel');
        panel.classList.remove('hidden');
        document.getElementById('task-banner').classList.add('hidden');
        
        this.updateActionButtons();
    }
    
    updateTaskPanel() {
        document.getElementById('task-panel-title').textContent = this.currentTask.title;
        document.getElementById('task-description').textContent = 
            this.currentTask.description || 'No description provided';
        
        // Show target location if present
        if (this.currentTask.target_location) {
            document.getElementById('task-target-location').classList.remove('hidden');
            // Initialize mini map
            this.showTargetOnMap(this.currentTask.target_location);
        }
    }
    
    updateActionButtons() {
        const state = this.currentTask.state;
        
        // Hide all first
        ['btn-acknowledge', 'btn-start', 'btn-complete', 'btn-unable'].forEach(id => {
            document.getElementById(id).classList.add('hidden');
        });
        
        // Show appropriate buttons based on state
        switch (state) {
            case 'assigned':
                document.getElementById('btn-acknowledge').classList.remove('hidden');
                break;
            case 'acknowledged':
                document.getElementById('btn-start').classList.remove('hidden');
                document.getElementById('btn-unable').classList.remove('hidden');
                break;
            case 'in_progress':
                document.getElementById('btn-complete').classList.remove('hidden');
                document.getElementById('btn-unable').classList.remove('hidden');
                break;
        }
    }
    
    async acknowledgeTask() {
        const response = await fetch(`/api/member/tasks/${this.currentTask.id}/acknowledge`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${this.getToken()}` }
        });
        
        if (response.ok) {
            const updated = await response.json();
            this.currentTask = updated;
            this.updateActionButtons();
            this.showNotification('Task acknowledged');
        }
    }
    
    async startTask() {
        // Transition to in_progress via WebSocket
        this.ws.send(JSON.stringify({
            type: 'task_start',
            task_id: this.currentTask.id
        }));
        
        this.currentTask.state = 'in_progress';
        this.updateActionButtons();
    }
    
    showCompleteModal() {
        document.getElementById('complete-task-title').textContent = this.currentTask.title;
        document.getElementById('task-complete-modal').classList.remove('hidden');
    }
    
    async submitCompletion() {
        const outcome = document.querySelector('input[name="outcome"]:checked').value;
        const notes = document.getElementById('completion-notes').value;
        
        const response = await fetch(`/api/member/tasks/${this.currentTask.id}/complete`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${this.getToken()}`
            },
            body: JSON.stringify({ outcome, notes })
        });
        
        if (response.ok) {
            this.hideTaskPanel();
            this.currentTask = null;
            this.stopTaskTimer();
            this.showNotification('Task completed');
        }
    }
    
    startTaskTimer() {
        this.stopTaskTimer();
        this.taskTimer = setInterval(() => {
            const remaining = this.currentTask.time_remaining_seconds;
            document.getElementById('task-timer-value').textContent = 
                this.formatTimeRemaining(remaining);
            
            if (remaining <= 0) {
                this.handleTaskTimeout();
            }
        }, 1000);
    }
    
    stopTaskTimer() {
        if (this.taskTimer) {
            clearInterval(this.taskTimer);
            this.taskTimer = null;
        }
    }
    
    handleTaskTimeout() {
        this.stopTaskTimer();
        this.showNotification('Task timed out');
        this.hideTaskPanel();
    }
    
    // WebSocket message handler for task updates
    handleWebSocketMessage(msg) {
        if (msg.type === 'task_assigned') {
            this.setCurrentTask(msg.task);
        } else if (msg.type === 'task_updated' && this.currentTask?.id === msg.task.id) {
            this.currentTask = msg.task;
            this.updateActionButtons();
        }
    }
    
    formatTimeRemaining(seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    }
}

// Initialize
const taskHandler = new TaskHandler();
```

**Validation Criteria:**
- [ ] Task notification appears on assignment
- [ ] Task panel shows correct information
- [ ] State transitions work (acknowledge → start → complete)
- [ ] Timer counts down correctly
- [ ] Completion modal submits successfully
- [ ] Task survives page refresh (reconnect)

---

## Workstream 5: Integration & Testing (Weeks 9-10)

### 5.1 End-to-End Integration Tests

**Files to Create:**
- `tests/e2e/test_task_flow.py` - End-to-end task flow tests
- `scripts/validate_1_2_0.py` - Validation script for release

**Test Cases:**

```python
# tests/e2e/test_task_flow.py

async def test_task_lifecycle():
    """Test complete task flow from creation to completion."""
    # 1. Coordinator creates task
    # 2. Member receives notification
    # 3. Member acknowledges
    # 4. Member completes
    # 5. Coordinator sees completion
    pass

async def test_task_reconnect_resilience():
    """Test that task state survives member reconnect."""
    # 1. Assign task
    # 2. Member disconnects
    # 3. Member reconnects
    # 4. Task still visible with correct state
    pass

async def test_task_timeout():
    """Test task timeout behavior."""
    # 1. Create task with short timeout
    # 2. Wait for timeout
    # 3. Verify timeout state
    pass

async def test_multiple_concurrent_tasks():
    """Test multiple tasks to different members."""
    # 1. Create tasks for 3 different members
    # 2. Each member sees only their task
    # 3. Complete all tasks
    pass
```

### 5.2 Manual Validation Checklist

```markdown
## 1.2.0 Validation Checklist

### Task Creation
- [ ] Coordinator can create all task types
- [ ] Location target optional but functional
- [ ] Priority levels work
- [ ] Timeout settings respected

### Task Assignment
- [ ] Member receives notification
- [ ] Task appears in member UI
- [ ] Correct task details shown

### Task State Flow
- [ ] ASSIGNED → ACKNOWLEDGED
- [ ] ACKNOWLEDGED → IN_PROGRESS
- [ ] IN_PROGRESS → COMPLETED (all outcomes)
- [ ] IN_PROGRESS → TIMEOUT

### Reconnect Resilience
- [ ] Task survives browser refresh
- [ ] Task survives WebSocket reconnect
- [ ] State synchronized correctly

### Coordinator Dashboard
- [ ] Active tasks list updates
- [ ] Completed tasks archived
- [ ] Overdue tasks highlighted
- [ ] Route confidence displays

### Audit Trail
- [ ] Task creation logged
- [ ] State changes logged
- [ ] Completions logged with outcome
```

---

## Workstream 6: Documentation & Release (Weeks 11-12)

### 6.1 Documentation Updates

**Files to Create/Update:**
- `docs/release/1.2.0-definition.md` - Release scope and claims
- `docs/release/1.2.0-validation-report.md` - Validation evidence
- `CHANGELOG.md` - Add 1.2.0 section
- `RELEASE-NOTES-1.2.0.md` - User-facing release notes

### 6.2 Release Checklist

```markdown
## 1.2.0 Release Checklist

### Code Complete
- [ ] All workstreams merged to main
- [ ] Tests passing
- [ ] Code review complete

### Validation
- [ ] E2E tests passing
- [ ] Manual validation complete
- [ ] Documentation updated

### Tagging
- [ ] Create `v1.2.0-rc1`
- [ ] Smoke test RC1
- [ ] Create `v1.2.0`

### Communication
- [ ] GitHub release notes
- [ ] Update README badges
- [ ] Announce (if applicable)
```

---

## File Summary

### New Files (12)
```
src/osk/migrations/009_tasks.sql
src/osk/tasking.py
tests/e2e/test_task_flow.py
scripts/validate_1_2_0.py
docs/release/1.2.0-definition.md
docs/release/1.2.0-validation-report.md
RELEASE-NOTES-1.2.0.md
```

### Modified Files (6)
```
src/osk/db.py                    - Task CRUD operations
src/osk/operation.py             - Task lifecycle methods
src/osk/server.py                - REST API and WebSocket handlers
src/osk/templates/coordinator.html - Task UI
src/osk/static/coordinator.js    - Task management
src/osk/static/coordinator.css   - Task styling
src/osk/templates/member.html    - Task notification/panel
src/osk/static/member.js         - Task handling
src/osk/static/member.css        - Task styling
CHANGELOG.md                     - Add 1.2.0 section
```

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Task state complexity | Extensive unit tests for state machine |
| WebSocket reliability | Fallback polling + reconnect logic |
| Performance at scale | Pagination for task lists, indexes in DB |
| Mobile UX issues | Test on actual devices early (Week 7) |
| Integration bugs | E2E tests from Week 9 |

---

## Success Criteria

Release 1.2.0 is successful when:

1. ✅ Coordinator can create and track tasks end-to-end
2. ✅ Members receive, acknowledge, and complete tasks
3. ✅ Task state survives reconnects
4. ✅ Dashboard shows clear operational picture
5. ✅ Audit trail captures decision context
6. ✅ All validation evidence documented

---

*Plan created: 2026-03-28*  
*Ready for implementation*
