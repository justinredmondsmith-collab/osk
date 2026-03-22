"""Ollama vision adapter and background worker loop for observations."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any

from osk.frame_ingest import FrameIngest
from osk.intelligence_contracts import FrameSample, ObservationKind, VisionAnalyzer
from osk.intelligence_pipeline import build_observation
from osk.worker_runtime import ObservationCallback, ProcessingWorkerMetrics, maybe_invoke_callback

logger = logging.getLogger(__name__)

DEFAULT_VISION_PROMPT = (
    "Describe the most operationally relevant visual observation in this frame in one or two "
    "plain-English sentences. If the frame offers no useful visual signal, "
    "return an empty response."
)


class OllamaVisionAnalyzer:
    """Real Ollama-backed implementation of the vision adapter protocol."""

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:11434",
        model: str = "llava:13b",
        prompt: str = DEFAULT_VISION_PROMPT,
        timeout_seconds: float = 20.0,
        client: Any | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.prompt = prompt
        self.timeout_seconds = max(1.0, timeout_seconds)
        self._client = client
        self._owns_client = client is None

    async def analyze(self, frame: FrameSample):
        if not frame.payload:
            return None

        client = await self._get_client()
        payload = {
            "model": self.model,
            "prompt": self.prompt,
            "stream": False,
            "images": [base64.b64encode(frame.payload).decode("ascii")],
            "options": {"temperature": 0},
        }
        response = await client.post(f"{self.base_url}/api/generate", json=payload)
        response.raise_for_status()
        data = response.json()
        raw = str(data.get("response", "")).strip()
        summary, tags = self._parse_vision_response(raw)
        if not summary:
            return None

        from osk.intelligence_contracts import VisionResult

        confidence = min(0.95, 0.55 + max(0.0, min(frame.change_score, 1.0)) * 0.4)
        return VisionResult(
            adapter="ollama-vision",
            frame_id=frame.frame_id,
            source_member_id=frame.source.member_id,
            summary=summary,
            tags=tags,
            confidence=confidence,
            captured_at=frame.captured_at,
        )

    def status(self) -> dict[str, object]:
        return {
            "adapter": "ollama-vision",
            "base_url": self.base_url,
            "model": self.model,
            "timeout_seconds": self.timeout_seconds,
        }

    async def close(self) -> None:
        if self._client is None or not self._owns_client:
            return
        await self._client.aclose()
        self._client = None

    async def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            import httpx
        except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError(
                "httpx is not installed. Install the intelligence extras to use "
                "OllamaVisionAnalyzer."
            ) from exc
        self._client = httpx.AsyncClient(timeout=self.timeout_seconds)
        return self._client

    def _parse_vision_response(self, raw: str) -> tuple[str, list[str]]:
        text = (raw or "").strip()
        if text.startswith("```"):
            lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
            text = "\n".join(lines).strip()
        if not text:
            return "", []

        for candidate in (text, text.replace("'", '"')):
            try:
                payload = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            summary, tags = self._normalize_payload(payload)
            if summary:
                return summary, tags
        return " ".join(text.split()), []

    def _normalize_payload(self, payload: Any) -> tuple[str, list[str]]:
        if isinstance(payload, dict):
            summary = str(
                payload.get("summary") or payload.get("detail") or payload.get("response") or ""
            ).strip()
            tags = self._coerce_tags(payload.get("tags"))
            return summary, tags
        if isinstance(payload, list):
            details: list[str] = []
            tags: list[str] = []
            for item in payload:
                if not isinstance(item, dict):
                    continue
                detail = str(
                    item.get("detail") or item.get("summary") or item.get("text") or ""
                ).strip()
                if detail:
                    details.append(detail)
                event_type = str(item.get("event_type") or "").strip()
                if event_type:
                    tags.append(event_type)
            if not details:
                return "", []
            deduped_tags = list(dict.fromkeys(tags))
            return "; ".join(details[:3]), deduped_tags
        return "", []

    def _coerce_tags(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]


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
