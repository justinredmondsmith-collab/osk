# Release 1.1 Plan: Truthful Field Foundation

**Date:** 2026-03-28  
**Status:** Draft - Ready for Review  
**Target Release:** 1.1.0  
**Timeline:** 4-6 weeks (contingent on resource availability)  

---

## Executive Summary

Release 1.1 establishes Osk as a **truthful, field-validated** product. While 1.0.0 ships a working system, 1.1 proves it works under real conditions with documented evidence.

The core mission is closing the gap between "works in the lab" and "works in the field" through real-device validation, long-duration stability proof, and automated regression protection.

---

## Current State Assessment

### What's Done (From 1.0.0)

| Component | Status | Evidence |
|-----------|--------|----------|
| Hub lifecycle | ✅ Complete | `osk start/stop/status` stable |
| Member join flow | ✅ Complete | Browser-based, cookie sessions |
| Evidence pipeline | ✅ Complete | Media artifacts, export, verify |
| Sensor streaming (synthetic) | ✅ Complete | 5 sensors @ 2.2% CPU |
| Semantic synthesis (code) | ✅ Complete | Ollama adapter, fallback logic |
| Dashboard | ✅ Complete | Runtime visibility, wipe readiness |
| Wipe workflows | ✅ Complete | Connected-browser wipe validated |
| 498 tests | ✅ Passing | CI green |

### What's Pending (Blocks 1.0.0 → Flows to 1.1)

| Component | Status | Blocker |
|-----------|--------|---------|
| Real-device sensor validation | ⏳ Pending | Needs 5-10 Chromebooks |
| Ollama synthesis validation | ⏳ Pending | Needs Ollama runtime |
| Long-duration stability | ⏳ Pending | Needs 1+ hour test run |
| Browser automation CI | ⏳ Pending | Needs Playwright setup |
| Evidence retention limits | ⏳ Pending | Needs implementation |

---

## 1.1 Release Definition

### Primary Mission

> Make the currently claimed single-hub product **truthful under real operating conditions** with documented evidence.

### Must Be True Before Calling 1.1 Done

1. **Real-device sensor validation** has been run and published
2. **Long-duration runtime behavior** is documented with credible stability evidence
3. **Browser automation** protects the member runtime against obvious regressions
4. **Evidence retention behavior** is explicit and test-covered
5. **1.1 documentation** describes supported and unsupported conditions without relying on synthetic-only claims

### Release Claims (What We Can Truthfully Say)

- "Osk has been validated with 5+ concurrent real sensor devices"
- "Hub stability has been demonstrated over 1+ hour operations"
- "Automated regression testing protects critical member workflows"
- "Evidence retention policies prevent silent storage sprawl"
- "Ollama semantic synthesis is evaluated on supported hardware"

---

## Workstreams

### Workstream 1: Real-Device Sensor Validation (Week 1-2)

**Goal:** Validate sensor streaming with physical devices, not just synthetic tests.

**Tasks:**

- [ ] **1.1** Execute Chromebook lab procedure
  - 5 Chromebooks minimum, 10 if available
  - 10-minute streaming session
  - Document battery impact, connection stability
  - File: `docs/release/2026-XX-XX-sensor-validation-real-report.md`

- [ ] **1.2** Validate pass criteria
  - Hub CPU <50% at 5 sensors
  - Observation latency <5s
  - 0 disconnections
  - Battery drain <15%/hour per device

- [ ] **1.3** (Optional) 10-sensor test
  - Hub CPU <80%
  - Observation latency <10s
  - <2 disconnections acceptable
  - Document graceful degradation

**Deliverable:** Real-device validation report with metrics

**Evidence:** Completed validation report in `docs/release/`

---

### Workstream 2: Long-Duration Stability (Week 2-3)

**Goal:** Prove the system doesn't degrade over extended operation.

**Tasks:**

- [ ] **2.1** Implement stability test script
  - Extend `scripts/stability_test.py` for 1+ hour runs
  - Monitor: CPU, memory, DB size, evidence store
  - Detect: Memory leaks, connection leaks, queue growth

- [ ] **2.2** Execute 1-hour stability run
  - 5 synthetic sensors
  - Continuous observation generation
  - Export evidence at end
  - Verify integrity

- [ ] **2.3** Execute 4-hour stability run (stretch)
  - Same metrics as 1-hour
  - Document any degradation

- [ ] **2.4** Generate stability report
  - CPU/memory graphs over time
  - Growth rates (MB/hour)
  - Any issues found and mitigations
  - File: `docs/release/2026-XX-XX-stability-report.md`

