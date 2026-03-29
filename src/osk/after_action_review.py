"""After-Action Review (AAR) system for operation closure

Release 2.0 - Mature Single-Hub Operational System
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
import uuid


@dataclass
class OperationSummary:
    """Summary of a completed operation."""
    operation_id: uuid.UUID
    operation_name: str
    coordinator: str
    start_time: datetime
    end_time: datetime
    
    # Statistics
    members_joined: int = 0
    members_peak: int = 0
    
    observations_created: int = 0
    findings_generated: int = 0
    findings_acknowledged: int = 0
    findings_escalated: int = 0
    
    tasks_created: int = 0
    tasks_completed: int = 0
    tasks_timed_out: int = 0
    tasks_cancelled: int = 0
    
    audio_chunks: int = 0
    frames_captured: int = 0
    manual_photos: int = 0
    manual_clips: int = 0
    
    @property
    def duration_hours(self) -> float:
        return (self.end_time - self.start_time).total_seconds() / 3600
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": str(self.operation_id),
            "operation_name": self.operation_name,
            "coordinator": self.coordinator,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "duration_hours": round(self.duration_hours, 2),
            "statistics": {
                "members": {
                    "total_joined": self.members_joined,
                    "peak_concurrent": self.members_peak,
                },
                "intelligence": {
                    "observations_created": self.observations_created,
                    "findings_generated": self.findings_generated,
                    "findings_acknowledged": self.findings_acknowledged,
                    "findings_escalated": self.findings_escalated,
                },
                "tasks": {
                    "created": self.tasks_created,
                    "completed": self.tasks_completed,
                    "timed_out": self.tasks_timed_out,
                    "cancelled": self.tasks_cancelled,
                },
                "media": {
                    "audio_chunks": self.audio_chunks,
                    "frames_captured": self.frames_captured,
                    "manual_photos": self.manual_photos,
                    "manual_clips": self.manual_clips,
                },
            },
        }


@dataclass
class TimelineEvent:
    """Single event in operation timeline."""
    timestamp: datetime
    event_type: str  # system, join, finding, task, etc.
    description: str
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "type": self.event_type,
            "description": self.description,
            "metadata": self.metadata,
        }


@dataclass
class EvidenceManifest:
    """Integrity manifest for evidence export."""
    manifest_version: str = "2.0"
    operation_id: Optional[uuid.UUID] = None
    exported_at: Optional[datetime] = None
    export_tool: str = "osk 2.0"
    files: list[dict[str, Any]] = field(default_factory=list)
    total_size_bytes: int = 0
    
    def add_file(self, path: str, size: int, content: bytes) -> None:
        """Add a file to the manifest with SHA-256 hash."""
        sha256_hash = hashlib.sha256(content).hexdigest()
        self.files.append({
            "path": path,
            "size": size,
            "sha256": sha256_hash,
        })
        self.total_size_bytes += size
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_version": self.manifest_version,
            "operation_id": str(self.operation_id) if self.operation_id else None,
            "exported_at": self.exported_at.isoformat() if self.exported_at else None,
            "export_tool": self.export_tool,
            "total_size_bytes": self.total_size_bytes,
            "file_count": len(self.files),
            "files": self.files,
            "verification_command": "sha256sum -c MANIFEST.sha256",
        }
    
    def generate_sha256_file(self) -> str:
        """Generate content for SHA256SUMS-style file."""
        lines = []
        for f in self.files:
            lines.append(f"{f['sha256']}  {f['path']}")
        return "\n".join(lines) + "\n"


class AARExporter:
    """Export operation evidence with integrity verification."""
    
    def __init__(self, db, storage_manager, config):
        self.db = db
        self.storage = storage_manager
        self.config = config
    
    async def generate_operation_summary(
        self,
        operation_id: uuid.UUID,
    ) -> OperationSummary:
        """Generate summary for an operation."""
        # Query database for operation stats
        async with self.db.acquire() as conn:
            # Get operation metadata
            row = await conn.fetchrow(
                "SELECT name, created_at FROM operations WHERE id = $1",
                operation_id,
            )
            
            if not row:
                raise ValueError(f"Operation {operation_id} not found")
            
            # Get member stats
            member_stats = await conn.fetchrow(
                """
                SELECT 
                    COUNT(*) as total,
                    MAX(concurrent_count) as peak
                FROM (
                    SELECT DATE_TRUNC('minute', created_at), COUNT(*) as concurrent_count
                    FROM members WHERE operation_id = $1
                    GROUP BY DATE_TRUNC('minute', created_at)
                ) sub
                """,
                operation_id,
            )
            
            # Get intelligence stats
            intel_stats = await conn.fetchrow(
                """
                SELECT 
                    COUNT(*) as observations,
                    COUNT(DISTINCT finding_id) as findings
                FROM intelligence_observations
                WHERE operation_id = $1
                """,
                operation_id,
            )
            
            # Get task stats
            task_stats = await conn.fetchrow(
                """
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE state = 'completed') as completed,
                    COUNT(*) FILTER (WHERE state = 'timed_out') as timed_out,
                    COUNT(*) FILTER (WHERE state = 'cancelled') as cancelled
                FROM tasks
                WHERE operation_id = $1
                """,
                operation_id,
            )
            
            summary = OperationSummary(
                operation_id=operation_id,
                operation_name=row["name"],
                coordinator="unknown",  # Would get from session
                start_time=row["created_at"],
                end_time=datetime.now(),
                members_joined=member_stats["total"] or 0,
                members_peak=member_stats["peak"] or 0,
                observations_created=intel_stats["observations"] or 0,
                tasks_created=task_stats["total"] or 0,
                tasks_completed=task_stats["completed"] or 0,
                tasks_timed_out=task_stats["timed_out"] or 0,
                tasks_cancelled=task_stats["cancelled"] or 0,
            )
            
            return summary
    
    async def export_evidence(
        self,
        operation_id: uuid.UUID,
        output_path: Path,
        include_media: bool = True,
    ) -> EvidenceManifest:
        """Export operation evidence to ZIP file."""
        manifest = EvidenceManifest(
            operation_id=operation_id,
            exported_at=datetime.now(),
        )
        
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            # 1. Operation summary
            summary = await self.generate_operation_summary(operation_id)
            summary_json = json.dumps(summary.to_dict(), indent=2).encode('utf-8')
            zf.writestr("operation-summary.json", summary_json)
            manifest.add_file("operation-summary.json", len(summary_json), summary_json)
            
            # 2. Timeline
            timeline = await self._generate_timeline(operation_id)
            timeline_json = json.dumps([e.to_dict() for e in timeline], indent=2).encode('utf-8')
            zf.writestr("timeline.json", timeline_json)
            manifest.add_file("timeline.json", len(timeline_json), timeline_json)
            
            # 3. Findings
            findings = await self._export_findings(operation_id)
            findings_json = json.dumps(findings, indent=2).encode('utf-8')
            zf.writestr("findings/findings.json", findings_json)
            manifest.add_file("findings/findings.json", len(findings_json), findings_json)
            
            # 4. Audit trail
            audit = await self._export_audit_trail(operation_id)
            audit_jsonl = "\n".join(json.dumps(line) for line in audit).encode('utf-8')
            zf.writestr("audit/audit-trail.jsonl", audit_jsonl)
            manifest.add_file("audit/audit-trail.jsonl", len(audit_jsonl), audit_jsonl)
            
            # 5. Media (if requested)
            if include_media:
                await self._export_media(operation_id, zf, manifest)
            
            # 6. Manifest
            manifest_json = json.dumps(manifest.to_dict(), indent=2).encode('utf-8')
            zf.writestr("MANIFEST.json", manifest_json)
            
            # 7. SHA256 sums file for verification
            sha256_content = manifest.generate_sha256_file().encode('utf-8')
            zf.writestr("MANIFEST.sha256", sha256_content)
            
            # 8. README
            readme = self._generate_readme(summary).encode('utf-8')
            zf.writestr("README.md", readme)
        
        return manifest
    
    async def _generate_timeline(
        self,
        operation_id: uuid.UUID,
    ) -> list[TimelineEvent]:
        """Generate operation timeline."""
        events = []
        
        async with self.db.acquire() as conn:
            # Get key events from audit log
            rows = await conn.fetch(
                """
                SELECT created_at, event_type, details
                FROM audit_events
                WHERE operation_id = $1
                ORDER BY created_at
                """,
                operation_id,
            )
            
            for row in rows:
                events.append(TimelineEvent(
                    timestamp=row["created_at"],
                    event_type=row["event_type"],
                    description=str(row["details"])[:200],
                    metadata=row["details"] if isinstance(row["details"], dict) else {},
                ))
        
        return events
    
    async def _export_findings(
        self,
        operation_id: uuid.UUID,
    ) -> list[dict[str, Any]]:
        """Export findings data."""
        findings = []
        
        async with self.db.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT 
                    id, category, severity, text,
                    created_at, acknowledged_at, resolved_at
                FROM synthesis_findings
                WHERE operation_id = $1
                """,
                operation_id,
            )
            
            for row in rows:
                findings.append({
                    "id": str(row["id"]),
                    "category": row["category"],
                    "severity": row["severity"],
                    "text": row["text"],
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                    "acknowledged_at": row["acknowledged_at"].isoformat() if row["acknowledged_at"] else None,
                    "resolved_at": row["resolved_at"].isoformat() if row["resolved_at"] else None,
                })
        
        return findings
    
    async def _export_audit_trail(
        self,
        operation_id: uuid.UUID,
    ) -> list[dict[str, Any]]:
        """Export audit trail."""
        audit = []
        
        async with self.db.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT created_at, event_type, actor, details
                FROM audit_events
                WHERE operation_id = $1
                ORDER BY created_at
                """,
                operation_id,
            )
            
            for row in rows:
                audit.append({
                    "timestamp": row["created_at"].isoformat(),
                    "event_type": row["event_type"],
                    "actor": row["actor"],
                    "details": row["details"],
                })
        
        return audit
    
    async def _export_media(
        self,
        operation_id: uuid.UUID,
        zf: zipfile.ZipFile,
        manifest: EvidenceManifest,
    ) -> None:
        """Export media files to ZIP."""
        # Get evidence storage path
        evidence_path = self.config.evidence_path / str(operation_id)
        
        if not evidence_path.exists():
            return
        
        for file_path in evidence_path.rglob("*"):
            if file_path.is_file():
                # Read and add to ZIP
                content = file_path.read_bytes()
                arc_name = f"media/{file_path.relative_to(evidence_path)}"
                zf.writestr(arc_name, content)
                manifest.add_file(arc_name, len(content), content)
    
    def _generate_readme(self, summary: OperationSummary) -> str:
        """Generate README for evidence export."""
        return f"""# Osk Evidence Export

