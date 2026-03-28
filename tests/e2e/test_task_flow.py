"""End-to-end tests for task management flow.

Release 1.2.0 - Coordinator-Directed Operations
"""

import asyncio
import json
import uuid
from datetime import datetime, timedelta
from typing import Any

import pytest
import websockets

from osk.tasking import TaskState, TaskOutcome, TaskType


@pytest.mark.asyncio
async def test_task_lifecycle(
    live_server,  # Fixture providing running hub
    coordinator_ws,  # Fixture providing authenticated coordinator WebSocket
    member_ws,  # Fixture providing authenticated member WebSocket
):
    """Test complete task flow from creation to completion.
    
    Steps:
    1. Coordinator creates task
    2. Member receives task_assigned message
    3. Member acknowledges task
    4. Coordinator receives task_acknowledged message
    5. Member starts task
    6. Member completes task
    7. Coordinator receives task_completed message
    """
    # Step 1: Coordinator creates task via REST API
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{live_server}/api/operator/tasks",
            headers={"Authorization": f"Bearer {coordinator_token}"},
            json={
                "assignee_id": str(member_id),
                "task_type": "CONFIRMATION",
                "title": "Test task lifecycle",
                "description": "Verify end-to-end task flow",
                "timeout_minutes": 15,
                "priority": 1,
            },
        ) as resp:
            assert resp.status == 201
            task = await resp.json()
            task_id = task["id"]
            assert task["state"] == "assigned"
            assert task["assignee_id"] == str(member_id)

    # Step 2: Member should receive task_assigned WebSocket message
    msg = await asyncio.wait_for(member_ws.recv(), timeout=5.0)
    payload = json.loads(msg)
    assert payload["type"] == "task_assigned"
    assert payload["task"]["id"] == task_id

    # Step 3: Member acknowledges task
    await member_ws.send(json.dumps({
        "type": "task_acknowledge",
        "task_id": task_id,
    }))

    # Step 4: Coordinator should receive task_acknowledged message
    msg = await asyncio.wait_for(coordinator_ws.recv(), timeout=5.0)
    payload = json.loads(msg)
    assert payload["type"] == "task_acknowledged"
    assert payload["task"]["id"] == task_id
    assert payload["task"]["state"] == "acknowledged"

    # Step 5: Member starts task
    await member_ws.send(json.dumps({
        "type": "task_start",
        "task_id": task_id,
    }))

    # Step 6: Member completes task
    await member_ws.send(json.dumps({
        "type": "task_complete",
        "task_id": task_id,
        "outcome": "SUCCESS",
        "notes": "Task completed successfully in E2E test",
    }))

    # Step 7: Coordinator should receive task_completed message
    msg = await asyncio.wait_for(coordinator_ws.recv(), timeout=5.0)
    payload = json.loads(msg)
    assert payload["type"] == "task_completed"
    assert payload["task"]["id"] == task_id
    assert payload["task"]["state"] == "completed"
    assert payload["task"]["outcome"] == "SUCCESS"


@pytest.mark.asyncio
async def test_task_reconnect_resilience(
    live_server,
    coordinator_ws,
    member_ws,
):
    """Test that task state survives member reconnect.
    
    Steps:
    1. Coordinator creates task
    2. Member receives task
    3. Member disconnects
    4. Member reconnects
    5. Member calls /api/member/tasks/active
    6. Should receive the same task
    """
    # Step 1: Create task
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{live_server}/api/operator/tasks",
            headers={"Authorization": f"Bearer {coordinator_token}"},
            json={
                "assignee_id": str(member_id),
                "task_type": "CHECKPOINT",
                "title": "Reconnect test task",
                "timeout_minutes": 30,
            },
        ) as resp:
            assert resp.status == 201
            task = await resp.json()
            task_id = task["id"]

    # Step 2: Member receives task
    msg = await asyncio.wait_for(member_ws.recv(), timeout=5.0)
    payload = json.loads(msg)
    assert payload["type"] == "task_assigned"

    # Step 3: Member disconnects
    await member_ws.close()

    # Step 4: Member reconnects with new WebSocket
    async with websockets.connect(
        f"ws://{live_server_host}/ws",
        extra_headers={"Cookie": f"osk_member_runtime_session={member_runtime_token}"},
    ) as new_ws:
        # Wait for auth_ok
        msg = await asyncio.wait_for(new_ws.recv(), timeout=5.0)
        payload = json.loads(msg)
        assert payload["type"] == "auth_ok"

        # Step 5 & 6: Fetch active task via REST API
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{live_server}/api/member/tasks/active",
                headers={"Authorization": f"Bearer {member_runtime_token}"},
            ) as resp:
                assert resp.status == 200
                data = await resp.json()
                assert data["task"] is not None
                assert data["task"]["id"] == task_id
                assert data["task"]["state"] == "assigned"