**Deliverable:** Stability report proving sustained operation

**Evidence:** Report with 1-hour (minimum) or 4-hour (preferred) run data

---

### Workstream 3: Browser Automation Regression (Week 3-4)

**Goal:** Protect member workflows with automated testing in CI.

**Tasks:**

- [ ] **3.1** Complete `scripts/browser_sensor_validation.py`
  - Playwright-based browser automation
  - Headless mode for CI
  - Simulate 3-5 concurrent browsers
  - Test: join, stream, disconnect, reconnect

- [ ] **3.2** Add CI workflow
  - GitHub Actions workflow file
  - Run on every PR
  - Nightly scheduled run
  - Artifact: test results, screenshots on failure

- [ ] **3.3** Test coverage
  - Member join flow
  - Sensor streaming (simulated)
  - Offline queue and replay
  - Wipe handling

- [ ] **3.4** Documentation
  - How to run locally
  - How to interpret failures
  - When to skip (known flaky conditions)

**Deliverable:** CI pipeline with browser automation

**Evidence:** Green CI runs, documented in `docs/runbooks/`

---

### Workstream 4: Evidence Retention and Cleanup (Week 4)

**Goal:** Prevent silent evidence sprawl with explicit retention policies.

**Tasks:**

- [ ] **4.1** Implement size limits
  - Config: `evidence_max_size_gb` (default: 1 GB)
  - LRU eviction when approaching limit
  - Warning logged before eviction

- [ ] **4.2** Add cleanup commands
  - `osk evidence stats` - Show store size, count, oldest
  - `osk evidence cleanup --older-than 30d`
  - `osk evidence cleanup --operation <id>`

- [ ] **4.3** Automatic cleanup
  - On operation wipe, optionally preserve or delete evidence
  - Configurable per-operation retention

- [ ] **4.4** Testing
  - Unit tests for retention logic
  - Integration test: fill to limit, verify eviction

**Deliverable:** Evidence retention policy implemented and tested

**Evidence:** Tests passing, documentation updated

---

### Workstream 5: Ollama Synthesis Evaluation (Week 4-5)

**Goal:** Evaluate semantic synthesis on real hardware with documented accuracy.

**Tasks:**

- [ ] **5.1** Run evaluation script
  - Execute `scripts/evaluate_semantic_synthesis.py`
  - Requires Ollama running locally
  - Test set: 50+ diverse observations

- [ ] **5.2** Validate targets
  - Classification accuracy >80%
  - Latency <3s per synthesis
  - Graceful fallback on errors

- [ ] **5.3** Prompt tuning (if accuracy <80%)
  - Adjust system prompt
  - Re-evaluate
  - Document final accuracy achieved

- [ ] **5.4** Generate evaluation report
  - Accuracy vs keyword baseline
  - Latency distribution
  - Example classifications (correct and incorrect)
  - File: `docs/release/2026-XX-XX-synthesis-evaluation-report.md`

- [ ] **5.5** Configuration guidance
  - Document when to use heuristic vs Ollama
  - Hardware requirements for Ollama
  - Recommended models

**Deliverable:** Evaluation report with accuracy metrics

**Evidence:** Report showing >80% accuracy (or documented lower with rationale)

---

### Workstream 6: Documentation Truthfulness (Week 5-6)

**Goal:** Update all docs to reflect 1.1 validated capabilities.

**Tasks:**

- [ ] **6.1** Update README.md
  - Sensor streaming: now validated with real devices
  - Synthesis: now includes semantic AI option
  - Evidence: now includes retention policies
  - Stability: now proven for X-hour operations

- [ ] **6.2** Update 1.0.0-definition.md → 1.1-definition.md
  - New validation claims
  - New supported conditions
  - Updated limitations

- [ ] **6.3** Create operator guides
  - `docs/ops/deployment-guide.md` - Hardware, OS, network setup
  - `docs/ops/field-procedures.md` - Checklists, monitoring, wipe
  - `docs/ops/troubleshooting.md` - Common issues, diagnostics

- [ ] **6.4** Create validation evidence index
  - Single page linking all validation reports
  - Synthetic vs real-device results
  - Stability runs
  - Synthesis evaluation

**Deliverable:** Documentation reflecting truthful 1.1 capabilities

**Evidence:** Updated docs, operator can deploy from docs alone

---

## Timeline

