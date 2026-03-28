# Chromebook Sensor Validation Procedure

**Purpose:** Validate sensor streaming with real browsers/devices  
**Target:** 5-10 concurrent sensor streams  
**Duration:** ~30 minutes

---

## Prerequisites

### Hardware
- Linux coordinator laptop with Osk installed
- 5-10 Chromebooks or Android phones with Chrome
- Local WiFi network (hotspot or existing)
- Optional: USB cables for device charging

### Software
- Osk hub running on coordinator
- Chrome browsers on all member devices
- `psutil` installed on coordinator: `pip install psutil`

---

## Setup

### 1. Start Coordinator Hub

```bash
# On coordinator laptop
osk start --fresh "Sensor Validation Test"
osk status --json  # Verify running
osk dashboard       # Get dashboard URL
```

Note the operation token and join URL.

### 2. Configure Coordinator for Sensor Testing

```bash
# Enable fake intelligence for faster processing (optional, for load testing)
osk config --set transcriber_backend=fake
osk config --set vision_backend=fake

# Or use real backends for end-to-end validation
osk config --set transcriber_backend=whisper
osk config --set vision_backend=ollama
```

### 3. Set Up Monitoring

```bash
# Terminal 1: Monitor hub resources
python3 << 'EOF'
import psutil, time, json
process = psutil.Process()
print("time,cpu_percent,memory_mb")
while True:
    cpu = process.cpu_percent()
    mem = process.memory_info().rss / (1024 * 1024)
    print(f"{time.time():.0f},{cpu:.1f},{mem:.1f}")
    time.sleep(1)
EOF
```

```bash
# Terminal 2: Monitor hub logs
tail -f ~/.local/state/osk/hub.log
```

---

## Test Procedure

### Phase 1: Single Sensor (Baseline)

**Duration:** 5 minutes  
**Devices:** 1 Chromebook

1. **Join as sensor:**
   - Open Chrome on Chromebook
   - Navigate to join URL
   - Enter name: "Sensor-01"
   - Select role: **Sensor**
   - Grant camera and microphone permissions

2. **Verify streaming:**
   - Check dashboard shows "Sensor-01" as connected
   - Verify audio indicator shows activity
   - Verify frame indicator shows activity
   - Check observations are being generated

3. **Record metrics:**
   - CPU usage on coordinator
   - Memory usage on coordinator
   - Battery drain on Chromebook (settings → battery)

### Phase 2: 5 Sensors

**Duration:** 10 minutes  
**Devices:** 5 Chromebooks

1. **Join 4 additional sensors:**
   - Repeat Phase 1 steps for "Sensor-02" through "Sensor-05"
   - Stagger joins by 30 seconds

2. **Monitor for issues:**
   - Watch for dropped connections
   - Check for audio queue warnings in logs
   - Verify all 5 sensors show "connected" in dashboard

3. **Record metrics at 5-minute mark:**
   ```bash
   # On coordinator
   osk status --json > validation-5sensors.json
   ```

### Phase 3: 10 Sensors (if available)

**Duration:** 10 minutes  
**Devices:** 10 Chromebooks (or mix of Chromebooks + phones)

1. **Join 5 additional sensors:**
   - "Sensor-06" through "Sensor-10"
   - Use phones if needed (Chrome browser)

2. **Watch for degradation:**
   - Increased latency in observations
   - Queue pressure warnings
   - Frame drops

3. **Record metrics:**
   ```bash
   osk status --json > validation-10sensors.json
   ```

---

## Data Collection

### Required Artifacts

1. **Hub state snapshots:**
   ```bash
   osk status --json > validation-status.json
   osk audit --json > validation-audit.json
   ```

2. **Resource usage log:**
   - CPU and memory samples from monitoring script

3. **Evidence export:**
   ```bash
   osk evidence export --output validation-evidence.zip
   ```

4. **Device metrics:**
   - Battery drain per device (% per hour)
   - Any disconnections/reconnections

---

## Pass Criteria

### Performance Requirements

| Metric | 5 Sensors | 10 Sensors |
|--------|-----------|------------|
| Hub CPU | <50% | <80% |
| Hub Memory | <1 GB | <2 GB |
| Observation latency | <5s | <10s |
| Disconnects | 0 | <2 |
| Battery drain | <15%/hour | <25%/hour |

### Quality Requirements

- All sensors remain connected for full test duration
- Observations generated for all active sensors
- No queue overflow errors
- Graceful degradation (if 10 sensors fail, 5 must still work)

---

## Troubleshooting

### High CPU Usage

**Symptoms:** Hub CPU >80% with 5 sensors  
**Actions:**
1. Switch to fake intelligence backends
2. Reduce frame sampling rate in config
3. Check for other processes consuming CPU

### Queue Overflow

**Symptoms:** Log warnings about "audio queue full"  
**Actions:**
1. Increase queue size: `osk config --set audio_queue_size=2000`
2. Reduce number of sensors
3. Check hub CPU (may be processing bottleneck)

### Connection Drops

**Symptoms:** Sensors disconnecting and reconnecting  
**Actions:**
1. Check WiFi signal strength
2. Reduce sensor stream rates
3. Check for IP address conflicts

---

## Validation Report Template

```markdown
# Sensor Validation Report

**Date:** YYYY-MM-DD  
**Coordinator:** [Hardware specs]  
**Network:** [WiFi/hotspot details]

## Test Configuration

- Transcriber backend: [whisper/fake]
- Vision backend: [ollama/fake]
- Test duration: [X minutes]

## Results

### 1 Sensor (Baseline)
- CPU: [X]%
- Memory: [X] MB
- Battery drain: [X]%/hour
- Status: [PASS/FAIL]

### 5 Sensors
- CPU: [X]%
- Memory: [X] MB
- Battery drain (avg): [X]%/hour
- Observations: [X] total
- Status: [PASS/FAIL]

### 10 Sensors
- CPU: [X]%
- Memory: [X] MB
- Observations: [X] total
- Disconnections: [X]
- Status: [PASS/FAIL]

## Conclusions

[Whether 1.0.0 sensor requirements are met]

## Artifacts

- [validation-status.json]
- [validation-evidence.zip]
- [resource-usage.csv]
```

---

## Automation Script

For automated validation, use:

```bash
# Automated synthetic validation (no real devices)
python scripts/sensor_validation.py --sensors 5 --duration 60 --output report-5sensors.json

# Check pass/fail
if [ $? -eq 0 ]; then
    echo "PASS: 5 sensor validation"
else
    echo "FAIL: 5 sensor validation"
fi
```

---

## Sign-off

| Role | Name | Date | Result |
|------|------|------|--------|
| Test Lead | | | |
| Coordinator Operator | | | |
| Device Manager | | | |
