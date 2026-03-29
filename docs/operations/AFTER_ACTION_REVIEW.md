# After-Action Review System

**Version:** 2.0  
**Status:** Design Document

## Overview

The After-Action Review (AAR) system helps coordinators review operations, export evidence, and document lessons learned.

## Components

### 1. Operation Summary

Auto-generated report with:
- Operation metadata (duration, participants)
- Statistics (findings, tasks, media)
- Timeline of key events
- Closure checklist status

### 2. Evidence Export

Export formats:
- **Standard (ZIP)**: All evidence with integrity manifest
- **Summary (PDF)**: Overview only, no media
- **Raw (JSONL)**: Machine-readable data

### 3. Closure Checklist

Automated checks:
- All findings reviewed
- All tasks completed/cancelled
- All members disconnected
- Evidence exported

## CLI Commands

```bash
# Generate report
osk aar generate --output report.json

# Export evidence
osk aar export --output evidence.zip

# View checklist
osk aar checklist

# Review timeline
osk aar timeline
```

## Export Structure

```
evidence-export/
├── MANIFEST.json          # Integrity verification
├── operation-summary.json
├── timeline.json
├── findings/
├── tasks/
├── media/
└── audit/
```

## Implementation Priority

1. **MVP (2.0)**: Basic export with manifest
2. **Enhanced (2.1)**: Timeline visualization, checklist UI
3. **Advanced (2.2)**: Encryption, custom policies