```
Week 1: Real-Device Validation
  Day 1-2: Chromebook lab setup and 5-sensor test
  Day 3-4: 10-sensor test (if devices available)
  Day 5: Write validation report

Week 2: Long-Duration Stability
  Day 6-7: Implement extended stability test
  Day 8-9: Execute 1-hour run
  Day 10: Execute 4-hour run (stretch)
  Day 11-12: Write stability report

Week 3: Browser Automation
  Day 13-14: Complete Playwright scripts
  Day 15: Add GitHub Actions workflow
  Day 16-17: Test and document

Week 4: Evidence Retention + Ollama Start
  Day 18-19: Implement retention limits
  Day 20: Add cleanup commands
  Day 21-22: Ollama evaluation (if available)
  Day 23-24: Evidence retention testing

Week 5: Ollama Completion + Documentation Start
  Day 25-26: Complete synthesis evaluation
  Day 27-28: Write synthesis report
  Day 29-30: Start operator documentation

Week 6: Documentation Completion + Release
  Day 31-33: Complete all documentation
  Day 34: Final validation matrix re-run
  Day 35: 1.1.0-rc1 tag
  Day 36-37: RC testing
  Day 38-40: Final fixes and 1.1.0 release
```

**Critical Path:** Real-device validation → Stability → Documentation → Release

---

## Milestone Checklist

### 1.1 Checklist: Truthful Field Foundation

- [ ] Real-device Chromebook sensor validation completed and published
- [ ] Ollama-backed synthesis evaluated on supported hardware
- [ ] Long-duration stability run published
- [ ] Browser automation regression path running in CI or nightly automation
- [ ] Evidence retention and cleanup behavior documented and tested
- [ ] 1.1 docs updated to reflect supported conditions and known limits

**Evidence expected before release:**

- Real-device validation report
- Stability report (1-hour minimum)
- CI/browser automation proof
- Retention policy documentation
- Synthesis evaluation report

---

## Dependencies and Blockers

### External Dependencies

| Dependency | Required For | Mitigation |
|------------|--------------|------------|
| 5-10 Chromebooks | Workstream 1 | Borrow from school/library; simulate with Android phones |
| Ollama runtime | Workstream 5 | Can ship with heuristic default if Ollama unavailable |

### Internal Dependencies

| Prerequisite | Required For | Owner |
|--------------|--------------|-------|
| 1.0.0 final | Starting 1.1 | Release lead |
| Stability script | Workstream 2 | Backend lead |
| Browser automation | Workstream 3 | QA lead |

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Chromebooks unavailable | Medium | High | Use Android phones; document as "5 devices" not specifically Chromebooks |
| Real-device test fails | Low | High | Fix issues; synthetic tests already pass so core pipeline is sound |
| Ollama accuracy <80% | Medium | Medium | Document actual accuracy; keep heuristic as default |
| Stability issues found | Medium | Medium | Fix critical; document acceptable limits |
| Timeline slips | Medium | Medium | Can release with subset if core validation done |

---

## Success Criteria

### Quantitative

- [ ] 5+ real devices validated
- [ ] 1+ hour stability run completed
- [ ] Browser automation in CI (green)
- [ ] Evidence retention <1GB with policy
- [ ] Synthesis accuracy documented (target: >80%)

### Qualitative

- [ ] Operator can deploy from docs alone
- [ ] All claims have linked validation evidence
- [ ] No synthetic-only claims in release docs
- [ ] CI protects against member workflow regressions

---

## Post-1.1: Transition to 1.2

After 1.1 ships with field truth, 1.2 focuses on **coordinator-directed operations**:

- Task assignment lifecycle
- Route confirmation workflows
- Dashboard maturation
- Member task UX

See: `docs/plans/2026-03-28-post-1.0.0-roadmap.md` for 1.2+ planning

---

## Decision Log

| Date | Decision | Rationale | Owner |
|------|----------|-----------|-------|
| 2026-03-28 | Require real-device validation for 1.1 | Must prove field truthfulness | Justin Smith |
| 2026-03-28 | Target 4-6 weeks for 1.1 | Depends on resource availability | Justin Smith |
| 2026-03-28 | Keep Ollama optional | Not all users have GPU for local LLM | Justin Smith |

---

## Related Documents

- [End-State Product Roadmap](./2026-03-28-end-state-product-roadmap.md)
- [Post-1.0.0 Roadmap](./2026-03-28-post-1.0.0-roadmap.md)
- [1.0.0 Gap Remediation Plan](../release/1.0.0-gap-remediation-plan.md)
- [1.0.0 Definition](../release/1.0.0-definition.md)
- [Synthetic Validation Report](../release/2026-03-28-sensor-validation-synthetic-report.md)
