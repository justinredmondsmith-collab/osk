# Plan 4: Coordinator Dashboard

> **For agentic workers:** Start from `AGENTS.md` and `docs/WORKFLOW.md`. Treat checklist items as decomposable tasks, keep changes narrow, and verify each step before moving on.

**Goal:** Build the coordinator's desktop dashboard — a three-panel web UI with member map, event timeline + SitRep, and sensor management. Served by the hub's FastAPI server.

**Architecture:** Single-page Jinja2 template with vanilla JS. Same-origin live transport for coordinator updates, starting with SSE for read-heavy review flows and expanding to WebSocket only where bidirectional control is warranted. Leaflet.js for the fuller map with offline tile support. No framework build step — follows bodycam-summarizer's pattern of a monolithic dashboard.html with inline JS.

**Current state:** A thinner review-focused coordinator shell now exists at `/coordinator`, backed by the local review/feed APIs and served with static HTML/CSS/JS. That shell is local-only, uses a one-time dashboard code exchange into a short-lived `HttpOnly` cookie rather than embedding auth in the server-rendered HTML, request URL, or browser-managed JS storage, and now has a same-origin live dashboard stream plus right-rail context for member health, live wipe readiness for stale/disconnected member browsers, ingest pressure, a rolling member-buffer trend window, sustained buffer warning signals in the local review feed/current pulse, local acknowledge/snooze controls for those transient signals, and a local cached-tile field map with a relative-position fallback when tiles are unavailable.

**Planning note:** Much of the checklist below is now historical. Treat the current shell and the existing FastAPI/JS/CSS assets as the starting point. The remaining work in this phase is dashboard hardening, richer review/map ergonomics, and real field validation rather than greenfield page creation.

**Tech Stack:** HTML, vanilla JS, Leaflet.js, Jinja2, SSE/WebSocket API

**Spec:** `docs/specs/2026-03-21-osk-design.md` — "Coordinator Dashboard" section
**Depends on:** Plan 1 (server, connection_manager), Plan 3 (events, alerts, sitreps)

---

## File Map

| File | Responsibility |
|---|---|
| `src/osk/templates/coordinator.html` | Three-panel dashboard: map, timeline, sensors |
| `src/osk/static/leaflet.js` | Leaflet.js library (vendored for offline use) |
| `src/osk/static/leaflet.css` | Leaflet CSS |
| `src/osk/static/dashboard.js` | Dashboard JS: WebSocket, map markers, timeline rendering |
| `src/osk/static/dashboard.css` | Dashboard styling (dark theme) |
| Modify: `src/osk/server.py` | Add coordinator dashboard route, static file serving, tile proxy |
| `tests/test_dashboard.py` | Dashboard route and static serving tests |

---

### Task 1: Dashboard HTML Template

**Files:**
- Create: `src/osk/templates/coordinator.html`
- Create: `src/osk/static/dashboard.css`

- [ ] **Step 1: Create the three-panel HTML layout**

Structure:
- Top bar: Osk logo, operation name, live timer, member/sensor count, QR button, emergency wipe button
- Left panel: Leaflet map container
- Center panel: latest SitRep card + scrolling event timeline
- Right panel: active sensor cards + operation stats

Use Jinja2 template variables only for non-secret bootstrap such as operation metadata and API paths. Do not embed operator tokens in HTML or request query parameters. Dark theme matching the wireframes (dark navy backgrounds, teal/red/yellow severity colors).

- [ ] **Step 2: Create dashboard.css**

Dark theme CSS. Color variables: `--color-bg: #0d0d1a`, `--color-panel: #1a1a2e`, `--color-teal: #4ecdc4`, `--color-red: #ff6b6b`, `--color-yellow: #ffd93d`, `--color-purple: #c084fc`. Three-column layout using CSS grid. Mobile-responsive breakpoints not needed (coordinator is always on desktop).

- [ ] **Step 3: Add coordinator route to server.py**

