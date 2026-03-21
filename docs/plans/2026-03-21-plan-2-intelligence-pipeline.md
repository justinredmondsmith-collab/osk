# Plan 2: Intelligence Pipeline

> **For agentic workers:** Start from `AGENTS.md` and `docs/WORKFLOW.md`. Treat checklist items as decomposable tasks, keep changes narrow, and verify each step before moving on.

**Goal:** Transplant and adapt the proven intelligence engines from bodycam-summarizer — Whisper transcription, Ollama vision analysis, temporal fusion — and build the new audio/frame ingest queues and location engine.

**Current recommendation:** The Phase 1 host/runtime foundation is now in the
repository. Start this phase with ingest contracts, fake adapters, and contract
tests before landing real Whisper or Ollama runtime integration.

**Architecture:** Three parallel processing engines fed by ingest queues. Audio ingest receives WebSocket binary frames and feeds a priority queue to the Whisper engine. Frame ingest receives JPEG key frames and feeds the vision engine. Location engine tracks GPS and detects spatial patterns. All engines output to the synthesis layer (Plan 3).

**Tech Stack:** faster-whisper, Ollama (httpx), asyncio queues, numpy

**Spec:** `docs/specs/2026-03-21-osk-design.md` — sections "Hub Components" and "Edge Components"
**Depends on:** Plan 1 (models, db, server, connection_manager)

---

## File Map

| File | Responsibility |
|---|---|
| `src/osk/audio_ingest.py` | Audio stream buffering, per-member queues, priority scheduling |
| `src/osk/transcriber.py` | Whisper engine — transplanted from bodycam-summarizer, adapted for multi-stream queue |
| `src/osk/whisper_runtime.py` | Adaptive model selection — transplanted with minimal changes |
| `src/osk/frame_ingest.py` | Key frame receiving, deduplication, queue management |
| `src/osk/vision_engine.py` | Ollama vision analysis — transplanted from cv_worker.py, adapted for pre-sampled frames |
| `src/osk/vision_fusion.py` | Temporal fusion — transplanted from cv_fusion.py |
| `src/osk/location_engine.py` | GPS tracking, cluster detection, geofence triggers |
| `tests/test_audio_ingest.py` | Audio queue tests |
| `tests/test_transcriber.py` | Whisper engine tests (mocked) |
| `tests/test_frame_ingest.py` | Frame queue tests |
| `tests/test_vision_engine.py` | Vision engine tests (mocked Ollama) |
| `tests/test_vision_fusion.py` | Temporal fusion tests |
| `tests/test_location_engine.py` | Location engine tests |

---

### Task 1: Audio Ingest Queue

**Files:**
- Create: `src/osk/audio_ingest.py`
- Create: `tests/test_audio_ingest.py`

- [ ] **Step 1: Write failing tests**

Test that the audio ingest queue:
- Accepts binary audio chunks tagged with member_id and priority
- Returns chunks in priority order (sensor > observer clip)
- Drops oldest chunks when queue is full (backpressure)
- Tracks per-member queue depth
- Can be started and stopped cleanly

