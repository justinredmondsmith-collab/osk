# Osk 2.0.0 Operator Quickstart Card

**One-page reference for field deployment**

---

## Pre-Flight (5 minutes)

```bash
# 1. Verify installation and profile
osk doctor --json | jq '.profile, .overall_ready'

# Expected output:
# "supported-full"
# true

# If unsupported, fix issues before proceeding

# 2. Check version
osk --version  # Should show 2.0.0
```

**Hardware Check:**
- [ ] Linux laptop charged/plugged in
- [ ] 4GB+ RAM available (8GB recommended)
- [ ] 10GB+ disk free
- [ ] WiFi working (or Ethernet)
- [ ] `osk doctor` shows "supported-full" or "supported-minimal"

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
osk aar export --output checkpoint-$(date +%Y%m%d-%H%M).zip

# Verify export
osk aar verify checkpoint-XXXX.zip
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

# Final AAR export (if not already done)
osk aar export --output final-aar.zip
osk aar verify final-aar.zip
```

**Post-wipe:** Follow up with disconnected members manually

---

## After-Action Review (Post-Operation)

```bash
# Generate operation summary
osk aar generate

# View summary
osk aar generate --format json | jq '.'

# Export complete bundle
osk aar export --output operation-aar-$(date +%Y%m%d).zip

# Verify integrity
osk aar verify operation-aar-XXXX.zip
```

**AAR Contents:**
- Operation summary (duration, members, findings)
- Timeline events (chronological)
- Evidence manifest (SHA-256 verified)
- Media files (audio, frames, metadata)
- Closure checklist

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
osk aar list | wc -l

# Export and verify
osk aar export --output emergency-export.zip
osk aar verify emergency-export.zip

# Destroy if exported successfully
osk aar destroy
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
- [ ] Profile is "supported-full" or "supported-minimal"
- [ ] Synthetic validation passes:
  ```bash
  python scripts/sensor_validation.py --sensors 5 --duration 60
  ```
- [ ] Test join from your device
- [ ] Test AAR export and verify
- [ ] Test wipe drill

### During Operation (every 30 min)
- [ ] Check dashboard shows all members
- [ ] Verify observations flowing
- [ ] Monitor CPU (<50% for 5 sensors)
- [ ] Export checkpoint evidence

### After Operation
- [ ] Final AAR export
- [ ] AAR verify passes
- [ ] Wipe executed
- [ ] Evidence archive secured
- [ ] Follow-up with disconnected members

---

## Configuration Quick Reference

```toml
# ~/.config/osk/config.toml

# Sensors (validated at 5 synthetically)
max_sensors = 10

# Synthesis (heuristic is default, Ollama optional)
synthesis_backend = "heuristic"

# Evidence
storage_backend = "luks"  # or "directory"
luks_volume_size_gb = 1

# Security (2.0.0 defaults)
[security]
operator_session_hours = 4
member_session_hours = 2
token_rotation_minutes = 30
max_concurrent_sessions = 5

# AAR (2.0.0)
[aar]
auto_export_on_close = false
evidence_retention_days = 90
include_media = true

# Performance
transcriber_backend = "fake"  # or "whisper"
vision_backend = "fake"       # or "ollama"
```

---

## Known Limitations (2.0.0)

1. **Sensor streaming:** Validated synthetically. Real-device battery/WebRTC pending.
2. **Semantic synthesis:** Code validated. Ollama accuracy pending; heuristic works.
3. **Browsers:** Chromium-class only. Firefox/Safari not supported.
4. **Offline:** PWA works for previously loaded pages only.
5. **Federation:** Single-hub only. Multi-hub is 3.x consideration.

---

## New in 2.0.0

| Feature | Command | Purpose |
|---------|---------|---------|
| Install Readiness | `osk doctor` | Validate environment before deploy |
| AAR Generate | `osk aar generate` | Operation summary |
| AAR Export | `osk aar export` | Complete evidence bundle |
| AAR Verify | `osk aar verify` | Integrity verification |
| Security Hardening | Automatic | Token rotation, session limits |

---

## Support

- **Issues:** https://github.com/justinredmondsmith-collab/osk/issues
- **Documentation:** `docs/` directory
- **Validation reports:** `docs/release/`
- **Install profiles:** `docs/SUPPORTED_PROFILES.md`

---

**Print this card and keep with coordinator laptop.**

**Version:** 2.0.0  
**Last Updated:** 2026-03-28
