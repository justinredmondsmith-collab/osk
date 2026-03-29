# Osk End-State Product Roadmap

**Date:** 2026-03-28  
**Status:** Authoritative roadmap for product direction after 1.0.0  
**Audience:** Maintainer, future contributors, AI implementation agents

---

## Purpose

This document is the single planning document for where Osk is going as a
product and how work should be sequenced to get there.

It exists because the current repo has three different truths:

1. the validated `1.0.0` slice that actually ships today
2. the larger design target described in the system spec
3. several tactical plans and validation runbooks that solve only part of the
   path between those two points

This roadmap ties those together so the project can keep shipping toward the
same end-goal instead of drifting into disconnected implementation work.

This document should be read alongside:

- [the current design spec](../specs/2026-03-21-osk-design.md)
- [the tactical post-1.0 roadmap](./2026-03-28-post-1.0.0-roadmap.md)
- [the 1.0.0 definition](../release/1.0.0-definition.md)

When there is tension between those documents:

- the `1.0.0` release docs define what is true now
- the design spec defines intended system behavior
- this roadmap defines what gets built next and in what order

---

## Product Vision

Osk should become a local-first field coordination and situational awareness
system for civilian groups operating in uncertain environments.

The end-state product is not just a browser feed that surfaces alerts. It is a
complete field operations loop:

1. a coordinator can stand up an operation quickly on local hardware
2. members can join with minimal friction from ordinary phones
3. a bounded number of sensors can continuously supply field signal
4. the hub can turn raw signal into actionable, reviewable events
5. the coordinator can assign follow-up tasks and confirm route decisions
6. the group can operate under degraded network conditions without losing the
   core workflow
7. the operation can end with trustworthy evidence handling, explicit cleanup,
   and documented residual risk

The product is successful when it helps a small group move from "everyone knows
only what they personally see" to "the coordinator has a usable operating
picture and can direct the group with confidence."

---

## What Osk Is Not

To hold the project on course, the end-goal also needs explicit boundaries.

Osk is not:

- a cloud intelligence platform
- a consumer social app
- a generic incident command system for every environment
- a surveillance product built around broad retention and centralized identity
- a product that claims anonymity, endpoint integrity, or perfect deletion

The project should keep optimizing for local-first coordination, bounded trust,
truthful claims, and operator control.

---

## Current Baseline

As of `1.0.0`, Osk already has a real and valuable base:

- local hub lifecycle and operator control
- browser join flow and member runtime shell
- manual reporting and early sensor ingest
- heuristic synthesis and bounded review flow
- evidence export and validation artifacts
- live wipe-readiness and related operator surfaces
- the first coordinator-directed route confirmation slice
- real browser and validation tooling

What it does not yet have is the full product shape implied by the design spec.

Major gaps still separate the current release from the real end-goal:

- real-device validation is still incomplete
- synthesis remains bounded and only partially fused
- coordinator tasking is still a narrow scripted slice
- the dashboard is still thinner than the intended command surface
- member UX is still validation-stage rather than field-mature
- offline and degraded-network behavior is only partially complete
- single-hub operational excellence is not yet fully proven, which means
  federation and broader platform expansion would be premature

---

## North-Star Outcomes

Every roadmap phase should move at least one of these outcomes materially
forward.

### 1. Fast Operation Startup

A motivated coordinator can launch a trustworthy local operation with minimal
prep and without needing cloud services.

### 2. Low-Friction Member Participation

Observers and sensors can join, reconnect, and operate from a mobile browser
with minimal operator intervention.

### 3. Actionable Coordinator Picture

The coordinator sees what matters, not just raw logs. The system should support
decision-making about routes, escalation, group movement, and follow-up tasks.

### 4. Trustworthy Field Intelligence

Audio, visual, location, and manual inputs should be fused into events that are
reviewable, attributable, and confidence-bounded.

### 5. Safe Operation Closure

At the end of an operation, the coordinator can see what was preserved, what
was cleared, what still needs follow-up, and what the system cannot guarantee.

---

## Planning Guardrails

These rules are the practical filter for deciding whether proposed work belongs
on the critical path.

### Guardrail 1: Keep Osk Local-First

Do not introduce a required cloud dependency without an explicit design change.
Optional cloud-backed tooling may exist outside the core runtime, but the
primary product must remain usable on local infrastructure.

### Guardrail 2: Truth Before Ambition

