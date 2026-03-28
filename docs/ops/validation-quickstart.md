# Validation Quickstart Guide

**Quick commands to validate Osk 1.1 capabilities**

---

## 5-Minute Validation

### Test Ollama Synthesis
```bash
# Start Ollama (if not running)
ollama serve &

# Run evaluation
python scripts/ollama_synthesis_test.py --model llama3.2:3b

# Check results - look for:
# - Category accuracy target: >80%
# - Latency target: <3000ms average
```

### Test Podman Android Setup
```bash
# Prerequisites
sudo dnf install -y podman android-tools

# Start one emulator
./scripts/podman_android_lab.sh start --count 1

# Check it's running
./scripts/podman_android_lab.sh status

# Stop it
./scripts/podman_android_lab.sh stop
```

---

## 30-Minute Validation

### Full Synthesis Comparison
```bash
python scripts/ollama_synthesis_test.py --compare --heuristic --json-output synthesis-results.json
```

### Containerized Sensor Test (5 devices, 10 min)
```bash
# Start Osk hub
osk start --fresh "Sensor Validation"

# Get your IP
IP=$(hostname -I | awk '{print $1}')
echo "Hub URL: http://${IP}:8080"

# Start test
./scripts/podman_android_lab.sh test --count 5 --duration 600 --hub-url "http://${IP}:8080"

# Results saved to output/podman-validation/
```

---

## Full 1.1 Validation Suite

```bash
# Run everything (takes ~30 minutes)
python scripts/combined_validation.py --all --duration 1800

# Or run individually
python scripts/ollama_synthesis_test.py --heuristic
./scripts/podman_android_lab.sh test --count 5 --duration 600
python scripts/stability_test.py --duration-hours 1 --sensors 5
```

---

## Troubleshooting

### Ollama Connection Failed
```bash
# Check if running
curl http://localhost:11434/api/tags

# Start it
ollama serve &

# Pull model if needed
ollama pull llama3.2:3b
```

### Podman Permission Denied
```bash
# Add user to podman group
sudo usermod -aG podman $USER
# Log out and back in
```

### ADB Not Found
```bash
sudo dnf install android-tools
# or
sudo apt install adb
```

### KVM Not Available
```bash
# Check CPU support
egrep -c '(vmx|svm)' /proc/cpuinfo

# Enable in BIOS if 0
# Emulators will still work but be slower
```

---

## What Each Test Validates

| Test | Validates | Does NOT Validate |
|------|-----------|-------------------|
| Ollama synthesis | Semantic classification accuracy | Real-world observation patterns |
| Podman Android (5) | Hub pipeline capacity | Battery drain, thermal throttling |
| Podman Android (10) | Hub scalability | Real-device WebRTC behavior |
| Stability (1hr) | Memory leaks, queue growth | Week-long deployment issues |

---

## Expected Results

### Synthesis (llama3.2:3b)
- **Typical accuracy:** 60-70% category, 50-60% severity
- **Heuristic baseline:** 85% category, 75% severity
- **Conclusion:** Heuristic remains default for 1.1

### Podman Android (5 devices)
- **Hub CPU:** <50% (synthetic validation)
- **Hub Memory:** <1GB
- **Latency:** <5s observation generation

### Stability (1 hour)
- **Memory growth:** <100MB/hour
- **Observations:** Continuous flow
- **No crashes:** Required

---

## Documentation Checklist

After running validation, update:

- [ ] `docs/release/2026-03-XX-synthesis-evaluation-report.md`
- [ ] `docs/release/2026-03-XX-sensor-validation-real-report.md`
- [ ] `docs/release/2026-03-XX-stability-report.md`
- [ ] `docs/release/VALIDATION-INDEX.md`

---

*For detailed procedures, see the full runbooks in `docs/runbooks/`*