## Operation Summary

- **Operation ID**: {summary.operation_id}
- **Operation Name**: {summary.operation_name}
- **Duration**: {summary.duration_hours:.2f} hours
- **Exported**: {datetime.now().isoformat()}

## Statistics

### Members
- Total Joined: {summary.members_joined}
- Peak Concurrent: {summary.members_peak}

### Intelligence
- Observations: {summary.observations_created}
- Findings Generated: {summary.findings_generated}
- Findings Acknowledged: {summary.findings_acknowledged}
- Findings Escalated: {summary.findings_escalated}

### Tasks
- Created: {summary.tasks_created}
- Completed: {summary.tasks_completed}
- Timed Out: {summary.tasks_timed_out}
- Cancelled: {summary.tasks_cancelled}

### Media
- Audio Chunks: {summary.audio_chunks}
- Frames Captured: {summary.frames_captured}
- Manual Photos: {summary.manual_photos}
- Manual Clips: {summary.manual_clips}

## File Structure

```
.
├── MANIFEST.json          # Integrity verification
├── MANIFEST.sha256        # SHA-256 checksums
├── README.md              # This file
├── operation-summary.json # Full operation statistics
├── timeline.json          # Event timeline
├── findings/              # Intelligence findings
├── tasks/                 # Task records
├── media/                 # Evidence media files
└── audit/                 # Audit trail
```

