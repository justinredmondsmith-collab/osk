# Next Sprint Plan: Post-1.0.0 Immediate Work

**Sprint Duration:** 2 weeks  
**Start:** 2026-03-28  
**Target:** Production hardening + documentation

---

## Sprint Goals

1. Complete any pending validation when resources become available
2. Harden 1.0.0 for production use
3. Improve developer/operator experience
4. Document operational procedures

---

## Week 1: Hardening & Documentation

### Day 1-2: Operator Documentation

**Owner:** Technical Writer / Dev Lead

**Tasks:**
- [ ] Create `docs/ops/deployment-guide.md`
  - Hardware requirements
  - OS setup (Fedora/Ubuntu)
  - Network configuration
  - Security hardening
  
- [ ] Create `docs/ops/field-procedures.md`
  - Pre-operation checklist
  - Runtime monitoring
  - Evidence handling
  - Wipe procedures
  
- [ ] Create `docs/ops/troubleshooting.md`
  - Common issues
  - Diagnostic commands
  - Recovery procedures

**Deliverable:** Operator can deploy Osk from docs alone

---

### Day 3-4: Long-Duration Testing

**Owner:** Backend Lead

**Tasks:**
- [ ] Run 1-hour stability test
  - 5 synthetic sensors
  - Monitor memory growth
  - Check for connection leaks
  - Verify evidence accumulation
  
- [ ] Document resource usage patterns
  - CPU over time
  - Memory growth
  - Database size
  - Evidence store growth

**Deliverable:** Stability report + any critical fixes

---

### Day 5: Developer Experience

**Owner:** Dev Lead

**Tasks:**
- [ ] Improve error messages in CLI
- [ ] Add progress indicators for long operations
- [ ] Review and update help text
- [ ] Create `make test-quick` for fast feedback

**Deliverable:** Smoother developer/operator UX

---

## Week 2: Validation & Automation

### Day 6-7: Validation Execution (If Resources Available)

**Option A: Chromebooks Available**
- Execute `scripts/chromebook_sensor_validation.md`
- Generate real-device validation report
- Update release notes

**Option B: Ollama Available**
- Run `scripts/evaluate_semantic_synthesis.py`
- Document accuracy results
- Tune prompt if needed

**Option C: Neither Available**
- Proceed with browser automation (below)

---

### Day 8-9: Browser Automation (Playwright)

**Owner:** QA Lead

**Tasks:**
- [ ] Complete `scripts/browser_sensor_validation.py`
  - Fix any remaining issues
  - Add headless mode support
  - Add concurrent sensor simulation
  
- [ ] Add to CI pipeline
  - GitHub Actions workflow
  - Run on PRs
  - Nightly scheduled run

**Deliverable:** Automated sensor testing in CI

---

### Day 10: Evidence Retention

**Owner:** Backend Lead

**Tasks:**
- [ ] Implement evidence size limits
  - Config: `evidence_max_size_gb`
  - LRU eviction
  - Warning before eviction
  
- [ ] Add cleanup commands
  - `osk evidence cleanup --older-than 30d`
  - `osk evidence stats`

**Deliverable:** Evidence retention policy implemented

---

## Stretch Goals (If Time Permits)

### Metrics & Monitoring

- [ ] Add Prometheus metrics endpoint
- [ ] Grafana dashboard for hub monitoring
- [ ] Alert thresholds for resource usage

### Performance

- [ ] Profile hub under load
- [ ] Optimize hot paths
- [ ] Reduce memory allocations

### Testing

- [ ] Property-based tests for synthesis
- [ ] Chaos testing (random disconnects)
- [ ] Load testing to breaking point

---

## Definition of Done

### Sprint Completion Criteria

- [ ] Operator documentation complete and tested
- [ ] 1-hour stability test passes
- [ ] Evidence retention working
- [ ] Either real-device validation OR browser automation in CI
- [ ] All 498 tests still passing
- [ ] No critical or high bugs open

### Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Documentation coverage | 100% critical paths | Checklist review |
| Stability test | 1 hour no issues | Automated test |
| Evidence retention | <1GB with policy | Configuration test |
| Test coverage | Maintain 498+ | CI count |

---

## Blockers & Risks

| Risk | Probability | Mitigation |
|------|-------------|------------|
| Chromebooks not available | High | Focus on browser automation |
| Ollama not available | High | Document heuristic as recommended |
| Stability issues found | Medium | Fix critical, document others |
| Documentation takes longer | Low | Prioritize critical paths |

---

## Daily Standup Template

```
Yesterday:
- 

Today:
- 

Blockers:
- 

Notes:
- 
```

---

## Sprint Review Checklist

- [ ] Demo operator documentation
- [ ] Show stability test results
- [ ] Review evidence retention
- [ ] Demo browser automation (if complete)
- [ ] Review any validation results
- [ ] Update roadmap based on findings

---

## Sprint Retrospective Questions

1. What went well?
2. What could be improved?
3. What should we start doing?
4. What should we stop doing?
5. Any process changes for next sprint?



> Roadmap note: This file is a scoped implementation or historical planning document. Read it through [`2026-03-28-end-state-product-roadmap.md`](./2026-03-28-end-state-product-roadmap.md). If sequencing, priority, or scope conflict with the roadmap, follow the roadmap.
