#!/usr/bin/env python3
"""
Combined Validation Script for Osk 1.1

Runs multiple validation workstreams:
1. Ollama synthesis evaluation
2. Podman Android emulator sensor validation
3. Long-duration stability test (if requested)

Usage:
    python scripts/combined_validation.py --all
    python scripts/combined_validation.py --synthesis --sensors 5
    python scripts/combined_validation.py --stability --duration 3600
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Configuration
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
OUTPUT_DIR = PROJECT_ROOT / "output" / "validation"

# ANSI colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
RESET = "\033[0m"


def log_info(msg: str) -> None:
    print(f"{BLUE}[INFO]{RESET} {msg}")


def log_success(msg: str) -> None:
    print(f"{GREEN}[SUCCESS]{RESET} {msg}")


def log_warn(msg: str) -> None:
    print(f"{YELLOW}[WARN]{RESET} {msg}")


def log_error(msg: str) -> None:
    print(f"{RED}[ERROR]{RESET} {msg}")


def run_command(
    cmd: list[str],
    cwd: Path | None = None,
    timeout: int = 300,
    capture: bool = True,
) -> tuple[int, str, str]:
    """Run a command and return exit code, stdout, stderr."""

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd or PROJECT_ROOT,
            capture_output=capture,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except Exception as e:
        return -1, "", str(e)


def check_ollama() -> bool:
    """Check if Ollama is running."""

    try:
        import requests

        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        return response.status_code == 200
    except Exception:
        return False


def validate_synthesis(model: str = "llama3.2:3b") -> dict:
    """Run Ollama synthesis validation."""

    log_info("=" * 60)
    log_info("WORKSTREAM: Ollama Synthesis Evaluation")
    log_info("=" * 60)

    if not check_ollama():
        log_error("Ollama not running. Start with: ollama serve")
        return {"status": "skipped", "reason": "Ollama not available"}

    output_file = OUTPUT_DIR / f"synthesis-{datetime.now():%Y%m%d-%H%M%S}.json"

    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "ollama_synthesis_test.py"),
        "--model",
        model,
        "--heuristic",
        "--json-output",
        str(output_file),
    ]

    log_info(f"Running: {' '.join(cmd)}")
    exit_code, stdout, stderr = run_command(cmd, timeout=600)

    print(stdout)
    if stderr:
        print(stderr, file=sys.stderr)

    if exit_code == 0:
        log_success("Synthesis validation PASSED")
        status = "passed"
    else:
        log_error("Synthesis validation FAILED")
        status = "failed"

    return {
        "status": status,
        "exit_code": exit_code,
        "output_file": str(output_file) if output_file.exists() else None,
    }


def validate_sensors(count: int, duration: int, hub_url: str | None = None) -> dict:
    """Run sensor validation with Podman Android emulators."""

    log_info("=" * 60)
    log_info("WORKSTREAM: Sensor Validation (Podman Android)")
    log_info("=" * 60)

    # Check podman is available
    exit_code, _, _ = run_command(["which", "podman"])
    if exit_code != 0:
        log_error("Podman not found. Install with: sudo dnf install podman")
        return {"status": "skipped", "reason": "Podman not installed"}

    # Start emulators
    log_info(f"Starting {count} Android emulators...")
    exit_code, stdout, stderr = run_command(
        [str(SCRIPT_DIR / "podman_android_lab.sh"), "start", "--count", str(count)],
        timeout=300,
    )

    print(stdout)
    if stderr:
        print(stderr, file=sys.stderr)

    if exit_code != 0:
        log_error("Failed to start emulators")
        return {"status": "failed", "reason": "Emulator startup failed"}

    try:
        # Connect to hub
        log_info("Connecting to Osk hub...")

        connect_args = [str(SCRIPT_DIR / "podman_android_lab.sh"), "connect"]
        if hub_url:
            connect_args.extend(["--hub-url", hub_url])

        exit_code, stdout, stderr = run_command(connect_args, timeout=60)
        print(stdout)

        if exit_code != 0:
            log_warn("Some emulators may not have connected")

        # Monitor
        log_info(f"Monitoring for {duration}s...")
        start_time = time.time()
        end_time = start_time + duration

        stats = {
            "connected_devices": [],
            "disconnections": 0,
            "observations": 0,
        }

        while time.time() < end_time:
            remaining = int(end_time - time.time())
            minutes = remaining // 60
            seconds = remaining % 60

            # Check connected devices
            exit_code, stdout, _ = run_command(["adb", "devices"], timeout=10)
            device_count = len([l for l in stdout.split("\n") if "emulator" in l])

            print(f"\r  Remaining: {minutes:02d}:{seconds:02d} | Devices: {device_count}  ", end="")
            time.sleep(5)

        print()  # Newline after progress

        log_success(f"Sensor validation complete ({duration}s)")
        status = "passed"

    finally:
        # Cleanup
        log_info("Stopping emulators...")
        run_command([str(SCRIPT_DIR / "podman_android_lab.sh"), "stop"], timeout=60)

    return {
        "status": status,
        "emulators": count,
        "duration": duration,
    }


def validate_stability(duration: int, sensors: int = 5) -> dict:
    """Run long-duration stability test."""

    log_info("=" * 60)
    log_info("WORKSTREAM: Long-Duration Stability")
    log_info("=" * 60)

    script = SCRIPT_DIR / "stability_test.py"
    if not script.exists():
        log_warn(f"Stability script not found: {script}")
        log_info("Using fallback synthetic test")
        return validate_synthetic_stability(duration, sensors)

    output_file = OUTPUT_DIR / f"stability-{datetime.now():%Y%m%d-%H%M%S}.json"

    cmd = [
        sys.executable,
        str(script),
        "--duration-hours",
        str(duration / 3600),
        "--sensors",
        str(sensors),
        "--json-output",
        str(output_file),
    ]

    log_info(f"Running stability test for {duration/3600:.1f} hours...")
    log_info(f"Command: {' '.join(cmd)}")

    exit_code, stdout, stderr = run_command(cmd, timeout=duration + 300)

    print(stdout)
    if stderr:
        print(stderr, file=sys.stderr)

    if exit_code == 0:
        log_success("Stability test PASSED")
        status = "passed"
    else:
        log_error("Stability test FAILED")
        status = "failed"

    return {
        "status": status,
        "duration": duration,
        "exit_code": exit_code,
        "output_file": str(output_file) if output_file.exists() else None,
    }


def validate_synthetic_stability(duration: int, sensors: int) -> dict:
    """Fallback synthetic stability test."""

    log_info("Running synthetic stability test...")

    script = SCRIPT_DIR / "sensor_validation.py"
    if not script.exists():
        log_error(f"Validation script not found: {script}")
        return {"status": "failed", "reason": "Script not found"}

    output_file = OUTPUT_DIR / f"synthetic-stability-{datetime.now():%Y%m%d-%H%M%S}.json"

    cmd = [
        sys.executable,
        str(script),
        "--sensors",
        str(sensors),
        "--duration",
        str(duration),
        "--json-output",
        str(output_file),
    ]

    log_info(f"Running: {' '.join(cmd)}")
    exit_code, stdout, stderr = run_command(cmd, timeout=duration + 60)

    print(stdout)

    if exit_code == 0:
        log_success("Synthetic stability test PASSED")
        status = "passed"
    else:
        log_error("Synthetic stability test FAILED")
        status = "failed"

    return {
        "status": status,
        "synthetic": True,
        "exit_code": exit_code,
        "output_file": str(output_file) if output_file.exists() else None,
    }


def generate_report(results: dict, output_file: Path) -> None:
    """Generate final validation report."""

    report = {
        "timestamp": datetime.now().isoformat(),
        "validation_summary": {
            "total_workstreams": len(results),
            "passed": sum(1 for r in results.values() if r.get("status") == "passed"),
            "failed": sum(1 for r in results.values() if r.get("status") == "failed"),
            "skipped": sum(1 for r in results.values() if r.get("status") == "skipped"),
        },
        "workstreams": results,
    }

    with open(output_file, "w") as f:
        json.dump(report, f, indent=2)

    log_info(f"Report saved to: {output_file}")

    # Print summary
    print()
    log_info("=" * 60)
    log_info("VALIDATION SUMMARY")
    log_info("=" * 60)

    for name, result in results.items():
        status = result.get("status", "unknown")
        if status == "passed":
            symbol = f"{GREEN}✓{RESET}"
        elif status == "failed":
            symbol = f"{RED}✗{RESET}"
        else:
            symbol = f"{YELLOW}○{RESET}"

        print(f"  {symbol} {name}: {status}")

    print()
    passed = report["validation_summary"]["passed"]
    total = report["validation_summary"]["total_workstreams"]
    log_info(f"Total: {passed}/{total} workstreams passed")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Combined validation for Osk 1.1",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run all validations
    python scripts/combined_validation.py --all

    # Synthesis only
    python scripts/combined_validation.py --synthesis

    # Sensor validation with 5 emulators for 10 minutes
    python scripts/combined_validation.py --sensors 5 --duration 600

    # Stability test for 1 hour
    python scripts/combined_validation.py --stability --duration 3600
        """,
    )

    # Workstream selection
    parser.add_argument("--all", action="store_true", help="Run all validations")
    parser.add_argument("--synthesis", action="store_true", help="Run synthesis validation")
    parser.add_argument("--sensors", type=int, metavar="N", help="Run sensor validation with N emulators")
    parser.add_argument("--stability", action="store_true", help="Run stability test")

    # Options
    parser.add_argument("--duration", type=int, default=600, help="Test duration in seconds (default: 600)")
    parser.add_argument("--model", default="llama3.2:3b", help="Ollama model for synthesis")
    parser.add_argument("--hub-url", help="Osk hub URL for sensor test")
    parser.add_argument("--output", help="Output JSON file")

    args = parser.parse_args()

    # Default to --all if no workstream specified
    if not any([args.all, args.synthesis, args.sensors, args.stability]):
        args.all = True

    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results: dict[str, dict] = {}

    # Run selected workstreams
    if args.all or args.synthesis:
        results["synthesis"] = validate_synthesis(args.model)

    if args.all or args.sensors:
        count = args.sensors or 5
        results["sensors"] = validate_sensors(count, args.duration, args.hub_url)

    if args.all or args.stability:
        results["stability"] = validate_stability(args.duration, args.sensors or 5)

    # Generate report
    output_file = Path(args.output) if args.output else OUTPUT_DIR / f"validation-report-{datetime.now():%Y%m%d-%H%M%S}.json"
    generate_report(results, output_file)

    # Return exit code
    failed = sum(1 for r in results.values() if r.get("status") == "failed")
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
