"""Background worker loop for draining frame ingest into vision observations."""

from __future__ import annotations

import asyncio
import logging

from osk.frame_ingest import FrameIngest
from osk.intelligence_contracts import ObservationKind, VisionAnalyzer
from osk.intelligence_pipeline import build_observation
from osk.worker_runtime import ObservationCallback, ProcessingWorkerMetrics, maybe_invoke_callback

logger = logging.getLogger(__name__)


class VisionWorker:
    def __init__(
        self,
        *,
        frame_ingest: FrameIngest,
        vision_analyzer: VisionAnalyzer,
        on_observation: ObservationCallback | None = None,
        poll_interval_seconds: float = 0.1,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be greater than zero")

        self.frame_ingest = frame_ingest
        self.vision_analyzer = vision_analyzer
        self.on_observation = on_observation
        self.poll_interval_seconds = poll_interval_seconds
        self.metrics = ProcessingWorkerMetrics()
        self._running = False
        self._task: asyncio.Task[None] | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> asyncio.Task[None]:
        if self.running and self._task is not None:
            return self._task

        self._running = True
        self._task = asyncio.create_task(self.run())
        return self._task

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            await self._task

    async def run(self) -> None:
        try:
            while True:
                processed = await self.process_next(timeout_seconds=self.poll_interval_seconds)
                if processed:
                    continue
                if self._queue_closed() or not self._running:
                    return
        finally:
            self._running = False
            self._task = None

    async def process_next(self, *, timeout_seconds: float | None = None) -> bool:
        timeout = timeout_seconds if timeout_seconds is not None else self.poll_interval_seconds
        try:
            frame = await asyncio.wait_for(self.frame_ingest.get(), timeout=timeout)
        except TimeoutError:
            return False

        if frame is None:
            return False

        started_at = asyncio.get_running_loop().time()
        self.metrics.processed_items += 1
        try:
            result = await self.vision_analyzer.analyze(frame)
            if result is None:
                self.metrics.empty_results += 1
                return True

            observation = build_observation(
                kind=ObservationKind.VISION,
                source_member_id=frame.source.member_id,
                summary=result.summary,
                confidence=result.confidence,
                result=result,
            )
            await maybe_invoke_callback(self.on_observation, observation)
            self.metrics.emitted_observations += 1
            self.metrics.last_error = None
            return True
        except Exception as exc:
            self.metrics.errors += 1
            self.metrics.last_error = str(exc)
            logger.exception("Vision worker failed for frame %s", frame.frame_id)
            return True
        finally:
            self.metrics.record_latency(started_at)

    def _queue_closed(self) -> bool:
        return not self.frame_ingest.is_running and self.frame_ingest.qsize() == 0
