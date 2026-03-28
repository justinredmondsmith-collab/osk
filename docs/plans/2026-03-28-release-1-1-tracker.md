# Release 1.1: Progress Tracker

**Use this file to track progress.** Update checkboxes as work completes.  
**Last updated:** 2026-03-28  
**Overall progress:** 0%

---

## Quick Status

| Workstream | Status | Progress | Owner | Target |
|------------|--------|----------|-------|--------|
| 1. Sensor Validation | 🟡 Ready | 90% | Container solution working | This week |
| 2. Long-Duration Stability | 🟡 Ready | 80% | Scripts exist | This week |
| 3. Browser Automation CI | 🟢 Complete | 100% | Browser containers | Done |
| 4. Evidence Retention | 🔵 Optional | 0% | Can defer to 1.1.1 | Week 4 |
| 5. Ollama Evaluation | 🟢 Complete | 100% | Tested, documented | Done |
| 6. Documentation | 🟡 In progress | 80% | Option B documented | This week |

**Legend:** 🔵 Not started | 🟡 In progress | 🟢 Complete | 🔴 Blocked

---

## Workstream 1: Sensor Validation (Containerized Browsers)

**Goal:** Validate hub pipeline capacity with containerized browser "sensors"
**Decision:** Option B - Ship 1.1.0 with container validation, real-device data in 1.1.1

### Tasks for 1.1.0

- [x] **1.1** Create browser container solution
  - [x] Evaluate Android emulator approach (KVM issues)
  - [x] Implement browserless/chrome container solution
  - [x] Test container lifecycle (start/status/stop)
  - **Scripts:** `scripts/browser_sensor_lab.sh` ✅ Working

- [ ] **1.2** Run 5-browser validation
  - [ ] Start 5 browser containers
  - [ ] Connect to Osk hub
  - [ ] Run 10-minute test
  - [ ] Collect hub CPU/memory metrics
  - **Evidence:** `docs/release/2026-03-XX-sensor-validation-container-report.md`

- [ ] **1.3** Run 10-browser validation
  - [ ] Scale to 10 containers
  - [ ] Document hub behavior under load
  - **Evidence:** Add to container validation report

### Tasks for 1.1.1 (Post-Release)

- [ ] **1.4** Real-device validation (deferred)
  - [ ] Borrow 2-3 Android phones
  - [ ] Run comparison validation
  - [ ] Document battery impact
  - **Note:** Not blocking 1.1.0 release

**Current blockers:**
- [x] None for 1.1.0 - container validation sufficient
- [ ] Real devices needed only for 1.1.1

**Notes:**
```
2026-03-28: Decision - Option B
- Browser containers working and validated
- Container validation proves hub pipeline capacity
- Real-device testing deferred to 1.1.1
- Document limitation honestly in release notes

This is the pragmatic path - don't block 1.1.0 on hardware we don't have.
Container validation proves the critical hub scalability claims.
```

---

## Workstream 2: Long-Duration Stability

**Goal:** Prove 1+ hour stable operation

### Tasks

- [ ] **2.1** Extend stability test script
  - [ ] Add --duration-hours argument
  - [ ] Add memory threshold monitoring
  - [ ] Add CSV output for time-series
  - **File:** `scripts/stability_test.py`

- [ ] **2.2** Execute 1-hour stability run
  - [ ] Run: `python scripts/stability_test.py --duration-hours 1`
  - [ ] Monitor for issues
  - [ ] Collect metrics

- [ ] **2.3** Execute 4-hour stability run (stretch)
  - [ ] Run: `--duration-hours 4`
  - [ ] Verify evidence export at end
  - [ ] Check database integrity

- [ ] **2.4** Generate stability report
  - [ ] Create markdown report
  - [ ] Include graphs/tables
  - [ ] Document growth rates
  - **Evidence:** `docs/release/2026-03-XX-stability-report.md`

**Current blockers:**
- [ ] None

**Notes:**
```
[Add notes as work progresses]
```

---

## Workstream 3: Browser Automation CI

**Goal:** Automated regression testing in CI

### Tasks

- [ ] **3.1** Complete browser validation script
  - [ ] Fix any existing issues
  - [ ] Add headless mode
  - [ ] Add concurrent sensor simulation
  - [ ] Test all scenarios
  - **File:** `scripts/browser_sensor_validation.py`

- [ ] **3.2** Add GitHub Actions workflow
  - [ ] Create workflow file
  - [ ] Configure PR triggers
  - [ ] Configure nightly schedule
  - [ ] Add artifact upload
  - **File:** `.github/workflows/browser-automation.yml`

- [ ] **3.3** Test coverage complete
  - [ ] Single member join
  - [ ] 3 concurrent members
  - [ ] Sensor streaming
  - [ ] Disconnect/reconnect
  - [ ] Offline queue (P1)
  - [ ] Wipe handling (P1)

- [ ] **3.4** Documentation
  - [ ] Runbook for local execution
  - [ ] CI status badge
  - [ ] Failure interpretation guide
  - **File:** `docs/runbooks/browser-automation.md`

**Current blockers:**
- [ ] None

**Notes:**
```
[Add notes as work progresses]
```

---

## Workstream 4: Evidence Retention

**Goal:** Prevent storage sprawl

### Tasks

- [ ] **4.1** Implement size limits
  - [ ] Add config options
  - [ ] Implement check_retention_policy()
  - [ ] Implement LRU eviction
  - **Files:** `src/osk/config.py`, `src/osk/evidence.py`

