# Plan 34: Release 2.0 "Mature Single-Hub Operational System"

**Date:** 2026-03-28  
**Status:** Draft for maintainer review  
**Prerequisite:** Release 1.3.0 completed and tagged  
**Target Completion:** 8-10 weeks (Weeks 1-10: 1.4.x Field-Ready, Weeks 11-16: 2.0 Polish)

---

## Purpose

This plan defines the path from Release 1.3.0 (Trustworthy Intelligence Fusion) to Release 2.0 (Mature Single-Hub Operational System). The goal is not to add new capabilities but to make the existing single-hub product operationally excellent, supportable, and repeatable.

Release 2.0 is the milestone where Osk graduates from "validated foundation" to "field-mature operational system."

---

## Mission Statement

A motivated coordinator can:
1. Install and launch Osk on supported hardware with minimal prep
2. Run a complete operation with confidence in the system's reliability
3. Direct members through tasking and intelligence review
4. Close the operation with trustworthy evidence and clear handoff
5. Trust the claims in the documentation to match real behavior

---

## Two-Phase Approach

### Phase A: Release 1.4.x "Field-Ready Member Experience" (Weeks 1-10)

Make the member-side runtime reliable enough to trust during real operations, not just validation sessions.

#### Workstream 1: PWA Resilience

| Week | Task | Deliverable |
|------|------|-------------|
| 1-2 | Harden offline shell behavior | Robust service worker, cached critical assets |
| 2-3 | Improve queued action handling | IndexedDB queue with sync recovery |
| 3-4 | Reduce partial-state cases after reconnect | State reconciliation, clear loading indicators |
| 4 | Create offline-first test suite | Automated tests for offline/online transitions |

**Success Criteria:**
- Member can queue actions offline and sync successfully upon reconnect
- Reconnect success rate >95% after transient disconnect
- No confusing partial-state UI cases

#### Workstream 2: Sensor Ergonomics

| Week | Task | Deliverable |
|------|------|-------------|
| 3-4 | Expose stream health clearly | Battery cost indicator, stream quality meter |
| 4-5 | Adaptive bandwidth/power policies | Auto-throttle on low battery/bandwidth |
| 5-6 | Capture behavior controls | User-visible sensor on/off, quality selection |
| 6 | Document sensor battery impact | Measured battery usage guide |

**Success Criteria:**
- Member understands battery cost of sensor streaming
- Adaptive policies reduce battery drain by >20% in degraded conditions
- Stream quality controls are discoverable and effective

#### Workstream 3: Browser Support Matrix

| Week | Task | Deliverable |
|------|------|-------------|
| 5-6 | Expand Firefox validation | Document Firefox capabilities and limits |
| 6-7 | Expand Safari validation | Document Safari capabilities and limits |
| 7-8 | Define degraded modes | Honest documentation of browser differences |
| 8 | Create browser regression CI | Automated matrix testing |

**Success Criteria:**
- Supported browsers documented with test evidence
- Degraded modes honestly described
- CI catches browser-specific regressions

#### Workstream 4: Observer/Sensor Role Polish

| Week | Task | Deliverable |
|------|------|-------------|
| 7-8 | Clarify role transitions | Explicit role selector, onboarding hints |
| 8-9 | Reduce accidental operator burden | Better member onboarding flow |
| 9-10 | Improve mobile alert readability | Optimized alert feed for small screens |
| 10 | Mobile task visibility improvements | Better task display under mobile constraints |

**Success Criteria:**
- Member understands their role and capabilities
- Role confusion reduced by >50% (measured in validation)
- Mobile experience feels intentional, not cramped

---

### Phase B: Release 2.0 "Mature Single-Hub Operational System" (Weeks 11-16)

Finish the product as a mature single-hub system before any platform expansion.

#### Workstream 5: Install and Deployment Maturity

| Week | Task | Deliverable |
|------|------|-------------|
| 11 | Harden install experience | Better error messages, prerequisite checks |
| 11-12 | Reduce coordinator tribal knowledge | Clearer startup guidance, common failure modes |
| 12 | Document operational prerequisites | Hardware, network, browser requirements |
| 12-13 | Define supported deployment profiles | Known-good configurations |

**Success Criteria:**
- New coordinator can install without maintainer intervention
- Prerequisites are explicit and checked
- Common failures have clear remediation steps

#### Workstream 6: After-Action and Review System

| Week | Task | Deliverable |
|------|------|-------------|
| 13 | Strengthen export artifacts | Better-formatted evidence exports |
| 13-14 | Operation summary generation | Auto-generated after-action summary |
| 14-15 | Unresolved follow-up tracking | Closure checklist with pending items |
| 15 | Post-operation review tools | Timeline replay, decision reconstruction |

