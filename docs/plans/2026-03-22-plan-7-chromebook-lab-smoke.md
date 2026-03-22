# Plan 7: Chromebook Lab Smoke Automation

> **For agentic workers:** Start from `AGENTS.md` and `docs/WORKFLOW.md`. Keep scope narrow, preserve truthful validation claims, and treat the dedicated Chromebook as a lab-only device rather than a normal member device.

**Goal:** Add a repo-owned host-to-Chromebook smoke workflow that drives the existing mocked `/join` -> `/member` member-shell path on a real external Chromebook, returns clear pass/fail, and saves artifacts for debugging.

**Architecture:** The host owns orchestration, assertions, and artifact packaging. The Chromebook is a dedicated lab device that the host reaches over a reachable SSH control endpoint, resets into a disposable Chrome lab profile, launches in automation mode, and drives remotely for one interactive smoke run at a time.

**Current state:** The repo already has `scripts/member_shell_smoke.py` for real-browser manual smoke testing against a mocked Osk member shell, plus `scripts/member_shell_playwright_smoke.sh` for a localhost-capable automated smoke path. Those tools are useful but stop short of a repo-owned real-device loop. The current gap is a single-command path that prepares the dedicated Chromebook, drives the browser remotely, captures artifacts, and resets cleanly for the next run.

**Planning note:** This plan is intentionally narrow. It targets the mocked member-shell smoke helper first, not the real hub runtime, hotspot orchestration, or unattended schedules. The value of v1 is determinism and observability on one real device, not broad field realism.

**Tech Stack:** Shell, Python, SSH, Chrome remote automation on a disposable lab profile

**Spec:** `docs/specs/2026-03-21-osk-design.md` — "Mobile client", "Authentication Protocol", and "Emergency Wipe" sections
**Depends on:** Plan 5 (member shell + PWA), Plan 6 (field validation and hardening)

---

## Understanding Summary

- Osk needs faster, more repeatable real-device validation for the member PWA.
- The user has a dedicated Chromebook with full administrative control and is willing to keep it in permanent lab mode.
- The first target is the existing mocked member-shell smoke path, not the real hub runtime.
- The preferred workflow is one interactive host-side command during active development.
- The Chromebook test path should optimize for clear pass/fail plus artifact capture, not for nightly scheduling yet.
- The host should control both browser driving and device reset/prep, rather than relying on browser automation alone.
- The repo should own this workflow directly instead of depending on an external Codex-only wrapper.

## Assumptions

- The Chromebook can be reached reliably from the host over a direct or reverse-tunnel SSH endpoint.
- The Chromebook can launch Chrome in a dedicated disposable lab profile for automation.
- Newer Chrome remote-debugging flows may require a non-default `user-data-dir`, so the lab browser launch should always use an explicit disposable profile.
- Lab-only settings on the Chromebook are acceptable if they improve determinism and reset speed.
- Artifacts should be saved on the host under a stable repo-local output directory.

## Decision Log

| Decision | Choice | Why |
|---|---|---|
| Primary target | Mocked member-shell smoke helper | Fastest way to validate the real device without entangling the full hub runtime |
| Device role | Dedicated lab Chromebook | Allows persistent test-only settings and aggressive cleanup without pretending this mirrors a normal member device |
| Control model | Host orchestration plus Chromebook prep/reset | Better repeatability than browser driving alone |
| SSH transport | Direct or reverse-tunnel endpoint | Crostini container IPs are not always directly reachable from the host |
| Run mode | Single-command interactive run | Best fit for active development loops |
| v1 success criteria | Clear pass/fail plus artifacts | Most leverage for debugging and trustworthiness |
| Browser state | Disposable lab profile per run | Minimizes flake from stale state and supports repeatable reset |

## Non-Goals

- Real-hub end-to-end validation in v1
- Hotspot or join-host orchestration in v1
- Scheduled or unattended runs in v1
- Multi-device or multi-browser matrix testing in v1
- Any production-member auth or privacy posture change for the normal browser flow

---

## File Map

| File | Responsibility |
|---|---|
| Create: `scripts/chromebook_member_shell_smoke.sh` | One-command host entrypoint for the real Chromebook smoke run |
| Create: `scripts/chromebook_lab_control.sh` | SSH-based Chromebook prep/reset/launch helper |
| Create: `scripts/chromebook_member_shell_smoke.py` | Repo-owned remote-browser smoke runner with assertions and artifact capture |
| Modify: `pyproject.toml` | Add any repo-owned dev dependency needed for browser automation |
| Create: `docs/runbooks/chromebook-lab-smoke.md` | Lab setup and operator runbook for the dedicated Chromebook |
| Create: `tests/test_chromebook_lab_contract.py` | Unit tests for config parsing, metadata/result contracts, and orchestration edge cases |

---

### Task 1: Define the Chromebook Lab Contract

**Files:**
- Create: `tests/test_chromebook_lab_contract.py`
- Modify: `pyproject.toml`

- [x] **Step 1: Write tests for the orchestration contract**