Do not claim a behavior is implemented, validated, secure, benchmarked, or
field-ready unless the repo actually proves it.

### Guardrail 3: Finish the Single-Hub Product Before Expanding the Platform

Federation, native apps, external integrations, and cross-operation analytics
are secondary to making the single-hub field workflow excellent.

### Guardrail 4: Prioritize Coordinator Leverage

The product exists to improve group coordination, not just data collection.
Coordinator surfaces, decision support, tasking, route confidence, and cleanup
visibility matter more than cosmetic UI breadth.

### Guardrail 5: Validation Precedes Feature Claims

If a major capability is still synthetic, lab-only, or partially bounded, the
next work should usually be validation or hardening before feature expansion.

### Guardrail 6: Browser-First Until It Becomes a Hard Limit

The browser PWA remains the default member path until real evidence shows that a
native client is required for battery, background execution, media capture, or
reliability.

### Guardrail 7: Privacy Is a Product Requirement

Retention, authentication, evidence handling, wipe semantics, and operator
review workflows are not compliance chores. They are central product behavior.

---

## End-State Capability Model

The end-goal product should eventually provide the following capability pillars.

### Pillar A: Deployment and Operation Lifecycle

Target state:

- installable and repeatable local deployment on supported Linux coordinator
  hardware
- startup flow that validates prerequisites, opens the operation, and gives the
  coordinator a clear readiness signal
- operation-level configuration for alerting, retention, sensor policies, and
  network posture
- shutdown, wipe, export, and post-operation review built into the normal
  lifecycle

### Pillar B: Member Runtime and Field UX

Target state:

- low-friction QR join
- robust reconnect and resume
- bounded offline and degraded-network behavior
- observer and sensor experiences tuned for different roles
- explicit feedback for queueing, battery impact, stream status, and tasking
- browser installability where supported

### Pillar C: Coordinator Command Surface

Target state:

- live member map and health view
- event and timeline review
- task assignment and route confirmation workflow
- visibility into follow-up, unresolved uncertainty, and operational drift
- decision support that helps the coordinator act, not just inspect

### Pillar D: Intelligence and Fusion

Target state:

- stable audio, vision, manual, and location ingest
- confidence-bounded multimodal event generation
- correlation across time, source, and location
- explainable synthesis outputs with source attribution
- configurable categories and thresholds without turning the product into a
  generic unbounded AI sandbox

### Pillar E: Evidence, Audit, and After-Action Review

Target state:

- selective preservation with integrity artifacts
- export paths that are actually useful to an operator
- audit trails that help reconstruct what happened and what decisions were made
- review tools for unresolved follow-up, false positives, and drift
- after-action outputs that support learning without overstating certainty

### Pillar F: Privacy, Security, and Wipe

Target state:

- truthful local transport and authentication model
- explicit trust boundaries and accepted risk
- operator-visible wipe readiness and closure state
- bounded residual data story
- hardening where it materially improves field trust without destroying join
  ergonomics

### Pillar G: Reliability and Performance

Target state:

- sustainable operation under the intended member and sensor load
- known device/browser support matrix
- stability under join churn, reconnects, and long-running sessions
- measurable latency and quality budgets for core intelligence and alert loops

---

## Roadmap Sequence

The phases below are intentionally ordered. That order matters.

Building later phases before earlier ones are credible will create a larger,
noisier, less trustworthy product.

---

## Release-by-Release Execution View

The roadmap phases below are the conceptual plan. This section translates them
into concrete release gates so the maintainer can decide whether the project is
actually ready to move on.

### Release 1.1: Truthful Field Foundation

This release should close the biggest gap between what Osk already claims and
what it has physically proven.

**Primary mission:** validate and harden the current single-hub product.

**Must be true before calling 1.1 done:**

- real-device sensor validation has been run and published
- long-duration runtime behavior is documented with credible stability evidence
- browser automation protects the member runtime against obvious regressions
- evidence retention behavior is explicit and test-covered
- `1.1` documentation can describe supported and unsupported conditions without
  relying on synthetic-only claims

**Should not block 1.1:**

- broad browser expansion
- major dashboard redesign
- advanced multimodal fusion
- federation

### Release 1.2: Coordinator-Directed Operations

This release should make Osk meaningfully better at directing a group, not just
observing one.

**Primary mission:** turn the coordinator shell into an operational command
surface with explicit tasking and route confidence workflows.

