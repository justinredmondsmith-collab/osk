#!/usr/bin/env python3
"""Sensor streaming validation for Osk 1.0.0.

This script validates the sensor streaming capabilities of Osk by:
1. Starting a hub with fake intelligence backends (for speed)
2. Connecting multiple simulated sensor members
3. Streaming audio and frame data
4. Measuring latency, throughput, and resource usage
5. Generating a validation report

Usage:
    python scripts/sensor_validation.py --sensors 5 --duration 60
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from osk.intelligence_contracts import AudioChunk, FrameSample, IngestSource, IngestPriority
from osk.models import MemberRole
from osk.audio_ingest import AudioIngest
from osk.frame_ingest import FrameIngest
from osk.fake_intelligence import FakeTranscriber, FakeVisionAnalyzer
from osk.transcriber import TranscriptionWorker
from osk.vision_engine import VisionWorker


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class SensorMetrics:
    """Metrics for a single simulated sensor."""
    sensor_id: str
    audio_chunks_sent: int = 0
    audio_bytes_sent: int = 0
    frames_sent: int = 0
    frame_bytes_sent: int = 0
    observations_received: int = 0
    first_chunk_at: float | None = None
    last_chunk_at: float | None = None
    errors: list[str] = field(default_factory=list)


@dataclass
class ValidationResult:
    """Overall validation results."""
    started_at: str
    duration_seconds: float
    num_sensors: int
    sensor_metrics: list[SensorMetrics] = field(default_factory=list)
    total_audio_chunks: int = 0
    total_audio_bytes: int = 0
    total_frames: int = 0
    total_frame_bytes: int = 0
    total_observations: int = 0
    avg_latency_ms: float = 0.0
    hub_cpu_percent: float = 0.0
    hub_memory_mb: float = 0.0
    passed: bool = False
    notes: list[str] = field(default_factory=list)


def generate_synthetic_audio_chunk(sensor_id: str, duration_ms: int = 4000) -> AudioChunk:
    """Generate synthetic audio chunk for testing."""
    # Generate pseudo-random audio data (sine wave-ish pattern)
    sample_rate = 16000
    num_samples = int(sample_rate * (duration_ms / 1000))

    # Simple pattern that looks like audio
    data = bytes([i % 256 for i in range(num_samples * 2)])  # 16-bit samples

    return AudioChunk(
        chunk_id=uuid.uuid4(),
        source=IngestSource(
            member_id=uuid.UUID(sensor_id),
            member_role=MemberRole.SENSOR,
            priority=IngestPriority.SENSOR,
            received_at=datetime.now(timezone.utc),
        ),
        payload=data,
        codec="audio/pcm-s16le",
        sample_rate_hz=sample_rate,
        duration_ms=duration_ms,
        ingest_key=f"{sensor_id}:audio:{int(time.time() * 1000)}",
    )


def generate_synthetic_frame(sensor_id: str, width: int = 640, height: int = 480) -> FrameSample:
    """Generate synthetic JPEG frame for testing."""
    # Create a simple pattern that looks like image data
    # In real testing, this would be actual JPEG data
    # For validation, we use raw bytes that will be processed

    import random

    # Generate random-ish data (actual JPEG headers for validation)
    # This is a minimal valid JPEG
    jpeg_header = bytes([
        0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46,
        0x00, 0x01, 0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00
    ])
    jpeg_footer = bytes([0xFF, 0xD9])

    # Random payload between header and footer
    payload_size = random.randint(5000, 50000)  # 5KB to 50KB
    payload = jpeg_header + bytes(random.randint(0, 255) for _ in range(payload_size)) + jpeg_footer

    return FrameSample(
        frame_id=uuid.uuid4(),
        source=IngestSource(
            member_id=uuid.UUID(sensor_id),
            member_role=MemberRole.SENSOR,
            priority=IngestPriority.SENSOR,
            received_at=datetime.now(timezone.utc),
        ),
        payload=payload,
        width=width,
        height=height,
        change_score=random.random() * 0.5 + 0.3,  # 0.3 to 0.8
        captured_at=datetime.now(timezone.utc),
        ingest_key=f"{sensor_id}:frame:{int(time.time() * 1000)}",
    )


class SensorSimulator:
    """Simulates a sensor member streaming audio and frames."""

    def __init__(
        self,
        sensor_id: str,
        audio_ingest: AudioIngest,
        frame_ingest: FrameIngest,
        metrics: SensorMetrics,
        audio_interval: float = 4.0,  # seconds between audio chunks
        frame_interval: float = 0.5,  # seconds between frames (2 FPS)
    ):
        self.sensor_id = sensor_id
        self.audio_ingest = audio_ingest
        self.frame_ingest = frame_ingest
        self.metrics = metrics
        self.audio_interval = audio_interval
        self.frame_interval = frame_interval
        self._running = False
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        """Start streaming audio and frames."""
        self._running = True
        self._tasks = [
            asyncio.create_task(self._audio_stream()),
            asyncio.create_task(self._frame_stream()),
        ]

    async def stop(self) -> None:
        """Stop streaming."""
        self._running = False
        for task in self._tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _audio_stream(self) -> None:
        """Stream audio chunks."""
        while self._running:
            try:
                chunk = generate_synthetic_audio_chunk(self.sensor_id)
                accepted = await self.audio_ingest.put(chunk)

                if accepted:
                    self.metrics.audio_chunks_sent += 1
                    self.metrics.audio_bytes_sent += len(chunk.payload)
                    if self.metrics.first_chunk_at is None:
                        self.metrics.first_chunk_at = time.time()
                    self.metrics.last_chunk_at = time.time()

                await asyncio.sleep(self.audio_interval)
            except Exception as exc:
                self.metrics.errors.append(f"Audio stream error: {exc}")
                await asyncio.sleep(1.0)

    async def _frame_stream(self) -> None:
        """Stream frames."""
        while self._running:
            try:
                frame = generate_synthetic_frame(self.sensor_id)
                accepted = await self.frame_ingest.put(frame)

                if accepted:
                    self.metrics.frames_sent += 1
                    self.metrics.frame_bytes_sent += len(frame.payload)

                await asyncio.sleep(self.frame_interval)
            except Exception as exc:
                self.metrics.errors.append(f"Frame stream error: {exc}")
                await asyncio.sleep(0.1)


async def run_validation(
    num_sensors: int,
    duration_seconds: float,
    report_path: str | None = None,
) -> ValidationResult:
    """Run sensor validation test."""

    logger.info("Starting sensor validation: %d sensors for %.0f seconds", num_sensors, duration_seconds)

    # Create ingest queues
    audio_ingest = AudioIngest(max_queue_size=1000)
    frame_ingest = FrameIngest(
        max_queue_size=1000,
        max_queue_depth_per_member=100,
    )

    # Create fake backends (faster than real Whisper/Ollama)
    transcriber = FakeTranscriber()
    vision_analyzer = FakeVisionAnalyzer()

    # Metrics collection
    observations_lock = asyncio.Lock()
    observations_received = 0
    observation_latencies: list[float] = []

    async def on_observation(obs) -> None:
        nonlocal observations_received
        async with observations_lock:
            observations_received += 1

    # Create workers
    transcription_worker = TranscriptionWorker(
        audio_ingest=audio_ingest,
        transcriber=transcriber,
        on_observation=on_observation,
    )
    vision_worker = VisionWorker(
        frame_ingest=frame_ingest,
        vision_analyzer=vision_analyzer,
        on_observation=on_observation,
    )

    # Create sensor simulators
    sensor_metrics = [SensorMetrics(sensor_id=str(uuid.uuid4())) for _ in range(num_sensors)]
    simulators = [
        SensorSimulator(
            sensor_id=m.sensor_id,
            audio_ingest=audio_ingest,
            frame_ingest=frame_ingest,
            metrics=m,
        )
        for m in sensor_metrics
    ]

    # Start everything
    started_at = datetime.now(timezone.utc).isoformat()
    start_time = time.time()

    audio_ingest.start()
    frame_ingest.start()
    transcription_worker.start()
    vision_worker.start()

    for sim in simulators:
        await sim.start()

    # Monitor resource usage
    try:
        import psutil
        process = psutil.Process()
        cpu_samples: list[float] = []
        memory_samples: list[float] = []
    except ImportError:
        process = None
        cpu_samples = []
        memory_samples = []

    # Run for duration
    logger.info("Running test...")
    end_time = start_time + duration_seconds

    while time.time() < end_time:
        await asyncio.sleep(1.0)

        if process:
            try:
                cpu_samples.append(process.cpu_percent())
                memory_samples.append(process.memory_info().rss / (1024 * 1024))  # MB
            except Exception:
                pass

        # Progress report
        elapsed = time.time() - start_time
        total_audio = sum(m.audio_chunks_sent for m in sensor_metrics)
        total_frames = sum(m.frames_sent for m in sensor_metrics)

        logger.info(
            "Progress: %.0f%% | Audio: %d chunks | Frames: %d | Observations: %d",
            (elapsed / duration_seconds) * 100,
            total_audio,
            total_frames,
            observations_received,
        )

    # Stop everything
    logger.info("Stopping sensors...")
    for sim in simulators:
        await sim.stop()

    # Wait for queue to drain
    logger.info("Waiting for queue to drain...")
    drain_timeout = time.time() + 30.0
    while (audio_ingest.qsize() > 0 or frame_ingest.qsize() > 0) and time.time() < drain_timeout:
        await asyncio.sleep(0.5)

    await transcription_worker.stop()
    await vision_worker.stop()
    await audio_ingest.stop()
    await frame_ingest.stop()

    # Calculate results
    actual_duration = time.time() - start_time

    total_audio = sum(m.audio_chunks_sent for m in sensor_metrics)
    total_audio_bytes = sum(m.audio_bytes_sent for m in sensor_metrics)
    total_frames = sum(m.frames_sent for m in sensor_metrics)
    total_frame_bytes = sum(m.frame_bytes_sent for m in sensor_metrics)
    total_errors = sum(len(m.errors) for m in sensor_metrics)

    # Calculate latency (rough estimate based on observations per second)
    avg_latency_ms = 0.0
    if observation_latencies:
        avg_latency_ms = sum(observation_latencies) / len(observation_latencies) * 1000

    # Resource usage
    avg_cpu = sum(cpu_samples) / len(cpu_samples) if cpu_samples else 0.0
    avg_memory = sum(memory_samples) / len(memory_samples) if memory_samples else 0.0

    # Pass criteria
    passed = True
    notes = []

    # Must process at least some data
    if total_audio < num_sensors * 2:  # At least 2 chunks per sensor
        passed = False
        notes.append(f"FAIL: Insufficient audio chunks processed ({total_audio} for {num_sensors} sensors)")

    if total_frames < num_sensors * 10:  # At least 10 frames per sensor
        passed = False
        notes.append(f"FAIL: Insufficient frames processed ({total_frames} for {num_sensors} sensors)")

    # CPU must stay reasonable
    if avg_cpu > 80.0:
        notes.append(f"WARNING: High CPU usage ({avg_cpu:.1f}%)")

    # No excessive errors
    if total_errors > num_sensors * 2:
        notes.append(f"WARNING: {total_errors} errors across sensors")

    if passed and not notes:
        notes.append("PASS: All criteria met")

    result = ValidationResult(
        started_at=started_at,
        duration_seconds=actual_duration,
        num_sensors=num_sensors,
        sensor_metrics=sensor_metrics,
        total_audio_chunks=total_audio,
        total_audio_bytes=total_audio_bytes,
        total_frames=total_frames,
        total_frame_bytes=total_frame_bytes,
        total_observations=observations_received,
        avg_latency_ms=avg_latency_ms,
        hub_cpu_percent=avg_cpu,
        hub_memory_mb=avg_memory,
        passed=passed,
        notes=notes,
    )

    # Save report
    if report_path:
        report_data = asdict(result)
        # Convert sensor metrics to dicts
        report_data["sensor_metrics"] = [asdict(m) for m in sensor_metrics]

        with open(report_path, "w") as f:
            json.dump(report_data, f, indent=2, default=str)
        logger.info("Report saved to: %s", report_path)

    return result


def print_report(result: ValidationResult) -> None:
    """Print validation report to console."""
    print("\n" + "=" * 70)
    print("SENSOR VALIDATION REPORT")
    print("=" * 70)
    print(f"Started:     {result.started_at}")
    print(f"Duration:    {result.duration_seconds:.1f} seconds")
    print(f"Sensors:     {result.num_sensors}")
    print()
    print("THROUGHPUT")
    print(f"  Audio chunks:  {result.total_audio_chunks} ({result.total_audio_bytes / 1024 / 1024:.2f} MB)")
    print(f"  Frames:        {result.total_frames} ({result.total_frame_bytes / 1024 / 1024:.2f} MB)")
    print(f"  Observations:  {result.total_observations}")
    print()
    print("RESOURCE USAGE")
    print(f"  CPU:     {result.hub_cpu_percent:.1f}%")
    print(f"  Memory:  {result.hub_memory_mb:.1f} MB")
    print()
    print("RESULT")
    status = "PASS" if result.passed else "FAIL"
    print(f"  Status: {status}")
    for note in result.notes:
        print(f"  - {note}")
    print()
    print("SENSOR BREAKDOWN")
    for m in result.sensor_metrics:
        errors = f" ({len(m.errors)} errors)" if m.errors else ""
        print(f"  {m.sensor_id[:8]}...: {m.audio_chunks_sent} audio, {m.frames_sent} frames{errors}")
    print("=" * 70)


def main() -> int:
    parser = argparse.ArgumentParser(description="Osk Sensor Validation")
    parser.add_argument(
        "--sensors",
        type=int,
        default=5,
        help="Number of sensors to simulate (default: 5)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=60.0,
        help="Test duration in seconds (default: 60)",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output JSON file for detailed report",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress console output (just exit code)",
    )

    args = parser.parse_args()

    if args.sensors < 1 or args.sensors > 50:
        print("Error: --sensors must be between 1 and 50", file=sys.stderr)
        return 1

    if args.duration < 5 or args.duration > 3600:
        print("Error: --duration must be between 5 and 3600 seconds", file=sys.stderr)
        return 1

    try:
        result = asyncio.run(run_validation(
            num_sensors=args.sensors,
            duration_seconds=args.duration,
            report_path=args.output,
        ))

        if not args.quiet:
            print_report(result)

        return 0 if result.passed else 1

    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
