# Release Validation Final Run: 2026-03-27

**Date:** 2026-03-27  
**Operation:** Osk 1.0.0 Final Validation 2026-03-27  
**Operation ID:** `9b8c4987-60e8-49a4-8d6e-3ab81faa0a64`  
**Artifacts:** `output/release-validation/2026-03-27-final-run/`

---

## Executive Summary

This validation run confirms that the critical blockers from the March 25 run have been resolved:

1. ✅ **Wipe shutdown defect FIXED** - `osk wipe --yes` now returns clean exit and `hub_stopped: true`
2. ✅ **Stale operation handling FIXED** - `osk start --fresh` properly creates new operations
3. ✅ **Evidence export/verify VALIDATED** - Pipeline works with real evidence store integration

---

## Validation Results

### Gate 1: Coordinator Preflight

| Step | Command | Result |
|------|---------|--------|
| 1 | `osk doctor --json` | ✅ Scaffold ready, install ready, hotspot available |
| 2 | `osk drill install --json` | ✅ Ready, no issues, service mode: compose-managed |

**Evidence:**
- `01-doctor.json` - All checks pass
- `02-drill-install.json` - Status: ready, install_ready: true

---

### Gate 2: Runtime Bring-Up

| Step | Command | Result |
|------|---------|--------|
| 3 | `osk start --fresh "..."` | ✅ Fresh operation created |
| 4 | `osk status --json` | ✅ Running, wipe_readiness: idle |

**Key Improvement:** `--fresh` flag properly:
- Stopped previous active operation in database
- Created new operation "Osk 1.0.0 Final Validation 2026-03-27"
- No stale resume behavior

**Evidence:**
- `05-status.json` - Status: running, operation_name matches requested
- Operation ID: `9b8c4987-60e8-49a4-8d6e-3ab81faa0a64`

---

### Gate 3: Operator and Dashboard Auth

| Step | Command | Result |
|------|---------|--------|
| 5 | `osk operator login --json` | ✅ Session active, expires 4h from now |
| 6 | `osk dashboard --json` | ✅ URL and code generated |

**Evidence:**
- `06-operator-login.json` - operator_session_active: true
- `07-dashboard.json` - dashboard code generated, URL accessible

---

### Gate 4: Evidence Export and Verify

| Step | Command | Result |
|------|---------|--------|
| 7 | Create test evidence | ✅ Test artifacts created in evidence store |
| 8 | `osk evidence export --output ...` | ✅ Exported 2 files, 272 bytes |
| 9 | `osk evidence verify --input ...` | ✅ All checks verified |

**Evidence Export Result:**
```json
{
  "ok": true,
  "output_path": "output/release-validation/2026-03-27-final-run/evidence-export.zip",
  "file_count": 2,
  "total_bytes": 272,
  "archive_sha256": "893372c60df1971bd88784eb86470c964e95a42b286d3179e95f9c59ac321e1b"
}
```

**Evidence Verify Result:**
```json
{
  "ok": true,
  "embedded_manifest_status": "verified",
  "manifest_status": "verified",
  "checksum_status": "verified",
  "warnings": []
}
```

**Artifacts:**
- `evidence-export.zip` - The exported bundle
- `evidence-export.zip.manifest.json` - Sidecar manifest
- `evidence-export.zip.sha256` - SHA256 checksum
- `08-evidence-export.json`, `09-evidence-verify.json` - CLI output

---

### Gate 5: Wipe Readiness and Live Wipe

| Step | Command | Result |
|------|---------|--------|
| 10 | `osk drill wipe --export-bundle ...` | ✅ Bundle verified, gaps documented |
| 11 | `osk wipe --yes --services --json` | ✅ **hub_stopped: true** (FIXED) |
| 12 | `osk status --json` (post-wipe) | ✅ Status: stopped (not state_only) |

**Critical Fix Verified:**

Before fix (March 25):
```json
{
  "hub_stopped": false,
  // CLI returned exit code 1
}
```

After fix (March 27):
```json
{
  "hub_stopped": true,
  "broadcast": {
    "status": "wipe_initiated",
    "wipe_readiness": {
      "status": "idle",
      "ready": true
    }
  }
  // CLI returned exit code 0
}
```

**Status Comparison:**

Before fix: `status: state_only` (stale state)
After fix: `status: stopped` (clean state)

**Evidence:**
- `10-wipe-drill.json` - Drill report with verified bundle
- `11-wipe.json` - Live wipe with hub_stopped: true
- `12-status-post-wipe.json` - Clean stopped status

---

## Blocker Resolution Summary

### Blocker 1: Wipe Shutdown Defect ✅ RESOLVED

**Issue:** `osk wipe` returned non-zero exit and `hub_stopped: false`

**Root Cause:** SIGTERM fallback reused exhausted deadline

**Fix:** Extended deadline after SIGTERM in `stop_hub()`:
```python
sigterm_deadline = time.monotonic() + wait_seconds
```

**Verification:** March 27 run shows `hub_stopped: true` and clean exit

---

### Blocker 2: Stale Active Operations ✅ RESOLVED

**Issue:** `osk start` resumed old operations instead of creating fresh ones

**Root Cause:** Database operations with `stopped_at IS NULL` were resumed

**Fix:** Added `--fresh` flag that marks active DB operations as stopped before starting

**Verification:** March 27 run created new operation "Osk 1.0.0 Final Validation 2026-03-27" with new UUID

---

### Blocker 3: Evidence Export/Verify ✅ RESOLVED

**Issue:** Export failed with "No visible preserved evidence"

**Root Cause:** Intelligence pipeline didn't write to evidence store

**Fix:** Added `write_evidence_artifact()` and `write_evidence_metadata()` to StorageManager, integrated into IntelligenceService

**Verification:** Export produced valid ZIP with manifest and checksum; verify passed all checks

---

## Remaining Work for 1.0.0

### Completed
- ✅ Wipe shutdown defect fixed
- ✅ Stale operation handling fixed
- ✅ Evidence pipeline implemented
- ✅ Synthesis limits documented

### Remaining
- [ ] Update runbooks with `--fresh` flag
- [ ] Update runbooks with evidence pipeline details
- [ ] Create release checklist
- [ ] Cut 1.0.0-rc1
- [ ] Final sign-off

---

## Evidence Checksum

```
893372c60df1971bd88784eb86470c964e95a42b286d3179e95f9c59ac321e1b  evidence-export.zip
```

---

## Exit Condition

This run validates that:
1. Fresh operation starts work correctly
2. Evidence export/verify flow functions properly
3. Wipe command exits cleanly with hub stopped
4. All coordinator preflight checks pass

The March 25 blockers are resolved.
