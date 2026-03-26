# Machine-Readable Members Parity Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Bring machine-readable local handoff up to parity with the enriched shell views by making `osk members --json` include decorated wipe readiness and by capturing that JSON snapshot in the real-hub validation artifacts.

**Architecture:** Replace the bare list JSON contract for `osk members --json` with a structured snapshot object containing `members` and decorated `wipe_readiness`. Reuse the existing local snapshot capture helper in `real_hub_validation.py` to persist a `members` snapshot alongside `doctor` and `status`.

**Tech Stack:** Python, CLI JSON contracts, repo-owned validation script, pytest

---

### Task 1: Extend `osk members --json`

**Files:**
- Modify: `src/osk/hub.py`
- Modify: `tests/test_hub.py`

**Step 1: Write the failing tests**

Cover:
- `osk members --json` returning an object with `members`
- the same payload also including decorated `wipe_readiness`
- recent follow-up trail metadata present in the JSON output

**Step 2: Keep the human output unchanged**

Only the JSON shape changes here. Human-readable `osk members` should stay concise.

### Task 2: Capture Members Snapshot In Validation Artifacts

**Files:**
- Modify: `scripts/real_hub_validation.py`
- Modify: `tests/test_real_hub_validation_contract.py`

**Step 1: Write the failing tests**

Cover:
- `_collect_local_snapshots` including `members_snapshot_path`
- dry-run result and preflight artifacts surfacing the members snapshot path and metadata

**Step 2: Reuse the existing capture helper**

Do not create a second snapshot path implementation when `_capture_local_snapshot` already exists.

### Task 3: Update Runbook Language

**Files:**
- Modify: `docs/runbooks/real-hub-validation.md`

**Step 1: Document the new local snapshot**

Clarify that local preflight snapshots now include `members --json`, which carries both member rows and decorated wipe readiness.

### Task 4: Verify

**Files:**
- Modify as needed based on earlier tasks

**Step 1: Run focused tests**

Run:
- `pytest tests/test_hub.py tests/test_real_hub_validation_contract.py -q`

**Step 2: Run lightweight static checks**

Run:
- `ruff check src/osk/hub.py scripts/real_hub_validation.py tests/test_hub.py tests/test_real_hub_validation_contract.py`

**Step 3: Run full suite**

Run:
- `pytest`

### Done When

- `osk members --json` includes `members` plus decorated `wipe_readiness`
- real-hub validation captures and reports a `members` snapshot path
- runbook language matches the new machine-readable handoff
- full test suite stays green
