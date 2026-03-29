"""Tests for security hardening module."""

from datetime import datetime, timedelta
from unittest import mock

import pytest

from osk.security_hardening import (
    TokenMetadata,
    TokenLifecycleManager,
    WipeEvent,
    WipeVerificationLogger,
    SECURITY_2_0_DEFAULTS,
)


class TestTokenMetadata:
    """Test TokenMetadata dataclass."""
    
    def test_token_not_expired(self):
        metadata = TokenMetadata(
            token_id="abc123",
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=1),
        )
        assert metadata.is_expired() is False
    
    def test_token_expired(self):
        metadata = TokenMetadata(
            token_id="abc123",
            created_at=datetime.now() - timedelta(hours=2),
            expires_at=datetime.now() - timedelta(hours=1),
        )
        assert metadata.is_expired() is True
    
    def test_should_rotate_after_interval(self):
        metadata = TokenMetadata(
            token_id="abc123",
            created_at=datetime.now() - timedelta(hours=1),
            expires_at=datetime.now() + timedelta(hours=1),
        )
        # Should rotate after 30 minutes
        assert metadata.should_rotate(timedelta(minutes=30)) is True
    
    def test_should_not_rotate_yet(self):
        metadata = TokenMetadata(
            token_id="abc123",
            created_at=datetime.now() - timedelta(minutes=5),
            expires_at=datetime.now() + timedelta(hours=1),
        )
        # Should not rotate after only 5 minutes
        assert metadata.should_rotate(timedelta(minutes=30)) is False
    
    def test_to_dict(self):
        metadata = TokenMetadata(
            token_id="abc123",
            created_at=datetime(2026, 1, 1, 12, 0, 0),
            expires_at=datetime(2026, 1, 1, 16, 0, 0),
            rotation_count=2,
        )
        data = metadata.to_dict()
        assert data["token_id"] == "abc123"
        assert data["rotation_count"] == 2
        assert "2026-01-01" in data["created_at"]


class TestTokenLifecycleManager:
    """Test TokenLifecycleManager."""
    
    def test_create_token_for_operator(self):
        manager = TokenLifecycleManager(None, None)
        token, metadata = manager.create_token(
            entity_type="operator",
            entity_id=mock.Mock(),
        )
        
        assert len(token) > 20  # Secure token
        assert metadata.token_id is not None
        # Operator tokens: 4 hours
        expected_expiry = datetime.now() + timedelta(hours=4)
        assert abs((metadata.expires_at - expected_expiry).total_seconds()) < 5
    
    def test_create_token_for_member(self):
        manager = TokenLifecycleManager(None, None)
        token, metadata = manager.create_token(
            entity_type="member",
            entity_id=mock.Mock(),
        )
        
        # Member tokens: 2 hours
        expected_expiry = datetime.now() + timedelta(hours=2)
        assert abs((metadata.expires_at - expected_expiry).total_seconds()) < 5
    
    def test_rotate_token_preserves_session(self):
        manager = TokenLifecycleManager(None, None)
        old_token, old_metadata = manager.create_token(
            entity_type="operator",
            entity_id=mock.Mock(),
        )
        old_metadata.rotation_count = 2
        
        new_token, new_metadata = manager.rotate_token(old_metadata)
        
        assert new_token != old_token
        assert new_metadata.created_at == old_metadata.created_at  # Preserved
        assert new_metadata.rotation_count == 3
        assert new_metadata.rotated_at is not None
    
    def test_validate_valid_token(self):
        manager = TokenLifecycleManager(None, None)
        token, metadata = manager.create_token(
            entity_type="operator",
            entity_id=mock.Mock(),
        )
        
        valid, reason = manager.validate_token_use(metadata)
        assert valid is True
        assert reason is None
    
    def test_validate_expired_token(self):
        manager = TokenLifecycleManager(None, None)
        metadata = TokenMetadata(
            token_id="abc",
            created_at=datetime.now() - timedelta(hours=5),
            expires_at=datetime.now() - timedelta(hours=1),
        )
        
        valid, reason = manager.validate_token_use(metadata)
        assert valid is False
        assert "expired" in reason.lower()
    
    def test_validate_device_mismatch(self):
        manager = TokenLifecycleManager(None, None)
        metadata = TokenMetadata(
            token_id="abc",
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=1),
            device_fingerprint="device_a",
        )
        
        valid, reason = manager.validate_token_use(
            metadata,
            current_fingerprint="device_b",
        )
        assert valid is False
        assert "mismatch" in reason.lower()
    
    def test_generate_device_fingerprint(self):
        manager = TokenLifecycleManager(None, None)
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "en-US",
        }
        fingerprint = manager.generate_device_fingerprint(headers)
        
        assert len(fingerprint) == 16  # Truncated SHA-256
        assert fingerprint.isalnum()


