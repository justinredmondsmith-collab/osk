# Plan 8: Real-Hub Validation

> **For agentic workers:** Start from `AGENTS.md` and `docs/WORKFLOW.md`. Keep scope narrow, preserve truthful validation claims, and treat this phase as validation-first rather than feature-first.

**Goal:** Add a repo-owned validation workflow that exercises the real Osk hub path on real devices, captures artifacts, and turns runtime truth into a concrete hardening backlog.

**Architecture:** The host owns orchestration, artifact capture, and result contracts. Validation targets a real running Osk hub with its actual `/join` and `/member` path, current cookie/session exchange, and current operator-side wipe/readiness surfaces. Device-driving can reuse the Chromebook lab path where useful, but mocked member-shell smoke and real-hub validation remain separate workflows.

**Current state:** The repo already has meaningful runtime slices across Phases 1 through 6, a real member shell, explicit wipe-readiness surfaces, install/wipe drills, and a dedicated Chromebook smoke path for the mocked member shell. The current gap is that the repo does not yet own a repeatable validation loop for the real hub/runtime flow. The most important next step is to prove the existing runtime path on real hardware and record enough evidence to drive hardening work without overstating readiness.

**Planning note:** This plan is intentionally validation-first. The first task defines the host-side contract and artifacts for real-hub validation before browser-driving or restart scenarios are added. The point of v1 is trustworthy run structure, not broad automation claims.

**Tech Stack:** Python, shell, existing Osk CLI/runtime, repo-owned artifact contracts

**Spec:** `docs/specs/2026-03-21-osk-design.md` — "Authentication Protocol", "Member Mobile UI", and "Emergency Wipe" sections
**Depends on:** Plan 5 (member shell + PWA), Plan 6 (operations tooling), Plan 7 (Chromebook lab smoke)

---

## Understanding Summary

- Osk is already in a field-validation and operational-hardening stage rather than a first-pass build stage.
- The repo has a real member shell and real operator/runtime tooling, but the strongest existing real-device loop still centers on a mocked member-shell path.
- The next phase should validate the actual hub path, not only the mocked helper path.
- The first phase output should be a trustworthy validation contract with stable artifacts and explicit result fields.
- Real-hub validation should stay separate from mocked smoke so repo claims remain precise.
- Restart/disconnect hardening should follow baseline real-hub validation, not be mixed into the first slice.

## Assumptions

- A real running Osk hub can be started and observed from the coordinator host during validation.
- The first real-hub target path is one narrow scenario rather than a broad matrix.
- Device-driving may reuse the existing Chromebook lab path later, but the contract should not hard-code that as the only future device.
- Artifact directories should live under a stable repo-local output root.
- Validation artifacts should be useful even when a run is only a dry run or preflight failure.

## Decision Log

| Decision | Choice | Why |
|---|---|---|
| Phase priority | Real-hub validation before new features | Matches the repo workflow and exposes the real next defects |
| First task shape | Contract-first dry-run runner | Keeps scope narrow and reviewable while defining the artifact model |
| Device model | Device-neutral contract, Chromebook-friendly later | Avoids baking the phase into one lab path too early |
| Workflow separation | Keep mocked smoke and real-hub validation distinct | Prevents inflated readiness claims |
| First scenario | Baseline join -> member -> reconnect -> wipe | Highest-value runtime path for current hardening |

## Non-Goals

- Replacing the existing mocked Chromebook smoke workflow
- Redesigning auth/session behavior in the first slice
- Claiming disconnected-member wipe is solved
- Adding richer synthesis, map UX, or coordinator feature surface
- Building a full unattended multi-device lab matrix in v1

---

## File Map

| File | Responsibility |
|---|---|
| Create: `scripts/real_hub_validation.py` | Host-side real-hub validation contract and dry-run entrypoint |
| Create: `tests/test_real_hub_validation_contract.py` | Unit tests for required inputs, artifact paths, and result shape |
| Modify later: `scripts/chromebook_real_hub_validation.sh` | Optional real-device wrapper once the contract exists |
| Modify later: `docs/runbooks/real-hub-validation.md` | Operator runbook for the real-hub validation flow |

