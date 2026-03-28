# Osk 1.0.0 Operator Quickstart Card

**One-page reference for field deployment**

---

## Pre-Flight (5 minutes)

```bash
# Verify installation
osk doctor --json | jq '.checks[] | select(.ok==false)'

# Should return empty - if not, fix issues before proceeding

# Check version
osk --version  # Should show 1.0.0
```

**Hardware Check:**
- [ ] Linux laptop charged/plugged in
- [ ] 4GB+ RAM available
- [ ] 10GB+ disk free
- [ ] WiFi working (or Ethernet)

---

## Operation Startup (2 minutes)

```bash
# Start fresh operation
osk start --fresh "Operation Name"

# Get status
osk status --json | jq '.running, .operation_name'

# Get dashboard URL for coordinator
osk dashboard
```

**Save these:**
- Operation token: _______________
- Join URL: _______________
- Dashboard URL: _______________

---

## Member Join (30 seconds each)

1. Member opens Chrome on phone/laptop
2. Navigate to join URL
3. Enter name, select role
4. Grant camera/mic permissions (for sensors)

**Verify in dashboard:** Member appears as connected

---

## Runtime Monitoring

```bash
# Quick status
osk status

# Detailed status
osk status --json | jq '.members, .findings, .alerts'

# View logs
osk logs --tail 50

# Check audit trail
osk audit --last 10
```

**Watch for:**
- Members disconnecting unexpectedly
- High CPU/memory usage
- Queue overflow warnings

---

## Evidence Export (1 minute)

```bash
# During operation - create checkpoint
osk evidence export --output checkpoint-$(date +%Y%m%d-%H%M).zip

# Verify export
osk evidence verify checkpoint-XXXX.zip
```

**Store securely:** Export contains raw audio/video

---

## Wipe & Shutdown (2 minutes)

```bash
# Check wipe readiness
osk drill wipe

# If ready, execute wipe
osk wipe --yes

# Verify stopped
osk status  # Should show "No operation running"

# Final evidence export (if needed)
osk evidence export --output final-evidence.zip
```

**Post-wipe:** Follow up with disconnected members manually

---

## Emergency Procedures

### Hub Unresponsive
```bash
# Force stop
osk stop --force

# Check for zombie processes
ps aux | grep osk

# Kill if needed
kill -9 <pid>
```

### Evidence Store Full
```bash
# Check usage
osk evidence list | wc -l

# Export and verify
osk evidence export --output emergency-export.zip
osk evidence verify emergency-export.zip

# Destroy if exported successfully
osk evidence destroy
```

### Network Issues
```bash
# Check hotspot status
osk hotspot status

# Restart hotspot
osk hotspot down && osk hotspot up

# Get connection instructions for members
osk hotspot instructions
```

---

## Validation Checklist

### Before Field Use
- [ ] `osk doctor` passes all checks
- [ ] Synthetic validation passes:
  ```bash
  python scripts/sensor_validation.py --sensors 5 --duration 60
  ```
- [ ] Test join from your device
- [ ] Test evidence export
- [ ] Test wipe drill

### During Operation (every 30 min)
- [ ] Check dashboard shows all members
- [ ] Verify observations flowing
- [ ] Monitor CPU (<50% for 5 sensors)
- [ ] Export checkpoint evidence

### After Operation
- [ ] Final evidence export
- [ ] Wipe executed
- [ ] Evidence archive secured
- [ ] Follow-up with disconnected members

---

## Configuration Quick Reference

```toml
# ~/.config/osk/config.toml

# Sensors (synthetically validated at 5)
max_sensors = 10

# Synthesis (heuristic is default, Ollama optional)
synthesis_backend = "heuristic"

# Evidence
storage_backend = "luks"  # or "directory"
luks_volume_size_gb = 1

# Performance
transcriber_backend = "fake"  # or "whisper"
vision_backend = "fake"       # or "ollama"
```

---

## Known Limitations (1.0.0)

1. **Sensor streaming:** Validated synthetically. Real-device battery/WebRTC pending.
2. **Semantic synthesis:** Code validated. Ollama accuracy pending; heuristic works.
3. **Browsers:** Chromium-class only. Firefox/Safari not supported.
4. **Offline:** PWA works for previously loaded pages only.

---

## Support

- **Issues:** https://github.com/justinredmondsmith-collab/osk/issues
- **Documentation:** `docs/` directory
- **Validation reports:** `docs/release/`

---

**Print this card and keep with coordinator laptop.**
