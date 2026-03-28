# Plan 3: Synthesis Layer

> **For agentic workers:** Start from `AGENTS.md` and `docs/WORKFLOW.md`. Treat checklist items as decomposable tasks, keep changes narrow, and verify each step before moving on.

**Goal:** Build the synthesis layer that fuses raw intelligence (transcripts, observations, GPS, manual reports) into unified Events, filters them into role-appropriate Alerts, and generates periodic SitReps for the coordinator.

**Current state:** The repository already has a working heuristic synthesis path
in `src/osk/synthesis.py` and `src/osk/intelligence_service.py`. Live member
GPS/audio/frame ingest can now produce persisted observations, events, alerts,
reviewable findings, and periodic SitReps, with coordinator triage/review
surfaces exposed through the CLI, admin APIs, and local dashboard shell. The
remaining work in this phase is to improve synthesis quality, correlation, and
operator review depth rather than to start from zero.

**Architecture:** The current repo uses a heuristic synthesizer that fuses
persisted observations and live ingest context into Events, role-filtered
Alerts, findings, and periodic SitReps. A future evolution may add more
model-assisted local synthesis, but current coordinator review and alert flows
depend on the heuristic path already in repo.

**Tech Stack:** Current path: Python, asyncio, Pydantic. Future deeper
model-assisted synthesis may also use Ollama (httpx).

**Spec:** `docs/specs/2026-03-21-osk-design.md` — "Synthesis Layer" section
**Depends on:** Plan 1 (models, db, connection_manager), Plan 2 (transcriber, vision_engine, location_engine)

---

## File Map

| File | Responsibility |
|---|---|
| `src/osk/synthesis.py` | Current heuristic synthesis, incident correlation, findings, alerts, SitReps |
| `src/osk/intelligence_service.py` | Owns observation persistence, synthesis invocation, and alert fan-out |
| `src/osk/server.py` | Review/feed/query surfaces and coordinator actions for synthesis output |
| `src/osk/hub.py` | Local CLI review and finding triage flows |
| `tests/test_synthesis.py` | Synthesis heuristics and SitRep cadence tests |
| `tests/test_intelligence_service.py` | Service persistence and synthesis-wiring tests |
| `tests/test_server.py` | Review/feed/dashboard API coverage |

---

The checklist below now describes the broader target for this phase. Any new
work should extend or replace the existing heuristic implementation rather than
assuming the repo has no synthesis layer yet.

### Task 1: Event Generator

**Files:**
- Create: `src/osk/event_generator.py`
- Create: `tests/test_event_generator.py`

- [ ] **Step 1: Write failing tests**

Test that the event generator:
- Accepts transcript segments and generates events from them via Ollama (mocked)
- Accepts observations and generates events from them
- Accepts manual reports and wraps them as events
- Accepts spatial events (cluster changes, geofence triggers) and wraps as events
- Classifies events by category and severity
- Deduplicates similar events within a time window
- Emits events via callback
- Handles Ollama errors gracefully (no crash, logs warning)

Key test: give the LLM mock a transcript about "police forming a line" and verify it produces an event with category=POLICE_ACTION and severity>=ADVISORY.

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement EventGenerator**

Adapted from bodycam-summarizer's `summarizer.py` + `alert_scanner.py`. Uses Ollama via httpx to classify transcripts and observations into structured Events. System prompt instructs the model to analyze input and output JSON with `severity`, `category`, `text`, and `location` fields. Includes a dedup window (don't generate duplicate events about the same thing within 60 seconds). Emits events to a callback that writes to DB and feeds Alert Engine.

- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit**

```bash
git add src/osk/event_generator.py tests/test_event_generator.py
git commit -m "feat: event generator — fuses intelligence sources into classified Events via Ollama"
```

---

### Task 2: Alert Engine

**Files:**
- Create: `src/osk/alert_engine.py`
- Create: `tests/test_alert_engine.py`

- [ ] **Step 1: Write failing tests**