---

### Task 1: Define the Real-Hub Validation Contract

**Files:**
- Create: `scripts/real_hub_validation.py`
- Create: `tests/test_real_hub_validation_contract.py`

- [x] **Step 1: Write failing contract tests**

Cover:
- required host-side inputs (`hub_url`, `join_url`, `device_id`, `artifact_root`)
- timestamped artifact directory naming
- structured `result.json` shape for dry runs
- dry-run failure behavior for missing or invalid config

- [x] **Step 2: Implement a dry-run runner**

The first version should:
- parse and validate the required inputs
- create a timestamped artifact directory
- write a stable `result.json`
- include provenance metadata
- clearly report that runtime browser-driving is not implemented yet

- [x] **Step 3: Run the new contract tests**

Expected outcome:
- the new contract tests pass locally
- no runtime behavior is claimed beyond dry-run contract generation

---

### Task 2: Add a Baseline Real-Hub Host Runner

**Files:**
- Modify: `scripts/real_hub_validation.py`

- [x] **Step 1: Add hub preflight capture**

The runner should collect:
- target hub URL
- join URL
- optional local status/doctor snapshots when available
- a preflight record in the artifact directory

- [x] **Step 2: Add the baseline scenario contract**

Represent the intended scenario steps explicitly:
- hub reachable
- join loads
- member session establishes
- disconnect/reconnect behavior observed
- wipe observed
- operator-side readiness/audit slices captured

- [x] **Step 3: Stop at contract/reporting only until browser-driving exists**

Do not claim the scenario is automated yet.

---

### Task 3: Add Real-Device Execution Path

**Files:**
- Create: `scripts/chromebook_real_hub_validation.sh`
- Modify: `scripts/real_hub_validation.py`

- [x] **Step 1: Reuse the lab device path where useful**
- [x] **Step 2: Drive the actual hub join/runtime path**
- [x] **Step 3: Capture screenshots, console logs, and step results**

Current Task 3 scope is intentionally narrow: it automates the real
`/join -> /member` path plus offline queue/reconnect evidence on the real hub
runtime, while leaving live wipe and operator-side closure as explicit manual
follow-up until those surfaces are captured truthfully.

---

### Task 4: Add Operator-Side Closure Capture

**Files:**
- Modify: `scripts/real_hub_validation.py`

- [x] **Step 1: Record wipe-readiness context**
- [x] **Step 2: Record relevant audit follow-up slice**
- [x] **Step 3: Preserve truthful evidence when wipe coverage is partial**

Task 4 now captures the same protected coordinator surfaces the dashboard uses:
`/api/coordinator/dashboard-state` for `wipe_readiness` and
`/api/audit?wipe_follow_up_only=true` for the relevant follow-up trail. The
runner stores those artifacts when local operator credentials are available,
and records explicit partial-evidence status instead of failing the whole run
or pretending coverage exists when credentials are missing.

---

### Task 5: Add Restart/Disconnect Scenarios

**Files:**
- Modify as needed

- [x] **Step 1: Add a restart-focused scenario**
- [x] **Step 2: Verify outbox/session expectations across hub restarts**
- [x] **Step 3: Record failures as hardening tasks, not implied guarantees**

Task 5 now has a scenario-aware restart contract plus a real host-side probe:
the runner adds an explicit `hub_restart_resume_observed` step for
`--scenario restart`, uses `osk stop --restart` / `osk start <operation>` by
default to preserve the active operation across a real coordinator restart, and
reconnects to the existing member browser over CDP to verify whether the
runtime session and queued replay survive. The code path now distinguishes
temporary coordinator restarts from true operation shutdowns, but the repo
still treats restart survivability as validation work rather than a blanket
readiness claim until the live lab path is exercised and the remaining failure
modes are measured.

---

## Done When

- [ ] The repo has a Plan 8 document that scopes real-hub validation truthfully
- [ ] The repo has a dry-run real-hub validation contract entrypoint
- [ ] The contract produces structured artifacts under a stable output root
- [ ] Mocked smoke and real-hub validation are documented as distinct paths
- [ ] No docs claim automated real-hub validation beyond what the repo actually implements
