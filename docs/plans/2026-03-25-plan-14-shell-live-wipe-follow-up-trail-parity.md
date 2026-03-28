# Shell And Live-Wipe Follow-Up Trail Parity Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make shell/operator flows show the same recent follow-up trail context as the live dashboard and API by decorating hub-side wipe readiness with recent review, verification, and reopen history.

**Architecture:** Reuse the existing follow-up history decoration logic instead of inventing a shell-only formatter. Apply it to hub-side wipe readiness snapshots and to the `/api/wipe` coverage response, then print concise trail summaries and recent entries in shell output.

**Tech Stack:** Python, FastAPI, CLI shell output, pytest

---

### Task 1: Decorate Live Wipe Coverage

**Files:**
- Modify: `src/osk/server.py`
- Modify: `tests/test_server.py`

**Step 1: Write the failing tests**

Cover:
- `/api/wipe` returning `follow_up_history_count` and `follow_up_history_summary`
- recent review or verification trail entries surviving in the wipe response

**Step 2: Keep ordering honest**

Decorate coverage from the pre-existing audit slice before the new `wipe_triggered` event is added.

### Task 2: Decorate Hub Shell Snapshots

**Files:**
- Modify: `src/osk/hub.py`
- Modify: `tests/test_hub.py`

**Step 1: Write the failing tests**

Cover:
- `osk status` printing follow-up-trail summary when recent history exists
- `osk members` printing the same trail summary
- `osk wipe` printing the trail summary and recent entries from the decorated response

**Step 2: Keep shell output concise**

Show the trail summary plus a short list of recent entries; do not dump the full audit slice.

### Task 3: Update Runbook Language

**Files:**
- Modify: `docs/runbooks/operations-drills.md`

**Step 1: Clarify shell parity**

Document that shell wipe-readiness surfaces now include recent follow-up trail context, not just current unresolved counts.

### Task 4: Verify

**Files:**
- Modify as needed based on earlier tasks

**Step 1: Run focused tests**

Run:
- `pytest tests/test_server.py tests/test_hub.py -q`

**Step 2: Run lightweight static checks**

Run:
- `ruff check src/osk/server.py src/osk/hub.py tests/test_server.py tests/test_hub.py`

**Step 3: Run full suite**

Run:
- `pytest`

### Done When

- `/api/wipe` includes decorated follow-up history fields
- `osk status`, `osk members`, and wipe output show recent follow-up trail context
- runbook language matches the shell behavior
- full test suite stays green



> Roadmap note: This file is a scoped implementation or historical planning document. Read it through [`2026-03-28-end-state-product-roadmap.md`](./2026-03-28-end-state-product-roadmap.md). If sequencing, priority, or scope conflict with the roadmap, follow the roadmap.
