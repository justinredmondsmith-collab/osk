# Real-Device Validation with Android Phone

**Purpose:** Validate Osk sensor streaming with actual mobile hardware  
**Audience:** Operators with access to Android phones  
**Duration:** ~30 minutes

---

## Prerequisites

### Hardware
- 1-3 Android phones (you have 1, can borrow more)
- Linux coordinator laptop with Osk installed
- WiFi network (home router or hotspot)
- USB cable for charging (optional)

### Phone Requirements
- Android 8.0+ (Oreo or newer)
- Chrome browser installed
- Battery at 50%+ (for drain measurement)
- Location services enabled
- Camera and microphone permissions available

### Coordinator Setup
- Osk hub running
- `osk doctor` passes all checks
- Dashboard accessible
- Network reachability between phone and laptop

---

## Quick Start (5-Minute Test)

```bash
# 1. Start Osk hub on coordinator
osk start --fresh "Real Device Test"

# 2. Get join URL
osk dashboard
# Note the URL and one-time code

# 3. On your Android phone:
#    - Connect to same WiFi as coordinator
#    - Open Chrome
#    - Navigate to coordinator URL
#    - Enter one-time code
#    - Select "Sensor" role
#    - Grant camera, mic, location permissions

# 4. Check dashboard - you should see your phone connected

# 5. Monitor for 5 minutes, then stop
osk stop
```

---

## Full Validation Procedure

### Phase 1: Setup (5 minutes)

#### 1.1 Prepare Coordinator

```bash
# Start fresh operation
osk start --fresh "Real Device Validation"

# Verify running
osk status --json

# Get network info
hostname -I
# Example: 192.168.1.100

# Start dashboard
osk dashboard
# Note: https://192.168.1.100:8444/coordinator
# Note: dashboard code for login
```

#### 1.2 Prepare Phone

1. **Connect to WiFi**
   - Same network as coordinator
   - Note: Some hotspots isolate clients (disable "AP isolation" if possible)

2. **Check battery level**
   - Settings → Battery
   - Should be 50%+ for meaningful drain test
   - Note starting percentage

3. **Enable developer options** (optional, for debugging)
   - Settings → About Phone → Tap "Build Number" 7 times
   - Settings → System → Developer Options
   - Enable "Stay awake while charging" (if testing while plugged)

---

### Phase 2: Join and Connect (5 minutes)

#### 2.1 Join from Phone

1. **Open Chrome**
   - Must use Chrome (not Samsung Internet, Firefox, etc.)
   - Version 90+ recommended

2. **Navigate to join URL**
   ```
   https://[coordinator-ip]:8444/join
   ```
   Example: `https://192.168.1.100:8444/join`

3. **Handle SSL warning**
   - Osk uses self-signed certificates
   - Chrome will show "Your connection is not private"
   - Tap "Advanced" → "Proceed to [IP] (unsafe)"

4. **Enter join code**
   - Get code from dashboard or `osk dashboard` output
   - Example: `DbHS79OWjtVXT3yFwT6bd3xR81fAJWnb-dv-08hz3PI`

5. **Select role**
   - Choose **"Sensor"** (not Observer)
   - Enter name: "Phone-01" or your name

6. **Grant permissions**
   - Camera: Allow
   - Microphone: Allow
   - Location: Allow while using app

#### 2.2 Verify Connection

On coordinator:
```bash
# Check members
osk members

# Expected output:
# {
#   "members": [
#     {
#       "name": "Phone-01",
#       "role": "sensor",
#       "connected": true,
#       ...
#     }
#   ]
# }
```

On phone:
- You should see the member shell interface
- Status shows "Connected"
- Audio/video indicators may show activity

---

### Phase 3: Data Collection (10 minutes)

#### 3.1 Record Initial State

**Coordinator (Terminal 1):**
```bash
# Save initial state
osk status --json > real-device-test-initial.json

# Start monitoring hub resources
while true; do
  date +%Y-%m-%dT%H:%M:%S
  ps -p $(pgrep -f "osk hub") -o %cpu,%mem | tail -1
  sleep 10
done > hub-metrics.csv
```

**Phone:**
- Screenshot battery level (Settings → Battery)
- Note starting percentage: ___%
- Note starting time: _______

#### 3.2 Monitor Streaming

**Coordinator Dashboard:**
- Open `https://[coordinator-ip]:8444/coordinator`
- Login with dashboard code
- Verify member appears
- Check observation count increasing

**What to watch for:**
- [ ] Member shows "Connected"
- [ ] Observations count increases
- [ ] No error messages in hub logs
- [ ] Phone remains responsive

#### 3.3 Record Battery Drain

After 10 minutes:
- Check phone battery level again
- Calculate drain rate: (start% - end%) × 6 = %/hour

Example:
- Started: 80%
- After 10 min: 77%
- Drain: 3% in 10 min = 18%/hour

---

### Phase 4: Multi-Device Test (Optional, 15 minutes)

If you have access to more phones:

#### 4.1 Scale to 2-3 Devices

Repeat Phase 2 for each additional phone:
- Phone 2: Name "Phone-02"
- Phone 3: Name "Phone-03"

#### 4.2 Monitor Load

