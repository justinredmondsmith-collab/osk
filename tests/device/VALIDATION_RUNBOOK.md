# Real-Device Validation Runbook

**Version:** 1.4.0  
**Purpose:** Step-by-step procedures for validating Osk on real devices

---

## Prerequisites

### Required Hardware

| Item | Purpose | Quantity |
|------|---------|----------|
| Android device (Pixel 6 or similar) | Primary test device | 1 |
| iOS device (iPhone 12+) | Safari validation | 1 (optional) |
| Linux laptop | Hub host | 1 |
| WiFi router/hotspot | Local network | 1 |

### Software Setup

1. Chrome 120+ installed on Android device
2. Firefox 120+ installed (for degraded mode testing)
3. Device developer options enabled
4. Battery at 80%+ before starting test
5. Screen brightness at 50% (consistent across tests)

---

## Test 1: Battery Impact Validation (30 minutes)

### Purpose
Measure battery drain during sensor operation.

### Setup

1. Start Osk hub on laptop
2. Join operation from Android device (Chrome)
3. Open `reconnect_stress_test.html` in second tab
4. Click "Start Battery Monitor"

### Procedure

```
Time: 0:00
Action: Enable audio + frame sensors
Note baseline battery level

Time: 0:05
Action: Verify sensors streaming
Check hub receiving data

Time: 0:15
Action: Midpoint check
Record battery level

Time: 0:30
Action: Stop test
Export battery report
```

### Pass Criteria

| Metric | Target | Result |
|--------|--------|--------|
| Battery drain | < 30% | ___% |
| Sensor uptime | > 95% | ___% |
| Reconnects | < 3 | ___ |

### Export

Save JSON report as: `battery-chrome-pixel6-{date}.json`

---

## Test 2: Reconnect Stress Test (15 minutes)

### Purpose
Validate reconnection reliability under stress.

### Setup

1. Join operation from Android device
2. Open `reconnect_stress_test.html`
3. Configure: 100 cycles, 500ms offline, 1000ms online

### Procedure

```
1. Click "Start Battery Monitor"
2. Click "Start Test"
3. Wait for completion (auto-runs 100 cycles)
4. Export results
```

### Pass Criteria

| Metric | Target | Result |
|--------|--------|--------|
| Success rate | >= 95% | ___% |
| Avg latency | < 500ms | ___ms |
| Failed cycles | < 5 | ___ |

### Export

Save JSON report as: `reconnect-chrome-pixel6-{date}.json`

---

## Test 3: Firefox Degraded Mode (15 minutes)

### Purpose
Validate graceful degradation on Firefox.

### Setup

1. Install Firefox on Android device
2. Join operation
3. Attempt to enable sensors

### Procedure

```
1. Join operation
2. Try manual report (should work)
3. Try photo capture (should work)
4. Try audio streaming (may fail - document)
5. Run 20-cycle reconnect test
```

### Expected Behavior

| Feature | Expected | Actual |
|---------|----------|--------|
| Join | ✅ Works | |
| Manual reports | ✅ Works | |
| Media capture | ✅ Works | |
| Audio streaming | ⚠️ May fail | |
| Frame capture | ⚠️ May be slow | |

### Document Issues

List any unexpected failures:
- ___
- ___
- ___

---

## Test 4: Safari iOS Validation (15 minutes)

### Purpose
Document Safari limitations.

### Setup

1. Use iOS device
2. Open Safari
3. Join operation

### Procedure

```
1. Join operation
2. Test manual features
3. Attempt sensor enable (expect failure/warning)
4. Test "Add to Home Screen" PWA flow
```

### Expected Behavior

| Feature | Expected | Actual |
|---------|----------|--------|
| Join | ✅ Works | |
| Manual reports | ✅ Works | |
| PWA install | ⚠️ Manual only | |
| Audio streaming | ❌ Not supported | |
| Background operation | ❌ Not supported | |

---

## Test 5: Long-Duration Stability (2 hours)

### Purpose
Catch memory leaks and drift issues.

### Setup

1. Start hub
2. Join with sensors enabled
3. Start battery monitor

### Procedure

```
Time: 0:00 - Start test
Time: 0:30 - Check sensors still streaming
Time: 1:00 - Midpoint check, record battery
Time: 1:30 - Check sensors still streaming
Time: 2:00 - Stop test, export all logs
```

### Watch For

- [ ] Memory growth (check browser task manager)
- [ ] Sensor dropouts
- [ ] Reconnect loops
- [ ] Battery drain acceleration

### Pass Criteria

| Metric | Target |
|--------|--------|
| Sensor uptime | > 98% |
| Manual reconnects needed | < 2 |
| Battery drain linear | No acceleration |

---

## Report Template

```markdown
# Validation Report: {Date}

## Device Info
- Device: ___
- OS: ___
- Browser: ___
- Browser Version: ___

## Test Results

### Battery Impact (30 min)
- Start: ___%
- End: ___%
- Drain: ___%
- Drain rate: ___%/hour
- Result: PASS / FAIL

### Reconnect Stress (100 cycles)
- Success rate: ___%
- Avg latency: ___ms
- Failed: ___ cycles
- Result: PASS / FAIL

### Firefox (if tested)
- Grade: Full / Degraded / Fail
- Issues: ___

### Safari iOS (if tested)
- Grade: Full / Degraded / Fail
- Issues: ___

### Long Duration (2 hour)
- Sensor uptime: ___%
- Issues: ___

## Overall Assessment
- [ ] Ready for 1.4.0
- [ ] Needs work (document blockers)
```

---

## Troubleshooting

### Issue: Battery monitor not showing

**Solution:** Battery API may not be available
- Check `navigator.getBattery` exists
- Some browsers require HTTPS
- iOS Safari doesn't support Battery API

### Issue: Reconnect test failing early

**Solution:** Check WebSocket connection
- Verify hub is running
- Check device is on same network
- Try manual disconnect/reconnect first

### Issue: Sensors not streaming

**Solution:** Check permissions
- Camera permission granted?
- Microphone permission granted?
- Try manual capture first

---

## Sign-Off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Tester | | | |
| Reviewer | | | |

---

## File Naming Convention

```
battery-{browser}-{device}-{YYYYMMDD}.json
reconnect-{browser}-{device}-{YYYYMMDD}.json
full-report-{YYYYMMDD}.md
```