## Verification

To verify integrity:

```bash
sha256sum -c MANIFEST.sha256
```

## Retention

This export should be retained according to your organization's
data retention policy. Default Osk retention is 30 days for raw
data, 90 days for findings.

---

Generated by Osk 2.0 After-Action Review System
"""


class ClosureChecklist:
    """Checklist for operation closure."""
    
    def __init__(self, db):
        self.db = db
        self.items: list[dict[str, Any]] = []
    
    async def generate(self, operation_id: uuid.UUID) -> list[dict[str, Any]]:
        """Generate closure checklist for operation."""
        items = []
        
        async with self.db.acquire() as conn:
            # Check 1: All findings reviewed
            finding_status = await conn.fetchrow(
                """
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE status = 'pending') as pending
                FROM synthesis_findings
                WHERE operation_id = $1
                """,
                operation_id,
            )
            
            items.append({
                "id": "findings_reviewed",
                "category": "intelligence",
                "description": "All findings reviewed",
                "automated": True,
                "passed": finding_status["pending"] == 0,
                "details": f"{finding_status['pending']} of {finding_status['total']} pending",
            })
            
            # Check 2: All tasks completed
            task_status = await conn.fetchrow(
                """
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE state IN ('completed', 'cancelled')) as done,
                    COUNT(*) FILTER (WHERE state = 'pending') as pending
                FROM tasks
                WHERE operation_id = $1
                """,
                operation_id,
            )
            
            items.append({
                "id": "tasks_completed",
                "category": "coordination",
                "description": "All tasks completed or cancelled",
                "automated": True,
                "passed": task_status["pending"] == 0,
                "details": f"{task_status['done']} of {task_status['total']} done",
            })
            
            # Check 3: Members disconnected
            member_status = await conn.fetchrow(
                """
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE disconnected_at IS NULL) as still_connected
                FROM members
                WHERE operation_id = $1
                """,
                operation_id,
            )
            
            items.append({
                "id": "members_disconnected",
                "category": "safety",
                "description": "All members disconnected",
                "automated": True,
                "passed": member_status["still_connected"] == 0,
                "details": f"{member_status['still_connected']} still connected",
            })
            
            # Check 4: Evidence exported (manual)
            items.append({
                "id": "evidence_exported",
                "category": "compliance",
                "description": "Evidence exported (if required)",
                "automated": False,
                "passed": None,
                "details": "Manual verification required",
            })
            
            # Check 5: Coordinator review (manual)
            items.append({
                "id": "coordinator_review",
                "category": "review",
                "description": "Coordinator review completed",
                "automated": False,
                "passed": None,
                "details": "Manual verification required",
            })
        
        self.items = items
        return items
    
    def all_passed(self) -> bool:
        """Check if all automated items passed."""
        automated = [i for i in self.items if i["automated"]]
        return all(i["passed"] for i in automated)
