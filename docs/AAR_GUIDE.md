# After-Action Review (AAR) Guide

**Version:** 2.0.0  
**Date:** 2026-03-28  

---

## What is AAR?

The After-Action Review system helps coordinators:

1. **Summarize** what happened during an operation
2. **Export** complete evidence with integrity verification
3. **Review** timeline and key events
4. **Track** unresolved items and closure state
5. **Learn** from operational experience

---

## AAR Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│                    AAR WORKFLOW                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   Operation Running        Operation Ends                      │
│        │                        │                              │
│        ▼                        ▼                              │
│   ┌──────────┐            ┌──────────┐                        │
│   │ Checkpoint│            │ Generate │                        │
│   │  Exports  │            │ Summary  │                        │
│   │ (Optional)│            │          │                        │
│   └──────────┘            └────┬─────┘                        │
│                                 │                              │
│                                 ▼                              │
│                          ┌──────────┐                        │
│                          │  Export  │                        │
│                          │   AAR    │                        │
│                          └────┬─────┘                        │
│                                 │                              │
│                                 ▼                              │
│                          ┌──────────┐                        │
│                          │  Verify  │                        │
│                          │ Integrity│                        │
│                          └────┬─────┘                        │
│                                 │                              │
│                                 ▼                              │
│                          ┌──────────┐                        │
│                          │  Archive │                        │
│                          │  Securely│                        │
│                          └──────────┘                        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Commands

### Generate Operation Summary

```bash
osk aar generate

# Output:
# Operation Summary: March on Washington
# ======================================
# Duration: 4h 23m
# Members: 12 joined, 8 active at close
# Findings: 47 total (3 critical, 12 warning, 32 info)
# Tasks: 15 assigned, 12 completed, 3 pending
# Media: 1.2 GB evidence collected
```

### Export Complete AAR

```bash
osk aar export --output march-2026-aar.zip

# Creates ZIP with:
# ├── manifest.json          # SHA-256 integrity manifest
# ├── operation-summary.json # Key metrics
# ├── timeline.jsonl         # Chronological events
# ├── findings/              # Synthesized findings
# ├── media/                 # Audio, video, frames
# │   ├── audio/
# │   ├── frames/
# │   └── metadata/
# └── closure-checklist.json # Pending items
```

### Verify Integrity

```bash
osk aar verify march-2026-aar.zip

# Output:
# ✅ Manifest signature valid
# ✅ All 1,247 files accounted for
# ✅ SHA-256 checksums verified
# ✅ Chain of custody intact
# ✅ No tampering detected
```

---

## AAR Export Contents

### manifest.json

```json
{
  "version": "2.0.0",
  "export_date": "2026-03-28T14:30:00Z",
  "operation_id": "uuid-here",
  "operation_name": "March on Washington",
  "integrity": {
    "algorithm": "sha256",
    "entries": [
      {
        "path": "media/audio/sensor-001-1648473600.wav",
        "hash": "abc123...",
        "size": 1048576
      }
    ]
  },
  "signatures": {
    "manifest_hash": "sha256:xyz789...",
    "exported_by": "coordinator-001"
  }
}
```

### operation-summary.json

```json
{
  "operation_id": "uuid-here",
  "name": "March on Washington",
  "duration_hours": 4.38,
  "members": {
    "total_joined": 12,
    "active_at_close": 8,
    "sensors": 5,
    "observers": 7
  },
  "findings": {
    "total": 47,
    "critical": 3,
    "warning": 12,
    "info": 32
  },
  "tasks": {
    "assigned": 15,
    "completed": 12,
    "pending": 3,
    "timeout": 0
  },
  "media_stats": {
    "audio_chunks": 1247,
    "video_frames": 3682,
    "total_size_bytes": 1283947562
  }
}
```

### timeline.jsonl

```jsonl
{"timestamp": "2026-03-28T10:00:00Z", "type": "operation_start", "data": {"name": "March on Washington"}}
{"timestamp": "2026-03-28T10:05:23Z", "type": "member_join", "data": {"member_id": "uuid", "name": "Alice", "role": "sensor"}}
{"timestamp": "2026-03-28T10:15:00Z", "type": "finding", "data": {"category": "POLICE_PRESENCE", "severity": "info", "confidence": 0.85}}
{"timestamp": "2026-03-28T14:23:00Z", "type": "operation_end", "data": {"duration_hours": 4.38}}
```

### closure-checklist.json

```json
{
  "operation_id": "uuid-here",
  "closed_at": "2026-03-28T14:23:00Z",
  "closed_by": "coordinator-001",
  "items": [
    {
      "category": "evidence_export",
      "status": "complete",
      "description": "All evidence exported and verified"
    },
    {
      "category": "wipe",
      "status": "complete",
      "description": "Wipe executed, 8/10 members confirmed"
    },
    {
      "category": "follow_up",
      "status": "pending",
      "description": "Contact 2 disconnected members: Bob, Carol"
    },
    {
      "category": "tasks",
      "status": "pending",
      "description": "3 tasks incomplete - review for next operation"
    }
  ],
  "residual_risks": [
    "2 members did not confirm wipe",
    "OS/browser artifacts may remain on member devices"
  ]
}
```

