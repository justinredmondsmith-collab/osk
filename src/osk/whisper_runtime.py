"""Adaptive runtime manager for local faster-whisper usage."""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Sequence

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class WhisperProfile:
    model: str
    device: str
    compute_type: str

    @property
    def label(self) -> str:
        return f"{self.model}:{self.device}:{self.compute_type}"


def _parse_profile_ladder(raw: str | None) -> list[WhisperProfile]:
    if not raw:
        return []

    profiles: list[WhisperProfile] = []
    for part in raw.split(","):
        token = part.strip()
        if not token:
            continue
        pieces = [piece.strip() for piece in token.split(":")]
        if len(pieces) != 3:
            logger.warning("Ignoring invalid WHISPER_PROFILE_LADDER token: %s", token)
            continue
        profiles.append(WhisperProfile(*pieces))
    return profiles


def _is_cuda_oom(exc: Exception) -> bool:
    message = str(exc).lower()
    return "cuda" in message and "out of memory" in message


def _default_profiles(model_size: str) -> list[WhisperProfile]:
    return [
        WhisperProfile(model_size, "cuda", "float16"),
        WhisperProfile(model_size, "cuda", "int8_float16"),
        WhisperProfile("medium", "cuda", "float16"),
        WhisperProfile("medium", "cuda", "int8_float16"),
        WhisperProfile("small", "cuda", "int8"),
        WhisperProfile(model_size, "cpu", "int8"),
    ]


class WhisperRuntimeManager:
    """Load and reuse a faster-whisper model with simple fallback handling."""

    def __init__(
        self,
        model_size: str = "large-v3",
        *,
        profiles: Sequence[WhisperProfile] | None = None,
        model_factory: Callable[[WhisperProfile], Any] | None = None,
    ) -> None:
        profile_ladder = list(
            profiles or _parse_profile_ladder(os.getenv("WHISPER_PROFILE_LADDER"))
        )
        self._profiles = profile_ladder or _default_profiles(model_size)
        self._model_factory = model_factory or self._default_model_factory
        self._model: Any | None = None
        self._profile_index = 0
        self._lock = threading.RLock()
        self.model_size = model_size
        self.last_oom_at: float | None = None
        self.last_fallback_reason: str | None = None
        self.last_transition_at: float | None = None

    @property
    def current_model(self) -> Any | None:
        return self._model

    @property
    def active_profile(self) -> WhisperProfile:
        return self._profiles[self._profile_index]

    @property
    def profiles(self) -> tuple[WhisperProfile, ...]:
        return tuple(self._profiles)

    def status(self) -> dict[str, Any]:
        return {
            "active_profile": self.active_profile.label,
            "profile_index": self._profile_index,
            "profiles": [profile.label for profile in self._profiles],
            "last_oom_at": self.last_oom_at,
            "last_fallback_reason": self.last_fallback_reason,
            "last_transition_at": self.last_transition_at,
        }

    def _default_model_factory(self, profile: WhisperProfile) -> Any:
        try:
            from faster_whisper import WhisperModel
        except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError(
                "faster-whisper is not installed. Install the intelligence extras to use "
                "WhisperRuntimeManager."
            ) from exc

        return WhisperModel(
            profile.model,
            device=profile.device,
            compute_type=profile.compute_type,
        )

    def ensure_loaded_sync(self) -> None:
        with self._lock:
            if self._model is not None:
                return

            last_exc: Exception | None = None
            for index in range(self._profile_index, len(self._profiles)):
                profile = self._profiles[index]
                try:
                    self._model = self._model_factory(profile)
                    self._profile_index = index
                    self.last_transition_at = time.time()
                    logger.info("Loaded Whisper profile %s", profile.label)
                    return
                except Exception as exc:
                    last_exc = exc
                    logger.warning(
                        "Failed to load Whisper profile %s",
                        profile.label,
                        exc_info=True,
                    )

            if last_exc is not None:
                raise last_exc
            raise RuntimeError("No Whisper profiles are configured.")

    def transcribe_sync(self, audio: Any, **kwargs):
        with self._lock:
            if self._model is None:
                self.ensure_loaded_sync()

            try:
                return self._model.transcribe(audio, **kwargs)
            except Exception as exc:
                if not _is_cuda_oom(exc):
                    raise
                if self._profile_index + 1 >= len(self._profiles):
                    raise

                previous_profile = self.active_profile.label
                self.last_oom_at = time.time()
                self.last_fallback_reason = "cuda_oom"
                self._profile_index += 1
                self._model = self._model_factory(self.active_profile)
                self.last_transition_at = time.time()
                logger.warning(
                    "Downgraded Whisper profile from %s to %s after CUDA OOM",
                    previous_profile,
                    self.active_profile.label,
                )
                return self._model.transcribe(audio, **kwargs)