```python
# tests/test_audio_ingest.py
from __future__ import annotations
import asyncio
import uuid
import pytest
from osk.audio_ingest import AudioIngest, AudioChunk

@pytest.fixture
def ingest() -> AudioIngest:
    return AudioIngest(max_queue_size=5)

async def test_enqueue_and_dequeue(ingest):
    mid = uuid.uuid4()
    chunk = AudioChunk(member_id=mid, data=b"\x00" * 100, duration_ms=500, priority=1)
    await ingest.put(chunk)
    result = await ingest.get()
    assert result.member_id == mid

async def test_priority_ordering(ingest):
    low = AudioChunk(member_id=uuid.uuid4(), data=b"\x00", duration_ms=100, priority=0)
    high = AudioChunk(member_id=uuid.uuid4(), data=b"\x01", duration_ms=100, priority=1)
    await ingest.put(low)
    await ingest.put(high)
    first = await ingest.get()
    assert first.priority == 1  # high priority first

async def test_backpressure_drops_oldest(ingest):
    mid = uuid.uuid4()
    for i in range(7):  # exceeds max_queue_size=5
        await ingest.put(AudioChunk(member_id=mid, data=bytes([i]), duration_ms=100, priority=0))
    assert ingest.qsize() <= 5

async def test_queue_depth_per_member(ingest):
    mid1 = uuid.uuid4()
    mid2 = uuid.uuid4()
    await ingest.put(AudioChunk(member_id=mid1, data=b"\x00", duration_ms=100, priority=0))
    await ingest.put(AudioChunk(member_id=mid1, data=b"\x01", duration_ms=100, priority=0))
    await ingest.put(AudioChunk(member_id=mid2, data=b"\x02", duration_ms=100, priority=0))
    assert ingest.member_depth(mid1) == 2
    assert ingest.member_depth(mid2) == 1
```

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement AudioIngest**

Implement `AudioIngest` with asyncio.PriorityQueue, `AudioChunk` dataclass with `(priority, timestamp)` sort key, per-member counters, and backpressure via dropping oldest low-priority item when full.

- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit**

```bash
git add src/osk/audio_ingest.py tests/test_audio_ingest.py
git commit -m "feat: audio ingest queue with priority scheduling and backpressure"
```

---

### Task 2: Whisper Transcriber (Transplant)

**Files:**
- Create: `src/osk/transcriber.py`
- Create: `src/osk/whisper_runtime.py`
- Create: `tests/test_transcriber.py`

- [ ] **Step 1: Write failing tests**

Test that the transcriber:
- Pulls chunks from an AudioIngest queue
- Calls the Whisper model in an executor thread
- Emits TranscriptSegment results via callback
- Handles quality heuristics (repetition collapse, uncertain tokens)
- Reports metrics (queue depth, processing latency)
- Can be started and stopped

All Whisper model calls are mocked — no GPU required for tests.

```python
# tests/test_transcriber.py
from __future__ import annotations
import asyncio
import uuid
from unittest.mock import MagicMock, AsyncMock, patch
import pytest
from osk.transcriber import Transcriber, TranscriptSegment, normalize_uncertain_tokens, collapse_repetition_loops

def test_normalize_uncertain_tokens():
    assert normalize_uncertain_tokens("he said __ something") == "he said [inaudible] something"

def test_collapse_repetition_loops():
    text = "go go go go go go go go"
    result = collapse_repetition_loops(text)
    assert result.count("go") < 8

def test_transcript_segment_creation():
    seg = TranscriptSegment(stream_id=uuid.uuid4(), member_id=uuid.uuid4(),
                            start=0.0, end=1.5, text="hello world", confidence=0.95)
    assert seg.text == "hello world"

async def test_transcriber_processes_chunk():
    mock_audio_ingest = MagicMock()
    on_segment = AsyncMock()
    # Mock the whisper model
    with patch("osk.transcriber.WhisperRuntimeManager") as MockRuntime:
        mock_runtime = MagicMock()
        mock_runtime.transcribe_sync.return_value = (
            [MagicMock(start=0.0, end=1.0, text="test audio", words=None)],
            MagicMock(language="en"),
        )
        MockRuntime.return_value = mock_runtime
        t = Transcriber(audio_ingest=mock_audio_ingest, on_segment=on_segment, runtime=mock_runtime)
        seg = t._transcribe_chunk(b"\x00" * 3200, uuid.uuid4(), uuid.uuid4())
        assert len(seg) > 0
        assert seg[0].text == "test audio"
```

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Transplant and adapt transcriber.py and whisper_runtime.py**

