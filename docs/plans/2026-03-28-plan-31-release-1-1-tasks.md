# Release 1.1: Detailed Task Breakdown

**Companion to:** `2026-03-28-plan-30-release-1-1-roadmap.md`  
**Purpose:** Specific tasks, files, and implementation details

---

## Quick Reference: Workstream Owners

| Workstream | Primary Owner | Reviewer | Est. Days |
|------------|---------------|----------|-----------|
| 1. Real-Device Validation | QA/Validation Lead | Backend Lead | 5 |
| 2. Long-Duration Stability | Backend Lead | DevOps Lead | 7 |
| 3. Browser Automation CI | QA Lead | Backend Lead | 7 |
| 4. Evidence Retention | Backend Lead | QA Lead | 5 |
| 5. Ollama Evaluation | ML/AI Lead | Backend Lead | 5 |
| 6. Documentation | Tech Writer | All Leads | 10 |

---

## Workstream 1: Real-Device Sensor Validation

### Task 1.1: Execute Chromebook Lab Procedure

**Files to execute:**
- `scripts/chromebook_sensor_validation.md` (procedure)
- `scripts/chromebook_member_shell_smoke.py` (automation helper)

**Files to create:**
```
docs/release/2026-03-XX-sensor-validation-real-report.md
```

**Report structure:**
```markdown
# Real-Device Sensor Validation Report

## Setup
- Devices: [list model, OS version]
- Network: [WiFi spec]
- Coordinator: [hardware spec]

## Results: 5 Sensors
| Metric | Target | Actual | Pass |
|--------|--------|--------|------|
| Hub CPU | <50% | X% | ✅/❌ |
| Latency | <5s | Xs | ✅/❌ |
| Disconnections | 0 | X | ✅/❌ |
| Battery/hour | <15% | X% | ✅/❌ |

## Results: 10 Sensors (if tested)
[same structure]

## Issues Found
- [List any issues]

## Sign-off
[Name, Date]
```

**Success criteria:**
- 5 sensors pass all criteria
- Report checked into `docs/release/`

---

### Task 1.2: Chromebook Validation Procedure (if not exists)

**File to create/update:**
```
scripts/chromebook_sensor_validation.md
```

**Procedure should include:**
1. Device preparation (Chrome OS version, Chrome version)
2. Network setup (WiFi configuration)
3. Hub startup command
4. Device joining sequence (QR code or URL)
5. Streaming duration and monitoring
6. Metrics collection commands
7. Sign-off checklist

---

## Workstream 2: Long-Duration Stability

### Task 2.1: Extend Stability Test Script

**File to modify:**
```
scripts/stability_test.py
```

**Additions needed:**
```python
# New CLI arguments
parser.add_argument("--duration-hours", type=float, default=1.0)
parser.add_argument("--memory-threshold-mb", type=int, default=1024)
parser.add_argument("--sample-interval-sec", type=int, default=60)

# New metrics to collect
- CPU % (sampled every minute)
- Memory MB (sampled every minute)
- Database size MB
- Evidence store size MB
- Observation count
- Connection count
- Queue depths

# Output
- CSV file with time-series data
- Summary statistics
- Growth rates (MB/hour)
- Any anomalies detected
```

---

### Task 2.2: Execute 1-Hour Stability Run

**Command:**
```bash
python scripts/stability_test.py \
  --duration-hours 1 \
  --sensors 5 \
  --json-output stability-1hr-$(date +%Y%m%d).json
```

**Monitoring:**
- Watch for memory growth >100MB/hour
- Watch for CPU creep
- Verify observations keep flowing
- Check evidence accumulation

**Success criteria:**
- No crashes
- Memory growth <100MB/hour
- Observations continuous

---

### Task 2.3: Execute 4-Hour Stability Run (Stretch)

**Same as 2.2 but:**
```bash
--duration-hours 4
```

**Additional checks:**
- Evidence export at end
- Database integrity
- Log rotation working

---

### Task 2.4: Generate Stability Report

**File to create:**
```
docs/release/2026-03-XX-stability-report.md
```