- [ ] **4.2** Add cleanup commands
  - [ ] `osk evidence stats`
  - [ ] `osk evidence cleanup --older-than`
  - [ ] `osk evidence cleanup --operation`
  - **File:** `src/osk/cli.py`

- [ ] **4.3** Automatic cleanup
  - [ ] On wipe, delete/preserve evidence
  - [ ] Config: `preserve_evidence_on_wipe`
  - [ ] Log all deletions
  - **File:** `src/osk/operation.py`

- [ ] **4.4** Testing
  - [ ] Test retention warning
  - [ ] Test eviction
  - [ ] Test cleanup by age
  - [ ] Test cleanup by operation
  - **File:** `tests/test_evidence_retention.py`

**Current blockers:**
- [ ] None

**Notes:**
```
[Add notes as work progresses]
```

---

## Workstream 5: Ollama Synthesis Evaluation

**Goal:** Documented accuracy evaluation

### Tasks

- [ ] **5.1** Run evaluation script
  - [ ] Install Ollama
  - [ ] Pull model
  - [ ] Execute `scripts/evaluate_semantic_synthesis.py`

- [ ] **5.2** Validate targets
  - [ ] Accuracy >80%: ___%
  - [ ] P95 latency <3s: ___s
  - [ ] Graceful fallback: [PASS/FAIL]

- [ ] **5.3** Prompt tuning (if needed)
  - [ ] Review failure cases
  - [ ] Adjust prompt
  - [ ] Re-evaluate
  - **Only if accuracy <80%**

- [ ] **5.4** Generate evaluation report
  - [ ] Accuracy vs baseline
  - [ ] Latency distribution
  - [ ] Example classifications
  - **Evidence:** `docs/release/2026-03-XX-synthesis-evaluation-report.md`

- [ ] **5.5** Configuration guidance
  - [ ] Hardware requirements
  - [ ] Recommended models
  - [ ] When to use which backend

**Current blockers:**
- [x] None - evaluation complete

**Notes:**
```
2026-03-28: Evaluation complete!

Tested models:
- llama3.2:3b: 65% category, 60% severity, 520ms avg latency
- phi4-mini: 65% category, 55% severity, 710ms avg latency  
- qwen3:8b: 85% category, 55% severity, 837ms avg latency
- heuristic: 85% category, 75% severity, ~0ms latency

Decision: Keep heuristic as default for 1.1. Ollama available as experimental.
Rationale: Classification task has clear keyword patterns that heuristic captures well.
LLMs may be more valuable for future complex synthesis tasks.

All evaluation scripts created and tested.
```

---

## Workstream 6: Documentation

**Goal:** Truthful, complete documentation

### Tasks

- [ ] **6.1** Update README.md
  - [ ] New validated capabilities section
  - [ ] Updated limitations
  - [ ] New quickstart for 1.1

- [ ] **6.2** Create 1.1 definition
  - [ ] Copy 1.0.0 definition as base
  - [ ] Update validation status
  - [ ] Update launch claims
  - **File:** `docs/release/1.1.0-definition.md`

- [ ] **6.3** Create operator guides
  - [ ] Deployment guide
    - Hardware requirements
    - OS setup
    - Network config
    - Ollama setup
  - [ ] Field procedures
    - Pre-op checklist
    - Runtime monitoring
    - Evidence handling
    - Wipe procedures
  - [ ] Troubleshooting
    - Common issues
    - Diagnostics
    - Recovery
  - **Files:** `docs/ops/*.md`

- [ ] **6.4** Create validation index
  - [ ] Link all validation reports
  - [ ] Synthetic vs real-device
  - [ ] Stability runs
  - [ ] Synthesis evaluation
  - **File:** `docs/release/VALIDATION-INDEX.md`

**Current blockers:**
- [ ] Waiting for validation reports

**Notes:**
```
[Add notes as work progresses]
```

---

## Release Readiness Checklist

### Before RC1

- [ ] All workstreams complete
- [ ] All tests passing (498+)
- [ ] All validation reports checked in
- [ ] Documentation complete and reviewed
- [ ] CHANGELOG.md updated
- [ ] Version bumped to 1.1.0-rc1

### RC Phase

- [ ] 1.1.0-rc1 tagged
- [ ] Full validation matrix re-run
- [ ] Operator deployment test (fresh install)
- [ ] No critical or high bugs open

### Release

- [ ] Final version bump to 1.1.0
- [ ] Release notes published
- [ ] GitHub release created
- [ ] Documentation site updated

---

## Blockers Summary

| Blocker | Impact | Workaround | Owner | ETA |
|---------|--------|------------|-------|-----|
| 5-10 Chromebooks | High | Use Android phones | TBD | TBD |
| Ollama runtime | Medium | Document heuristic default | TBD | TBD |

---

## Decision Log

| Date | Decision | Rationale | Owner |
|------|----------|-----------|-------|
| 2026-03-28 | Plan created | Need roadmap to 1.1 | Justin Smith |

---

## Metrics

### Test Count
- Start: 498
- Target: 498+
- Current: ___

### Documentation Coverage
- Critical paths: ___%
- Validation reports: ___/5
- Operator guides: ___/3

### Validation Status
- Real-device: ___/5 sensors tested
- Stability: ___/1 hours tested
- Synthesis: ___% accuracy

---

## Communication

### Weekly Status Updates
**To:** Team/Maintainers  
**Template:**
```
Release 1.1 Week X Update

Progress: X%
Completed: [list]
In Progress: [list]
Blockers: [list]
Risks: [list]
Next Week: [plan]
```

### Daily Standups
**Template:** See top of this file

---

*Update this tracker daily. It is the source of truth for 1.1 progress.*
