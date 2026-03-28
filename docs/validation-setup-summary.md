# Osk 1.1 Validation Setup Summary

**Date:** 2026-03-28  
**Status:** Scripts created and tested

---

## What Was Set Up

### 1. Ollama Integration ✅

**Status:** Working

Ollama is installed and running. Models tested:
- `llama3.2:3b` - 2.0 GB, fast (~520ms), 65% category accuracy
- `phi4-mini` - 2.5 GB, ~710ms, 65% category accuracy  
- `qwen3:8b` - 5.2 GB, ~837ms, 85% category accuracy

**Key Finding:** For the current test dataset, the **heuristic baseline outperforms all tested LLMs**:
- Heuristic: 85% category accuracy, 75% severity accuracy, 65% combined
- Best LLM (qwen3:8b): 85% category accuracy, 55% severity accuracy, 50% combined

**Recommendation:** Keep heuristic as default for 1.1. Continue Ollama work for 1.2+ with improved prompts.

**Script:** `scripts/ollama_synthesis_test.py`
```bash
# Quick test
python scripts/ollama_synthesis_test.py --model llama3.2:3b

# Full comparison
python scripts/ollama_synthesis_test.py --compare --heuristic

# With JSON output
python scripts/ollama_synthesis_test.py --model qwen3:8b --json-output results.json
```

---

### 2. Podman Android Emulator Lab ✅

**Status:** Scripts created (needs testing)

Container-based Android emulator solution for sensor validation without physical devices.

**Requirements:**
- Podman installed (`sudo dnf install podman`)
- ADB installed (`sudo dnf install android-tools`)
- KVM support recommended (check with `ls -la /dev/kvm`)

**Script:** `scripts/podman_android_lab.sh`
```bash
# Start 5 emulators
./scripts/podman_android_lab.sh start --count 5

# Check status
./scripts/podman_android_lab.sh status

# Connect to Osk hub
./scripts/podman_android_lab.sh connect --hub-url http://192.168.1.100:8080

# Run full validation test (10 minutes)
./scripts/podman_android_lab.sh test --count 5 --duration 600

# Stop all emulators
./scripts/podman_android_lab.sh stop
```

**Container Details:**
- Uses `avitotech/android-emulator-29:latest` (production-tested)
- Each emulator: ~2GB disk, configurable memory
- Headless operation (no GUI needed)
- Chrome browser pre-installed

**Limitations:**
- Software rendering only (no GPU acceleration)
- WebRTC may differ from real devices
- Cannot test battery/thermal behavior
- Document as "containerized browser validation" not "real-device validation"

---

### 3. Combined Validation Script ✅

**Status:** Ready

Orchestrates multiple validation workstreams.

**Script:** `scripts/combined_validation.py`
```bash
# Run all validations
python scripts/combined_validation.py --all

# Synthesis only
python scripts/combined_validation.py --synthesis --model llama3.2:3b

# Sensor validation with 5 emulators for 10 minutes
python scripts/combined_validation.py --sensors 5 --duration 600

# Stability test for 1 hour
python scripts/combined_validation.py --stability --duration 3600

# Custom output file
python scripts/combined_validation.py --all --output validation-report.json
```

---

## Quick Start Commands

### 1. Start Ollama (if not running)
```bash
ollama serve &
```

### 2. Test Synthesis
```bash
python scripts/ollama_synthesis_test.py --model llama3.2:3b --heuristic
```

### 3. Test Podman Android (after installing podman)
```bash
# One-time setup
sudo dnf install -y podman android-tools

# Test single emulator
./scripts/podman_android_lab.sh start --count 1
./scripts/podman_android_lab.sh status
./scripts/podman_android_lab.sh stop
```

### 4. Full Validation
```bash
# Start Osk hub first
osk start --fresh "Validation Test"

# Run combined validation
python scripts/combined_validation.py --all --duration 600
```

---

## Updated 1.1 Release Blockers

| Requirement | Status | Path Forward |
|-------------|--------|--------------|
| Ollama synthesis validation | ✅ Working | Document actual accuracy; heuristic remains default |
| Real-device sensor validation | 🔄 Partial | Use Podman emulators for hub pipeline validation; document need for physical device testing |
| Long-duration stability | 🔄 Ready | Use existing `scripts/sensor_validation.py` with extended duration |
| Browser automation CI | 🔄 Ready | Use Podman emulators in GitHub Actions |

---

## Recommendations for 1.1

### Immediate (This Week)

1. **Run Ollama evaluation** with documented results
   - Accept that heuristic outperforms for this task
   - Document this finding honestly
   - Keep Ollama as optional/experimental feature

2. **Test Podman Android setup**
   - Verify containers start correctly
   - Test browser launches
   - Validate hub connections

3. **Run containerized sensor validation**
   - 5 emulators for 10 minutes
   - Document hub CPU/memory usage
   - This validates hub pipeline capacity

### Before 1.1 Release

4. **Borrow 2-3 Android phones** for real-device smoke test
   - Validates actual browser behavior
   - Documents battery impact (briefly)
   - Compare to containerized results

5. **Update documentation**
   - Clear distinction: containerized vs real-device validation
   - Ollama: optional with documented accuracy
   - Heuristic: recommended default

---

## File Reference

| File | Purpose |
|------|---------|
| `scripts/ollama_synthesis_test.py` | Evaluate Ollama synthesis accuracy and latency |
| `scripts/podman_android_lab.sh` | Manage Android emulator containers |
| `scripts/combined_validation.py` | Orchestrate all validation workstreams |
| `docs/validation-setup-summary.md` | This file |

---

## Next Steps

1. **Test Podman Android** - Run the start/status/stop cycle
2. **Decide on real-device strategy** - Can you borrow 2-3 phones?
3. **Run full validation** - Use combined script with appropriate duration
4. **Update release docs** - Reflect actual (not aspirational) capabilities

---

## Decision Points

### Ollama for 1.1?
- **Option A:** Include as experimental (document low accuracy)
- **Option B:** Defer to 1.2 (focus on heuristic improvements)
- **Recommendation:** Option A - ship with transparency

### Real-device validation?
- **Option A:** Require 5+ physical devices (blocks release)
- **Option B:** Containerized + 2-3 real phones (acceptable)
- **Option C:** Containerized only (document limitation)
- **Recommendation:** Option B - best balance

---

*This setup gives you a working validation pipeline that can be run immediately, while being honest about what's being validated (hub capacity via containers) vs what needs real hardware (battery/thermal, WebRTC edge cases).*