Cover:
- required host-side inputs (`chromebook_host`, SSH target, debug port, artifact root)
- smoke-helper metadata consumption
- structured result shape (`result.json`)
- artifact directory naming and required files
- dry-run / missing-config failure behavior

- [x] **Step 2: Decide and declare the repo-owned browser automation dependency**

Prefer a repo-owned automation path that can connect to a remote Chrome session from the host and does not depend on Codex skill wrappers.

- [x] **Step 3: Run the new contract tests**

Verify they fail before implementation and document any missing dependency decision in the plan/PR description.

---

### Task 2: Add Chromebook Prep and Reset Helper

**Files:**
- Create: `scripts/chromebook_lab_control.sh`

- [x] **Step 1: Implement SSH-based device checks**

The helper should:
- verify the Chromebook is reachable
- verify the required Chrome binary path and automation prerequisites are present
- fail clearly if the device is not in the expected lab shape

- [x] **Step 2: Implement disposable-browser reset**

The helper should:
- kill the prior lab Chrome process if present
- remove or recreate the disposable lab profile directory
- avoid touching any non-lab browser profile

- [x] **Step 3: Implement lab-browser launch**

The helper should:
- launch Chrome with an explicit disposable `user-data-dir`
- expose the remote-control endpoint needed by the host runner
- print or write connection details in a machine-readable form

- [x] **Step 4: Add a cleanup path**

The helper should stop the lab browser cleanly after the run unless a keep-open debug mode is explicitly requested.

---

### Task 3: Add the Host Smoke Orchestrator

**Files:**
- Create: `scripts/chromebook_member_shell_smoke.sh`

- [x] **Step 1: Wrap the existing mocked smoke helper**

The host entrypoint should:
- start `scripts/member_shell_smoke.py`
- wait for metadata/control URLs
- fail fast if the helper never becomes reachable

- [x] **Step 2: Call the Chromebook lab helper**

The host entrypoint should:
- prepare the Chromebook
- launch the lab browser
- hand connection details to the remote-browser smoke runner

- [x] **Step 3: Create a stable output directory**

Save all run artifacts under a timestamped directory like:
`output/chromebook/member-shell-smoke/<timestamp>/`

- [x] **Step 4: Ensure cleanup happens on failure**

If any step fails, the script should still try to stop the smoke helper and clean up the Chromebook lab session unless debug flags say otherwise.

---

### Task 4: Add the Repo-Owned Remote-Browser Smoke Runner

**Files:**
- Create: `scripts/chromebook_member_shell_smoke.py`

- [x] **Step 1: Connect to the remote Chromebook browser**

Use the repo-owned automation client to connect from the host to the Chromebook lab browser session.

- [x] **Step 2: Implement the v1 smoke checkpoints**

Assert, in order:
- `/join` loads
- join submits and reaches `/member`
- offline field note enters the outbox
- reconnect drains the outbox
- reload resumes the member session
- live wipe transitions to the cleared state

- [x] **Step 3: Capture artifacts at each checkpoint**

Save:
- checkpoint screenshots
- browser console logs
- a network/error summary
- final structured result JSON with the first failed step, if any

- [x] **Step 4: Stop on the first real failure**

Do not keep marching after a failed assertion. Record the failed step and preserve artifacts.

---

### Task 5: Add the Chromebook Lab Runbook

**Files:**
- Create: `docs/runbooks/chromebook-lab-smoke.md`

- [x] **Step 1: Document one-time Chromebook setup**

Include:
- how the Chromebook is expected to be reached from the host
- where the disposable lab profile lives
- how the lab browser is launched
- which settings are lab-only and should not be confused with normal member-device assumptions

- [x] **Step 2: Document normal run and debug flows**

Include:
- one-command normal run
- how to keep the browser open for debugging
- how to inspect artifacts after a failure
- how to re-run after a failed cleanup

---

### Task 6: Verification

**Files:**
- Modify as needed based on earlier tasks

- [x] **Step 1: Run unit tests for the orchestration contract**

Expected outcome:
- config, result-shape, and failure-mode tests pass locally

- [x] **Step 2: Run the existing mocked helper tests**

Expected outcome:
- `tests/test_member_shell_smoke.py` still passes unchanged

- [x] **Step 3: Run one real Chromebook smoke session**

Expected outcome:
- one host command reaches the dedicated Chromebook
- the mocked member-shell flow executes on the real browser
- the run produces pass/fail plus artifacts in the output directory

- [x] **Step 4: Review docs and claims for truthfulness**

Confirm:
- no README or runbook text claims broader field validation than what was actually exercised
- the lab workflow is described as a dedicated test path, not as production member behavior

---

## Done When

- [x] The repo has a one-command Chromebook lab smoke entrypoint
- [x] The repo has a device prep/reset helper for the dedicated Chromebook
- [x] The smoke runner produces structured pass/fail plus artifacts on the host
- [x] The runbook documents setup, run, cleanup, and debug behavior truthfully
- [x] The implementation is still scoped to the mocked member-shell path only
