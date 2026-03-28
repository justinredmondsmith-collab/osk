# Closure Trail Artifact Capture Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend the repo-owned real-hub closure artifacts so they retain the same member-scoped follow-up trail context now available in the live dashboard and API, including recent history-only members whose current follow-up has already cleared.

**Architecture:** Reuse the existing `/api/coordinator/dashboard-state` and `/api/coordinator/wipe-follow-up/{member_id}` surfaces. Expand the artifact writer to capture unique member detail files from both unresolved follow-up and recent follow-up history, and add follow-up-trail summary fields to `closure-summary.json` for handoff parity.

**Tech Stack:** Python, repo-owned validation script, pytest

---

### Task 1: Extend the Closure Summary Contract

**Files:**
- Modify: `scripts/real_hub_validation.py`
- Modify: `tests/test_real_hub_validation_contract.py`

**Step 1: Write the failing tests**

Cover:
- `closure-summary.json` including `follow_up_history_count` and `follow_up_history_summary`
- open-follow-up capture still working with the new summary fields present

**Step 2: Implement minimal summary additions**

Mirror the already-available `wipe_readiness` history fields. Do not invent a second summary model.

### Task 2: Capture Member Detail Artifacts for Trail Members

**Files:**
- Modify: `scripts/real_hub_validation.py`
- Modify: `tests/test_real_hub_validation_contract.py`

**Step 1: Write the failing tests**

Cover:
- recent follow-up-history members getting `wipe-follow-up-<member-id>.json` artifacts even when `follow_up` is `null`
- duplicate member IDs across unresolved follow-up and history only producing one artifact fetch

**Step 2: Keep artifact semantics honest**

History-only detail artifacts should remain member-scoped context captures, not active-task indicators.

### Task 3: Update Runbook Language

**Files:**
- Modify: `docs/runbooks/real-hub-validation.md`

**Step 1: Clarify artifact scope**

Document that:
- `closure-summary.json` now carries follow-up-trail summary metadata
- `wipe-follow-up-<member-id>.json` may be captured for recent trail members even after current follow-up has cleared

### Task 4: Verify

**Files:**
- Modify as needed based on earlier tasks

**Step 1: Run focused tests**

Run:
- `pytest tests/test_real_hub_validation_contract.py -q`

**Step 2: Run lightweight static checks**

Run:
- `ruff check scripts/real_hub_validation.py tests/test_real_hub_validation_contract.py`

**Step 3: Run full suite**

Run:
- `pytest`

### Done When

- `closure-summary.json` includes follow-up-trail count and summary fields
- closure capture writes member detail artifacts for recent follow-up trail members, not only unresolved current items
- runbook language matches the new artifact behavior
- full test suite stays green



> Roadmap note: This file is a scoped implementation or historical planning document. Read it through [`2026-03-28-end-state-product-roadmap.md`](./2026-03-28-end-state-product-roadmap.md). If sequencing, priority, or scope conflict with the roadmap, follow the roadmap.