**Contents:**
```markdown
# Stability Report

## Test Configuration
- Duration: X hours
- Sensors: 5 synthetic
- Hub hardware: [spec]

## Results Summary
| Metric | Initial | Final | Growth/Hour |
|--------|---------|-------|-------------|
| CPU % | X | Y | Z |
| Memory MB | X | Y | Z |
| DB Size MB | X | Y | Z |
| Evidence MB | X | Y | Z |

## Graphs
[Include or link to CPU/memory over time graphs]

## Anomalies
[Any spikes, drops, or concerning patterns]

## Conclusion
[Pass/Fail with rationale]
```

---

## Workstream 3: Browser Automation CI

### Task 3.1: Complete Browser Sensor Validation Script

**File to modify:**
```
scripts/browser_sensor_validation.py
```

**Current state check:**
```bash
head -100 scripts/browser_sensor_validation.py
```

**Required functionality:**
```python
# Must support:
--headless  # CI mode
--sensors N  # Number of concurrent browsers
--duration-sec N  # Test duration
--hub-url URL  # Hub endpoint

# Must test:
1. Browser joins via token
2. Member shell loads
3. Simulated sensor streaming
4. Observations received by hub
5. Disconnect handling
6. Reconnect handling
```

**Dependencies:**
```bash
pip install playwright
playwright install chromium
```

---

### Task 3.2: Add GitHub Actions Workflow

**File to create:**
```
.github/workflows/browser-automation.yml
```

**Workflow structure:**
```yaml
name: Browser Automation Tests

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  schedule:
    - cron: '0 2 * * *'  # Nightly at 2am

jobs:
  browser-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install -e .
          pip install playwright
          playwright install chromium
      
      - name: Start Osk hub
        run: |
          osk start --fresh "Browser Test" &
          sleep 5
      
      - name: Run browser validation
        run: |
          python scripts/browser_sensor_validation.py \
            --headless \
            --sensors 3 \
            --duration-sec 60 \
            --json-output results.json
      
      - name: Upload results
        uses: actions/upload-artifact@v3
        if: failure()
        with:
          name: browser-test-results
          path: results.json
      
      - name: Stop hub
        if: always()
        run: osk stop
```

---

### Task 3.3: Test Coverage Requirements

**Test scenarios:**

| Scenario | Priority | Implementation |
|----------|----------|----------------|
| Single member join | P0 | Basic flow validation |
| 3 concurrent members | P0 | Load validation |
| Sensor streaming | P0 | Observation flow |
| Disconnect/reconnect | P1 | Resilience |
| Offline queue | P1 | Replay validation |
| Wipe handling | P1 | Clean disconnect |

---

### Task 3.4: Documentation

**File to create:**
```
docs/runbooks/browser-automation.md
```

**Contents:**
```markdown
# Browser Automation Runbook

## Running Locally
```bash
# Start hub
osk start --fresh "Browser Test"

# Run automation
python scripts/browser_sensor_validation.py --sensors 3

# Stop hub
osk stop
```

## CI Status
[Link to GitHub Actions]

## Interpreting Failures
- Timeout: Hub not responding
- Join failed: Token or routing issue
- No observations: Pipeline breakdown

## Skipping Tests
Known flaky conditions: [list]
```

---

## Workstream 4: Evidence Retention

### Task 4.1: Implement Size Limits

**Files to modify:**
```
src/osk/config.py  # Add new config options
src/osk/evidence.py  # Add retention logic
```

**Config additions:**
```python
# config.py
evidence_max_size_gb: float = 1.0  # Default 1GB
evidence_retention_days: int = 30
evidence_warn_threshold_pct: float = 0.8  # Warn at 80%
```

**Evidence class additions:**
```python
def check_retention_policy(self):
    """Check if evidence store exceeds limits and evict if needed."""
    current_size = self.get_total_size()
    max_size = self.config.evidence_max_size_gb * 1024 * 1024 * 1024
    
    if current_size > max_size * self.config.evidence_warn_threshold_pct:
        logger.warning(f"Evidence store at {current_size/max_size:.1%}")
    
    if current_size > max_size:
        self._evict_oldest(current_size - max_size)

def _evict_oldest(self, bytes_to_free: int):
    """LRU eviction of oldest evidence artifacts."""
    # Implementation
```

