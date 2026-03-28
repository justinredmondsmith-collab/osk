# Historical Drift Review Capture Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let operators record that a historical-drift wipe follow-up item was reviewed, and surface that review across the existing API and dashboard without resolving the cleanup boundary.

**Architecture:** Reuse the existing wipe follow-up audit trail, member detail endpoint, and wipe-readiness summary model. Add a new non-destructive audit marker for historical-drift review, thread it into wipe-readiness decoration, and render it in the dashboard as operator guidance rather than closure.

**Tech Stack:** Python, FastAPI, existing audit trail helpers, dashboard JS, pytest

---

### Task 1: Define the Historical Drift Review Contract

**Files:**
- Modify: `src/osk/audit.py`
- Modify: `tests/test_server.py`

**Step 1: Write the failing tests**

Cover:
- a dedicated audit action for historical-drift review
- `wipe_follow_up_only=true` including that action
- detail and summary payloads exposing review markers without changing `follow_up_required`

**Step 2: Keep the semantics narrow**

The review action must mean:
- an operator inspected this historical-drift item
- the item is still unresolved unless separately verified
- age plus review still do not silently close the wipe boundary

### Task 2: Add the Review Marker to Wipe Follow-Up State

**Files:**
- Modify: `src/osk/wipe_readiness.py`
- Modify: `src/osk/server.py`
- Modify: `tests/test_wipe_readiness.py`
- Modify: `tests/test_server.py`

**Step 1: Extend follow-up items with review metadata**

At minimum:
- `historical_reviewed`
- `historical_reviewed_at`
- summary/count fields for reviewed vs unreviewed historical drift

**Step 2: Keep review metadata scoped**

Only historical-drift items should use the review marker. Active unresolved items should continue to use the verify/reopen loop.

**Step 3: Preserve closure truth**

Reviewed historical drift can improve operator interpretation and handoff, but it must not alter `resolution`, `follow_up_required`, or ready/blocked status by itself.

### Task 3: Add the Operator Review Endpoint

**Files:**
- Modify: `src/osk/server.py`
- Modify: `tests/test_server.py`

**Step 1: Write the failing endpoint test**

Add a POST route for member-scoped historical-drift review that:
- rejects unknown members
- rejects non-historical items
- records an audit event for valid historical-drift items
- returns updated wipe-readiness and member detail payloads

**Step 2: Implement minimal route logic**

Use the existing local-admin boundary and audit event insertion flow. Do not create new persistence beyond the audit trail.

### Task 4: Surface the Review in the Dashboard

**Files:**
- Modify: `src/osk/static/dashboard.js`

**Step 1: Render reviewed historical drift explicitly**

Show:
- a separate count in the wipe summary
- a review note in current/detail cards
- a `Record review` action only for unresolved historical-drift items

**Step 2: Keep the message honest**

The UI copy should say the item was reviewed, not resolved or cleared.

### Task 5: Update Runbooks and Verify

**Files:**
- Modify: `docs/runbooks/operations-drills.md`
- Modify: `docs/runbooks/real-hub-validation.md`

**Step 1: Document what review means**

Clarify:
- reviewed historical drift is a handoff/interpretation aid
- it does not replace verification or cleanup
- closure remains open until unresolved follow-up is actually cleared or verified

**Step 2: Verify**

Run:
- `pytest tests/test_wipe_readiness.py tests/test_server.py -q`
- `pytest`

### Done When

- A historical-drift item can be reviewed without being resolved
- API payloads expose reviewed vs unreviewed historical drift counts
- Member detail shows the latest historical-drift review marker
- Dashboard operators can record review from the current follow-up surface
- Audit filtering includes the new review action
- Full test suite stays green



> Roadmap note: This file is a scoped implementation or historical planning document. Read it through [`2026-03-28-end-state-product-roadmap.md`](./2026-03-28-end-state-product-roadmap.md). If sequencing, priority, or scope conflict with the roadmap, follow the roadmap.
