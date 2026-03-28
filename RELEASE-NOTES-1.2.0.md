# Release Notes - Osk 1.2.0

**Release:** 1.2.0 "Coordinator-Directed Operations"  
**Date:** March 28, 2026  
**Tag:** `v1.2.0`

---

## 🎯 Overview

Release 1.2.0 transforms Osk from **passive awareness** into **active field coordination**. Coordinators can now direct group operations by assigning tasks to members, tracking progress in real-time, and making informed decisions based on task outcomes.

This is a major milestone toward the "Coordinator-Directed Operations" vision outlined in the product roadmap.

---

## ✨ What's New

### Task Management System

The core feature of 1.2.0 is a complete task management system:

**For Coordinators:**
- Create tasks with types: Confirmation, Checkpoint, Report, or Custom
- Assign to specific members with priority levels
- Set geographic targets and deadlines
- Track task state in real-time
- Cancel or retry timed-out tasks

**For Members:**
- Receive notification banners for new tasks
- View task details in full-screen panel
- Acknowledge, start, and complete tasks
- Report inability to complete
- See countdown timer for deadlines

### Task Lifecycle

```
[Coordinator Creates] 
         ↓
   [ASSIGNED] → Member receives notification
         ↓
[ACKNOWLEDGED] → Member confirms receipt
         ↓
 [IN_PROGRESS] → Member starts work
         ↓
   [COMPLETED] → Success / Failed / Unable
         ↓
[Coordinator Reviews Outcome]
```

---

## 📋 Task Types

| Type | Use Case |
|------|----------|
| **CONFIRMATION** | Verify something at a location |
| **CHECKPOINT** | Reach a checkpoint and report |
| **REPORT** | Gather and report observations |
| **CUSTOM** | Freeform task description |

---

## 🚀 Quick Start

### Creating a Task (Coordinator)

1. Open Coordinator Dashboard (`osk dashboard`)
2. Click "+ Assign Task"
3. Select member, type, title
4. Optional: Add location target, set priority
5. Click "Assign Task"

### Completing a Task (Member)

1. Tap notification banner or "View Task"
2. Review task details
3. Tap "Acknowledge" → "Start" → "Complete"
4. Select outcome: Success / Failed / Unable
5. Add optional notes

---

## 🔌 API Reference

### Coordinator Endpoints

```bash
# Create task
POST /api/operator/tasks
{
  "assignee_id": "uuid",
  "task_type": "CONFIRMATION",
  "title": "Check intersection",
  "timeout_minutes": 15,
  "priority": 2
}

# List tasks
GET /api/operator/tasks?state=assigned&assignee_id=uuid

# Cancel task
POST /api/operator/tasks/{id}/cancel
{"reason": "No longer needed"}
```

### Member Endpoints

```bash
# Get active task
GET /api/member/tasks/active

# Acknowledge task
POST /api/member/tasks/{id}/acknowledge

# Complete task
POST /api/member/tasks/{id}/complete
{
  "outcome": "SUCCESS",
  "notes": "Intersection clear"
}
```

---

## 📊 Performance

- Task list loads in <500ms
- WebSocket notifications delivered in <100ms
- Background timeout checking every 30 seconds
- UI polling every 5 seconds for coordinators

---

## 🧪 Testing

Run the validation script:

```bash
python scripts/validate_1_2_0.py --hub-url https://localhost:8444
```

Run E2E tests:

```bash
pytest tests/e2e/test_task_flow.py -v
```

---

## 📚 Documentation

- [Implementation Plan](docs/plans/2026-03-28-plan-32-release-1-2-0-implementation.md)
- [End-State Roadmap](docs/plans/2026-03-28-end-state-product-roadmap.md)
- [Full Changelog](CHANGELOG.md)

---

## 🔄 Migration Notes

Database migration `009_tasks.sql` is automatically applied on hub start. No manual action required.

---

## 🙏 Credits

- Implementation by @justinredmondsmith-collab
- Architecture based on End-State Product Roadmap
- Testing with Pixel 6 and containerized browsers

---

## 🔗 Links

- GitHub: https://github.com/justinredmondsmith-collab/osk
- Documentation: See `docs/` directory
- Issues: https://github.com/justinredmondsmith-collab/osk/issues

---

*Release 1.2.0 - Coordinator-Directed Operations*