Add `GET /coordinator` that serves a local-only shell and renders the template. Keep coordinator auth on the data APIs or a dedicated same-origin bootstrap exchange rather than the initial HTML request. Add static file serving for `/static/` directory.

- [ ] **Step 4: Test that the route serves HTML**
- [ ] **Step 5: Commit**

```bash
git add src/osk/templates/coordinator.html src/osk/static/dashboard.css src/osk/server.py
git commit -m "feat: coordinator dashboard HTML template with three-panel layout"
```

---

### Task 2: Leaflet Map Integration

**Files:**
- Create: `src/osk/static/leaflet.js` (vendored)
- Create: `src/osk/static/leaflet.css` (vendored)
- Modify: `src/osk/templates/coordinator.html`

- [ ] **Step 1: Vendor Leaflet.js**

Download Leaflet.js 1.9.4 (or latest) and CSS. Place in `static/` for offline availability. No CDN dependency.

- [ ] **Step 2: Add tile proxy endpoint to server.py**

Add `GET /tiles/{z}/{x}/{y}.png` that serves pre-cached tiles from `map_tile_cache_path`. Returns 404 with a placeholder if tile not cached.

- [ ] **Step 3: Initialize map in dashboard**

In the template's left panel, initialize Leaflet map pointing at the local tile proxy. Default center on first member's GPS or a configurable default. Add marker layers for member clusters and individual sensors.

- [ ] **Step 4: Test tile endpoint returns 404 gracefully when no tiles cached**
- [ ] **Step 5: Commit**

```bash
git add src/osk/static/leaflet.* src/osk/server.py src/osk/templates/coordinator.html
git commit -m "feat: Leaflet map integration with offline tile proxy"
```

---

### Task 3: Dashboard JavaScript (WebSocket + Rendering)

**Files:**
- Create: `src/osk/static/dashboard.js`

- [ ] **Step 1: Implement WebSocket connection**

Connect to `wss://<host>/ws`. Send auth message with coordinator token. Handle incoming message types: `event`, `sitrep`, `member_update`, `alert`, `status`, `ping`.

- [ ] **Step 2: Implement member map updates**

On `member_update` messages: add/move/remove markers on the Leaflet map. Cluster observers into circle markers with count. Show sensors as individual markers with red icons. Draw alert zone overlays from recent warning/critical events.

- [ ] **Step 3: Implement event timeline**

On `event` messages: prepend to the timeline panel. Color-code by severity. Show timestamp, category, text, source attribution. Add pin button that calls `POST /api/pin/<event_id>`.

- [ ] **Step 4: Implement SitRep panel**

On `sitrep` messages: replace the SitRep card content. Show trend badge (escalating=red, stable=teal, de-escalating=green).

- [ ] **Step 5: Implement sensor management panel**

Render active sensor cards from `member_update` messages where role=sensor. Show stream metrics (latency, frame rate). Add Pause and Demote buttons that call the REST API.

- [ ] **Step 6: Implement top bar**

Live timer (JS setInterval counting from operation start). Member/sensor count from `status` messages. QR code button (shows modal with QR image from `/api/qr`). Emergency wipe button with confirmation dialog that calls `POST /api/wipe`.

- [ ] **Step 7: Implement ping/pong**

On `ping` message, respond with `pong`. Show connection status indicator in top bar.

- [ ] **Step 8: Commit**

```bash
git add src/osk/static/dashboard.js
git commit -m "feat: coordinator dashboard JS with WebSocket, map, timeline, sensors, SitRep"
```

---

### Task 4: QR Code Display Endpoint

**Files:**
- Modify: `src/osk/server.py`

- [ ] **Step 1: Add QR image endpoint**

Add `GET /api/qr` that generates and returns the QR code PNG as an image response. Uses `osk.qr.generate_qr_png()` with the current join URL.

- [ ] **Step 2: Test QR endpoint returns PNG**
- [ ] **Step 3: Commit**

```bash
git add src/osk/server.py tests/test_server.py
git commit -m "feat: QR code image endpoint for coordinator dashboard"
```

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
