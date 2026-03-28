"""Whisper adapter and background worker loop for transcript observations."""

from __future__ import annotations

import asyncio
import logging
import math
import re
import shutil
import subprocess
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

from osk.audio_ingest import AudioIngest
from osk.intelligence_contracts import (
    AudioChunk,
    ObservationKind,
)
from osk.intelligence_contracts import (
    Transcriber as TranscriberProtocol,
)
from osk.intelligence_pipeline import build_observation
from osk.whisper_runtime import WhisperRuntimeManager
from osk.worker_runtime import (
    ObservationCallback,
    ProcessingWorkerMetrics,
    maybe_invoke_callback,
)

logger = logging.getLogger(__name__)
COMPRESSED_AUDIO_CODECS = {
    "audio/webm",
    "video/webm",
    "audio/ogg",
    "audio/opus",
    "audio/oga",
    "audio/mp4",
    "audio/aac",
    "audio/mpeg",
    "audio/mpga",
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "audio/flac",
}


def normalize_uncertain_tokens(text: str) -> str:
    if not text:
        return text
    normalized = re.sub(r"_{2,}", "[inaudible]", text)
    normalized = re.sub(r"(?:\s*\[inaudible\]\s*){2,}", " [inaudible] ", normalized)
    return " ".join(normalized.split())