**Must be true before calling 1.2 done:**

- coordinator tasks have a clear lifecycle from creation to completion or
  timeout
- member task state survives reconnects and remains legible to the coordinator
- route confirmation is generalized beyond the initial scripted slice
- the dashboard shows open gaps, active tasks, and route confidence clearly
- audit and review artifacts preserve enough context to reconstruct why a task
  or route call happened

**Should not block 1.2:**

- generalized workflow automation
- native client investment
- cross-operation analytics

### Release 1.3: Trustworthy Intelligence Fusion

This release should materially improve signal quality without making the product
opaque or over-claiming AI certainty.

**Primary mission:** produce better, more reviewable events from combined
inputs.

**Must be true before calling 1.3 done:**

- multimodal event correlation exists and is evaluated against the current
  single-source baseline
- coordinator review surfaces can explain why a synthesized event exists
- source attribution and confidence are visible enough to support operator
  trust
- false-positive and duplicate-event behavior improves in documented evaluation
- configuration remains bounded and operationally understandable

**Should not block 1.3:**

- federation
- broad integration surface
- highly customizable AI pipelines

### Release 2.0: Mature Single-Hub Operational System

This is the first release that should plausibly describe Osk as a mature
single-hub field system rather than a validated foundation still climbing toward
its intended shape.

**Primary mission:** make the single-hub system operationally excellent,
supportable, and repeatable.

**Must be true before calling 2.0 done:**

- a supported coordinator can install, launch, run, and close an operation from
  the documented path
- the member runtime feels intentional and reliable on the supported browser and
  hardware matrix
- tasking, route confidence, intelligence review, evidence export, and closure
  form one coherent end-to-end workflow
- security, privacy, retention, and wipe language are truthful and stable
- the project can define supported profiles instead of relying on one-off
  maintainer knowledge

**Should not block 2.0:**

- federation
- native apps
- hub appliance packaging
- large external integration work

### Release 3.x and Beyond: Expansion Only by Explicit Choice

Anything beyond the mature single-hub product is optional expansion, not the
default path.

**Examples:**

- multi-hub federation
- native clients
- cross-operation analytics
- broader communications integrations

**Entry gate:**

- the maintainer explicitly decides the added complexity is worth owning after
  the single-hub product is already excellent

---

## Milestone Checklist

This section is the operational checklist view of the roadmap. It is meant to
help future planning, issue creation, and PR review stay anchored to the same
release gates.

### 1.1 Checklist: Truthful Field Foundation

- [ ] Real-device Chromebook sensor validation completed and published
- [ ] Ollama-backed synthesis evaluated on supported hardware
- [ ] Long-duration stability run published
- [ ] Browser automation regression path running in CI or nightly automation
- [ ] Evidence retention and cleanup behavior documented and tested
- [ ] `1.1` docs updated to reflect supported conditions and known limits

**Evidence expected before release:**

- real-device validation report
- stability report
- CI/browser automation proof
- retention policy documentation

### 1.2 Checklist: Coordinator-Directed Operations

- [ ] General task lifecycle implemented
- [ ] Task assignment and timeout behavior documented
- [ ] Member task UX survives reconnects
- [ ] Route confirmation generalized beyond the scripted slice
- [ ] Dashboard clearly shows tasks, gaps, and route confidence
- [ ] Audit trail captures why task and route decisions occurred

**Evidence expected before release:**

- coordinator task flow demo or validation script
- reconnect/resume verification for task state
- dashboard screenshots or walkthrough
- audit artifact examples

### 1.3 Checklist: Trustworthy Intelligence Fusion

- [ ] Multimodal event correlation implemented
- [ ] Source attribution and confidence surfaced to coordinator review
- [ ] Duplicate-event reduction measured against baseline
- [ ] False-positive behavior evaluated and documented
- [ ] Configurable categories and thresholds remain bounded and understandable

**Evidence expected before release:**

- evaluation report comparing baseline versus fused outputs
- coordinator review screenshots or trace artifacts
- documented confidence model and correction workflow

### 2.0 Checklist: Mature Single-Hub Operational System

**Status:** ✅ COMPLETE as of 2026-03-28