@pytest.mark.asyncio
async def test_task_cancel(
    live_server,
    coordinator_ws,
    member_ws,
):
    """Test task cancellation by coordinator.
    
    Steps:
    1. Coordinator creates task
    2. Member receives task
    3. Coordinator cancels task
    4. Member should receive cancellation notification
    """
    # Step 1: Create task
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{live_server}/api/operator/tasks",
            headers={"Authorization": f"Bearer {coordinator_token}"},
            json={
                "assignee_id": str(member_id),
                "task_type": "CUSTOM",
                "title": "Cancel test task",
            },
        ) as resp:
            assert resp.status == 201
            task = await resp.json()
            task_id = task["id"]

    # Step 2: Member receives task
    msg = await asyncio.wait_for(member_ws.recv(), timeout=5.0)
    payload = json.loads(msg)
    assert payload["type"] == "task_assigned"

    # Step 3: Coordinator cancels task
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{live_server}/api/operator/tasks/{task_id}/cancel",
            headers={"Authorization": f"Bearer {coordinator_token}"},
            json={"reason": "Test cancellation"},
        ) as resp:
            assert resp.status == 200

    # Step 4: Member should receive cancellation
    msg = await asyncio.wait_for(member_ws.recv(), timeout=5.0)
    payload = json.loads(msg)
    assert payload["type"] == "task_cancelled"
    assert payload["task_id"] == task_id


# Manual validation checklist (for human testing)
MANUAL_VALIDATION_CHECKLIST = """
# Task Management Manual Validation Checklist

## Task Creation
- [ ] Coordinator can create all task types (CONFIRMATION, CHECKPOINT, REPORT, CUSTOM)
- [ ] Location target optional but functional
- [ ] Priority levels work correctly
- [ ] Timeout settings respected

## Task Assignment
- [ ] Member receives notification banner
- [ ] Task appears in member UI
- [ ] Correct task details shown

## Task State Flow
- [ ] ASSIGNED → ACKNOWLEDGED transition works
- [ ] ACKNOWLEDGED → IN_PROGRESS transition works
- [ ] IN_PROGRESS → COMPLETED (all outcomes) works
- [ ] Invalid transitions rejected

## Reconnect Resilience
- [ ] Task survives browser refresh
- [ ] Task survives WebSocket reconnect
- [ ] State synchronized correctly after reconnect

## Timeout Handling
- [ ] Task times out after deadline
- [ ] Member receives timeout notification
- [ ] Coordinator receives timeout notification

## Cancellation
- [ ] Coordinator can cancel active task
- [ ] Member receives cancellation notification
- [ ] Cancelled task disappears from active list

## Coordinator Dashboard
- [ ] Active tasks list updates in real-time
- [ ] Priority indicators show correctly
- [ ] Overdue tasks highlighted
- [ ] Task detail modal shows correct info
- [ ] Cancel/Retry buttons work

## Member UX
- [ ] Notification banner displays
- [ ] Task panel opens correctly
- [ ] State buttons appear appropriately
- [ ] Timer counts down correctly
- [ ] Completion modal submits successfully
- [ ] Push feed shows task events

## Performance
- [ ] Task list loads quickly (<1s)
- [ ] WebSocket messages delivered promptly
- [ ] No UI lag during task operations
"""