---

## Checkpoint Exports (During Operation)

Export evidence while operation is running:

```bash
# Create timestamped checkpoint
osk aar export --output checkpoint-$(date +%Y%m%d-%H%M).zip

# Verify immediately
osk aar verify checkpoint-20260328-1200.zip

# Store securely
mv checkpoint-*.zip /secure/evidence/
```

**When to checkpoint:**
- Every 30 minutes during long operations
- Before high-risk activities
- When members join/leave significantly
- Before coordinator handoffs

---

## Post-Operation Workflow

### Immediate (Within 1 hour)

```bash
# 1. Generate summary
osk aar generate

# 2. Export complete AAR
osk aar export --output operation-aar.zip

# 3. Verify integrity
osk aar verify operation-aar.zip

# 4. Copy to secure storage
cp operation-aar.zip /secure/evidence/
```

### Short-term (Within 24 hours)

```bash
# Review closure checklist
osk aar generate --format json | jq '.closure_checklist'

# Follow up on pending items
# - Contact disconnected members
# - Review incomplete tasks
# - Document lessons learned
```

### Long-term (Archival)

```bash
# Move to long-term storage
mv operation-aar.zip /archive/osk/2026/

# Create hash for long-term verification
sha256sum operation-aar.zip > operation-aar.zip.sha256

# Document in operation log
echo "2026-03-28: March on Washington - AAR archived" >> operation-log.txt
```

---

## Security Considerations

### Evidence Sensitivity

AAR exports contain:
- Raw audio/video from member devices
- Location data
- Operational communications
- Member identities

**Handle with appropriate security:**
- Encrypt at rest
- Limit access to authorized personnel
- Follow organization's data retention policy

### Integrity Verification

Always verify before relying on evidence:

```bash
# Before legal proceedings
osk aar verify evidence.zip

# After storage/transfer
osk aar verify evidence.zip

# Periodically for archived evidence
osk aar verify /archive/2026/evidence.zip
```

### Chain of Custody

The manifest.json includes:
- Export timestamp
- Exporting coordinator identity
- SHA-256 hashes of all files
- Digital signatures

**Maintain chain of custody:**
1. Note who exports the AAR
2. Log all transfers
3. Verify on receipt
4. Document storage location

---

## Integration with External Systems

### Import to Document Management

```bash
# Extract for DMS import
unzip operation-aar.zip -d /tmp/aar-extract/

# Import structured data
curl -X POST https://dms.example.com/api/cases \
  -F "manifest=@/tmp/aar-extract/manifest.json" \
  -F "summary=@/tmp/aar-extract/operation-summary.json"
```

### Analytics

```bash
# Extract timeline for analysis
jq -r '.timestamp, .type' timeline.jsonl | \
  awk '{ts=$1; getline type; print ts, type}' | \
  sort | uniq -c | sort -rn

# Find peak activity periods
# Analyze finding patterns
# Review response times
```

---

## Troubleshooting

### "Export fails with memory error"

```bash
# Export without media (metadata only)
osk aar export --no-media --output metadata-only.zip

# Export in chunks (future feature)
# Contact maintainer for large operations
```

### "Verification fails"

```bash
# Check which files failed
osk aar verify --verbose failed-export.zip

# Likely causes:
# - Incomplete export (operation still running)
# - Corrupted transfer
# - Tampering (unlikely)

# Re-export if needed
osk aar export --output new-export.zip
```

### "Missing operation data"

```bash
# Check operation exists
osk status --json | jq '.operation_id'

# List available operations
osk aar list

# Generate summary with explicit ID
osk aar generate --operation-id <uuid>
```

---

## Best Practices

### Do

✅ Export AAR immediately after operation close  
✅ Verify integrity before storage  
✅ Create checkpoints during long operations  
✅ Review closure checklist promptly  
✅ Follow up on all pending items  
✅ Store in multiple locations  
✅ Document chain of custody  

### Don't

❌ Delete evidence before AAR export  
❌ Store unencrypted on shared drives  
❌ Ignore verification failures  
❌ Delay follow-up on pending items  
❌ Modify exported AAR contents  

---

## See Also

- **Quickstart Card:** `docs/ops/quickstart-card.md`
- **Supported Profiles:** `docs/SUPPORTED_PROFILES.md`
- **Install Guide:** `docs/INSTALL_GUIDE.md`
- **Security:** `docs/SECURITY.md`

---

**Questions?** Open an issue at https://github.com/justinredmondsmith-collab/osk/issues