- [x] Supported deployment profile documented → `docs/SUPPORTED_PROFILES.md`
- [x] Install, startup, operation, shutdown, and closure paths validated → `docs/INSTALL_GUIDE.md`, `docs/AAR_GUIDE.md`, 545 tests
- [x] Member runtime support matrix documented → `docs/SUPPORTED_PROFILES.md` browser/hardware matrix
- [x] Tasking, intelligence, evidence, and closure workflow feel coherent → AAR system (`osk aar` commands)
- [x] Security, privacy, retention, and wipe claims reviewed for truthfulness → `docs/SECURITY.md`, 23 security tests
- [x] Operator handoff and after-action artifacts are stable and usable → `ClosureChecklist`, integrity verification

**Evidence delivered:**

| Requirement | Evidence | Status |
|-------------|----------|--------|
| Install-to-operation walkthrough | `docs/INSTALL_GUIDE.md` | ✅ Complete |
| Supported hardware/browser matrix | `docs/SUPPORTED_PROFILES.md` | ✅ Complete |
| End-to-end validation | 545 tests + `docs/release/2.0.0-completion-report.md` | ✅ Complete |
| Doc review confirming truthful claims | All docs reviewed, no false claims | ✅ Complete |
| Security documentation | `docs/SECURITY.md` | ✅ Complete |
| AAR documentation | `docs/AAR_GUIDE.md` | ✅ Complete |

### 3.x Checklist: Optional Platform Expansion

- [ ] Maintainer explicitly chooses expansion over single-hub polishing
- [ ] Single-hub product is already judged excellent and supportable
- [ ] Federation or platform work has a concrete operational use case
- [ ] Complexity and ownership cost are accepted deliberately

**Evidence expected before expansion work:**

- written rationale for why single-hub is no longer the highest-leverage focus
- proposed architecture note for the expansion area

---

## Phase 1: Field Truth and Reliability

**Primary goal:** Make the currently claimed single-hub product truthful under
real operating conditions.

**Why this phase comes first:**

The current product already has meaningful surface area. The highest-value work
is proving, hardening, and instrumenting that surface area before expanding it.

**Target release band:** `1.1.x`

### Outcomes

- real-device confidence for sensor behavior
- stronger stability evidence
- clearer evidence retention behavior
- better automated regression detection

### Workstreams

#### 1. Real-device sensor validation

- run the Chromebook lab plan on real hardware
- measure battery, thermal, reconnect, and media stability behavior
- publish the results as release-grade evidence
- feed findings back into browser support and sensor policy decisions

#### 2. Ollama synthesis validation

- benchmark bounded Ollama-backed synthesis against the current heuristic path
- validate latency, quality, and operational cost on supported hardware
- decide when heuristic remains default and when Ollama becomes the preferred
  path

#### 3. Stability and churn hardening

- run long-duration operations, not just short matrix passes
- measure queue growth, memory drift, and reconnect churn
- verify evidence export and cleanup still behave correctly after prolonged runs

#### 4. Browser automation as regression infrastructure

- complete the browser sensor validation path
- move repeatable regression checks into CI and nightly automation
- use synthetic automation to protect the member runtime while keeping the
  claims clearly separate from real-device validation

#### 5. Evidence retention and rotation

- make retention limits explicit and configurable
- prevent silent evidence sprawl
- provide predictable cleanup and operator-facing documentation

### Exit criteria

- real-device validation report exists and is linked from release docs
- a long-duration operation run is documented and repeatable
- CI catches browser/runtime regressions that matter to the field workflow
- retention behavior is explicit, testable, and documented

### Non-goals

- federation
- native mobile apps
- advanced map polish for its own sake
- major new intelligence categories without validation

---

## Phase 2: Coordinator-Directed Operations

**Primary goal:** Move Osk from passive awareness toward active field
coordination.

**Why this phase matters:**

The product becomes much more valuable when the coordinator can turn uncertainty
into directed follow-up and route decisions rather than merely reading alerts.

**Target release band:** `1.2.x`

### Outcomes

- coordinator can assign and track field confirmation tasks
- route recommendations become a maintained workflow, not a one-off output
- the dashboard becomes a genuine operator surface

### Workstreams

#### 1. Tasking model

- formalize coordinator task types
- define assignment, acknowledgement, timeout, retry, and handoff rules
- support freshness- and capability-aware routing of tasks to members

#### 2. Route and gap lifecycle

- evolve the current route confirmation slice from scripted exits to a general
  workflow
- make open gaps, recommended actions, current confidence, and invalidated
  routes visible in both state and audit

