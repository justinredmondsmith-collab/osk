#!/usr/bin/env python3
"""
Browser-based sensor validation using headless Chrome instances.

This script launches multiple headless Chrome browsers to simulate real sensor
streaming without requiring physical Chromebooks. It validates the hub's ability
to handle concurrent WebRTC connections and media streaming.

Usage:
    python scripts/browser_sensor_validation.py --sensors 5 --duration 60

Requirements:
    - Chrome/Chromium installed
    - Osk hub running locally
    - Playwright: pip install playwright && playwright install chromium
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class SensorMetrics:
    """Metrics for a single simulated sensor."""
    sensor_id: str
    connected_at: float = 0.0
    disconnected_at: float | None = None
    observations_received: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class ValidationResult:
    """Overall validation results."""
    sensor_count: int
    duration_seconds: int
    start_time: float = 0.0
    end_time: float = 0.0
    sensors: list[SensorMetrics] = field(default_factory=list)
    hub_cpu_samples: list[tuple[float, float]] = field(default_factory=list)
    hub_memory_samples: list[tuple[float, float]] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    @property
    def total_observations(self) -> int:
        return sum(s.observations_received for s in self.sensors)

    @property
    def disconnected_count(self) -> int:
        return sum(1 for s in self.sensors if s.disconnected_at is not None)

    @property
    def avg_cpu(self) -> float:
        if not self.hub_cpu_samples:
            return 0.0
        return sum(cpu for _, cpu in self.hub_cpu_samples) / len(self.hub_cpu_samples)

    @property
    def max_cpu(self) -> float:
        if not self.hub_cpu_samples:
            return 0.0
        return max((cpu for _, cpu in self.hub_cpu_samples), default=0.0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sensor_count": self.sensor_count,
            "duration_seconds": self.duration_seconds,
            "actual_duration": self.duration,
            "total_observations": self.total_observations,
            "disconnected_count": self.disconnected_count,
            "avg_cpu_percent": round(self.avg_cpu, 1),
            "max_cpu_percent": round(self.max_cpu, 1),
            "sensors": [
                {
                    "id": s.sensor_id,
                    "connected_at": s.connected_at,
                    "disconnected_at": s.disconnected_at,
                    "observations": s.observations_received,
                    "errors": s.errors,
                }
                for s in self.sensors
            ],
            "pass": self._check_pass(),
        }

    def _check_pass(self) -> bool:
        """Check if validation passes criteria."""
        if self.sensor_count <= 5:
            return self.max_cpu < 50 and self.disconnected_count == 0
        else:
            return self.max_cpu < 80 and self.disconnected_count < 2


class HubMonitor:
    """Monitor hub resource usage."""

    def __init__(self) -> None:
        self.process: subprocess.Popen | None = None
        self.samples: list[tuple[float, float, float]] = []
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        """Start monitoring hub process."""
        try:
            import psutil
        except ImportError:
            logger.warning("psutil not installed, skipping resource monitoring")
            return

        # Find hub process
        hub_pid = None
        for proc in psutil.process_iter(["pid", "cmdline"]):
            try:
                cmdline = proc.info.get("cmdline") or []
                if any("osk" in str(arg) for arg in cmdline):
                    hub_pid = proc.info["pid"]
                    break
            except Exception:
                continue

        if hub_pid is None:
            logger.warning("Could not find hub process")
            return

        self.process = psutil.Process(hub_pid)
        asyncio.create_task(self._monitor_loop())

    async def _monitor_loop(self) -> None:
        """Monitor loop."""
        while not self._stop_event.is_set():
            try:
                if self.process:
                    cpu = self.process.cpu_percent()
                    mem = self.process.memory_info().rss / (1024 * 1024)
                    self.samples.append((time.time(), cpu, mem))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                break
            await asyncio.sleep(1)

    async def stop(self) -> list[tuple[float, float]]:
        """Stop monitoring and return CPU samples."""
        self._stop_event.set()
        await asyncio.sleep(0.1)
        return [(t, cpu) for t, cpu, _ in self.samples]


class BrowserSensorSimulator:
    """Simulate a sensor using headless browser."""

    def __init__(self, sensor_id: str, hub_url: str) -> None:
        self.sensor_id = sensor_id
        self.hub_url = hub_url
        self.metrics = SensorMetrics(sensor_id=sensor_id)
        self.page: Any | None = None

    async def run(self, duration_seconds: int) -> SensorMetrics:
        """Run sensor simulation."""
        try:
            import playwright
        except ImportError:
            self.metrics.errors.append("playwright not installed")
            return self.metrics

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=True,
                args=[
                    "--use-fake-ui-for-media-stream",
                    "--use-fake-device-for-media-stream",
                    "--disable-web-security",
                ],
            )

            context = await browser.new_context(
                permissions=["camera", "microphone"],
            )
            self.page = await context.new_page()

            # Navigate to join page
            await self.page.goto(self.hub_url)
            self.metrics.connected_at = time.time()

            # Fill in sensor details
            await self.page.fill('input[name="name"]', self.sensor_id)
            await self.page.select_option('select[name="role"]', "sensor")
            await self.page.click('button[type="submit"]')

            # Wait for connection
            await asyncio.sleep(2)

            # Simulate streaming for duration
            end_time = time.time() + duration_seconds
            while time.time() < end_time:
                await asyncio.sleep(5)
                # Check if still connected (look for disconnect indicator)
                try:
                    disconnect_btn = await self.page.query_selector("text=Disconnect")
                    if not disconnect_btn:
                        self.metrics.errors.append("Lost connection")
                        break
                except Exception:
                    pass

            self.metrics.disconnected_at = time.time()
            await browser.close()

        return self.metrics


async def run_validation(
    sensor_count: int,
    duration_seconds: int,
    hub_url: str,
) -> ValidationResult:
    """Run validation with specified number of sensors."""
    result = ValidationResult(
        sensor_count=sensor_count,
        duration_seconds=duration_seconds,
    )

    # Start hub monitoring
    monitor = HubMonitor()
    await monitor.start()

    # Create and start sensors
    logger.info(f"Starting {sensor_count} browser sensors...")
    sensors = [
        BrowserSensorSimulator(f"Browser-Sensor-{i+1:02d}", hub_url)
        for i in range(sensor_count)
    ]

    result.start_time = time.time()

    # Run sensors concurrently
    tasks = [s.run(duration_seconds) for s in sensors]
    sensor_results = await asyncio.gather(*tasks, return_exceptions=True)

    result.end_time = time.time()

    # Process results
    for sr in sensor_results:
        if isinstance(sr, Exception):
            # Create failed sensor record
            failed = SensorMetrics(sensor_id="unknown")
            failed.errors.append(str(sr))
            result.sensors.append(failed)
        else:
            result.sensors.append(sr)

    # Get resource samples
    cpu_samples = await monitor.stop()
    result.hub_cpu_samples = cpu_samples

    return result


def check_prerequisites() -> bool:
    """Check if prerequisites are met."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("Error: playwright not installed.")
        print("Install with: pip install playwright && playwright install chromium")
        return False

    # Check if hub is running
    import urllib.request
    try:
        urllib.request.urlopen("http://localhost:8443", timeout=2)
    except Exception:
        print("Error: Osk hub not running at http://localhost:8443")
        print("Start with: osk start 'Test Operation'")
        return False

    return True


