# Plan 9: Operator Closure Hardening

> **For agentic workers:** Start from `AGENTS.md` and `docs/WORKFLOW.md`. Keep scope narrow, preserve truthful wipe and validation claims, and prefer strengthening existing operator/runtime surfaces over adding new product surface area.

**Goal:** Close the current validation loop by making operator-side wipe follow-up closure easier to capture, easier to interpret, and less vulnerable to stale lab residue.

**Architecture:** Reuse the existing local admin/dashboard boundary, wipe-readiness summary model, audit trail, and real-hub validation runner. Add better closure artifacts and better follow-up classification before considering any destructive cleanup automation.

**Current state:** The repo already has explicit wipe-readiness summaries, dashboard follow-up verification controls, reopen audit events, member-scoped follow-up detail views, and a real-device validation runner that can capture top-level wipe-readiness and audit slices when local operator credentials are available. The remaining gap is not baseline runtime behavior; it is operator-side closure automation and cleanup discipline for older unresolved follow-up members that still pollute the current boundary.

**Planning note:** This phase is intentionally non-destructive. The first slice should improve truthfulness and observability around closure, not automatically clear, delete, or silently resolve wipe follow-up items based on age or heuristics.

**Tech Stack:** Python, existing Osk CLI/runtime, FastAPI dashboard/admin APIs, repo-owned validation scripts, existing dashboard JS/CSS

**Spec:** `docs/specs/2026-03-21-osk-design.md` — "Emergency Wipe", "Authentication Protocol", and "Member Mobile UI"
**Depends on:** Plan 6 (operations tooling), Plan 8 (real-hub validation)

---

## Understanding Summary

- Osk already has real wipe-readiness and follow-up surfaces; the problem is closing the loop cleanly after validation or live cleanup work.
- The repo has a real-device validation path that proves join, member session, reconnect, and restart/resume on hardware.
- That validation path still treats operator closure capture as partial or unavailable when credentials are missing.
- Older unresolved wipe follow-up members can remain visible long after the original boundary, which makes readiness noisier than it should be.
- The next phase should improve closure evidence and follow-up interpretation before introducing any cleanup mutation.
- The same truth should be visible in the validation runner, the dashboard, the shell/read-only drills, and the runbooks.
- Automatic resolution of wipe follow-up based only on age is out of scope for this phase.

## Assumptions

- The existing local admin credential paths in the real-hub validation runner remain the correct trust boundary for operator-only capture.
- Operators need to distinguish current wipe risk from historical lab drift without digging through raw audit rows.
- A follow-up item can be "historical drift" without being safe to silently close.
- The current dashboard and drill surfaces are the right places to expose closure status rather than introducing a separate new top-level workflow.
- Validation artifact quality is more valuable right now than new coordinator or member UI surface area.

## Decision Log

| Decision | Choice | Why |
|---|---|---|
| Phase priority | Operator closure hardening before broader device expansion | It closes the main documented gap after Plan 8 |
| Cleanup posture | Non-destructive classification first | Avoids overstating wipe guarantees or silently mutating safety-relevant state |
| Surface strategy | Extend existing runner, dashboard, and drill flows | Keeps operator truth in one owned workflow instead of splitting it across new commands |
| Follow-up model | Distinguish active risk from historical drift | Reduces operational noise without pretending old entries are resolved |
| Acceptance signal | Better closure artifacts and consistent summaries | More useful than cosmetic dashboard changes alone |

## Non-Goals

- Claiming fully automated live wipe confirmation on the remote member device
- Adding new mobile UX or broader coordinator dashboard feature surface
- Auto-resolving or deleting follow-up items solely because they are old
- Redesigning the existing auth/session model
- Replacing the current audit trail or wipe-readiness model with a new subsystem

---

## File Map

| File | Responsibility |
|---|---|
| Modify: `scripts/real_hub_validation.py` | Capture a stronger operator-closure artifact bundle and classify closure outcome |
| Modify: `tests/test_real_hub_validation_contract.py` | Cover closure artifact shape and partial/open-clear result states |
| Modify: `src/osk/wipe_readiness.py` | Add follow-up classification for unresolved vs verified vs historical drift |
| Modify: `src/osk/server.py` | Surface classification and closure summary through existing dashboard/admin APIs |
| Modify: `tests/test_wipe_readiness.py` | Unit tests for follow-up classification rules |
| Modify: `tests/test_server.py` | API and dashboard-state tests for closure summary and classified follow-up output |
| Modify later: `src/osk/hub.py` and/or `src/osk/drills.py` | Expose the same summary in read-only shell/drill output if needed |
| Modify: `src/osk/static/dashboard.js` | Render any new closure-summary or follow-up classification fields without changing auth posture |
| Modify: `docs/runbooks/real-hub-validation.md` | Document the new closure artifact bundle and the meaning of open vs clear closure states |
| Modify: `docs/runbooks/operations-drills.md` | Document how operators should interpret historical drift and when manual cleanup is still required |