#### 3. Coordinator dashboard maturation

- strengthen member health views
- improve task and event correlation
- add timeline and route context that reduces coordinator cognitive load
- make review and closure actions quicker and more legible

#### 4. Member-side task UX

- show assigned tasks clearly in the member runtime
- support acknowledgement, progress, completion, and inability-to-comply states
- preserve task state across reconnects and partial offline conditions

### Exit criteria

- coordinator can issue and track non-trivial field tasks end to end
- task state survives reconnects and is visible in operator review surfaces
- route calls are backed by an explicit confidence and confirmation workflow
- dashboard use no longer depends on reading low-level audit detail to
  understand current operational state

### Non-goals

- full native mapping stack
- broad workflow customization engine
- speculative automation that hides uncertainty from the coordinator

---

## Phase 3: Trustworthy Multimodal Intelligence

**Primary goal:** Turn the intelligence layer from bounded parallel pipelines
into a more coherent, reviewable operating picture.

**Why this phase comes after coordinator tasking:**

Better fusion is only useful if the operator workflow can consume it. The
coordinator loop should exist before major intelligence sophistication is added.

**Target release band:** `1.3.x`

### Outcomes

- better event quality from combined signals
- stronger attribution and confidence
- lower coordinator review burden for obvious correlated events

### Workstreams

#### 1. Multimodal fusion

- correlate audio, vision, manual reports, and location
- group repeated observations into better event candidates
- avoid double-reporting the same field condition from parallel sources

#### 2. Temporal and spatial reasoning

- detect persistence, escalation, and movement patterns
- distinguish one-off noise from developing situations
- support route relevance and proximity-aware synthesis

#### 3. Confidence and explainability

- attach clearer source and confidence signals to generated events
- expose why the system believes something happened
- make coordinator review able to confirm, downgrade, or reject outputs without
  losing context

#### 4. Category and threshold policy

- make categories configurable where it improves operations
- preserve a bounded default policy so the product stays understandable

### Exit criteria

- multimodal events outperform separate single-source outputs in documented
  evaluation
- correlated outputs reduce duplicate review burden
- coordinator-facing intelligence remains explainable and source-attributed
- tuning remains bounded and operationally understandable

### Non-goals

- general-purpose conversational AI inside the product
- opaque agent autonomy
- unreviewable long-form automated analysis

---

## Phase 4: Field-Ready Member Experience

**Primary goal:** Make the member-side runtime reliable enough to trust during
real operations, not just validation sessions.

**Target release band:** `1.4.x`

### Outcomes

- stronger degraded-network behavior
- better sensor ergonomics and battery-awareness
- clearer browser support posture
- installable, resilient member runtime

### Workstreams

#### 1. PWA resilience

- strengthen offline shell behavior
- improve queued action handling and sync recovery
- reduce confusing partial-state cases after reconnect

#### 2. Sensor ergonomics

- expose stream health, battery cost, and quality controls more clearly
- support adaptive policies for bandwidth and power
- keep capture behavior understandable to the user

#### 3. Browser support matrix

- expand beyond the current Chromium-first posture only where validation
  supports it
- document degraded modes honestly for Firefox and Safari

#### 4. Observer and sensor role polish

- make role transitions clearer
- reduce accidental operator burden caused by member confusion
- improve alert feed readability and task visibility under mobile constraints

### Exit criteria

- reconnect and queue behavior are legible and durable
- supported-browser guidance is backed by actual tests
- sensor UX makes tradeoffs visible instead of hidden
- the member path feels intentionally designed rather than validation-stage

### Non-goals

- broad native-app investment unless browser evidence demands it
- feature expansion that increases complexity without improving field use

---

## Phase 5: Single-Hub Operational System

**Primary goal:** Finish the product as a mature single-hub system before
platform expansion.

**Target release band:** `2.0`

### Outcomes

- repeatable deployable field package
- strong operator drills and after-action review
- explicit support posture for hardware, browsers, and operational constraints

### Workstreams

#### 1. Install and deployment maturity

- harden install and startup experience on supported hardware
- reduce coordinator-only tribal knowledge
- clarify operational prerequisites and failure modes

#### 2. After-action and review system

- strengthen exports, summaries, and review artifacts
- make unresolved follow-up and closure state first-class after the operation
- support post-operation learning without claiming more certainty than exists

#### 3. Security and privacy hardening

