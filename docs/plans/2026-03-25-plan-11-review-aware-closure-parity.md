# Review-Aware Closure Parity Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Carry historical-drift review markers into real-hub closure artifacts and read-only shell/drill surfaces so browser, JSON, and terminal workflows tell the same closure story.

**Architecture:** Reuse the existing wipe-readiness summary model, closure-summary artifact, and hub/drill reporting surfaces. Add reviewed historical-drift counts and messaging to those outputs without changing resolution semantics or cleanup guarantees.

**Tech Stack:** Python, repo-owned validation script, hub/drill CLI surfaces, pytest

---

### Task 1: Extend the Closure Artifact Contract

**Files:**
- Modify: `scripts/real_hub_validation.py`
- Modify: `tests/test_real_hub_validation_contract.py`

**Step 1: Write the failing tests**

Cover:
- `closure-summary.json` including reviewed vs unreviewed historical drift counts
- open follow-up summaries reflecting reviewed historical drift separately from active unresolved risk
- per-member detail capture still working when unresolved items include reviewed historical drift

**Step 2: Implement minimal closure-summary additions**

Add only the review-aware fields already present in `wipe_readiness`; do not invent a second closure model.

### Task 2: Mirror Review-Aware Counts in Hub Output

**Files:**
- Modify: `src/osk/hub.py`
- Modify: `tests/test_hub.py`

**Step 1: Write the failing tests**

Cover:
- shell summary counts including reviewed historical drift
- follow-up rows indicating whether a historical-drift item was reviewed

**Step 2: Keep the text honest**

Shell output should say reviewed historical drift was inspected, not resolved.

### Task 3: Extend the Wipe Drill Report

**Files:**
- Modify: `src/osk/drills.py`
- Modify: `tests/test_drills.py`

**Step 1: Write the failing tests**

Cover:
- `closure_interpretation` mentioning reviewed historical drift
- drill output distinguishing reviewed drift from unreviewed drift in guidance text

**Step 2: Keep drill semantics read-only**

The drill remains explanatory only. No new mutation or automatic cleanup behavior.

### Task 4: Update Runbook Language

**Files:**
- Modify: `docs/runbooks/operations-drills.md`
- Modify: `docs/runbooks/real-hub-validation.md`

**Step 1: Document review-aware closure interpretation**

Clarify:
- reviewed historical drift is now visible in closure artifacts and terminal output
- it remains a handoff aid, not a closure event
- unresolved follow-up still keeps the boundary open

### Task 5: Verify

**Files:**
- Modify as needed based on earlier tasks

**Step 1: Run focused tests**

Run:
- `pytest tests/test_real_hub_validation_contract.py tests/test_hub.py tests/test_drills.py -q`

**Step 2: Run full suite**

Run:
- `pytest`

### Done When

- `closure-summary.json` includes reviewed historical drift counts
- shell/read-only outputs show reviewed historical drift separately from unreviewed drift
- runbooks explain the new parity without overstating cleanup guarantees
- full test suite stays green