**Success Criteria:**
- Evidence export is usable for post-operation review
- After-action summary captures key decisions and events
- Coordinator knows what remains unresolved at closure

#### Workstream 7: Security and Privacy Hardening

| Week | Task | Deliverable |
|------|------|-------------|
| 14 | Token and membership control review | Stronger auth where justified |
| 14-15 | Key handling hardening | Better secret management |
| 15 | Wipe orchestration improvements | More thorough cleanup verification |
| 15-16 | Privacy claims review | Documentation matches actual behavior |

**Success Criteria:**
- Security improvements don't sacrifice join simplicity
- Wipe verification is trustworthy
- Privacy claims are provably true

#### Workstream 8: Documentation and Release Polish

| Week | Task | Deliverable |
|------|------|-------------|
| 15 | Supported configuration profiles | Documented and tested profiles |
| 15-16 | End-to-end operation demo | Video walkthrough or validation bundle |
| 16 | Doc review and truthful claims | All documentation reviewed for accuracy |
| 16 | Release checklist completion | CHANGELOG, validation evidence, tagging |

---

## Release Gates

### 1.4.x Exit Criteria (Before Starting 2.0)

- [ ] Reconnect and queue behavior are legible and durable
- [ ] Sensor UX makes tradeoffs visible instead of hidden
- [ ] Supported-browser guidance is backed by actual tests
- [ ] Member path feels intentionally designed rather than validation-stage

### 2.0 Exit Criteria

- [ ] A new operator can stand up and close down a supported deployment using the documented path
- [ ] Single-hub lifecycle, evidence handling, and wipe posture are coherent and honest
- [ ] The repo can describe the product as a mature local operational system without hiding validation caveats

---

## Non-Goals (Explicitly Out of Scope)

These are legitimate ideas but **will not** be in 2.0:

- ❌ Multi-hub federation
- ❌ Native Android/iOS apps
- ❌ Social media ingestion
- ❌ External messaging integrations (Slack, Discord, etc.)
- ❌ Cross-operation analytics
- ❌ Hub appliance packaging
- ❌ Plugin/customization engine
- ❌ Broad workflow automation beyond tasking

These remain backlog for **3.x or later**, only after explicit maintainer decision.

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Install Success Rate | >95% | New coordinator can install without help |
| Reconnect Success Rate | >95% | After transient disconnect |
| Offline Queue Recovery | >90% | Queued actions sync successfully |
| Battery Impact (Documented) | Accurate | Measured vs claimed |
| Browser Test Coverage | 100% | Chrome, Firefox, Safari in CI |
| Evidence Export Usability | Validated | User test with real operators |
| Wipe Verification | Trustworthy | Forensic check confirms cleanup |

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Browser limitations block PWA goals | Medium | High | Document degraded modes honestly |
| Battery optimization harder than expected | Medium | Medium | Set realistic targets, document tradeoffs |
| Security hardening breaks join simplicity | Medium | High | Balance rigor with usability |
| Timeline slips | Medium | Low | Scope is fixed, ship when ready |

---

## Relationship to Prior Releases

```
1.0.0 (Foundation)
    ↓
1.1.0 (Field Truth) - validation infrastructure
    ↓
1.2.0 (Coordinator Operations) - tasking system
    ↓
1.3.0 (Intelligence Fusion) - multimodal correlation
    ↓
1.4.x (Field-Ready Member) ← CURRENT FOCUS
    ↓
2.0 (Mature Single-Hub) ← END GOAL
    ↓
3.x (Platform Expansion) - federation, native apps (conditional)
```

---

## Immediate Next Steps

1. **Week 1:** Create feature branch `feature/1.4.0-field-ready`
2. **Week 1:** Begin PWA resilience work (service worker hardening)
3. **Week 1:** Set up browser matrix CI testing
4. **Week 2:** First sensor ergonomics prototypes
5. **Week 3:** First offline-first validation tests

---

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-03-28 | Split into 1.4.x and 2.0 | Field-ready work is substantial enough for intermediate release |
| 2026-03-28 | Explicit non-goals list | Prevent scope creep into federation/platform expansion |
| 2026-03-28 | No native apps | Browser-first until evidence shows hard limits |

---

## Appendix: Reference Documents

- [End-State Product Roadmap](./2026-03-28-end-state-product-roadmap.md)
- [Design Spec](../specs/2026-03-21-osk-design.md)
- [1.3.0 Evaluation](../release/1.3.0-evaluation.md)

---

**Author:** AI Implementation Agent  
**Review Required:** Maintainer sign-off before Week 1 start  
**Status:** Draft → Ready for Implementation
