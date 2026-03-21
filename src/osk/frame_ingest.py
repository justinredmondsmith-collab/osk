"""Frame ingest queue with bounded priority, dedupe, and observer rate limits."""

from __future__ import annotations

import asyncio
import heapq
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from osk.intelligence_contracts import FrameSample
from osk.models import MemberRole


@dataclass(order=True, slots=True)
class _FrameQueueEntry:
    sort_key: tuple[float, int, int]
    sequence_no: int = field(compare=False)
    frame: FrameSample = field(compare=False)
    dropped: bool = field(default=False, compare=False)


class FrameIngest:
    def __init__(
        self,
        *,
        max_queue_size: int = 64,
        max_queue_depth_per_member: int = 4,
        dedupe_window_seconds: float = 2.0,
        dedupe_change_threshold: float = 0.15,
        observer_min_interval_seconds: float = 1.0,
    ) -> None:
        if max_queue_size < 1:
            raise ValueError("max_queue_size must be at least 1")
        if max_queue_depth_per_member < 1:
            raise ValueError("max_queue_depth_per_member must be at least 1")

        self.max_queue_size = max_queue_size
        self.max_queue_depth_per_member = max_queue_depth_per_member
        self.dedupe_window_seconds = dedupe_window_seconds
        self.dedupe_change_threshold = dedupe_change_threshold
        self.observer_min_interval_seconds = observer_min_interval_seconds
        self._condition = asyncio.Condition()
        self._entries: list[_FrameQueueEntry] = []
        self._next_sequence_no = 0
        self._active_count = 0
        self._member_depths: dict[uuid.UUID, int] = defaultdict(int)
        self._last_frame_by_member: dict[uuid.UUID, FrameSample] = {}
        self._last_observer_frame_at: dict[uuid.UUID, datetime] = {}
        self._running = True
        self.accepted_frames = 0
        self.duplicate_frames = 0
        self.evicted_frames = 0
        self.rate_limited_frames = 0
        self.rejected_frames = 0

    def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        async with self._condition:
            self._running = False
            self._condition.notify_all()

    def qsize(self) -> int:
        return self._active_count

    def member_depth(self, member_id: uuid.UUID) -> int:
        return self._member_depths.get(member_id, 0)

    async def put(self, frame: FrameSample) -> bool:
        async with self._condition:
            if not self._running:
                raise RuntimeError("Frame ingest queue is stopped.")

            member_id = frame.source.member_id
            if self._is_rate_limited(frame):
                self.rate_limited_frames += 1
                return False

            if self._is_duplicate(frame):
                self.duplicate_frames += 1
                return False

            if self.member_depth(member_id) >= self.max_queue_depth_per_member:
                candidate = self._find_member_eviction_candidate(member_id)
                if candidate is None:
                    self.rejected_frames += 1
                    return False
                if frame.change_score < candidate.frame.change_score:
                    self.rejected_frames += 1
                    return False
                self._mark_dropped(candidate)

            if self._active_count >= self.max_queue_size:
                candidate = self._find_global_eviction_candidate()
                if candidate is None:
                    self.rejected_frames += 1
                    return False
                if not self._should_replace(candidate, frame):
                    self.rejected_frames += 1
                    return False
                self._mark_dropped(candidate)

            entry = _FrameQueueEntry(
                sort_key=(-frame.change_score, -int(frame.source.priority), self._next_sequence_no),
                sequence_no=self._next_sequence_no,
                frame=frame,
            )
            self._next_sequence_no += 1
            heapq.heappush(self._entries, entry)
            self._active_count += 1
            self._member_depths[member_id] += 1
            self._last_frame_by_member[member_id] = frame
            if frame.source.member_role == MemberRole.OBSERVER:
                self._last_observer_frame_at[member_id] = frame.captured_at
            self.accepted_frames += 1
            self._condition.notify()
            return True

    async def get(self) -> FrameSample | None:
        async with self._condition:
            while True:
                while self._entries:
                    entry = heapq.heappop(self._entries)
                    if entry.dropped:
                        continue
                    self._remove_active_entry(entry)
                    return entry.frame

                if not self._running:
                    return None
                await self._condition.wait()

    def _find_member_eviction_candidate(self, member_id: uuid.UUID) -> _FrameQueueEntry | None:
        candidates = [
            entry
            for entry in self._entries
            if not entry.dropped and entry.frame.source.member_id == member_id
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda entry: (entry.frame.change_score, entry.sequence_no))

    def _find_global_eviction_candidate(self) -> _FrameQueueEntry | None:
        candidates = [entry for entry in self._entries if not entry.dropped]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda entry: (
                entry.frame.change_score,
                int(entry.frame.source.priority),
                entry.sequence_no,
            ),
        )

    def _should_replace(self, candidate: _FrameQueueEntry, incoming: FrameSample) -> bool:
        if incoming.change_score > candidate.frame.change_score:
            return True
        if incoming.change_score < candidate.frame.change_score:
            return False
        return int(incoming.source.priority) >= int(candidate.frame.source.priority)

    def _is_rate_limited(self, frame: FrameSample) -> bool:
        if frame.source.member_role != MemberRole.OBSERVER:
            return False
        last_seen = self._last_observer_frame_at.get(frame.source.member_id)
        if last_seen is None:
            return False
        delta_seconds = (frame.captured_at - last_seen).total_seconds()
        return delta_seconds < self.observer_min_interval_seconds

    def _is_duplicate(self, frame: FrameSample) -> bool:
        last_frame = self._last_frame_by_member.get(frame.source.member_id)
        if last_frame is None:
            return False
        delta_seconds = (frame.captured_at - last_frame.captured_at).total_seconds()
        if delta_seconds > self.dedupe_window_seconds:
            return False
        if frame.payload and last_frame.payload and frame.payload == last_frame.payload:
            return True
        return (
            frame.payload_size_bytes == last_frame.payload_size_bytes
            and frame.width == last_frame.width
            and frame.height == last_frame.height
            and frame.change_score <= self.dedupe_change_threshold
            and last_frame.change_score <= self.dedupe_change_threshold
        )

    def _mark_dropped(self, entry: _FrameQueueEntry) -> None:
        if entry.dropped:
            return
        entry.dropped = True
        self.evicted_frames += 1
        self._remove_active_entry(entry)

    def _remove_active_entry(self, entry: _FrameQueueEntry) -> None:
        self._active_count -= 1
        member_id = entry.frame.source.member_id
        new_depth = self._member_depths.get(member_id, 0) - 1
        if new_depth > 0:
            self._member_depths[member_id] = new_depth
        else:
            self._member_depths.pop(member_id, None)