class TestWipeEvent:
    """Test WipeEvent dataclass."""
    
    def test_successful_event(self):
        event = WipeEvent(
            timestamp=datetime.now(),
            event_type="test",
            details={"key": "value"},
            success=True,
        )
        assert event.success is True
        assert event.error_message is None
    
    def test_failed_event(self):
        event = WipeEvent(
            timestamp=datetime.now(),
            event_type="test",
            details={},
            success=False,
            error_message="Something failed",
        )
        data = event.to_dict()
        assert data["success"] is False
        assert data["error_message"] == "Something failed"


class TestWipeVerificationLogger:
    """Test WipeVerificationLogger."""
    
    def test_log_member_wipe_success(self):
        import uuid
        logger = WipeVerificationLogger(uuid.uuid4())
        logger.log_member_wipe(
            member_id=uuid.uuid4(),
            acknowledged=True,
        )
        
        member_events = [e for e in logger.events if e.event_type == "member_wipe"]
        assert len(member_events) == 1
        assert member_events[0].success is True
    
    def test_log_member_wipe_failure(self):
        import uuid
        logger = WipeVerificationLogger(uuid.uuid4())
        logger.log_member_wipe(
            member_id=uuid.uuid4(),
            acknowledged=False,
            error="Timeout",
        )
        
        member_events = [e for e in logger.events if e.event_type == "member_wipe"]
        assert len(member_events) == 1
        assert member_events[0].success is False
        assert member_events[0].error_message == "Timeout"
    
    def test_generate_report_summary(self):
        import uuid
        logger = WipeVerificationLogger(uuid.uuid4())
        logger.start_wipe("coordinator", 5)
        
        # Log some members
        logger.log_member_wipe(uuid.uuid4(), True)
        logger.log_member_wipe(uuid.uuid4(), True)
        logger.log_member_wipe(uuid.uuid4(), False, "Timeout")
        
        logger.complete_wipe(True)
        
        report = logger.generate_report()
        assert report["summary"]["member_wipe_attempts"] == 3
        assert report["summary"]["member_wipe_acknowledged"] == 2
        assert report["summary"]["member_wipe_failed"] == 1
    
    def test_assess_residual_risk_low(self):
        import uuid
        logger = WipeVerificationLogger(uuid.uuid4())
        logger.start_wipe("coordinator", 2)
        logger.log_member_wipe(uuid.uuid4(), True)
        logger.log_member_wipe(uuid.uuid4(), True)
        logger.complete_wipe(True)
        
        risk = logger._assess_residual_risk()
        assert "Low" in risk
    
    def test_assess_residual_risk_high(self):
        import uuid
        logger = WipeVerificationLogger(uuid.uuid4())
        logger.start_wipe("coordinator", 2)
        logger.log_member_wipe(uuid.uuid4(), True)
        logger.log_member_wipe(uuid.uuid4(), False, "Timeout")
        logger.log_evidence_cleanup(10, 1000, ["File locked"])
        
        risk = logger._assess_residual_risk()
        assert "High" in risk


class TestSecurityDefaults:
    """Test SECURITY_2_0_DEFAULTS configuration."""
    
    def test_operator_timeout(self):
        # 4 hours = 14400 seconds
        assert SECURITY_2_0_DEFAULTS["session_timeout_operator_seconds"] == 14400
    
    def test_member_timeout(self):
        # 2 hours = 7200 seconds
        assert SECURITY_2_0_DEFAULTS["session_timeout_member_seconds"] == 7200
    
    def test_rotation_interval(self):
        # 30 minutes = 1800 seconds
        assert SECURITY_2_0_DEFAULTS["token_rotation_interval_seconds"] == 1800
    
    def test_security_features_enabled(self):
        assert SECURITY_2_0_DEFAULTS["token_rotation_enabled"] is True
        assert SECURITY_2_0_DEFAULTS["device_binding_enabled"] is True
        assert SECURITY_2_0_DEFAULTS["security_audit_enabled"] is True
        assert SECURITY_2_0_DEFAULTS["wipe_verification_enabled"] is True