On coordinator:
```bash
# Check hub status
osk status

# Look for:
# - CPU usage (should be <50%)
# - Memory usage
# - All members connected
```

#### 4.3 Document Results

| Device | Battery Start | Battery End | Drain/Hour | Status |
|--------|---------------|-------------|------------|--------|
| Phone-01 | 80% | 77% | 18%/hr | ✅ Connected |
| Phone-02 | 75% | 71% | 24%/hr | ✅ Connected |
| ... | ... | ... | ... | ... |

---

### Phase 5: Cleanup

```bash
# On coordinator - stop hub
osk stop

# Generate evidence export
osk evidence export --output real-device-validation.zip

# Verify export
osk evidence verify --input real-device-validation.zip
```

On phones:
- Close Chrome tabs
- Disconnect from WiFi (optional)

---

## Troubleshooting

### Can't Connect to Hub

**Symptom:** Phone can't load join page

**Solutions:**
1. Check phone and laptop on same WiFi
2. Disable "AP isolation" on router/hotspot
3. Try using laptop's hotspot:
   ```bash
   osk hotspot up
   # Connect phone to Osk hotspot
   ```
4. Check firewall:
   ```bash
   sudo firewall-cmd --list-ports
   # Should show 8444/tcp
   ```

### SSL Certificate Warning

**Symptom:** Chrome blocks page as "not private"

**Solution:**
- This is expected with self-signed certs
- Tap "Advanced" → "Proceed anyway"
- For permanent fix, see SAFETY.md

### Camera/Mic Not Working

**Symptom:** No audio/video stream

**Solutions:**
1. Check permissions in Chrome:
   - Chrome menu → Settings → Site Settings
   - Check Camera and Microphone permissions
2. Refresh the page
3. Try joining again

### High Battery Drain

**Symptom:** Battery drops >30%/hour

**Causes:**
- Screen brightness high
- Video streaming at high resolution
- Weak WiFi signal (phone boosts radio power)

**Mitigation:**
- Lower screen brightness
- Stay close to WiFi router
- Use power saving mode

---

## Data Collection Template

```markdown
# Real Device Validation Report

**Date:** YYYY-MM-DD
**Coordinator:** [Hardware/OS]
**Network:** [WiFi Router / Hotspot]

## Test Configuration

- Osk version: [output of `osk version`]
- Hub backend: [heuristic/ollama]
- Test duration: [X minutes]

## Device 1: [Phone Model]

- Android version: [e.g., 13]
- Chrome version: [e.g., 120]
- Battery start: [XX%]
- Battery end: [XX%]
- Drain rate: [XX%/hour]

### Results
- [ ] Joined successfully
- [ ] Permissions granted
- [ ] Streamed audio/video
- [ ] Remained connected
- [ ] Observations generated

### Issues
[None / describe any]

## Device 2: [Phone Model]
[Same format]

## Hub Performance

- CPU usage: [X%]
- Memory usage: [X MB]
- Observations generated: [X total]

## Conclusions

[Pass/Fail and notes]

## Artifacts

- [ ] Initial status: `real-device-test-initial.json`
- [ ] Hub metrics: `hub-metrics.csv`
- [ ] Evidence export: `real-device-validation.zip`
```

---

## Comparison: Real Device vs Container

| Aspect | Container | Real Device | Notes |
|--------|-----------|-------------|-------|
| Setup | Fast (<1 min) | Slower (5 min) | Phone needs WiFi, permissions |
| Battery drain | N/A | 15-25%/hour | Key real-device metric |
| Thermal | N/A | Warm to touch | Real devices heat up |
| WebRTC | Simulated | Real | May differ |
| Network switching | N/A | Real behavior | WiFi ↔ mobile handoff |
| Hub CPU | Same | Same | Validates pipeline |
| Reliability | Very high | Variable | Real world conditions |

---

## Next Steps After Testing

1. **Fill out report template** above
2. **Add to validation index:** `docs/release/VALIDATION-INDEX.md`
3. **Compare to container results:** Note differences
4. **Update 1.1.0 docs:** Remove "real-device pending" limitation
5. **Submit evidence:** Include in release notes

---

## Quick Reference Card

```
┌─────────────────────────────────────────────┐
│  REAL DEVICE TEST - 30 SECOND VERSION       │
├─────────────────────────────────────────┬───┤
│ 1. osk start --fresh "Test"             │   │
│ 2. osk dashboard → note URL + code      │   │
│ 3. Phone: Connect to WiFi               │   │
│ 4. Phone: Chrome → URL/join             │   │
│ 5. Phone: Enter code → Select Sensor    │   │
│ 6. Phone: Grant permissions             │   │
│ 7. Coordinator: Check dashboard         │   │
│ 8. Wait 10 min, note battery            │   │
│ 9. osk stop                             │   │
└─────────────────────────────────────────┴───┘
```

---

## Sign-off

| Device | Model | Android | Chrome | Result | Tester |
|--------|-------|---------|--------|--------|--------|
| Phone-01 | | | | | |
| Phone-02 | | | | | |
| Phone-03 | | | | | |

---

## Related Documents

- [Container Validation](./2026-03-28-sensor-validation-container-report.md)
- [Chromebook Lab Smoke](./chromebook-lab-smoke.md)
- [Validation Index](../release/VALIDATION-INDEX.md)