Test that the alert engine:
- Filters events by severity threshold per role (observers: critical only, sensors: advisory+, coordinator: all)
- Rate limits alerts of the same category (configurable cooldown, default 60s)
- Generates proximity-based alerts (alerts members near the event location)
- Detects escalation patterns (3+ warning/critical events in 5 minutes → escalation alert)
- Pushes alerts via ConnectionManager.broadcast_alert
- Writes alerts to database
- Does not alert kicked/disconnected members

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement AlertEngine**

New module. Receives events from EventGenerator callback. Maintains a cooldown tracker (dict of category → last_alert_time). For each event, checks if it passes the cooldown. If so, creates an Alert, writes to DB, and calls `conn_manager.broadcast_alert()`. Proximity targeting uses LocationEngine to find members within radius of event location. Escalation detection counts recent warning/critical events and fires a meta-alert if threshold exceeded.

- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit**

```bash
git add src/osk/alert_engine.py tests/test_alert_engine.py
git commit -m "feat: alert engine with severity filtering, rate limiting, proximity targeting, escalation detection"
```

---

### Task 3: SitRep Generator

**Files:**
- Create: `src/osk/sitrep_generator.py`
- Create: `tests/test_sitrep_generator.py`

- [ ] **Step 1: Write failing tests**

Test that the SitRep generator:
- Runs on a configurable interval (default 10 minutes)
- Collects recent events, member positions, and alert counts
- Sends context to Ollama (mocked) and gets a structured summary
- Detects trend (escalating/stable/de-escalating) based on event severity distribution
- Emits SitRep to coordinator via ConnectionManager
- Writes SitRep to database
- Handles Ollama failures gracefully

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement SitRepGenerator**

Adapted from bodycam-summarizer's `summarizer.py` periodic summary pattern. Runs as an asyncio background task. Every N minutes, queries DB for recent events, builds a prompt with event timeline + member count + cluster info, sends to Ollama, parses structured JSON response. Trend detection: compare severity distribution of last period vs previous period. Output: SitRep model written to DB and broadcast to coordinator.

- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit**

```bash
git add src/osk/sitrep_generator.py tests/test_sitrep_generator.py
git commit -m "feat: SitRep generator with periodic AI summaries and trend detection"
```

---

### Task 4: Wire Synthesis Layer to Hub

**Files:**
- Modify: `src/osk/hub.py` — instantiate and wire EventGenerator, AlertEngine, SitRepGenerator
- Modify: `src/osk/server.py` — add SitRep and Event endpoints for coordinator

- [ ] **Step 1: Write integration test**

Test that when a transcript segment is produced by the transcriber, it flows through EventGenerator → AlertEngine → ConnectionManager broadcast.

- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Wire components in hub.py**

In `run_hub()`, instantiate EventGenerator, AlertEngine, and SitRepGenerator. Wire transcriber's `on_segment` callback to feed EventGenerator. Wire VisionEngine's `on_observation` callback similarly. Wire EventGenerator's `on_event` to AlertEngine. Start SitRepGenerator background task.

- [ ] **Step 4: Run test to verify it passes**
- [ ] **Step 5: Commit**

```bash
git add src/osk/hub.py src/osk/server.py tests/
git commit -m "feat: wire synthesis layer into hub orchestrator"
```

Note: the current repo already wires synthesis through
`src/osk/intelligence_service.py`. Treat the checklist above as the broader
direction for replacing or deepening that existing path, not as a literal
description of today's file layout.

---

### Task 5: Run Full Test Suite

- [ ] **Step 1: Run all tests**

Run: `pytest tests/ -v --tb=short`
Expected: all PASS

- [ ] **Step 2: Lint, format, commit, push**

```bash
ruff check src/ tests/ --fix && ruff format src/ tests/
git add -A && git commit -m "style: lint fixes" && git push origin main
```



> Roadmap note: This file is a scoped implementation or historical planning document. Read it through [`2026-03-28-end-state-product-roadmap.md`](./2026-03-28-end-state-product-roadmap.md). If sequencing, priority, or scope conflict with the roadmap, follow the roadmap.
