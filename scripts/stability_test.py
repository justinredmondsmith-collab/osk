#!/usr/bin/env python3
"""
1-hour stability test for Osk hub with real device connection.

Usage:
    # Terminal 1: Start this script
    python scripts/stability_test.py --duration 3600 --output stability-report.json
    
    # Terminal 2: Join Chromebook as sensor when prompted
    # Then let it run for the full duration

The test will:
1. Monitor hub CPU/memory continuously
2. Track observation generation rate
3. Detect connection drops/reconnects
4. Monitor for errors in logs
5. Generate comprehensive report
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class StabilityMetrics:
    """Metrics collected during stability test."""
    start_time: float = 0.0
    end_time: float = 0.0
    
    # CPU/Memory samples: (timestamp, cpu_percent, memory_mb)
    resource_samples: list[tuple[float, float, float]] = field(default_factory=list)
    
    # Observation counts over time
    observation_samples: list[tuple[float, int]] = field(default_factory=list)
    
    # Member connection events: (timestamp, member_id, event_type)
    connection_events: list[tuple[float, str, str]] = field(default_factory=list)
    
    # Errors detected
    errors: list[tuple[float, str]] = field(default_factory=list)
    
    # Test configuration
    duration_seconds: int = 3600
    target_sensors: int = 1
    
    def to_dict(self) -> dict[str, Any]:
        duration = self.end_time - self.start_time if self.end_time else 0
        
        # Calculate statistics
        if self.resource_samples:
            cpus = [cpu for _, cpu, _ in self.resource_samples]
            mems = [mem for _, _, mem in self.resource_samples]
            avg_cpu = sum(cpus) / len(cpus)
            max_cpu = max(cpus)
            avg_mem = sum(mems) / len(mems)
            max_mem = max(mems)
        else:
            avg_cpu = max_cpu = avg_mem = max_mem = 0
        
        # Observation rate
        if len(self.observation_samples) >= 2:
            first_time, first_count = self.observation_samples[0]
            last_time, last_count = self.observation_samples[-1]
            time_diff = last_time - first_time
            count_diff = last_count - first_count
            obs_rate = (count_diff / time_diff * 60) if time_diff > 0 else 0
        else:
            obs_rate = 0
        
        # Connection stability
        disconnects = sum(1 for _, _, event in self.connection_events if event == "disconnect")
        reconnects = sum(1 for _, _, event in self.connection_events if event == "reconnect")
        
        return {
            "test_config": {
                "duration_seconds": self.duration_seconds,
                "target_sensors": self.target_sensors,
                "actual_duration": duration,
            },
            "timestamps": {
                "start": datetime.fromtimestamp(self.start_time).isoformat(),
                "end": datetime.fromtimestamp(self.end_time).isoformat() if self.end_time else None,
            },
            "resource_usage": {
                "avg_cpu_percent": round(avg_cpu, 2),
                "max_cpu_percent": round(max_cpu, 2),
                "avg_memory_mb": round(avg_mem, 2),
                "max_memory_mb": round(max_mem, 2),
                "sample_count": len(self.resource_samples),
            },
            "observations": {
                "total": self.observation_samples[-1][1] if self.observation_samples else 0,
                "rate_per_minute": round(obs_rate, 2),
                "sample_count": len(self.observation_samples),
            },
            "connection_stability": {
                "disconnects": disconnects,
                "reconnects": reconnects,
                "events": [
                    {"time": datetime.fromtimestamp(t).isoformat(), "member": m, "event": e}
                    for t, m, e in self.connection_events
                ],
            },
            "errors": [
                {"time": datetime.fromtimestamp(t).isoformat(), "message": msg}
                for t, msg in self.errors
            ],
            "pass": self._check_pass(),
        }
    
    def _check_pass(self) -> bool:
        """Check if stability test passes criteria."""
        if not self.resource_samples:
            return False
        
        cpus = [cpu for _, cpu, _ in self.resource_samples]
        max_cpu = max(cpus)
        avg_cpu = sum(cpus) / len(cpus)
        
        # Criteria for 1 sensor over 1 hour
        return (
            max_cpu < 30  # Should be well under 50% even for 1 sensor
            and avg_cpu < 15
            and sum(1 for _, _, e in self.connection_events if e == "disconnect") <= 2
            and len(self.errors) == 0
        )


class StabilityTest:
    """Run 1-hour stability test."""
    
    def __init__(self, duration_seconds: int, target_sensors: int):
        self.duration = duration_seconds
        self.target_sensors = target_sensors
        self.metrics = StabilityMetrics(
            duration_seconds=duration_seconds,
            target_sensors=target_sensors,
        )
        self._stop_event = asyncio.Event()
        self._hub_pid: int | None = None
        
    async def run(self) -> StabilityMetrics:
        """Run the stability test."""
        logger.info("=" * 60)
        logger.info("OSK 1-HOUR STABILITY TEST")
        logger.info("=" * 60)
        logger.info(f"Duration: {self.duration} seconds ({self.duration/60:.0f} minutes)")
        logger.info(f"Target sensors: {self.target_sensors}")
        logger.info("")
        logger.info("PREPARATION:")
        logger.info("1. Ensure hub is running: osk start 'Stability Test'")
        logger.info("2. Join Chromebook as sensor when prompted")
        logger.info("3. Test will auto-start when sensor detected")
        logger.info("")
        
        # Wait for hub
        if not await self._wait_for_hub():
            logger.error("Hub not running. Start with: osk start 'Stability Test'")
            return self.metrics
        
        # Wait for sensors
        logger.info("Waiting for sensor connection...")
        if not await self._wait_for_sensors():
            logger.error(f"Target: {self.target_sensors} sensors. Please join Chromebook.")
            return self.metrics
        
        # Run test
        self.metrics.start_time = time.time()
        logger.info("")
        logger.info("=" * 60)
        logger.info("STABILITY TEST STARTED")
        logger.info("DO NOT DISCONNECT - Running for 1 hour")
        logger.info("=" * 60)
        logger.info("")
        
        # Start monitoring tasks
        tasks = [
            asyncio.create_task(self._monitor_resources()),
            asyncio.create_task(self._monitor_observations()),
            asyncio.create_task(self._monitor_connections()),
            asyncio.create_task(self._monitor_logs()),
            asyncio.create_task(self._progress_display()),
        ]
        
        # Wait for duration or stop signal
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=self.duration)
        except asyncio.TimeoutError:
            pass  # Expected - test completed
        
        # Cancel monitoring tasks
        for task in tasks:
            task.cancel()
        
        self.metrics.end_time = time.time()
        
        logger.info("")
        logger.info("=" * 60)
        logger.info("STABILITY TEST COMPLETED")
        logger.info("=" * 60)
        
        return self.metrics
    
    async def _wait_for_hub(self, timeout: int = 30) -> bool:
        """Wait for hub to be running."""
        start = time.time()
        while time.time() - start < timeout:
            try:
                result = subprocess.run(
                    ["osk", "status", "--json"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    # Find JSON in output (skip log lines)
                    output = result.stdout
                    json_start = output.find('{')
                    if json_start >= 0:
                        data = json.loads(output[json_start:])
                        # Hub is running if operation_id exists and pid is present
                        if data.get("operation_id") and data.get("pid"):
                            self._hub_pid = data.get("pid")
                            logger.info(f"Hub detected (PID: {self._hub_pid})")
                            return True
            except Exception as exc:
                logger.debug(f"Hub check failed: {exc}")
            await asyncio.sleep(1)
        return False
    
    async def _wait_for_sensors(self, timeout: int = 120) -> bool:
        """Wait for target number of sensors to connect."""
        start = time.time()
        while time.time() - start < timeout:
            try:
                result = subprocess.run(
                    ["osk", "status", "--json"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    # Find JSON in output (skip log lines)
                    output = result.stdout
                    json_start = output.find('{')
                    if json_start >= 0:
                        data = json.loads(output[json_start:])
                        members = data.get("members", [])
                        sensor_count = sum(1 for m in members if m.get("role") == "sensor")
                        if sensor_count >= self.target_sensors:
                            logger.info(f"✓ {sensor_count} sensor(s) connected")
                            for m in members:
                                if m.get("role") == "sensor":
                                    name = m.get('name', 'unknown')
                                    mid = m.get('id', 'unknown')[:8]
                                    logger.info(f"  - {name} ({mid}...)")
                            return True
                        logger.info(f"Waiting... {sensor_count}/{self.target_sensors} sensors")
            except Exception as exc:
                logger.debug(f"Sensor check failed: {exc}")
            await asyncio.sleep(5)
        return False
    
    async def _monitor_resources(self) -> None:
        """Monitor hub CPU and memory."""
        try:
            import psutil
        except ImportError:
            logger.warning("psutil not installed, resource monitoring disabled")
            return
        
        if not self._hub_pid:
            return
        
        try:
            process = psutil.Process(self._hub_pid)
        except psutil.NoSuchProcess:
            logger.error("Hub process not found")
            self.metrics.errors.append((time.time(), "Hub process disappeared"))
            return
        
        while not self._stop_event.is_set():
            try:
                cpu = process.cpu_percent()
                mem = process.memory_info().rss / (1024 * 1024)
                self.metrics.resource_samples.append((time.time(), cpu, mem))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                self.metrics.errors.append((time.time(), "Lost access to hub process"))
                break
            await asyncio.sleep(5)  # Sample every 5 seconds
    
    async def _monitor_observations(self) -> None:
        """Monitor observation count."""
        last_count = 0
        while not self._stop_event.is_set():
            try:
                # Try to get observation count from status
                result = subprocess.run(
                    ["osk", "status", "--json"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    # Find JSON in output (skip log lines)
                    output = result.stdout
                    json_start = output.find('{')
                    if json_start >= 0:
                        data = json.loads(output[json_start:])
                        # Count observations across members
                        members = data.get("members", [])
                        obs_count = sum(len(m.get("observations", [])) for m in members)
                        if obs_count > last_count:
                            self.metrics.observation_samples.append((time.time(), obs_count))
                            last_count = obs_count
            except Exception:
                pass
            await asyncio.sleep(10)  # Check every 10 seconds
    
    async def _monitor_connections(self) -> None:
        """Monitor member connections/disconnections."""
        connected_members: set[str] = set()
        
        while not self._stop_event.is_set():
            try:
                result = subprocess.run(
                    ["osk", "status", "--json"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    # Find JSON in output (skip log lines)
                    output = result.stdout
                    json_start = output.find('{')
                    if json_start < 0:
                        await asyncio.sleep(5)
                        continue
                    data = json.loads(output[json_start:])
                    members = data.get("members", [])
                    current_ids = {m.get("id") for m in members if m.get("connected")}
                    
                    # Detect disconnects
                    for member_id in connected_members - current_ids:
                        self.metrics.connection_events.append(
                            (time.time(), member_id, "disconnect")
                        )
                        logger.warning(f"Member disconnected: {member_id[:8]}...")
                    
                    # Detect reconnects
                    for member_id in current_ids - connected_members:
                        self.metrics.connection_events.append(
                            (time.time(), member_id, "reconnect")
                        )
                        logger.info(f"Member reconnected: {member_id[:8]}...")
                    
                    connected_members = current_ids
            except Exception:
                pass
            await asyncio.sleep(5)  # Check every 5 seconds
    
    async def _monitor_logs(self) -> None:
        """Monitor hub logs for errors."""
        log_path = Path.home() / ".local" / "state" / "osk" / "hub.log"
        if not log_path.exists():
            return
        
        # Get initial size
        last_size = log_path.stat().st_size
        
        while not self._stop_event.is_set():
            try:
                current_size = log_path.stat().st_size
                if current_size > last_size:
                    with log_path.open("r") as f:
                        f.seek(last_size)
                        new_lines = f.read()
                        
                        # Check for errors
                        for line in new_lines.split("\n"):
                            if "ERROR" in line or "CRITICAL" in line:
                                self.metrics.errors.append((time.time(), line.strip()))
                                logger.error(f"Log error: {line.strip()[:100]}")
                            elif "WARNING" in line and "queue" in line.lower():
                                logger.warning(f"Queue warning: {line.strip()[:100]}")
                    
                    last_size = current_size
            except Exception:
                pass
            await asyncio.sleep(10)  # Check every 10 seconds
    
    async def _progress_display(self) -> None:
        """Display progress updates."""
        start = time.time()
        next_update = start + 300  # First update at 5 minutes
        
        while not self._stop_event.is_set():
            await asyncio.sleep(1)
            now = time.time()
            elapsed = now - start
            
            if now >= next_update:
                remaining = self.duration - elapsed
                pct = (elapsed / self.duration) * 100
                
                # Get current stats
                if self.metrics.resource_samples:
                    last_cpu = self.metrics.resource_samples[-1][1]
                    last_mem = self.metrics.resource_samples[-1][2]
                    logger.info(
                        f"Progress: {pct:.0f}% ({elapsed/60:.0f}m elapsed, "
                        f"{remaining/60:.0f}m remaining) | "
                        f"CPU: {last_cpu:.1f}% | Mem: {last_mem:.0f}MB"
                    )
                else:
                    logger.info(f"Progress: {pct:.0f}% ({elapsed/60:.0f}m elapsed)")
                
                next_update = now + 300  # Update every 5 minutes
    
    def stop(self) -> None:
        """Stop the test early."""
        logger.info("Stopping test...")
        self._stop_event.set()


async def main():
    parser = argparse.ArgumentParser(description="1-hour stability test for Osk")
    parser.add_argument("--duration", type=int, default=3600, help="Test duration seconds (default: 3600)")  # noqa: E501
    parser.add_argument("--sensors", type=int, default=1, help="Target sensor count (default: 1)")
    parser.add_argument("--output", help="Output JSON file for report")
    args = parser.parse_args()
    
    test = StabilityTest(duration_seconds=args.duration, target_sensors=args.sensors)
    
    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        test.stop()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Run test
    metrics = await test.run()
    
    # Generate report
    report = metrics.to_dict()
    
    # Print summary
    print("\n" + "=" * 60)
    print("STABILITY TEST SUMMARY")
    print("=" * 60)
    print(f"Duration: {report['test_config']['actual_duration']/60:.1f} minutes")
    print("Resource Usage:")
    print(f"  Avg CPU: {report['resource_usage']['avg_cpu_percent']:.1f}%")
    print(f"  Max CPU: {report['resource_usage']['max_cpu_percent']:.1f}%")
    print(f"  Avg Memory: {report['resource_usage']['avg_memory_mb']:.1f} MB")
    print(f"  Max Memory: {report['resource_usage']['max_memory_mb']:.1f} MB")
    print(f"Observations: {report['observations']['total']} total, "
          f"{report['observations']['rate_per_minute']:.1f}/min")
    print(f"Connection Events: {report['connection_stability']['disconnects']} disconnects, "
          f"{report['connection_stability']['reconnects']} reconnects")
    print(f"Errors: {len(report['errors'])}")
    print(f"Status: {'PASS' if report['pass'] else 'FAIL'}")
    print("=" * 60)
    
    # Save report
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(json.dumps(report, indent=2))
        print(f"\nFull report saved to: {output_path}")
    
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
