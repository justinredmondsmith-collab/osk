"""Installation readiness checker for Osk 2.0

Provides comprehensive pre-flight checks with actionable guidance.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ReadinessCheck:
    """Individual readiness check result."""
    name: str
    passed: bool
    message: str
    severity: str = "info"  # info, warning, error
    remediation: Optional[str] = None
    docs_link: Optional[str] = None


@dataclass
class ReadinessReport:
    """Complete installation readiness report."""
    overall_ready: bool
    checks: list[ReadinessCheck] = field(default_factory=list)
    profile: str = "unknown"
    recommendations: list[str] = field(default_factory=list)


def check_python_version() -> ReadinessCheck:
    """Check Python version compatibility."""
    import sys
    
    version = sys.version_info
    version_str = f"{version.major}.{version.minor}.{version.micro}"
    
    if version.major < 3 or (version.major == 3 and version.minor < 11):
        return ReadinessCheck(
            name="Python Version",
            passed=False,
            message=f"Python {version_str} is too old. Osk requires Python 3.11+",
            severity="error",
            remediation="Install Python 3.11 or newer from python.org or your package manager",
            docs_link="https://docs.python.org/3/using/index.html",
        )
    
    return ReadinessCheck(
        name="Python Version",
        passed=True,
        message=f"Python {version_str} (compatible)",
        severity="info",
    )


def check_postgres_installed() -> ReadinessCheck:
    """Check if PostgreSQL is installed."""
    psql_path = shutil.which("psql")
    
    if not psql_path:
        return ReadinessCheck(
            name="PostgreSQL",
            passed=False,
            message="PostgreSQL client (psql) not found in PATH",
            severity="warning",
            remediation="Install PostgreSQL 14+ or use Docker Compose (osk will manage it)",
        )
    
    # Try to get version
    try:
        result = subprocess.run(
            ["psql", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        version_line = result.stdout.strip()
        # Extract version number (e.g., "psql (PostgreSQL) 15.3")
        if "PostgreSQL" in version_line:
            version_str = version_line.split()[-1]
            major_version = int(version_str.split(".")[0])
            
            if major_version < 14:
                return ReadinessCheck(
                    name="PostgreSQL",
                    passed=False,
                    message=f"PostgreSQL {version_str} is too old (need 14+)",
                    severity="warning",
                    remediation="Upgrade PostgreSQL to version 14 or newer",
                )
            
            return ReadinessCheck(
                name="PostgreSQL",
                passed=True,
                message=f"PostgreSQL {version_str} installed at {psql_path}",
                severity="info",
            )
    except (subprocess.TimeoutExpired, ValueError, IndexError):
        pass
    
    return ReadinessCheck(
        name="PostgreSQL",
        passed=True,
        message=f"PostgreSQL client found at {psql_path}",
        severity="info",
    )


def check_openssl() -> ReadinessCheck:
    """Check if OpenSSL is available."""
    openssl_path = shutil.which("openssl")
    
    if not openssl_path:
        return ReadinessCheck(
            name="OpenSSL",
            passed=False,
            message="OpenSSL not found in PATH",
            severity="error",
            remediation="Install OpenSSL (usually pre-installed on Linux, use Homebrew on macOS)",
        )
    
    try:
        result = subprocess.run(
            ["openssl", "version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        version = result.stdout.strip()
        return ReadinessCheck(
            name="OpenSSL",
            passed=True,
            message=version,
            severity="info",
        )
    except subprocess.TimeoutExpired:
        pass
    
    return ReadinessCheck(
        name="OpenSSL",
        passed=True,
        message=f"OpenSSL found at {openssl_path}",
        severity="info",
    )


def check_ffmpeg() -> ReadinessCheck:
    """Check if ffmpeg is installed (needed for audio processing)."""
    ffmpeg_path = shutil.which("ffmpeg")
    
    if not ffmpeg_path:
        return ReadinessCheck(
            name="FFmpeg",
            passed=False,
            message="FFmpeg not found in PATH (needed for audio transcription)",
            severity="warning",
            remediation="Install FFmpeg: sudo apt install ffmpeg (Debian/Ubuntu) or brew install ffmpeg (macOS)",
            docs_link="https://ffmpeg.org/download.html",
        )
    
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        first_line = result.stdout.split("\n")[0]
        return ReadinessCheck(
            name="FFmpeg",
            passed=True,
            message=first_line,
            severity="info",
        )
    except subprocess.TimeoutExpired:
        pass
    
    return ReadinessCheck(
        name="FFmpeg",
        passed=True,
        message=f"FFmpeg found at {ffmpeg_path}",
        severity="info",
    )


def check_docker() -> ReadinessCheck:
    """Check if Docker is available (optional but recommended)."""
    docker_path = shutil.which("docker")
    
    if not docker_path:
        return ReadinessCheck(
            name="Docker",
            passed=False,
            message="Docker not found (optional but recommended for managed Postgres)",
            severity="info",
            remediation="Install Docker or use system PostgreSQL",
            docs_link="https://docs.docker.com/get-docker/",
        )
    
    # Check if docker is running
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return ReadinessCheck(
                name="Docker",
                passed=True,
                message="Docker installed and running",
                severity="info",
            )
        else:
            return ReadinessCheck(
                name="Docker",
                passed=False,
                message="Docker installed but not running",
                severity="warning",
                remediation="Start Docker service: sudo systemctl start docker",
            )
    except subprocess.TimeoutExpired:
        pass
    
    return ReadinessCheck(
        name="Docker",
        passed=True,
        message=f"Docker found at {docker_path}",
        severity="info",
    )


def check_disk_space() -> ReadinessCheck:
    """Check available disk space."""
    try:
        import shutil
        stat = shutil.disk_usage("/")
        free_gb = stat.free / (1024**3)
        total_gb = stat.total / (1024**3)
        
        if free_gb < 1:
            return ReadinessCheck(
                name="Disk Space",
                passed=False,
                message=f"Only {free_gb:.1f} GB free (critical)",
                severity="error",
                remediation="Free up disk space - Osk needs at least 1 GB for operations",
            )
        elif free_gb < 5:
            return ReadinessCheck(
                name="Disk Space",
                passed=False,
                message=f"Only {free_gb:.1f} GB free ({free_gb/total_gb*100:.0f}% of {total_gb:.0f} GB)",
                severity="warning",
                remediation="Consider freeing up space for evidence storage",
            )
        
        return ReadinessCheck(
            name="Disk Space",
            passed=True,
            message=f"{free_gb:.1f} GB free ({free_gb/total_gb*100:.0f}% of {total_gb:.0f} GB)",
            severity="info",
        )
    except Exception as e:
        return ReadinessCheck(
            name="Disk Space",
            passed=False,
            message=f"Could not check disk space: {e}",
            severity="warning",
        )


def check_memory() -> ReadinessCheck:
    """Check available memory."""
    try:
        with open("/proc/meminfo", "r") as f:
            meminfo = f.read()
        
        total_kb = 0
        available_kb = 0
        
        for line in meminfo.split("\n"):
            if line.startswith("MemTotal:"):
                total_kb = int(line.split()[1])
            elif line.startswith("MemAvailable:"):
                available_kb = int(line.split()[1])
        
        total_gb = total_kb / (1024**2)
        available_gb = available_kb / (1024**2)
        
        if total_gb < 2:
            return ReadinessCheck(
                name="Memory",
                passed=False,
                message=f"{total_gb:.1f} GB RAM (need at least 2 GB)",
                severity="error",
                remediation="Add more RAM or use a machine with at least 2 GB",
            )
        elif available_gb < 0.5:
            return ReadinessCheck(
                name="Memory",
                passed=False,
                message=f"Only {available_gb:.1f} GB RAM available ({total_gb:.1f} GB total)",
                severity="warning",
                remediation="Close other applications to free up memory",
            )
        
        return ReadinessCheck(
            name="Memory",
            passed=True,
            message=f"{available_gb:.1f} GB available / {total_gb:.1f} GB total",
            severity="info",
        )
    except Exception:
        # Non-Linux systems or error
        return ReadinessCheck(
            name="Memory",
            passed=True,
            message="Could not verify (Linux only check)",
            severity="info",
        )


def check_network_ports() -> ReadinessCheck:
    """Check if required ports are available."""
    import socket
    
    ports_to_check = [
        (8444, "HTTPS (main hub)"),
        (8080, "HTTP redirect"),
        (5432, "PostgreSQL (if using local)"),
    ]
    
    unavailable = []
    for port, description in ports_to_check:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                result = s.connect_ex(("localhost", port))
                if result == 0:
                    unavailable.append(f"{port} ({description})")
        except Exception:
            pass
    
    if unavailable:
        return ReadinessCheck(
            name="Network Ports",
            passed=False,
            message=f"Ports in use: {', '.join(unavailable)}",
            severity="warning",
            remediation="Stop services using these ports or configure Osk to use different ports",
        )
    
    return ReadinessCheck(
        name="Network Ports",
        passed=True,
        message="Required ports are available",
        severity="info",
    )


def check_tls_capable() -> ReadinessCheck:
    """Check if TLS certificates can be generated."""
    # Check if we can write to the state directory
    from .config import state_dir
    
    try:
        state_path = state_dir()
        if not state_path.exists():
            state_path.mkdir(parents=True, exist_ok=True)
        
        test_file = state_path / ".write_test"
        test_file.touch()
        test_file.unlink()
        
        return ReadinessCheck(
            name="TLS Certificate Storage",
            passed=True,
            message=f"Can write to {state_path}",
            severity="info",
        )
    except Exception as e:
        return ReadinessCheck(
            name="TLS Certificate Storage",
            passed=False,
            message=f"Cannot write to state directory: {e}",
            severity="error",
            remediation="Fix permissions on state directory or set OSK_STATE_PATH to writable location",
        )


def run_all_checks() -> ReadinessReport:
    """Run all installation readiness checks."""
    checks = [
        check_python_version(),
        check_postgres_installed(),
        check_openssl(),
        check_ffmpeg(),
        check_docker(),
        check_disk_space(),
        check_memory(),
        check_network_ports(),
        check_tls_capable(),
    ]
    
    # Determine if overall ready
    critical_failures = [c for c in checks if not c.passed and c.severity == "error"]
    overall_ready = len(critical_failures) == 0
    
    # Generate recommendations
    recommendations = []
    for check in checks:
        if not check.passed and check.remediation:
            recommendations.append(f"{check.name}: {check.remediation}")
    
    # Determine profile
    profile = determine_support_profile(checks)
    
    return ReadinessReport(
        overall_ready=overall_ready,
        checks=checks,
        profile=profile,
        recommendations=recommendations,
    )


def determine_support_profile(checks: list[ReadinessCheck]) -> str:
    """Determine the supported configuration profile."""
    check_map = {c.name: c for c in checks}
    
    # Check for ideal setup
    if all(c.passed for c in checks):
        return "supported-full"
    
    # Check for Docker-based setup (no system Postgres needed)
    if (
        check_map.get("PostgreSQL", ReadinessCheck("", False, "")).passed is False
        and check_map.get("Docker", ReadinessCheck("", False, "")).passed is True
    ):
        return "supported-docker-managed"
    
    # Check for minimal setup
    critical_checks = ["Python Version", "OpenSSL", "TLS Certificate Storage"]
    critical_passed = all(
        check_map.get(name, ReadinessCheck("", False, "")).passed
        for name in critical_checks
    )
    if critical_passed:
        return "supported-minimal"
    
    return "unsupported"


def format_report(report: ReadinessReport, json_output: bool = False) -> str:
    """Format readiness report for display."""
    if json_output:
        return json.dumps({
            "overall_ready": report.overall_ready,
            "profile": report.profile,
            "checks": [
                {
                    "name": c.name,
                    "passed": c.passed,
                    "message": c.message,
                    "severity": c.severity,
                    "remediation": c.remediation,
                }
                for c in report.checks
            ],
            "recommendations": report.recommendations,
        }, indent=2)
    
    lines = []
    lines.append("=" * 60)
    lines.append("Osk Installation Readiness Check")
    lines.append("=" * 60)
    lines.append("")
    
    # Overall status
    if report.overall_ready:
        lines.append("✅ Status: READY FOR INSTALLATION")
    else:
        lines.append("❌ Status: NOT READY - Action Required")
    lines.append(f"   Profile: {report.profile}")
    lines.append("")
    
    # Individual checks
    lines.append("Checks:")
    lines.append("-" * 60)
    
    for check in report.checks:
        icon = "✅" if check.passed else "⚠️" if check.severity == "warning" else "❌"
        lines.append(f"{icon} {check.name}")
        lines.append(f"   {check.message}")
        if not check.passed and check.remediation:
            lines.append(f"   💡 {check.remediation}")
        lines.append("")
    
    # Recommendations
    if report.recommendations:
        lines.append("-" * 60)
        lines.append("Recommendations:")
        for rec in report.recommendations:
            lines.append(f"  • {rec}")
        lines.append("")
    
    lines.append("=" * 60)
    
    return "\n".join(lines)


if __name__ == "__main__":
    # Allow running standalone for testing
    report = run_all_checks()
    print(format_report(report))
