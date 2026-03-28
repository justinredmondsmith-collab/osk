# Plan 8: Release 1.0 Readiness

> **For agentic workers:** Start from `AGENTS.md` and `docs/WORKFLOW.md`. Treat this plan as a release-gating document, not a license to grow scope. Prefer validation, hardening, and truthful claims over net-new surface area.

**Goal:** Get Osk from a real-but-alpha implementation state to a truthful, supportable `1.0.0` release by closing the trust gap: validated behavior, release-grade operations, bounded product scope, and explicit go/no-go gates.

**Architecture:** This is a cross-cutting release plan spanning the existing vertical slices already present in the repo: hub/runtime, intelligence pipeline, coordinator dashboard, member PWA, and operations tooling. The work here is mostly integration quality, validation coverage, security/privacy review, operator ergonomics, and release engineering rather than foundational architecture.

**Current state:** The repo already has real implementation slices across Plans 1 through 7, including the hub/runtime path, member shell, offline/outbox behavior, evidence handling, live intelligence flow, dashboard shell, and real browser/device validation helpers. The current gap is not “is there a product at all?” but “can the project truthfully claim 1.0 reliability, safety, and operator readiness?” The repo still marks itself as alpha, explicitly says it is not yet production-ready or fully validated, and calls out remaining gaps in synthesis quality, mobile/dashboard completeness, media/session robustness, broader field validation, and evidence/export operations.

**Planning note:** This plan intentionally freezes major scope expansion. The path to `1.0.0` should optimize for release confidence, not feature count. If a task does not materially improve trust, validation coverage, operator usability, or release packaging, it is probably not on the critical path.

**Tech Stack:** Python, shell, GitHub Actions, real-device/browser validation, operational runbooks, release documentation

**Spec:** `docs/specs/2026-03-21-osk-design.md`
**Depends on:** Plans 1 through 7

---

## Understanding Summary

- Osk is already beyond prototype stage and has real end-to-end slices.
- The main blocker to `1.0.0` is release confidence, not architecture invention.
- The repo’s own docs still draw a hard line between shipped slices and validated guarantees.
- A `1.0.0` release needs explicit scope boundaries so the team stops treating every missing idea as a release blocker.
- The release should be gated by truthfulness, field validation, security/privacy review, operator runbooks, and packaging/upgrade discipline.

## Release Principles

| Principle | Meaning |
|---|---|
| Truth over ambition | Do not claim behavior that has not been exercised and documented |
| Scope freeze over drift | Prefer finishing and hardening the existing product shape |
| Validation over intuition | Real-device, real-browser, and real-operator coverage beats theoretical confidence |
| Operator-first release quality | A coordinator must be able to install, run, recover, export, and wipe with confidence |
| Release gates, not vibes | `1.0.0` should require explicit pass/fail evidence |

## Non-Goals

- Adding major new product surfaces that are not required for the first trustworthy release
- Replacing the existing architecture with a cleaner greenfield design
- Expanding hardware assumptions beyond the currently supported coordinator and member workflows
- Treating aspirational design goals as `1.0.0` requirements if they are not already near the shipped path

---

## Release Gates

### Gate 1: Scope and Claim Lock

**Intent:** Define exactly what Osk `1.0.0` is, and what it is not.

**Artifacts:**
- `docs/release/1.0.0-definition.md`
- `docs/release/1.0.0-blockers.md`

- [x] **Step 1: Write a `1.0.0` release definition**

Capture:
- supported coordinator environment
- supported member-device/browser matrix for launch
- supported operational workflows
- explicit non-goals and deferred post-1.0 work

- [x] **Step 2: Align top-level docs with that definition**

Update release-facing docs so README, SAFETY, runbooks, and contributor guidance all describe the same bounded release target.

- [x] **Step 3: Create a release blocker list**

Maintain one canonical checklist of blockers that must be closed before version bump and release tag.

**Exit criteria:** There is no ambiguity about the `1.0.0` product boundary or launch claims.

---

### Gate 2: Security, Privacy, and Wipe Confidence

**Intent:** Convert the current “not yet guaranteed” posture into a documented and tested launch posture.

- [x] **Step 1: Complete a focused threat/privacy review of the shipped architecture**

Cover:
- coordinator trust boundaries
- member session and join flow
- evidence handling and export
- wipe semantics for connected and disconnected clients
- operator secrets and environment assumptions

- [x] **Step 2: Harden or narrow risky flows**

Fix or explicitly de-scope any behavior that cannot be defended for a `1.0.0` release.

- [ ] **Step 3: Validate wipe and evidence guarantees**

Produce repeatable tests and operator evidence for:
- live wipe behavior on connected browsers
- expected residual risk on disconnected browsers
- preserved-evidence behavior
- operator-visible readiness reporting before wipe

- [x] **Step 4: Rewrite safety claims to match validated truth**

The `1.0.0` release should make precise guarantees and explicitly name remaining limits.

**Exit criteria:** Security/privacy posture and wipe semantics are reviewed, tested, documented, and truthful enough to ship.

---

### Gate 3: Field Validation Matrix

**Intent:** Replace narrow smoke confidence with launch-grade validation coverage.

- [x] **Step 1: Define the minimum supported matrix**

