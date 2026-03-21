"""Background worker loop for draining audio ingest into transcript observations."""

from __future__ import annotations

import asyncio
import logging

from osk.audio_ingest import AudioIngest
from osk.intelligence_contracts import ObservationKind, Transcriber
from osk.intelligence_pipeline import build_observation
from osk.worker_runtime import ObservationCallback, ProcessingWorkerMetrics, maybe_invoke_callback

logger = logging.getLogger(__name__)


class TranscriptionWorker:
    def __init__(
        self,
        *,
        audio_ingest: AudioIngest,
        transcriber: Transcriber,
        on_observation: ObservationCallback | None = None,
        poll_interval_seconds: float = 0.1,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be greater than zero")

        self.audio_ingest = audio_ingest
        self.transcriber = transcriber
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
            chunk = await asyncio.wait_for(self.audio_ingest.get(), timeout=timeout)
        except TimeoutError:
            return False

        if chunk is None:
            return False

        started_at = asyncio.get_running_loop().time()
        self.metrics.processed_items += 1
        try:
            result = await self.transcriber.transcribe(chunk)
            if result is None:
                self.metrics.empty_results += 1
                return True

            observation = build_observation(
                kind=ObservationKind.TRANSCRIPT,
                source_member_id=chunk.source.member_id,
                summary=result.text,
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
            logger.exception("Audio transcription worker failed for chunk %s", chunk.chunk_id)
            return True
        finally:
            self.metrics.record_latency(started_at)

    def _queue_closed(self) -> bool:
        return not self.audio_ingest.is_running and self.audio_ingest.qsize() == 0