- improve token and membership control where justified
- tighten key handling and wipe orchestration
- preserve join simplicity unless security benefit clearly outweighs the cost

#### 4. Supported configuration profiles

- define a smaller set of known-good deployment profiles
- tie performance and support claims to those profiles

### Exit criteria

- a new operator can stand up and close down a supported deployment using the
  documented path
- single-hub lifecycle, evidence handling, and wipe posture are coherent and
  honest
- the repo can describe the product as a mature local operational system
  without hiding validation caveats

### Non-goals

- multi-hub federation
- large integration surface
- broad platform portability beyond supported profiles

---

## Phase 6: Platform Expansion Only After Single-Hub Excellence

**Primary goal:** Expand Osk only after the single-hub product is clearly good.

**Target release band:** `3.x` or later

This phase is explicitly conditional. It should not begin just because the ideas
are attractive.

### Candidate work

- multi-hub federation
- cross-hub member roaming
- broader offline-first sync protocol
- native sensor clients if browser limits remain binding
- cross-operation analysis and trend tooling

### Entry criteria

- the single-hub product is already trustworthy and supportable
- there is a real operational use case that cannot be met without expansion
- the maintainer explicitly wants to own the added complexity

### Default posture

Until those conditions are true, federation and platform expansion remain
backlog, not roadmap-critical work.

---

## Capability Dependencies

These dependencies should guide planning and PR review.

### Must come before broader browser support

- real-device validation
- stable sensor policies
- clear degraded-mode behavior

### Must come before advanced synthesis

- operator workflows that can consume better intelligence
- review surfaces that can explain and correct outputs

### Must come before federation

- strong single-hub operation lifecycle
- well-defined event, task, and closure semantics
- supported deployment profiles

### Must come before native apps

- proof that browser constraints are materially blocking the roadmap

---

## Program-Level Metrics

These are not all current metrics. They are the metrics the roadmap should
eventually drive toward.

### Startup and Join

- coordinator startup to operation-ready time
- member scan-to-joined time
- reconnect success rate after transient disconnect

### Intelligence

- ingest-to-alert latency
- event correlation accuracy
- operator-confirmed false positive and false negative rates

### Coordination

- task assignment to acknowledgement latency
- task completion and timeout rates
- route confirmation turnaround time

### Reliability

- sustainable concurrent sensor count on supported hardware
- memory growth over long-duration runs
- browser regression catch rate in CI

### Closure

- percentage of operations with clear operator handoff artifacts
- unresolved wipe follow-up count at operation end
- evidence export integrity success rate

---

## How Work Should Map to This Roadmap

Every meaningful feature or hardening change should answer four questions:

1. Which phase does this belong to?
2. Which end-state pillar does it move forward?
3. What operator or member outcome improves because of it?
4. What claim becomes more truthful after it lands?

If a change cannot answer those questions, it is probably not on the critical
path.

For solo-maintainer discipline:

- prefer work that closes a roadmap dependency
- prefer validation over speculative expansion
- prefer coordinator leverage over surface-area growth
- prefer reversible architecture over permanent complexity

---

## Backlog Outside the Critical Path

These are legitimate ideas, but they are not the main path unless the maintainer
explicitly reprioritizes them.

- native Android client
- iOS-specific expansion beyond what browser support allows
- social media ingestion
- external messaging integrations
- cross-operation analytics
- hub appliance packaging
- broad plug-in style customization

---

## Decision Framework for Future Changes

When two plausible directions compete, choose the one that most improves the
following in order:

1. truthfulness of product claims
2. reliability of the single-hub field workflow
3. coordinator ability to make better decisions
4. member ability to join and operate with low friction
5. privacy and closure posture
6. future expansion potential

If a proposal scores well only on future expansion or architectural elegance but
not on the first five items, it should usually wait.

---

## Immediate Translation of This Roadmap

The next practical planning cycle should treat these as the active priorities:

1. complete real-device and long-duration validation
2. harden evidence retention and browser automation regression coverage
3. continue evolving coordinator-directed tasking and route confidence
4. only then deepen multimodal intelligence and mature the member runtime

That is the shortest path from the current validated slice to the intended
product.

---

## Relationship to Existing Documents

- The design spec remains the high-level intended system design.
- The old post-1.0 roadmap remains a useful tactical snapshot.
- This document is the roadmap to use when deciding what Osk is becoming and
  what should happen next.