---

### Task 4.2: Add Cleanup Commands

**Files to modify:**
```
src/osk/cli.py  # Add CLI commands
```

**New commands:**
```python
@evidence.command()
def stats(ctx):
    """Show evidence store statistics."""
    # Total size, count, oldest/newest
    # Operations represented
    # Retention policy settings

@evidence.command()
@click.option("--older-than-days", type=int, help="Delete evidence older than N days")
@click.option("--operation", help="Delete evidence for specific operation")
@click.confirmation_option(prompt="Delete evidence? This cannot be undone.")
def cleanup(ctx, older_than_days, operation):
    """Clean up evidence artifacts."""
    # Implementation
```

---

### Task 4.3: Automatic Cleanup

**Files to modify:**
```
src/osk/operation.py  # On operation stop/wipe
```

**Behavior:**
- On `osk wipe --yes`: Optionally delete or preserve evidence
- Config: `preserve_evidence_on_wipe: bool = False`
- Log all deletions

---

### Task 4.4: Testing

**Files to create/modify:**
```
tests/test_evidence_retention.py  # New test file
```

**Test cases:**
```python
def test_retention_warning_threshold():
    # Fill to 80%, verify warning logged

def test_retention_eviction():
    # Fill to 100%+1, verify LRU eviction

def test_cleanup_by_age():
    # Create old evidence, cleanup --older-than, verify gone

def test_cleanup_by_operation():
    # Create op evidence, cleanup --operation, verify gone
```

---

## Workstream 5: Ollama Synthesis Evaluation

### Task 5.1: Run Evaluation Script

**Prerequisites:**
```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull model
ollama pull llama3.2:3b  # Or configured model
```

**File to execute:**
```
scripts/evaluate_semantic_synthesis.py
```

**Verify script exists and has:**
- Test dataset (50+ observations)
- Accuracy metrics
- Latency measurements
- Baseline comparison (keyword)

---

### Task 5.2: Validate Targets

**Success criteria:**
- Accuracy >80% vs keyword baseline
- P95 latency <3s
- Graceful fallback on Ollama errors

**If accuracy <80%:**
- Proceed to Task 5.3
- Document actual accuracy
- Keep heuristic as default

---

### Task 5.3: Prompt Tuning (If Needed)

**File to modify:**
```
src/osk/ollama_synthesis.py
```

**Approach:**
1. Review failure cases
2. Adjust system prompt
3. Re-run evaluation
4. Iterate

**Time box:** 2 days max

---

### Task 5.4: Generate Evaluation Report

**File to create:**
```
docs/release/2026-03-XX-synthesis-evaluation-report.md
```

**Structure:**
```markdown
# Semantic Synthesis Evaluation Report

## Configuration
- Model: llama3.2:3b
- Hardware: [spec]
- Dataset: 50 observations

## Results
| Metric | Target | Actual | Pass |
|--------|--------|--------|------|
| Accuracy | >80% | X% | ✅/❌ |
| P50 Latency | <3s | Xs | ✅/❌ |
| P95 Latency | <3s | Xs | ✅/❌ |

## Comparison to Baseline
| Observation | Keyword | Ollama | Correct |
|-------------|---------|--------|---------|
| [Example 1] | WARNING | INFO | ✅ |
| [Example 2] | INFO | WARNING | ❌ |

## Recommendations
- Use Ollama when: [conditions]
- Use heuristic when: [conditions]
```

---

### Task 5.5: Configuration Guidance

**File to update:**
```
docs/ops/deployment-guide.md  # Or create new section
```

**Document:**
- Hardware requirements for Ollama
- Recommended models
- When to use heuristic vs Ollama
- Fallback behavior

---

## Workstream 6: Documentation

### Task 6.1: Update README.md

**Sections to update:**

**Current:**
```markdown
## Current Product Boundary
The release has been validated synthetically; real-device validation is
documented as pending.
```

