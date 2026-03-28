# 1-Hour Stability Test Procedure

**Purpose:** Validate Osk hub stability with real sensor streaming over extended duration  
**Duration:** 1 hour (plus 5-10 minutes setup)  
**Hardware:** Linux coordinator + 1 remote Chromebook

---

## Prerequisites

### Coordinator (Linux Laptop)
- Osk 1.0.0+ installed
- Python 3.11+ with psutil: `pip install psutil`
- Network accessible to Chromebook
- Stable power (plugged in)

### Chromebook
- Chrome browser
- Camera and microphone (for sensor streaming)
- Stable WiFi connection
- Power connected (test runs 1 hour)

### Network
- Coordinator and Chromebook on same network, OR
- Coordinator reachable from Chromebook (port forwarding if needed)

---

## Setup (5 minutes)

### Step 1: Start Hub

On coordinator:

```bash
# Start fresh operation
osk start --fresh "Stability Test $(date +%Y-%m-%d)"

# Verify running
osk status

# Get join information
osk dashboard
```

**Save:**
- Join URL: _______________________________
- Operation token: ________________________

### Step 2: Prepare Monitoring

Open 2-3 terminal windows on coordinator:

**Terminal 1 - Stability Script:**
```bash
cd /path/to/osk
python scripts/stability_test.py --duration 3600 --output stability-report-$(date +%Y%m%d-%H%M).json
```

**Terminal 2 - Watch Logs (optional):**
```bash
tail -f ~/.local/state/osk/hub.log | grep -E "ERROR|WARNING|disconnect"
```

**Terminal 3 - Manual Status (optional):**
```bash
# For periodic manual checks
watch -n 30 'osk status --json | jq "{running, members: [.members[] | {name, connected, role}]}"'
```

---

## Test Execution

### Step 3: Connect Chromebook

On Chromebook:

1. Open Chrome browser
2. Navigate to the join URL from Step 1
3. Enter name: `Stability-Sensor-01`
4. Select role: **Sensor**
5. Grant permissions when prompted:
   - Camera: **Allow**
   - Microphone: **Allow**
   - Location: **Allow** (optional)

**Verify:** Dashboard shows "Stability-Sensor-01" as connected with green indicator.

### Step 4: Test Auto-Starts

The stability script will detect the sensor and automatically begin the 1-hour test.

You should see:
```
============================================================
STABILITY TEST STARTED
DO NOT DISCONNECT - Running for 1 hour
============================================================
```

**Progress updates every 5 minutes:**
```
Progress: 17% (10m elapsed, 50m remaining) | CPU: 2.3% | Mem: 185MB
```

---

## During the Test

### What to Monitor

**On Coordinator:**
- CPU should stay under 30% (well under 50% target)
- Memory should stay under 500MB
- No ERROR or CRITICAL in logs
- No queue overflow warnings

**On Chromebook:**
- Keep browser tab active (don't minimize)
- Keep device plugged in
- Maintain WiFi connection
- Check battery not draining excessively

### If Issues Occur

**High CPU (>50%):**
```bash
# Check which process
htop

# If needed, reduce sensor load
osk config --set transcriber_backend=fake
osk config --set vision_backend=fake
```

**Connection Drops:**
- Check WiFi signal on Chromebook
- Look for "disconnect" events in stability script output
- Note any pattern (time-based, activity-based)

**Test Interrupted:**
- Press Ctrl+C to stop gracefully
- Report will still be generated with partial data

---

## Completion

### Step 5: Generate Report

After 1 hour (or if stopped early), the script outputs:

```
============================================================
STABILITY TEST SUMMARY
============================================================
Duration: 60.2 minutes
Resource Usage:
  Avg CPU: 2.8%
  Max CPU: 5.2%
  Avg Memory: 192.3 MB
  Max Memory: 210.5 MB
Observations: 1250 total, 20.8/min
Connection Events: 0 disconnects, 0 reconnects
Errors: 0
Status: PASS
============================================================

Full report saved to: stability-report-20260328-1430.json
```

### Step 6: Cleanup

```bash
# Stop hub
osk stop

# Export any evidence if needed
osk evidence export --output stability-test-evidence.zip

# Archive report
cp stability-report-*.json docs/release/
```

---

## Pass Criteria

| Metric | Target | Rationale |
|--------|--------|-----------|
| Max CPU | <30% | Conservative vs 50% 5-sensor target |
| Avg CPU | <15% | Should be efficient |
| Max Memory | <500MB | Conservative vs 1GB target |
| Disconnects | ≤2 | Some tolerance for network issues |
| Errors | 0 | No crashes or critical errors |
| Observation Rate | >10/min | Confirms streaming working |

**PASS:** All criteria met  
**FAIL:** Any criterion not met (investigate and retry)

---

## Troubleshooting

### Chromebook Won't Connect

1. **Check join URL is correct**
   ```bash
   osk dashboard
   ```

2. **Verify hub is accessible**
   ```bash
   # On coordinator
   curl http://localhost:8443/health
   
   # On Chromebook (if same network)
   curl http://<coordinator-ip>:8443/health
   ```

3. **Check firewall**
   ```bash
   sudo firewall-cmd --list-ports
   # Should show 8443/tcp
   ```

### No Observations Generated

1. **Check sensor is streaming**
   - Dashboard should show "streaming" indicator
   - Audio level indicator should move

2. **Check backends**
   ```bash
   osk config --get transcriber_backend
   osk config --get vision_backend
   # For real processing, use "whisper" and "ollama"
   # For testing, "fake" is fine
   ```

3. **Check logs for processing errors**
   ```bash
   osk logs --tail 50
   ```

### High CPU Usage

1. **Switch to fake backends** (for load testing only)
   ```bash
   osk config --set transcriber_backend=fake
   osk config --set vision_backend=fake
   osk restart
   ```

2. **Reduce frame sampling**
   ```bash
   osk config --set frame_sampling_fps=1.0
   ```

3. **Check for other processes**
   ```bash
   htop
   ```

---

## Expected Results

Based on synthetic testing, expect:

| Metric | Expected | Notes |
|--------|----------|-------|
| CPU | 2-5% | One sensor is light load |
| Memory | 150-250MB | Baseline + one sensor |
| Observations | 15-25/min | Depends on audio activity |
| Disconnects | 0 | If network stable |

If results significantly differ, investigate:
- Network issues (high latency, packet loss)
- Chromebook performance limitations
- Hub configuration issues

---

## Next Steps After Success

1. **Archive report:** Add to `docs/release/`
2. **Update validation matrix:** Mark 1-hour stability as validated
3. **Try longer duration:** 2-hour, 4-hour tests if needed
4. **Add sensors:** Test with 2-3 Chromebooks

---

## Report Format

The JSON report contains:

```json
{
  "test_config": {
    "duration_seconds": 3600,
    "target_sensors": 1,
    "actual_duration": 3612.5
  },
  "resource_usage": {
    "avg_cpu_percent": 2.8,
    "max_cpu_percent": 5.2,
    "avg_memory_mb": 192.3,
    "max_memory_mb": 210.5
  },
  "observations": {
    "total": 1250,
    "rate_per_minute": 20.8
  },
  "connection_stability": {
    "disconnects": 0,
    "reconnects": 0
  },
  "errors": [],
  "pass": true
}
```

---

**Print this procedure and have it available during the test.**
