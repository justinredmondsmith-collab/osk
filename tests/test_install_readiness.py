"""Tests for install readiness checker."""

import sys
from unittest import mock
import sys

import pytest

from osk.install_readiness import (
    ReadinessCheck,
    ReadinessReport,
    check_python_version,
    check_disk_space,
    determine_support_profile,
)


class TestReadinessCheck:
    """Test ReadinessCheck dataclass."""
    
    def test_basic_check(self):
        check = ReadinessCheck(
            name="Test Check",
            passed=True,
            message="All good",
        )
        assert check.name == "Test Check"
        assert check.passed is True
        assert check.message == "All good"
        assert check.severity == "info"
    
    def test_failed_check_with_remediation(self):
        check = ReadinessCheck(
            name="Failed Check",
            passed=False,
            message="Something wrong",
            severity="error",
            remediation="Fix it",
            docs_link="https://docs.example.com",
        )
        assert check.passed is False
        assert check.severity == "error"
        assert check.remediation == "Fix it"


class TestCheckPythonVersion:
    """Test Python version check."""
    
    def test_current_python_passes(self):
        # Test with actual Python version (should pass on 3.11+)
        check = check_python_version()
        # This test only verifies the function runs without error
        assert check.passed is (sys.version_info >= (3, 11))
        assert "Python" in check.message


class TestCheckDiskSpace:
    """Test disk space check."""
    
    @mock.patch('osk.install_readiness.shutil.disk_usage')
    def test_plenty_of_space(self, mock_disk_usage):
        # 100 GB free, 200 GB total
        mock_disk_usage.return_value = mock.Mock(free=100*1024**3, total=200*1024**3)
        check = check_disk_space()
        assert check.passed is True
        assert "100.0 GB free" in check.message
    
    @mock.patch('osk.install_readiness.shutil.disk_usage')
    def test_low_space_warning(self, mock_disk_usage):
        # 3 GB free, 100 GB total
        mock_disk_usage.return_value = mock.Mock(free=3*1024**3, total=100*1024**3)
        check = check_disk_space()
        assert check.passed is False
        assert check.severity == "warning"
    
    @mock.patch('osk.install_readiness.shutil.disk_usage')
    def test_critical_space_error(self, mock_disk_usage):
        # 500 MB free
        mock_disk_usage.return_value = mock.Mock(free=500*1024*1024, total=100*1024**3)
        check = check_disk_space()
        assert check.passed is False
        assert check.severity == "error"


class TestDetermineSupportProfile:
    """Test profile determination."""
    
    def test_full_profile(self):
        checks = [
            ReadinessCheck("Python", True, "ok"),
            ReadinessCheck("PostgreSQL", True, "ok"),
            ReadinessCheck("Docker", True, "ok"),
        ]
        profile = determine_support_profile(checks)
        assert profile == "supported-full"
    
    def test_docker_managed_profile(self):
        checks = [
            ReadinessCheck("Python", True, "ok"),
            ReadinessCheck("PostgreSQL", False, "not found"),
            ReadinessCheck("Docker", True, "ok"),
        ]
        profile = determine_support_profile(checks)
        assert profile == "supported-docker-managed"
    
    def test_minimal_profile(self):
        # Minimal profile requires these specific check names
        checks = [
            ReadinessCheck("Python Version", True, "ok"),
            ReadinessCheck("PostgreSQL", True, "ok"),
            ReadinessCheck("OpenSSL", True, "ok"),
            ReadinessCheck("TLS Certificate Storage", True, "ok"),
            ReadinessCheck("Docker", False, "not found"),
        ]
        profile = determine_support_profile(checks)
        assert profile == "supported-minimal"
    
    def test_unsupported_profile(self):
        # Missing critical checks should result in unsupported
        checks = [
            ReadinessCheck("Python Version", False, "too old"),
            ReadinessCheck("OpenSSL", True, "ok"),
            ReadinessCheck("TLS Certificate Storage", True, "ok"),
        ]
        profile = determine_support_profile(checks)
        assert profile == "unsupported"


class TestReadinessReport:
    """Test ReadinessReport dataclass."""
    
    def test_all_passed(self):
        checks = [
            ReadinessCheck("Check 1", True, "ok"),
            ReadinessCheck("Check 2", True, "ok"),
        ]
        report = ReadinessReport(
            overall_ready=True,
            checks=checks,
            profile="supported-full",
        )
        assert report.overall_ready is True
        assert len(report.checks) == 2
        assert report.profile == "supported-full"
    
    def test_not_ready(self):
        checks = [
            ReadinessCheck("Check 1", True, "ok"),
            ReadinessCheck("Check 2", False, "failed", severity="error"),
        ]
        report = ReadinessReport(
            overall_ready=False,
            checks=checks,
            profile="unsupported",
            recommendations=["Fix check 2"],
        )
        assert report.overall_ready is False
        assert len(report.recommendations) == 1
