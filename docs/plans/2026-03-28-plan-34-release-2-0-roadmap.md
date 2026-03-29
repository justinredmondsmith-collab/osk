# Plan 34: Release 2.0 "Mature Single-Hub Operational System"

**Date:** 2026-03-28 (Revised)  
**Status:** Draft - Critical Review Applied  
**Prerequisite:** Release 1.3.0 completed and tagged  
**Target Completion:** 14-18 weeks (realistic with buffer)

---

## Critical Revisions from Initial Draft

| Issue | Original | Revised |
|-------|----------|---------|
| Timeline | 16 weeks claimed as "8-10" | 14-18 weeks honest estimate |
| Work pattern | 4 overlapping workstreams | 2 sequential phases with focus |
| Validation | Metrics without methodology | Each metric has test plan |
| Buffer | None | 2-3 week buffer included |
| Scope risk | Complex features in final weeks | Complex work front-loaded |

---

## Purpose

Transform Osk from "validated foundation with good features" to "field-mature operational system that a new coordinator can trust without maintainer help."

The focus is **operational excellence, not new capabilities**.

---

## Revised Two-Phase Approach

### Phase A: Release 1.4.0 "Field-Ready Foundation" (Weeks 1-8)

Focus: PWA resilience + real-device validation (foundational for everything else)

#### Sprint 1-2: PWA Core Resilience (Weeks 1-2)

| Task | Deliverable | Validation |
|------|-------------|------------|
| Service worker hardening | Robust caching, offline shell | Synthetic: 100 offline/online cycles |
| IndexedDB queue recovery | Queue survives crashes/restarts | Test: kill browser mid-queue, verify recovery |
| State reconciliation | Clear loading states, no partial UI | Manual: 20 reconnect scenarios |

**Sprint Exit:** Demo queue recovery after simulated crash.

#### Sprint 3-4: Real-Device Validation (Weeks 3-4)

| Task | Deliverable | Validation |
|------|-------------|------------|
| Battery measurement framework | Instrumented battery logging | Pixel 6 baseline measurement |
| Reconnect stress test | Automated reconnect scenarios | 100 disconnect/reconnect cycles |
| Firefox validation | Document capabilities/limits | Test matrix: Chrome vs Firefox |
| Safari validation (iOS) | Document capabilities/limits | Test matrix: Chrome vs Safari |

**Sprint Exit:** Real-device validation report with battery/reconnect data.

#### Sprint 5-6: Sensor Ergonomics (Weeks 5-6)

| Task | Deliverable | Validation |
|------|-------------|------------|
| Battery cost indicator | Visible battery drain estimate | User comprehension test (n=3) |
| Stream health display | Connection quality, dropped frames | Synthetic: throttle bandwidth, verify indicators |
| Adaptive quality policies | Auto-reduce on low battery | Test: simulate 20% battery, verify throttle |

**Sprint Exit:** Sensor ergonomics validated on real device with battery verification.

#### Sprint 7-8: Integration & 1.4.0 Polish (Weeks 7-8)

| Task | Deliverable | Validation |
|------|-------------|------------|
| Browser matrix CI | Automated Chrome/Firefox/Safari tests | CI passing all browsers |
| Bug fixes from validation | Address issues found in Weeks 3-4 | All P1/P2 bugs closed |
| 1.4.0 documentation | What's new, known limitations | Doc review complete |
| Tag 1.4.0 | Release cut | All tests passing |

**Phase A Exit Criteria:**
- [ ] Real-device validation report published
- [ ] Reconnect success rate >95% (measured on real device, n=100)
- [ ] Offline queue recovery >90% (synthetic tests)
- [ ] Browser matrix documented with honest degraded modes
- [ ] 1.4.0 tagged and released

**Buffer:** If validation finds major issues, use Week 8 buffer before cutting 1.4.0.

---

### Phase B: Release 2.0 "Mature System" (Weeks 9-16)

Focus: Install maturity + after-action review (coordinator-facing excellence)

#### Sprint 9-10: Install Hardening (Weeks 9-10)

| Task | Deliverable | Validation |
|------|-------------|------------|
| Prerequisite checker | `osk doctor` validates all deps | Test on fresh Ubuntu install |
| Clear error messages | Every failure has actionable guidance | Review: all error paths documented |
| Common failure playbook | Document top 10 install failures | Test: simulate each failure, verify guidance |
| Supported profiles defined | Hardware, OS, browser matrix | Doc: supported configuration profiles |

**Sprint Exit:** New coordinator (simulated) can install without asking for help.

#### Sprint 11-12: After-Action Review System (Weeks 11-12)

| Task | Deliverable | Validation |
|------|-------------|------------|
| Evidence export improvements | Better-formatted exports (PDF/HTML) | User test: can operator understand export? |
| Operation summary generation | Auto-generated after-action report | Test: summary captures key events |
| Closure checklist | Pending items tracking | Test: unresolved tasks visible at closure |
| **[DEFERRED]** Timeline replay | Too complex for 2.0, cut or simplify | Replace with: event timeline export |

**Scope Correction:** "Timeline replay, decision reconstruction" cut. Replaced with simpler "event timeline export" (CSV/JSON).

**Sprint Exit:** Demo after-action workflow from operation end to export.

#### Sprint 13-14: Security Hardening (Weeks 13-14)

| Task | Deliverable | Validation |
|------|-------------|------------|
| Token lifecycle review | Shorter-lived tokens where possible | Security review checklist |
| Key handling audit | No keys in logs, proper permissions | Audit: grep for secrets in codebase |
| Wipe verification improvements | Better cleanup confirmation | **[DEFERRED]** Forensic verification (too complex) |
| Privacy claims audit | Docs match actual behavior | Doc review: every claim has test |