Copy from `bodycam-summarizer/src/bodycam_summarizer/transcriber.py` and adapt:
- Remove officer/session references
- Accept chunks from `AudioIngest` queue instead of per-session chunk_queue
- Each chunk includes `member_id` and `stream_id` for attribution
- Output `TranscriptSegment` (from osk.models or local dataclass) with member_id
- Keep quality heuristics: `normalize_uncertain_tokens`, `collapse_repetition_loops`, overlap trimming

Copy `whisper_runtime.py` with minimal changes (rename imports to osk package).

- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit**

```bash
git add src/osk/transcriber.py src/osk/whisper_runtime.py tests/test_transcriber.py
git commit -m "feat: Whisper transcriber transplanted from bodycam-summarizer with multi-stream queue"
```

---

### Task 3: Frame Ingest Queue

**Files:**
- Create: `src/osk/frame_ingest.py`
- Create: `tests/test_frame_ingest.py`

- [ ] **Step 1: Write failing tests**

Test that the frame ingest queue:
- Accepts JPEG key frames tagged with member_id and change_score
- Deduplicates near-identical frames (by perceptual hash or size+member within time window)
- Prioritizes high-change frames over baseline frames
- Enforces max queue depth per member
- Rate-limits observer submissions

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement FrameIngest**

Similar to AudioIngest but for JPEG blobs. `KeyFrame` dataclass with `member_id`, `data` (bytes), `change_score` (float), `timestamp`. Priority queue sorted by change_score descending. Deduplication: skip frame if last frame from same member was <2 seconds ago and change_score < threshold.

- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit**

```bash
git add src/osk/frame_ingest.py tests/test_frame_ingest.py
git commit -m "feat: frame ingest queue with deduplication and priority scheduling"
```

---

### Task 4: Vision Engine (Transplant)

**Files:**
- Create: `src/osk/vision_engine.py`
- Create: `tests/test_vision_engine.py`

- [ ] **Step 1: Write failing tests**

Test that the vision engine:
- Pulls key frames from FrameIngest queue
- Sends frames to Ollama vision model via HTTP (mocked)
- Parses structured response into Observation model
- Emits observations via callback
- Handles Ollama errors gracefully

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Transplant and adapt cv_worker.py**

Copy from `bodycam-summarizer/src/bodycam_summarizer/cv_worker.py` and adapt:
- Remove video file/URL/RTSP source handling — frames arrive pre-sampled via FrameIngest
- Keep Ollama HTTP call logic (base64 encode JPEG, send to vision model)
- Adapt prompt from bodycam scene analysis to civilian situational awareness (describe scene, identify threats, count people, detect vehicles/barriers)
- Output Observation model (from osk.models)

- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit**

```bash
git add src/osk/vision_engine.py tests/test_vision_engine.py
git commit -m "feat: vision engine transplanted from bodycam-summarizer for key frame analysis"
```

---

### Task 5: Temporal Fusion (Transplant)

**Files:**
- Create: `src/osk/vision_fusion.py`
- Create: `tests/test_vision_fusion.py`

- [ ] **Step 1: Write failing tests**

Test temporal fusion:
- Merges observations of same scene from same member within time window
- Increments evidence count on merge
- Respects different fusion windows by observation type
- Does not merge observations from different members

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Transplant cv_fusion.py**

Copy from `bodycam-summarizer/src/bodycam_summarizer/cv_fusion.py` with minimal changes. Update import paths to osk package. Replace `CVSceneFactCandidate` with Observation model fields.

- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit**

```bash
git add src/osk/vision_fusion.py tests/test_vision_fusion.py
git commit -m "feat: temporal fusion transplanted from bodycam-summarizer"
```

---

### Task 6: Location Engine

**Files:**
- Create: `src/osk/location_engine.py`
- Create: `tests/test_location_engine.py`

- [ ] **Step 1: Write failing tests**