async def main():
    parser = argparse.ArgumentParser(description="Browser-based sensor validation")
    parser.add_argument("--sensors", type=int, default=5, help="Number of sensors (default: 5)")
    parser.add_argument("--duration", type=int, default=60, help="Test duration seconds (default: 60)")  # noqa: E501
    parser.add_argument("--hub-url", default="http://localhost:8443", help="Hub URL")
    parser.add_argument("--output", help="Output JSON file")
    parser.add_argument("--quiet", action="store_true", help="Minimal output")
    args = parser.parse_args()

    if not check_prerequisites():
        return 1

    if not args.quiet:
        print(f"Starting validation: {args.sensors} sensors for {args.duration}s")
        print(f"Hub URL: {args.hub_url}")
        print("-" * 50)

    result = await run_validation(
        sensor_count=args.sensors,
        duration_seconds=args.duration,
        hub_url=args.hub_url,
    )

    # Output results
    result_dict = result.to_dict()

    if args.output:
        Path(args.output).write_text(json.dumps(result_dict, indent=2))
        if not args.quiet:
            print(f"Results saved to: {args.output}")

    if not args.quiet:
        print("\nResults:")
        print(f"  Duration: {result.duration:.1f}s")
        print(f"  Observations: {result.total_observations}")
        print(f"  Avg CPU: {result.avg_cpu:.1f}%")
        print(f"  Max CPU: {result.max_cpu:.1f}%")
        print(f"  Disconnections: {result.disconnected_count}")
        print(f"  Status: {'PASS' if result_dict['pass'] else 'FAIL'}")

    return 0 if result_dict["pass"] else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