**New:**
```markdown
## Validated Capabilities (1.1)
- Sensor streaming validated with 5+ real devices
- Hub stability proven for 1+ hour operations
- Semantic synthesis evaluated at X% accuracy
- Automated regression testing in CI
- Evidence retention policies

## Current Limitations
- Real-device validation: 5 devices confirmed, 10+ pending
- Ollama synthesis: Optional, requires GPU
- Long-duration: 1+ hour proven, 4+ hour pending
```

---

### Task 6.2: Create 1.1 Definition

**File to create:**
```
docs/release/1.1.0-definition.md
```

**Use 1.0.0-definition.md as template, update:**
- Validation status table
- Launch claims
- Supported environment
- Explicit non-goals

---

### Task 6.3: Create Operator Guides

**Files to create:**

```
docs/ops/deployment-guide.md
```
Contents:
- Hardware requirements (coordinator)
- OS setup (Fedora/Ubuntu steps)
- Network configuration (hotspot, WiFi)
- Security hardening (firewall, TLS)
- Ollama setup (optional)

```
docs/ops/field-procedures.md
```
Contents:
- Pre-operation checklist
- Startup sequence
- Runtime monitoring commands
- Evidence handling procedures
- Wipe and closure procedures

```
docs/ops/troubleshooting.md
```
Contents:
- Common issues (join failures, streaming issues)
- Diagnostic commands (`osk doctor`, `osk logs`)
- Recovery procedures
- When to restart vs wipe

---

### Task 6.4: Create Validation Evidence Index

**File to create:**
```
docs/release/VALIDATION-INDEX.md
```

**Structure:**
```markdown
# Osk Validation Evidence Index

## Release 1.1

### Real-Device Validation
- [Sensor Validation Report](./2026-03-XX-sensor-validation-real-report.md)
  - 5 devices: [PASS/PENDING]
  - 10 devices: [PASS/PENDING]

### Stability Validation
- [Stability Report](./2026-03-XX-stability-report.md)
  - 1 hour: [PASS/PENDING]
  - 4 hour: [PASS/PENDING]

### Synthesis Validation
- [Synthesis Evaluation](./2026-03-XX-synthesis-evaluation-report.md)
  - Accuracy: X%
  - Latency: Xs

### Automated Testing
- [Browser Automation](../runbooks/browser-automation.md)
  - CI Status: [LINK]
  - Last run: [DATE]

### Historical (1.0.0)
- [Synthetic Validation](./2026-03-28-sensor-validation-synthetic-report.md)
- [Final Validation Run](./2026-03-27-release-validation-final-run.md)
```

---

## File Summary

### New Files to Create

```
docs/release/1.1.0-definition.md
docs/release/2026-03-XX-sensor-validation-real-report.md
docs/release/2026-03-XX-stability-report.md
docs/release/2026-03-XX-synthesis-evaluation-report.md
docs/release/VALIDATION-INDEX.md
docs/ops/deployment-guide.md
docs/ops/field-procedures.md
docs/ops/troubleshooting.md
docs/runbooks/browser-automation.md
tests/test_evidence_retention.py
.github/workflows/browser-automation.yml
```

### Files to Modify

```
scripts/stability_test.py
scripts/browser_sensor_validation.py
src/osk/config.py
src/osk/evidence.py
src/osk/cli.py
src/osk/operation.py
src/osk/ollama_synthesis.py  # If prompt tuning needed
README.md
```

---

## Daily Standup Template

```
## [Date] - Release 1.1 Progress

### Yesterday
- 

### Today
-

### Blockers
-

### Workstream Status
1. Real-Device: [X/5 tasks]
2. Stability: [X/4 tasks]
3. Browser CI: [X/4 tasks]
4. Retention: [X/4 tasks]
5. Ollama: [X/5 tasks]
6. Documentation: [X/4 tasks]

### Risks
-
```

---

## Sign-off Checklist

Before merging to main:

- [ ] All new files have proper headers
- [ ] All modified files have tests passing
- [ ] Documentation reviewed for accuracy
- [ ] Validation reports checked in
- [ ] CI workflow green
- [ ] CHANGELOG.md updated
- [ ] Version bumped to 1.1.0-rc1

---

*This plan is authoritative for Release 1.1. If conflicts arise with other documents, this plan takes precedence.*