Test that the location engine:
- Tracks member positions (update GPS)
- Detects clusters (members within N meters grouped together)
- Calculates member count per cluster
- Detects movement (member moved > threshold since last update)
- Triggers geofence events (member enters/exits defined zone)
- Returns "nearby" count for a given member (members within radius)

```python
# tests/test_location_engine.py
from __future__ import annotations
import uuid
import pytest
from osk.location_engine import LocationEngine

@pytest.fixture
def engine() -> LocationEngine:
    return LocationEngine(cluster_radius_meters=100, nearby_radius_meters=200)

def test_update_position(engine):
    mid = uuid.uuid4()
    engine.update(mid, 39.750, -104.990)
    pos = engine.get_position(mid)
    assert pos == (39.750, -104.990)

def test_nearby_count(engine):
    m1 = uuid.uuid4()
    m2 = uuid.uuid4()
    m3 = uuid.uuid4()
    # All within 200m of each other (~0.001 degrees ≈ 111m)
    engine.update(m1, 39.750, -104.990)
    engine.update(m2, 39.7505, -104.990)
    engine.update(m3, 39.760, -104.990)  # far away
    assert engine.nearby_count(m1) == 1  # m2 is nearby, m3 is not

def test_detect_clusters(engine):
    m1 = uuid.uuid4()
    m2 = uuid.uuid4()
    m3 = uuid.uuid4()
    engine.update(m1, 39.750, -104.990)
    engine.update(m2, 39.7505, -104.990)
    engine.update(m3, 39.760, -104.990)
    clusters = engine.get_clusters()
    assert len(clusters) == 2  # one cluster of 2, one singleton

def test_movement_detection(engine):
    mid = uuid.uuid4()
    engine.update(mid, 39.750, -104.990)
    moved = engine.update(mid, 39.750, -104.990)  # same spot
    assert not moved
    moved = engine.update(mid, 39.760, -104.990)  # ~1km away
    assert moved

def test_add_geofence(engine):
    engine.add_geofence("danger_zone", 39.750, -104.990, radius_meters=50)
    mid = uuid.uuid4()
    events = engine.update(mid, 39.7501, -104.990)  # inside zone
    # Returns True for movement + geofence info accessible
    inside = engine.check_geofences(mid)
    assert "danger_zone" in inside
```

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement LocationEngine**

New module. Use haversine distance formula for GPS distance. Simple clustering via greedy grouping (assign each member to nearest existing cluster or create new one). Geofence as named circles with center + radius.

- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit**

```bash
git add src/osk/location_engine.py tests/test_location_engine.py
git commit -m "feat: location engine with GPS tracking, clustering, and geofence triggers"
```

---

### Task 7: Wire Ingest Queues to WebSocket Server

**Files:**
- Modify: `src/osk/server.py` — WebSocket handler routes binary frames to ingest queues

- [ ] **Step 1: Write failing integration test**

Test that when a sensor sends `audio_meta` JSON + binary frame via WebSocket, the audio ingest queue receives the chunk. Same for `frame_meta` + JPEG binary.

- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Update server.py WebSocket handler**

In the WebSocket message loop, when `audio_meta` is received, store the metadata. On next binary frame, create an `AudioChunk` and put it in the audio ingest queue. Same pattern for `frame_meta` + JPEG binary. The ingest queues are passed to `create_app()`.

- [ ] **Step 4: Run test to verify it passes**
- [ ] **Step 5: Commit**

```bash
git add src/osk/server.py tests/test_server.py
git commit -m "feat: wire WebSocket binary frames to audio and frame ingest queues"
```

---

### Task 8: Run Full Test Suite

- [ ] **Step 1: Run all tests**

Run: `pytest tests/ -v --tb=short`
Expected: all PASS

- [ ] **Step 2: Lint and format**

Run: `ruff check src/ tests/ --fix && ruff format src/ tests/`

- [ ] **Step 3: Commit and push**

```bash
git add -A && git commit -m "style: lint fixes" && git push origin main
```