At minimum:
- coordinator host baseline
- member browser set
- member device classes
- online, reconnect, and offline/outbox flows
- operator install/start/stop/export/wipe flows

- [x] **Step 2: Add stable validation commands and artifact capture for each critical path**

Every required scenario should have a repeatable command, expected result, and artifact location.

- [ ] **Step 3: Run the matrix and record failures centrally**

Track:
- pass/fail
- environment used
- artifacts
- follow-up issue or plan link

Current evidence:
- Initial coordinator-host run recorded in
  `docs/release/2026-03-25-release-validation-host-run.md`
- That run proved coordinator preflight/startup/dashboard-session behavior on a
  Linux host, but it also exposed inherited disconnected-member wipe follow-up
  on a resumed operation and did not validate the live Chromium member path or
  evidence export/verify on a preserved bundle
- Clean Chromium run recorded in
  `docs/release/2026-03-25-release-validation-clean-run.md`
- That run proved join, online report, offline queueing, reconnect drain,
  reload resume, and browser-side live wipe on a supported Chromium path, but
  it also exposed stale active-operation cleanup before a fresh start and a
  non-zero wipe shutdown path that left stale host state until a second stop
  cleanup

- [ ] **Step 4: Close all launch-blocking validation gaps**

Do not carry “known flaky but probably okay” paths into `1.0.0`.

**Exit criteria:** The launch matrix is defined, exercised, and green on the minimum supported environments.

---

### Gate 4: Product Completeness and UX Hardening

**Intent:** Bring the existing shipped surfaces up to a release-quality baseline without reopening the design space.

- [ ] **Step 1: Finalize synthesis quality for the `1.0.0` bar**

Decide whether the current heuristic path is sufficient with documented limits or whether a targeted improvement is required for launch.

- [ ] **Step 2: Finish coordinator-dashboard operator essentials**

Ensure the dashboard covers the workflows the release claims to support:
- runtime status
- member visibility
- wipe readiness
- evidence/export handoff
- validation/alert visibility

- [ ] **Step 3: Finish member PWA operator-critical UX**

Focus on:
- reconnect behavior
- offline note/media flow
- session continuity
- wipe aftermath clarity
- user-visible failure states

- [ ] **Step 4: Tighten media/session robustness**

Harden the launch-supported path for resend/session semantics and any media handling the release keeps in scope.

**Exit criteria:** The product surfaces required for `1.0.0` feel complete and legible for their supported workflows.

---

### Gate 5: Operations and Release Engineering

**Intent:** Make Osk shippable, installable, supportable, and releasable as a versioned product.

- [ ] **Step 1: Finalize operator runbooks**

Ship runbooks for:
- install
- preflight
- start/stop
- validation
- evidence export
- wipe
- failure recovery

- [ ] **Step 2: Build the release checklist and sign-off flow**

Include:
- validation matrix completion
- security/privacy review sign-off
- docs truthfulness review
- version bump
- changelog/release notes

- [ ] **Step 3: Add release-oriented CI/workflow support**

At minimum:
- one command or workflow to run required release checks
- one workflow or documented process to cut a tagged release
- artifact packaging expectations

- [ ] **Step 4: Define support and upgrade posture**

Document:
- how a user installs `1.0.0`
- how future upgrades will be handled
- what environments are explicitly unsupported

**Exit criteria:** Releasing `1.0.0` is an explicit documented process, not an informal branch state.

---

### Gate 6: Release Candidate and Version Bump

**Intent:** Prove the release end to end before calling it `1.0.0`.

- [ ] **Step 1: Cut a `1.0.0-rc1` candidate**

Freeze scope except for release blockers.

- [ ] **Step 2: Run the full release checklist against the candidate**

Collect final evidence for:
- validation matrix
- security/privacy sign-off
- runbook accuracy
- packaging/install flow

- [ ] **Step 3: Fix only release blockers**

No opportunistic feature work during RC.

- [ ] **Step 4: Bump to `1.0.0` and publish release notes**

Explain:
- what is supported
- what was validated
- what remains intentionally out of scope

**Exit criteria:** The project can point to a release candidate cycle with evidence, not just confidence.

---

## Suggested Sequencing

1. Lock scope and launch claims first.
2. Run the security/privacy/wipe review in parallel with validation-matrix definition.
3. Use the matrix and review output to drive only the hardening work required for product completeness.
4. Add release engineering only after the launch boundary is stable.
5. Cut an RC before the final version bump.

## Done When

- [ ] Osk has a written `1.0.0` release definition and blocker list
- [ ] Top-level docs describe a bounded, truthful launch target
- [ ] Security/privacy and wipe semantics are reviewed, tested, and documented
- [ ] The minimum supported field-validation matrix is green
- [ ] Dashboard, member PWA, and core synthesis behavior meet the release bar for supported workflows
- [ ] Operator runbooks cover install, run, export, wipe, and recovery
- [ ] Release engineering exists for a repeatable tagged release process
- [ ] A release candidate has been exercised before the final `1.0.0` bump



> Roadmap note: This file is a scoped implementation or historical planning document. Read it through [`2026-03-28-end-state-product-roadmap.md`](./2026-03-28-end-state-product-roadmap.md). If sequencing, priority, or scope conflict with the roadmap, follow the roadmap.
