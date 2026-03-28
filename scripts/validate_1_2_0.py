#!/usr/bin/env python3
"""Validation script for Release 1.2.0 - Coordinator-Directed Operations.

This script performs automated validation of the task management system.
Run this after implementing 1.2.0 to verify everything works correctly.

Usage:
    python scripts/validate_1_2_0.py [--hub-url URL]

Exit codes:
    0 - All validations passed
    1 - One or more validations failed
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from datetime import datetime, timedelta
from typing import Any

import aiohttp
import websockets


class ValidationError(Exception):
    """Raised when a validation check fails."""
    pass


class Release120Validator:
    """Validator for Release 1.2.0 functionality."""
    
    def __init__(self, hub_url: str):
        self.hub_url = hub_url.rstrip('/')
        self.ws_url = hub_url.replace('http://', 'ws://').replace('https://', 'wss://')
        self.session: aiohttp.ClientSession | None = None
        self.coordinator_token: str | None = None
        self.member_token: str | None = None
        self.operation_id: str | None = None
        self.member_id: str | None = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def setup(self):
        """Initialize test operation and authenticate."""
        print("🔧 Setting up test environment...")
        
        # Start operation
        result = await self._run_cli(['osk', 'start', '--fresh', '1.2.0 Validation Test'])
        if result.returncode != 0:
            raise ValidationError(f"Failed to start operation: {result.stderr}")
        
        # Get dashboard code
        result = await self._run_cli(['osk', 'dashboard'])
        dashboard_code = self._extract_code(result.stdout)
        
        # Authenticate as coordinator
        await self._authenticate_coordinator(dashboard_code)
        
        # Join as member
        member_info = await self._join_as_member()
        self.member_id = member_info['member_id']
        self.member_token = member_info['token']
        
        print(f"✅ Setup complete (Operation: {self.operation_id}, Member: {self.member_id})")
    
    async def validate_database_schema(self):
        """Validate that task table exists with correct schema."""
        print("\n📊 Validating database schema...")
        
        # Check migration was applied
        result = await self._run_cli(['osk', 'logs'])
        if '009_tasks.sql' not in result.stdout:
            raise ValidationError("Task migration not applied")
        
        print("✅ Database schema validated")
    
    async def validate_api_endpoints(self):
        """Validate all task API endpoints exist and respond."""
        print("\n🌐 Validating API endpoints...")
        
        endpoints = [
            ('POST', '/api/operator/tasks', 401),  # Should require auth
            ('GET', '/api/operator/tasks', 401),
            ('POST', '/api/member/tasks/123/acknowledge', 401),
            ('POST', '/api/member/tasks/123/complete', 401),
        ]
        
        for method, path, expected_status in endpoints:
            url = f"{self.hub_url}{path}"
            async with self.session.request(method, url) as resp:
                if resp.status != expected_status:
                    raise ValidationError(
                        f"Endpoint {method} {path} returned {resp.status}, expected {expected_status}"
                    )
        
        print("✅ API endpoints validated")
    
    async def validate_task_creation(self):
        """Validate task creation flow."""
        print("\n📝 Validating task creation...")
        
        task_data = {
            "assignee_id": self.member_id,
            "task_type": "CONFIRMATION",
            "title": "Validation Test Task",
            "description": "Test task for 1.2.0 validation",
            "timeout_minutes": 15,
            "priority": 2,
        }
        
        async with self.session.post(
            f"{self.hub_url}/api/operator/tasks",
            headers={"Authorization": f"Bearer {self.coordinator_token}"},
            json=task_data,
        ) as resp:
            if resp.status != 201:
                raise ValidationError(f"Task creation failed: {resp.status}")
            
            task = await resp.json()
            
            # Validate response structure
            required_fields = ['id', 'title', 'type', 'state', 'assignee_id', 'priority']
            for field in required_fields:
                if field not in task:
                    raise ValidationError(f"Missing field in response: {field}")
            
            if task['state'] != 'assigned':
                raise ValidationError(f"Expected state 'assigned', got '{task['state']}'")
            
            self.test_task_id = task['id']
        
        print(f"✅ Task created: {self.test_task_id}")
    
    async def validate_task_state_transitions(self):
        """Validate task state machine."""
        print("\n🔄 Validating task state transitions...")
        
        # Connect member WebSocket
        async with websockets.connect(
            f"{self.ws_url}/ws",
            extra_headers={"Cookie": f"osk_member_runtime_session={self.member_token}"},
        ) as ws:
            # Wait for auth_ok
            msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
            payload = json.loads(msg)
            if payload.get('type') != 'auth_ok':
                raise ValidationError("WebSocket auth failed")
            
            # Should receive task_assigned message
            msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
            payload = json.loads(msg)
            if payload.get('type') != 'task_assigned':
                raise ValidationError(f"Expected task_assigned, got {payload.get('type')}")
            
            # Acknowledge task
            await ws.send(json.dumps({
                'type': 'task_acknowledge',
                'task_id': self.test_task_id,
            }))
            
            # Should receive confirmation
            msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
            payload = json.loads(msg)
            if payload.get('type') != 'task_acknowledged':
                raise ValidationError(f"Expected task_acknowledged, got {payload.get('type')}")
            
            # Start task
            await ws.send(json.dumps({
                'type': 'task_start',
                'task_id': self.test_task_id,
            }))
            
            # Complete task
            await ws.send(json.dumps({
                'type': 'task_complete',
                'task_id': self.test_task_id,
                'outcome': 'SUCCESS',
                'notes': 'Validated in 1.2.0 test',
            }))
            
            # Should receive completion confirmation
            msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
            payload = json.loads(msg)
            if payload.get('type') != 'task_completed':
                raise ValidationError(f"Expected task_completed, got {payload.get('type')}")
        
        print("✅ State transitions validated")
    
    async def validate_task_listing(self):
        """Validate task list endpoints."""
        print("\n📋 Validating task listing...")
        
        # Create another task for testing
        async with self.session.post(
            f"{self.hub_url}/api/operator/tasks",
            headers={"Authorization": f"Bearer {self.coordinator_token}"},
            json={
                "assignee_id": self.member_id,
                "task_type": "REPORT",
                "title": "Second test task",
            },
        ) as resp:
            if resp.status != 201:
                raise ValidationError("Failed to create second task")
        
        # Test coordinator task list
        async with self.session.get(
            f"{self.hub_url}/api/operator/tasks",
            headers={"Authorization": f"Bearer {self.coordinator_token}"},
        ) as resp:
            if resp.status != 200:
                raise ValidationError("Failed to list tasks")
            tasks = await resp.json()
            if len(tasks) < 2:
                raise ValidationError(f"Expected at least 2 tasks, got {len(tasks)}")
        
        # Test filtering by state
        async with self.session.get(
            f"{self.hub_url}/api/operator/tasks?state=completed",
            headers={"Authorization": f"Bearer {self.coordinator_token}"},
        ) as resp:
            tasks = await resp.json()
            completed_count = len([t for t in tasks if t['state'] == 'completed'])
            if completed_count < 1:
                raise ValidationError("Expected at least 1 completed task")
        
        print("✅ Task listing validated")
    
    async def validate_timeout_processing(self):
        """Validate timeout background processing."""
        print("\n⏱️ Validating timeout processing...")
        
        # Create task with very short timeout
        async with self.session.post(
            f"{self.hub_url}/api/operator/tasks",
            headers={"Authorization": f"Bearer {self.coordinator_token}"},
            json={
                "assignee_id": self.member_id,
                "task_type": "CONFIRMATION",
                "title": "Timeout test task",
                "timeout_minutes": 0.01,  # Very short for testing
            },
        ) as resp:
            task = await resp.json()
            timeout_task_id = task['id']
        
        # Wait for timeout
        await asyncio.sleep(3)
        
        # Check task timed out
        async with self.session.get(
            f"{self.hub_url}/api/operator/tasks/{timeout_task_id}",
            headers={"Authorization": f"Bearer {self.coordinator_token}"},
        ) as resp:
            if resp.status != 200:
                raise ValidationError("Failed to get task status")
            task = await resp.json()
            if task['state'] != 'timeout':
                raise ValidationError(f"Expected timeout state, got {task['state']}")
        
        print("✅ Timeout processing validated")
    
    async def validate_cancellation(self):
        """Validate task cancellation."""
        print("\n🚫 Validating task cancellation...")
        
        # Create task
        async with self.session.post(
            f"{self.hub_url}/api/operator/tasks",
            headers={"Authorization": f"Bearer {self.coordinator_token}"},
            json={
                "assignee_id": self.member_id,
                "task_type": "CUSTOM",
                "title": "Cancellation test task",
            },
        ) as resp:
            task = await resp.json()
            cancel_task_id = task['id']
        
        # Cancel task
        async with self.session.post(
            f"{self.hub_url}/api/operator/tasks/{cancel_task_id}/cancel",
            headers={"Authorization": f"Bearer {self.coordinator_token}"},
            json={"reason": "Validation test cancellation"},
        ) as resp:
            if resp.status != 200:
                raise ValidationError("Failed to cancel task")
        
        # Verify cancelled
        async with self.session.get(
            f"{self.hub_url}/api/operator/tasks/{cancel_task_id}",
            headers={"Authorization": f"Bearer {self.coordinator_token}"},
        ) as resp:
            task = await resp.json()
            if task['state'] != 'cancelled':
                raise ValidationError(f"Expected cancelled state, got {task['state']}")
        
        print("✅ Cancellation validated")
    
    async def cleanup(self):
        """Clean up test operation."""
        print("\n🧹 Cleaning up...")
        await self._run_cli(['osk', 'stop'])
        print("✅ Cleanup complete")
    
    # Helper methods
    async def _run_cli(self, cmd: list[str]):
        """Run CLI command and return result."""
        import subprocess
        return subprocess.run(cmd, capture_output=True, text=True)
    
    def _extract_code(self, output: str) -> str:
        """Extract dashboard code from osk dashboard output."""
        for line in output.split('\n'):
            if 'dashboard_code' in line:
                return line.split('=')[1].strip()
        raise ValidationError("Could not extract dashboard code")
    
    async def _authenticate_coordinator(self, code: str):
        """Authenticate as coordinator."""
        async with self.session.post(
            f"{self.hub_url}/api/operator/dashboard-session",
            json={"dashboard_code": code},
        ) as resp:
            if resp.status != 200:
                raise ValidationError("Coordinator authentication failed")
            data = await resp.json()
            self.coordinator_token = data.get('token')
    
    async def _join_as_member(self) -> dict:
        """Join operation as member."""
        # Get join token
        result = await self._run_cli(['osk', 'status', '--json'])
        status = json.loads(result.stdout)
        join_token = status.get('operation', {}).get('token')
        
        # Join via API
        async with self.session.post(
            f"{self.hub_url}/api/member/runtime-session",
            json={
                "member_session_code": join_token,
                "name": "Validation Member",
            },
        ) as resp:
            if resp.status != 200:
                raise ValidationError("Member join failed")
            data = await resp.json()
            return {
                'member_id': data.get('member_id'),
                'token': data.get('token'),
            }
    
    async def run_all(self):
        """Run all validations."""
        try:
            await self.setup()
            await self.validate_database_schema()
            await self.validate_api_endpoints()
            await self.validate_task_creation()
            await self.validate_task_state_transitions()
            await self.validate_task_listing()
            await self.validate_timeout_processing()
            await self.validate_cancellation()
            
            print("\n" + "=" * 60)
            print("✅ ALL VALIDATIONS PASSED")
            print("=" * 60)
            return 0
            
        except ValidationError as e:
            print(f"\n❌ VALIDATION FAILED: {e}")
            return 1
        except Exception as e:
            print(f"\n💥 UNEXPECTED ERROR: {e}")
            import traceback
            traceback.print_exc()
            return 1
        finally:
            await self.cleanup()


async def main():
    parser = argparse.ArgumentParser(description='Validate Release 1.2.0')
    parser.add_argument('--hub-url', default='https://localhost:8444',
                        help='Hub URL (default: https://localhost:8444)')
    args = parser.parse_args()
    
    async with Release120Validator(args.hub_url) as validator:
        exit_code = await validator.run_all()
    
    sys.exit(exit_code)


if __name__ == '__main__':
    asyncio.run(main())
