"""Security hardening for Release 2.0

Token lifecycle management, key handling, and wipe verification.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional
import uuid


@dataclass
class TokenMetadata:
    """Metadata for session tokens."""
    token_id: str
    created_at: datetime
    expires_at: datetime
    rotated_at: Optional[datetime] = None
    device_fingerprint: Optional[str] = None
    ip_address: Optional[str] = None
    last_used_at: Optional[datetime] = None
    rotation_count: int = 0
    
    def is_expired(self) -> bool:
        return datetime.now() > self.expires_at
    
    def should_rotate(self, rotation_interval: timedelta = timedelta(minutes=30)) -> bool:
        if not self.rotated_at:
            return datetime.now() - self.created_at > rotation_interval
        return datetime.now() - self.rotated_at > rotation_interval
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "token_id": self.token_id,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "rotated_at": self.rotated_at.isoformat() if self.rotated_at else None,
            "device_fingerprint": self.device_fingerprint,
            "ip_address": self.ip_address,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "rotation_count": self.rotation_count,
        }


class TokenLifecycleManager:
    """Manage token lifecycle with rotation and expiration."""
    
    # 2.0: Shorter timeouts as per security hardening
    DEFAULT_OPERATOR_TIMEOUT = timedelta(hours=4)  # Was 8 hours
    DEFAULT_MEMBER_TIMEOUT = timedelta(hours=2)    # Was 4 hours
    ROTATION_INTERVAL = timedelta(minutes=30)
    
    def __init__(self, db, config):
        self.db = db
        self.config = config
    
    def create_token(
        self,
        entity_type: str,  # 'operator' or 'member'
        entity_id: uuid.UUID,
        device_fingerprint: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> tuple[str, TokenMetadata]:
        """Create a new session token."""
        # Generate cryptographically secure token
        token_value = secrets.token_urlsafe(32)
        token_id = hashlib.sha256(token_value.encode()).hexdigest()[:16]
        
        # Determine expiration based on entity type
        if entity_type == 'operator':
            timeout = self.DEFAULT_OPERATOR_TIMEOUT
        else:
            timeout = self.DEFAULT_MEMBER_TIMEOUT
        
        now = datetime.now()
        metadata = TokenMetadata(
            token_id=token_id,
            created_at=now,
            expires_at=now + timeout,
            device_fingerprint=device_fingerprint,
            ip_address=ip_address,
            last_used_at=now,
        )
        
        return token_value, metadata
    
    def rotate_token(self, old_metadata: TokenMetadata) -> tuple[str, TokenMetadata]:
        """Rotate a token while maintaining session continuity."""
        # Generate new token
        new_token = secrets.token_urlsafe(32)
        new_token_id = hashlib.sha256(new_token.encode()).hexdigest()[:16]
        
        # Create new metadata preserving session info
        now = datetime.now()
        new_metadata = TokenMetadata(
            token_id=new_token_id,
            created_at=old_metadata.created_at,  # Keep original creation time
            expires_at=now + (old_metadata.expires_at - old_metadata.created_at),
            rotated_at=now,
            device_fingerprint=old_metadata.device_fingerprint,
            ip_address=old_metadata.ip_address,
            last_used_at=now,
            rotation_count=old_metadata.rotation_count + 1,
        )
        
        return new_token, new_metadata
    
    def validate_token_use(
        self,
        metadata: TokenMetadata,
        current_fingerprint: Optional[str] = None,
        current_ip: Optional[str] = None,
    ) -> tuple[bool, Optional[str]]:
        """Validate token use and detect anomalies."""
        # Check expiration
        if metadata.is_expired():
            return False, "Token expired"
        
        # Check device fingerprint (if enabled)
        if metadata.device_fingerprint and current_fingerprint:
            if metadata.device_fingerprint != current_fingerprint:
                return False, "Device mismatch"
        
        # Check rotation needed
        if metadata.should_rotate(self.ROTATION_INTERVAL):
            return True, "Rotation required"
        
        return True, None
    
    def generate_device_fingerprint(self, request_headers: dict) -> str:
        """Generate a simple device fingerprint from request headers."""
        # Combine several factors for fingerprinting
        factors = [
            request_headers.get('User-Agent', ''),
            request_headers.get('Accept-Language', ''),
            request_headers.get('Accept-Encoding', ''),
        ]
        fingerprint_data = '|'.join(factors)
        return hashlib.sha256(fingerprint_data.encode()).hexdigest()[:16]


@dataclass
class WipeEvent:
    """Single event during wipe process."""
    timestamp: datetime
    event_type: str
    details: dict[str, Any]
    success: bool = True
    error_message: Optional[str] = None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "details": self.details,
            "success": self.success,
            "error_message": self.error_message,
        }


class WipeVerificationLogger:
    """Log and verify wipe operations."""
    
    def __init__(self, operation_id: uuid.UUID):
        self.operation_id = operation_id
        self.events: list[WipeEvent] = []
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
    
    def log_event(
        self,
        event_type: str,
        details: dict[str, Any],
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> None:
        """Log a wipe event."""
        event = WipeEvent(
            timestamp=datetime.now(),
            event_type=event_type,
            details=details,
            success=success,
            error_message=error_message,
        )
        self.events.append(event)
    
    def start_wipe(self, coordinator: str, member_count: int) -> None:
        """Mark wipe as started."""
        self.started_at = datetime.now()
        self.log_event(
            "wipe_started",
            {
                "coordinator": coordinator,
                "member_count": member_count,
                "operation_id": str(self.operation_id),
            },
        )
    
    def log_member_wipe(
        self,
        member_id: uuid.UUID,
        acknowledged: bool,
        error: Optional[str] = None,
    ) -> None:
        """Log member wipe acknowledgment."""
        self.log_event(
            "member_wipe",
            {
                "member_id": str(member_id),
                "acknowledged": acknowledged,
            },
            success=acknowledged,
            error_message=error,
        )
    
    def log_hub_stop(self, success: bool, error: Optional[str] = None) -> None:
        """Log hub stop."""
        self.log_event(
            "hub_stopped",
            {"operation_id": str(self.operation_id)},
            success=success,
            error_message=error,
        )
    
    def log_evidence_cleanup(
        self,
        files_deleted: int,
        bytes_freed: int,
        errors: list[str],
    ) -> None:
        """Log evidence cleanup."""
        self.log_event(
            "evidence_cleanup",
            {
                "files_deleted": files_deleted,
                "bytes_freed": bytes_freed,
                "errors": errors,
            },
            success=len(errors) == 0,
            error_message="; ".join(errors) if errors else None,
        )
    
    def complete_wipe(self, success: bool, residual_risk: str = "") -> None:
        """Mark wipe as complete."""
        self.completed_at = datetime.now()
        self.log_event(
            "wipe_completed",
            {
                "duration_seconds": (self.completed_at - self.started_at).total_seconds() if self.started_at else 0,
                "residual_risk": residual_risk,
            },
            success=success,
        )
    
    def generate_report(self) -> dict[str, Any]:
        """Generate wipe verification report."""
        member_events = [e for e in self.events if e.event_type == "member_wipe"]
        acknowledged = sum(1 for e in member_events if e.success)
        failed = len(member_events) - acknowledged
        
        return {
            "operation_id": str(self.operation_id),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": (
                (self.completed_at - self.started_at).total_seconds()
                if self.completed_at and self.started_at
                else None
            ),
            "summary": {
                "total_events": len(self.events),
                "member_wipe_attempts": len(member_events),
                "member_wipe_acknowledged": acknowledged,
                "member_wipe_failed": failed,
                "overall_success": all(e.success for e in self.events),
            },
            "events": [e.to_dict() for e in self.events],
            "residual_risk": self._assess_residual_risk(),
        }
    
    def _assess_residual_risk(self) -> str:
        """Assess residual risk after wipe."""
        risks = []
        
        # Check for unacknowledged members
        member_events = [e for e in self.events if e.event_type == "member_wipe"]
        failed = [e for e in member_events if not e.success]
        if failed:
            risks.append(f"{len(failed)} member(s) did not acknowledge wipe")
        
        # Check for cleanup errors
        cleanup_events = [e for e in self.events if e.event_type == "evidence_cleanup"]
        for event in cleanup_events:
            if not event.success:
                risks.append("Evidence cleanup had errors")
        
        if not risks:
            return "Low: Standard wipe completed successfully"
        elif len(risks) == 1:
            return f"Medium: {risks[0]}"
        else:
            return f"High: Multiple issues - {', '.join(risks)}"


class SecurityAuditLogger:
    """Central security audit logging."""
    
    def __init__(self, db):
        self.db = db
    
    async def log_security_event(
        self,
        event_type: str,
        actor: str,
        details: dict[str, Any],
        severity: str = "info",  # info, warning, error, critical
    ) -> None:
        """Log a security event to the audit trail."""
        async with self.db.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO audit_events 
                (id, created_at, event_type, actor, details, severity)
                VALUES ($1, NOW(), $2, $3, $4, $5)
                """,
                uuid.uuid4(),
                f"security:{event_type}",
                actor,
                json.dumps(details),
                severity,
            )
    
    async def log_token_event(
        self,
        event_type: str,  # created, rotated, revoked, expired
        token_id: str,
        entity_type: str,
        entity_id: uuid.UUID,
        metadata: Optional[TokenMetadata] = None,
    ) -> None:
        """Log token lifecycle events."""
        details = {
            "token_id": token_id,
            "entity_type": entity_type,
            "entity_id": str(entity_id),
        }
        if metadata:
            details["rotation_count"] = metadata.rotation_count
            details["expires_at"] = metadata.expires_at.isoformat()
        
        await self.log_security_event(
            f"token:{event_type}",
            entity_id if entity_type == "operator" else str(entity_id),
            details,
            severity="info" if event_type in ("created", "rotated") else "warning",
        )
    
    async def log_key_access(
        self,
        key_type: str,
        operation: str,
        actor: str,
        success: bool = True,
    ) -> None:
        """Log key access events."""
        await self.log_security_event(
            "key:access",
            actor,
            {
                "key_type": key_type,
                "operation": operation,
                "success": success,
            },
            severity="info" if success else "warning",
        )


# 2.0 Configuration overrides for security hardening
SECURITY_2_0_DEFAULTS = {
    # Shorter session timeouts
    "session_timeout_operator_seconds": 4 * 60 * 60,  # 4 hours
    "session_timeout_member_seconds": 2 * 60 * 60,     # 2 hours
    
    # Token rotation
    "token_rotation_enabled": True,
    "token_rotation_interval_seconds": 30 * 60,  # 30 minutes
    "token_rotation_grace_seconds": 60,  # 1 minute grace period
    
    # Device binding
    "device_binding_enabled": True,
    "device_binding_strict": False,  # Warn but don't block on mismatch
    
    # Audit logging
    "security_audit_enabled": True,
    "security_audit_retention_days": 365,
    
    # Wipe verification
    "wipe_verification_enabled": True,
    "wipe_member_timeout_seconds": 30,
    "wipe_forensic_mode": False,  # Optional deep cleanup
}