**Scope Correction:** "Forensic wipe verification" cut. Replaced with "better cleanup confirmation logs" (achievable).

**Sprint Exit:** Security audit complete, no P1/P2 issues open.

#### Sprint 15-16: Release Polish & Buffer (Weeks 15-16)

| Task | Deliverable | Validation |
|------|-------------|------------|
| End-to-end walkthrough | Video or scripted demo | Maintainer review: complete workflow |
| Documentation review | All docs accurate and truthful | Checklist: every claim verified |
| Final bug fixes | Address issues from sprints 9-14 | All P1/P2 closed |
| Buffer week | Contingency for overruns | Use if needed |
| Tag 2.0 | Release cut | All tests, validation complete |

**Phase B Exit Criteria:**
- [ ] New coordinator can install using only documentation (tested)
- [ ] After-action export is usable for review (user test)
- [ ] Security audit complete with no critical issues
- [ ] Documentation truthful and complete
- [ ] 2.0 tagged and released

**Buffer:** Week 16 is buffer for overruns. If ahead of schedule, use for additional hardening.

---

## What Was Cut (Scope Discipline)

| Original Plan | Decision | Rationale |
|---------------|----------|-----------|
| Timeline replay, decision reconstruction | ❌ CUT | Complex feature, not polish. Replace with simple export. |
| Forensic wipe verification | ❌ CUT | Requires specialized tooling. Replace with better logs. |
| Native app consideration | ❌ CUT | Stick to browser-first. Evidence doesn't demand native yet. |
| Plugin/customization mentions | ❌ CUT | Out of scope for 2.0, already in non-goals but worth restating. |
| Video walkthrough | ⚠️ OPTIONAL | If time permits. Scripted demo is minimum. |

---

## Revised Non-Goals (Reinforced)

- ❌ Multi-hub federation
- ❌ Native Android/iOS apps  
- ❌ Social media/external integrations
- ❌ Cross-operation analytics
- ❌ Hub appliance packaging
- ❌ Plugin/customization engine
- ❌ Timeline replay (decision reconstruction)
- ❌ Forensic-level wipe verification
- ❌ AI-powered after-action analysis

---

## Revised Success Metrics (With Measurement Plans)

| Metric | Target | How Measured | When |
|--------|--------|--------------|------|
| Install Success Rate | >90% | Fresh VM test: 10 install attempts | Week 10 |
| Reconnect Success Rate | >95% | Real device: 100 disconnect/reconnect | Week 4 |
| Offline Queue Recovery | >90% | Synthetic: 50 crash scenarios | Week 2 |
| Battery Documentation | Accurate | Measured vs claimed on Pixel 6 | Week 6 |
| Browser Test Coverage | Core paths | CI: Chrome, Firefox, Safari | Week 8 |
| Evidence Export Usability | Understandable | User test: 3 people review export | Week 12 |
| Security Audit | No P1/P2 | Manual audit + automated scan | Week 14 |

---

## Revised Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Browser limitations block goals | **High** | High | Document degraded modes honestly; Safari may have limits |
| Real-device validation finds major issues | **Medium** | High | 2-week buffer in Phase A (Week 8) |
| Security changes break existing flows | **Medium** | Medium | Test join flow after every security change |
| Install experience still requires help | **Medium** | High | Test with actual new user in Week 10 |
| Scope creep from "polish" to "features" | **High** | Medium | Strict cut list above; any addition requires cut elsewhere |

---

## Resource Requirements

| Resource | Needed For | Status |
|----------|------------|--------|
| Real Android device (Pixel 6 or similar) | Weeks 3-6 validation | Required by Week 3 |
| iOS device (iPhone) | Safari validation | Required by Week 4 |
| Fresh Linux VM/container | Install testing | Required by Week 9 |
| Test coordinator (human) | Install success validation | Required by Week 10 |

---

## Release Cadence

```
Week 8:  Tag v1.4.0 (Field-Ready Foundation)
         ↓
Week 16: Tag v2.0.0 (Mature Single-Hub System)
         ↓
Future:  v2.0.x patch releases as needed
         3.x platform expansion (conditional)
```

---

## Immediate Next Steps (Week 1)

1. **Create branch:** `feature/1.4.0-field-ready`
2. **Verify resources:** Confirm real Android device available
3. **Begin Sprint 1:** Service worker hardening
4. **Set up:** Battery measurement framework on test device

---

## Decision Log (Revised)

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-03-28 | Timeline: 14-18 weeks (was "8-10") | Honest estimate based on work required |
| 2026-03-28 | Cut "timeline replay" feature | Complex feature masquerading as polish |
| 2026-03-28 | Cut "forensic wipe verification" | Requires tooling that doesn't exist |
| 2026-03-28 | Sequential sprints, not overlapping | Focus beats context switching |
| 2026-03-28 | Add 2-3 week buffer | Realistic planning includes contingency |
| 2026-03-28 | Real-device validation in Phase A | Foundation must be proven before polish |

---

## Appendix: Why This Plan Changed

**Original plan had these problems:**
1. Claimed 8-10 weeks but scheduled 16 weeks of work
2. Four overlapping workstreams caused context switching
3. Complex features (timeline replay) in final weeks
4. No buffer for bug fixes or validation failures
5. Metrics without measurement methodology

**Revised plan fixes:**
1. Honest timeline (14-18 weeks)
2. Sequential sprints with clear focus
3. Complex work front-loaded or cut
4. 2-3 week buffer included
5. Every metric has measurement plan

---

**Author:** AI Implementation Agent  
**Critical Review:** Applied (see Appendix)  
**Status:** Ready for Implementation