def collapse_repetition_loops(text: str) -> tuple[str, bool]:
    words = text.split()
    if len(words) < 12:
        return text, False

    def _key(parts: list[str]) -> tuple[str, ...]:
        return tuple(re.sub(r"[^a-z0-9\[\]]+", "", part.lower()) for part in parts)

    changed = False
    max_window = min(12, max(3, len(words) // 2))
    for window in range(max_window, 2, -1):
        index = 0
        while index + (window * 3) <= len(words):
            base = _key(words[index : index + window])
            if not any(base):
                index += 1
                continue

            repetitions = 1
            while index + ((repetitions + 1) * window) <= len(words):
                nxt = _key(
                    words[index + (repetitions * window) : index + ((repetitions + 1) * window)]
                )
                if nxt != base:
                    break
                repetitions += 1
            if repetitions >= 3:
                words = words[: index + window] + words[index + (repetitions * window) :]
                changed = True
                index = 0
                continue
            index += 1
    return " ".join(words), changed


def decode_audio_chunk(chunk: AudioChunk, *, ffmpeg_binary: str = "ffmpeg") -> Any:
    try:
        import numpy as np
    except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "numpy is not installed. Install the intelligence extras to decode audio chunks "
            "for Whisper."
        ) from exc

    codec = _normalize_audio_codec(chunk.codec)
    payload = chunk.payload
    if not payload:
        return np.zeros(0, dtype=np.float32)

    if codec in {"audio/pcm-s16le", "audio/raw", "audio/l16"}:
        audio = np.frombuffer(payload, dtype=np.int16).astype(np.float32)
        return audio / 32768.0

    if codec in {"audio/pcm-f32le", "audio/float32", "audio/f32le"}:
        return np.frombuffer(payload, dtype=np.float32)

    if codec in COMPRESSED_AUDIO_CODECS or codec.startswith("audio/") or codec.startswith("video/"):
        return _decode_compressed_audio_with_ffmpeg(
            payload,
            codec=codec,
            ffmpeg_binary=ffmpeg_binary,
            sample_rate_hz=chunk.sample_rate_hz,
        )

    raise ValueError(
        f"Unsupported audio codec for WhisperTranscriber: {chunk.codec!r}. "
        "Provide a custom decoder for compressed formats."
    )


def _normalize_audio_codec(codec: str | None) -> str:
    raw = str(codec or "").strip().lower()
    return raw.split(";", 1)[0].strip()


def _decode_compressed_audio_with_ffmpeg(
    payload: bytes,
    *,
    codec: str,
    ffmpeg_binary: str,
    sample_rate_hz: int,
):
    try:
        import numpy as np
    except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "numpy is not installed. Install the intelligence extras to decode audio chunks "
            "for Whisper."
        ) from exc

    ffmpeg = shutil.which(ffmpeg_binary)
    if ffmpeg is None:
        raise RuntimeError(
            f"ffmpeg binary '{ffmpeg_binary}' is not installed or not in PATH. Install "
            "ffmpeg to decode compressed audio such as WebM or Ogg uploads."
        )

    sample_rate = max(int(sample_rate_hz or 16_000), 8_000)
    timeout_seconds = 2.0 + min(10.0, max(len(payload), 1) / 500_000.0)
    cmd = [
        ffmpeg,
        "-v",
        "error",
        "-nostdin",
        "-i",
        "pipe:0",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "f32le",
        "pipe:1",
    ]
    try:
        result = subprocess.run(
            cmd,
            input=payload,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:  # pragma: no cover - defensive path
        raise RuntimeError("ffmpeg binary could not be executed.") from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError(
            f"Timed out decoding compressed audio for codec {codec!r} with ffmpeg."
        ) from exc
    except subprocess.CalledProcessError as exc:
        stderr_text = exc.stderr.decode("utf-8", errors="ignore").strip()
        detail = f" ({stderr_text})" if stderr_text else ""
        raise ValueError(f"ffmpeg could not decode codec {codec!r}{detail}") from exc

    if not result.stdout:
        return np.zeros(0, dtype=np.float32)
    return np.frombuffer(result.stdout, dtype=np.float32)


def build_audio_decoder(*, ffmpeg_binary: str) -> Callable[[AudioChunk], Any]:
    def _decoder(chunk: AudioChunk) -> Any:
        return decode_audio_chunk(chunk, ffmpeg_binary=ffmpeg_binary)

    return _decoder


class WhisperTranscriber:
    """Real Whisper-backed implementation of the transcript adapter protocol."""

    def __init__(
        self,
        *,
        runtime_manager: WhisperRuntimeManager | None = None,
        decoder: Callable[[AudioChunk], Any] | None = None,
        model_size: str = "large-v3",
        beam_size: int = 5,
        best_of: int = 5,
        vad_filter: bool = True,
        condition_on_previous_text: bool = True,
        temperature: tuple[float, ...] = (0.0, 0.2, 0.4),
        initial_prompt: str | None = None,
    ) -> None:
        self.runtime_manager = runtime_manager or WhisperRuntimeManager(model_size=model_size)
        self.decoder = decoder or decode_audio_chunk
        self.beam_size = beam_size
        self.best_of = best_of
        self.vad_filter = vad_filter
        self.condition_on_previous_text = condition_on_previous_text
        self.temperature = temperature
        self.initial_prompt = initial_prompt.strip() if initial_prompt else None
        self._context_prompt = ""
        self._context_chars = 320
        self._recent_text_for_dedupe = ""
        self._recent_chars_for_dedupe = 600
        self._last_emitted_text_norm = ""
        self._last_emitted_repeat_count = 0

    async def transcribe(self, chunk: AudioChunk):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._transcribe_sync, chunk)

    def status(self) -> dict[str, Any]:
        return {
            "adapter": "whisper-local",
            "beam_size": self.beam_size,
            "best_of": self.best_of,
            "model_size": self.runtime_manager.model_size,
            "runtime": self.runtime_manager.status(),
            "vad_filter": self.vad_filter,
        }

    def _transcribe_sync(self, chunk: AudioChunk):
        audio = self.decoder(chunk)
        prompt_parts = []
        if self.initial_prompt:
            prompt_parts.append(self.initial_prompt)
        if self._context_prompt:
            prompt_parts.append(self._context_prompt)
        prompt = " ".join(prompt_parts).strip() or None
        kwargs = {
            "beam_size": self.beam_size,
            "best_of": self.best_of,
            "temperature": self.temperature,
            "language": "en",
            "vad_filter": self.vad_filter,
            "condition_on_previous_text": self.condition_on_previous_text,
            "initial_prompt": prompt,
        }
        segments_iter, info = self.runtime_manager.transcribe_sync(audio, **kwargs)

        emitted_text: list[str] = []
        confidences: list[float] = []
        for segment in segments_iter:
            text = str(getattr(segment, "text", "") or "").strip()
            text = self._trim_overlapped_prefix(text)
            text = normalize_uncertain_tokens(text)
            text, collapsed = collapse_repetition_loops(text)
            if collapsed:
                logger.info("Collapsed repeated phrase loop in transcript segment")
            if not text:
                continue
            if self._should_drop_duplicate_segment(text):
                logger.info("Dropped duplicate transcript segment")
                continue
            emitted_text.append(text)
            confidences.append(self._segment_confidence(segment, info))

        if not emitted_text:
            return None

        combined = " ".join(emitted_text).strip()
        self._update_context(combined)
        ended_at = chunk.source.received_at
        started_at = ended_at - timedelta(milliseconds=max(chunk.duration_ms, 0))
        confidence = sum(confidences) / len(confidences) if confidences else 0.0
        language = str(getattr(info, "language", "en") or "en")
        from osk.intelligence_contracts import TranscriptResult

        return TranscriptResult(
            adapter="whisper-local",
            chunk_id=chunk.chunk_id,
            source_member_id=chunk.source.member_id,
            text=combined,
            language=language,
            confidence=max(0.0, min(confidence, 1.0)),
            started_at=started_at,
            ended_at=ended_at,
        )

    def _trim_overlapped_prefix(self, text: str) -> str:
        if not text or not self._recent_text_for_dedupe:
            return text

        previous_words = self._recent_text_for_dedupe.lower().split()
        new_words = text.split()
        if len(previous_words) < 3 or len(new_words) < 3:
            return text

        max_n = min(20, len(previous_words), len(new_words))
        overlap_n = 0
        for size in range(max_n, 2, -1):
            if previous_words[-size:] == [word.lower() for word in new_words[:size]]:
                overlap_n = size
                break
        if overlap_n == 0:
            return text
        return " ".join(new_words[overlap_n:]).strip()

    def _should_drop_duplicate_segment(self, text: str) -> bool:
        normalized = " ".join(text.lower().split())
        if not normalized:
            return True
        if normalized == self._last_emitted_text_norm:
            self._last_emitted_repeat_count += 1
            return self._last_emitted_repeat_count >= 2
        self._last_emitted_text_norm = normalized
        self._last_emitted_repeat_count = 0
        return False

    def _update_context(self, text: str) -> None:
        if not text:
            return
        merged = (self._context_prompt + " " + text).strip()
        self._context_prompt = merged[-self._context_chars :]
        merged_recent = (self._recent_text_for_dedupe + " " + text).strip()
        self._recent_text_for_dedupe = merged_recent[-self._recent_chars_for_dedupe :]

    def _segment_confidence(self, segment, info) -> float:
        if hasattr(segment, "confidence"):
            try:
                return float(getattr(segment, "confidence"))
            except (TypeError, ValueError):
                pass
        if hasattr(segment, "avg_logprob"):
            try:
                avg_logprob = float(getattr(segment, "avg_logprob"))
                return max(0.0, min(math.exp(avg_logprob), 1.0))
            except (TypeError, ValueError, OverflowError):
                pass
        if hasattr(info, "language_probability"):
            try:
                return float(getattr(info, "language_probability"))
            except (TypeError, ValueError):
                pass
        return 0.75


ArtifactCallback = Callable[[AudioChunk, str], Awaitable[None] | None]


class TranscriptionWorker:
    def __init__(
        self,
        *,
        audio_ingest: AudioIngest,
        transcriber: TranscriberProtocol,
        on_observation: ObservationCallback | None = None,
        on_artifact: ArtifactCallback | None = None,
        poll_interval_seconds: float = 0.1,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be greater than zero")

        self.audio_ingest = audio_ingest
        self.transcriber = transcriber
        self.on_observation = on_observation
        self.on_artifact = on_artifact
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
            # Write audio artifact to evidence store if callback provided
            if self.on_artifact is not None:
                await maybe_invoke_callback(self.on_artifact, chunk, str(observation.id))
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