---

### Task 1: Define the Closure Artifact Contract

**Files:**
- Modify: `scripts/real_hub_validation.py`
- Modify: `tests/test_real_hub_validation_contract.py`

- [ ] **Step 1: Write failing tests for closure artifact output**

Cover:
- `closure-summary.json` shape
- explicit closure states such as `captured_clear`, `captured_open_follow_up`, and `unavailable`
- per-member follow-up detail capture when unresolved items exist
- truthful partial behavior when credentials are missing or API capture fails

- [ ] **Step 2: Implement stronger closure capture in the runner**

The runner should:
- continue capturing top-level `wipe-readiness.json` and `audit-slice.json`
- fetch member-scoped follow-up detail for unresolved items
- write a compact closure summary that answers whether the current cleanup boundary is still open
- distinguish "credentials unavailable" from "credentials available but unresolved follow-up remains"

- [ ] **Step 3: Keep the result summary truthful**

Do not treat "closure captured" as equivalent to "cleanup boundary cleared" unless unresolved follow-up is actually zero.

---

### Task 2: Classify Follow-Up Items for Operator Use

**Files:**
- Modify: `src/osk/wipe_readiness.py`
- Modify: `tests/test_wipe_readiness.py`

- [ ] **Step 1: Define a small classification model**

At minimum, classify follow-up items into:
- active unresolved risk
- verified current boundary
- historical drift / stale residue

- [ ] **Step 2: Add deterministic rules**

Use existing member state, audit markers, and timestamps to classify items without introducing hidden heuristics.

- [ ] **Step 3: Preserve current safety posture**

Historical drift should reduce noise and improve operator interpretation, but it must not silently convert into a resolved or safe state by itself.

---

### Task 3: Surface Closure Summary Through Existing APIs

**Files:**
- Modify: `src/osk/server.py`
- Modify: `tests/test_server.py`
- Modify: `src/osk/static/dashboard.js`

- [ ] **Step 1: Add closure summary fields to dashboard/admin payloads**

Expose:
- current closure state
- classified follow-up counts
- a short operator-facing summary string

- [ ] **Step 2: Keep member-scoped drill-down useful**

When an item is historical-only, the detail surface should still explain why it is being shown and what the operator can or cannot conclude from it.

- [ ] **Step 3: Update dashboard rendering narrowly**

Prefer small UI changes that make the current boundary easier to read. Avoid broad layout or style rewrites in this phase.

---

### Task 4: Extend Read-Only Operational Guidance

**Files:**
- Modify: `src/osk/hub.py` and/or `src/osk/drills.py`
- Modify: `docs/runbooks/operations-drills.md`
- Modify: `docs/runbooks/real-hub-validation.md`

- [ ] **Step 1: Mirror the same closure story in shell/drill output**

Read-only operational surfaces should reflect:
- whether follow-up remains open
- whether noise is primarily active risk or historical drift
- what manual action is still required

- [ ] **Step 2: Document the safe cleanup interpretation**

The runbooks should explain:
- what historical drift means
- what it does not mean
- when a manual browser check or rejoin is still required

- [ ] **Step 3: Keep claims scoped**

Do not update docs to imply that live wipe confirmation or disconnected-member cleanup is fully automated unless that code actually lands in a later phase.

---

### Task 5: Verification

**Files:**
- Modify as needed based on earlier tasks

- [ ] **Step 1: Run the relevant unit tests**

Expected outcome:
- `tests/test_real_hub_validation_contract.py` passes
- `tests/test_wipe_readiness.py` passes
- relevant `tests/test_server.py` coverage passes

- [ ] **Step 2: Run a local real-hub validation dry run or captured run**

Expected outcome:
- the artifact set includes closure summary output
- the result distinguishes open follow-up from a clear boundary

- [ ] **Step 3: Review docs and claims for truthfulness**

Confirm:
- no new cleanup guarantee is implied
- operator closure capture remains accurately described as credential-dependent
- historical drift is framed as interpretation aid, not automatic resolution

---

## Done When

- [ ] The real-hub validation runner emits a stronger operator-closure artifact bundle
- [ ] Closure outcome is explicitly distinguished from mere capture success
- [ ] Wipe-follow-up output distinguishes active unresolved risk from historical drift
- [ ] Dashboard/admin/read-only drill surfaces tell the same closure story
- [ ] Runbooks explain the new closure states without overstating wipe guarantees
- [ ] No code silently resolves wipe follow-up items based only on age
