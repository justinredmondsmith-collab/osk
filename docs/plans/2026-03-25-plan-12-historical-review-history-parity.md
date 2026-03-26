# Historical Review History Parity Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Carry historical-drift review events into the same member-scoped follow-up history trail used for verification and reopen events so dashboard detail, member detail, audit filtering, and CLI guidance all describe the same operator workflow.

**Architecture:** Extend the existing `follow_up_history` model instead of creating a second review-history surface. Keep verification semantics intact, add explicit review event metadata for historical-drift items, and update UI/CLI wording so review is visible as audit evidence without being misread as closure.

**Tech Stack:** Python, FastAPI payload shaping, dashboard JavaScript, argparse help text, pytest

---

### Task 1: Generalize the Follow-Up History Contract

**Files:**
- Modify: `src/osk/server.py`
- Modify: `tests/test_server.py`

**Step 1: Write the failing tests**

Cover:
- dashboard-state `follow_up_history` including historical review entries
- member detail returning review events in `history`
- summary text no longer pretending the trail is verification-only

**Step 2: Implement minimal history-contract changes**

Add explicit event metadata such as review timestamps and event kind while preserving the existing verification fields used by current callers.

### Task 2: Keep Dashboard Detail Honest

**Files:**
- Modify: `src/osk/static/dashboard.js`

**Step 1: Render review entries distinctly**

Update member/detail and sidebar history rendering so review events say `Reviewed ...` rather than `Verified ...`, and rename any verification-only labels that now represent a mixed audit trail.

**Step 2: Preserve closure semantics**

Review entries must remain visibly non-closing. The detail text should continue to distinguish review evidence from verified cleanup.

### Task 3: Align CLI Audit Guidance

**Files:**
- Modify: `src/osk/cli.py`
- Modify: `tests/test_cli.py`

**Step 1: Write the failing test**

Cover:
- `osk audit --help` or parser help text mentioning review events in the `--wipe-follow-up-only` description

**Step 2: Update wording only**

No behavior change is needed here; the filter already includes the review action.

### Task 4: Update Runbook Language

**Files:**
- Modify: `docs/runbooks/operations-drills.md`
- Modify: `docs/runbooks/real-hub-validation.md`

**Step 1: Clarify the history trail**

Document that:
- review events now appear in member follow-up history
- they are evidence of operator inspection
- they do not close the wipe boundary by themselves

### Task 5: Verify

**Files:**
- Modify as needed based on earlier tasks

**Step 1: Run focused tests**

Run:
- `pytest tests/test_server.py tests/test_cli.py -q`

**Step 2: Run lightweight static checks**

Run:
- `ruff check src/osk/server.py src/osk/cli.py tests/test_server.py tests/test_cli.py`
- `node --check src/osk/static/dashboard.js`

**Step 3: Run full suite**

Run:
- `pytest`

### Done When

- historical review events appear in `follow_up_history` and member detail history
- dashboard history labels no longer describe a mixed trail as verification-only
- CLI help for `--wipe-follow-up-only` matches actual audit filtering
- docs explain review history without overstating closure semantics
- full test suite stays green
