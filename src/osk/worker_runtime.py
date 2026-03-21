"""Shared runtime helpers for background intelligence workers."""

from __future__ import annotations

import inspect
import time
from dataclasses import dataclass
from typing import Awaitable, Callable

from osk.intelligence_contracts import IntelligenceObservation

ObservationCallback = Callable[[IntelligenceObservation], Awaitable[None] | None]


@dataclass(slots=True)
class ProcessingWorkerMetrics:
    processed_items: int = 0
    emitted_observations: int = 0
    empty_results: int = 0
    errors: int = 0
    last_latency_ms: float | None = None
    total_latency_ms: float = 0.0
    last_error: str | None = None

    @property
    def average_latency_ms(self) -> float | None:
        if self.processed_items == 0:
            return None
        return self.total_latency_ms / self.processed_items

    def record_latency(self, started_at: float) -> float:
        latency_ms = (time.perf_counter() - started_at) * 1000.0
        self.last_latency_ms = latency_ms
        self.total_latency_ms += latency_ms
        return latency_ms


async def maybe_invoke_callback(
    callback: ObservationCallback | None,
    observation: IntelligenceObservation,
) -> None:
    if callback is None:
        return

    result = callback(observation)
    if inspect.isawaitable(result):
        await result
