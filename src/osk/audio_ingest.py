"""Audio ingest queue with bounded priority scheduling and backpressure."""

from __future__ import annotations

import asyncio
import heapq
import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from osk.intelligence_contracts import AudioChunk


@dataclass(order=True, slots=True)
class _AudioQueueEntry:
    sort_key: tuple[int, int]
    sequence_no: int = field(compare=False)
    chunk: AudioChunk = field(compare=False)
    dropped: bool = field(default=False, compare=False)


class AudioIngest:
    def __init__(self, *, max_queue_size: int = 128) -> None:
        if max_queue_size < 1:
            raise ValueError("max_queue_size must be at least 1")

        self.max_queue_size = max_queue_size
        self._condition = asyncio.Condition()
        self._entries: list[_AudioQueueEntry] = []
        self._next_sequence_no = 0
        self._active_count = 0
        self._member_depths: dict[uuid.UUID, int] = defaultdict(int)
        self._running = True
        self.accepted_chunks = 0
        self.evicted_chunks = 0
        self.rejected_chunks = 0

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

    async def put(self, chunk: AudioChunk) -> bool:
        async with self._condition:
            if not self._running:
                raise RuntimeError("Audio ingest queue is stopped.")

            if self._active_count >= self.max_queue_size:
                candidate = self._find_eviction_candidate()
                if candidate is None:
                    self.rejected_chunks += 1
                    return False

                incoming_priority = int(chunk.source.priority)
                queued_priority = int(candidate.chunk.source.priority)
                if incoming_priority < queued_priority:
                    self.rejected_chunks += 1
                    return False
                self._mark_dropped(candidate)

            entry = _AudioQueueEntry(
                sort_key=(-int(chunk.source.priority), self._next_sequence_no),
                sequence_no=self._next_sequence_no,
                chunk=chunk,
            )
            self._next_sequence_no += 1
            heapq.heappush(self._entries, entry)
            self._active_count += 1
            self._member_depths[chunk.source.member_id] += 1
            self.accepted_chunks += 1
            self._condition.notify()
            return True

    async def get(self) -> AudioChunk | None:
        async with self._condition:
            while True:
                while self._entries:
                    entry = heapq.heappop(self._entries)
                    if entry.dropped:
                        continue
                    self._remove_active_entry(entry)
                    return entry.chunk

                if not self._running:
                    return None
                await self._condition.wait()

    def _find_eviction_candidate(self) -> _AudioQueueEntry | None:
        active_entries = [entry for entry in self._entries if not entry.dropped]
        if not active_entries:
            return None
        return min(
            active_entries,
            key=lambda entry: (int(entry.chunk.source.priority), entry.sequence_no),
        )

    def _mark_dropped(self, entry: _AudioQueueEntry) -> None:
        if entry.dropped:
            return
        entry.dropped = True
        self.evicted_chunks += 1
        self._remove_active_entry(entry)

    def _remove_active_entry(self, entry: _AudioQueueEntry) -> None:
        self._active_count -= 1
        member_id = entry.chunk.source.member_id
        new_depth = self._member_depths.get(member_id, 0) - 1
        if new_depth > 0:
            self._member_depths[member_id] = new_depth
        else:
            self._member_depths.pop(member_id, None)
