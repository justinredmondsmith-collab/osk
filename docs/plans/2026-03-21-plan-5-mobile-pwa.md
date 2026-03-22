# Plan 5: Mobile PWA Client

> **For agentic workers:** Start from `AGENTS.md` and `docs/WORKFLOW.md`. Treat checklist items as decomposable tasks, keep changes narrow, and verify each step before moving on.

**Goal:** Build the mobile Progressive Web App that members use on their phones — join flow, observer view (alert feed + manual reports), sensor view (streaming + alerts), edge-side key frame sampling, and audio capture.

**Architecture:** Vanilla JS PWA served from the hub. Service worker for offline resilience. WebSocket for real-time communication. MediaRecorder API for audio capture. Canvas + Web Worker for edge-side video frame sampling. No build tools or frameworks.

**Tech Stack:** HTML, vanilla JS, Web Workers, MediaRecorder API, getUserMedia, Service Worker, Canvas API

**Spec:** `docs/specs/2026-03-21-osk-design.md` — "Edge Components" and "Member Mobile UI" sections
**Depends on:** Plan 1 (server, connection_manager), Plan 3 (alerts)

**Current state:** A cookie-backed member join/runtime shell now exists at `/join` and `/member`. The QR token is exchanged into a clean `HttpOnly` join cookie before the shell loads, the browser authenticates the member WebSocket from that cookie, and the server then upgrades the browser into a short-lived `HttpOnly` member runtime cookie so reload/reconnect do not depend on a reconnect secret in browser JavaScript storage. The runtime already includes live alerts, opt-in GPS sharing, manual report submission, observer-side photo/short-audio-clip capture, early sensor-side audio plus key-frame capture, an IndexedDB-backed browser outbox for reconnect-safe manual note/media replay with per-item review controls, duplicate-safe manual note replay when the same `report_id` is resent after reconnect or ack loss, bounded sensor-side reconnect buffering for recent audio/key-frame capture, and the first manifest/service-worker/installable offline PWA layer. The current live `wipe` / `op_ended` path now clears queued browser state, current member cookies, cached shell assets, and unregisters the current member-shell service worker on connected devices; stale `/member` reloads now also self-clear local member state before returning to `/join`. Disconnected browsers still remain outside the live wipe path. Coordinator-facing surfaces now expose member browser buffer pressure with a rolling trend window, and for real browser/device validation outside this sandbox the repo includes both `scripts/member_shell_smoke.py` for manual smoke testing and `scripts/member_shell_playwright_smoke.sh` for localhost-capable automated browser smoke runs.

**Planning note:** Much of the checklist below is now historical. Treat the current member shell, capture modules, outbox, and PWA assets as the starting point. The remaining work in this phase is resilience, real device/browser validation, and mobile UX hardening rather than first-pass join/runtime scaffolding.

---

## File Map

| File | Responsibility |
|---|---|
| `src/osk/templates/join.html` | QR join flow — display name entry, permission requests |
| `src/osk/templates/member.html` | Observer/Sensor mobile UI — alert feed, actions, stream controls |
| `src/osk/static/member.js` | Mobile client JS: WebSocket, alerts, GPS, reports |
| `src/osk/static/member.css` | Mobile-first styling |
| `src/osk/static/audio-capture.js` | MediaRecorder audio capture and streaming |
| `src/osk/static/frame-sampler.js` | Web Worker for edge-side key frame sampling |
| `src/osk/static/sampling-worker.js` | Web Worker script for pixel difference computation |
| `src/osk/static/member-outbox.js` | Browser outbox for reconnect-safe manual note/media replay |
| `src/osk/static/sw.js` | Service worker for PWA offline resilience |
| `src/osk/static/manifest.webmanifest` | PWA manifest for install/add-to-home-screen |
| Modify: `src/osk/server.py` | Add join and member page routes |
| `tests/test_server.py` | Route and member-shell tests for join/member pages |

---

### Task 1: Join Flow Page

**Files:**
- Create: `src/osk/templates/join.html`
- Modify: `src/osk/server.py`

- [ ] **Step 1: Create join.html template**

Page flow:
1. Shows "Connected to Operation: [name]" with a checkmark
2. Display name input with placeholder "Choose a display name"
3. Note: "No real names needed. This is temporary."
4. Permission request section: Location (required), Microphone (optional), Camera (optional)
5. "Join as Observer" button
6. On submit: stores display name in `sessionStorage`, relies on the existing cookie-backed join session, and redirects to `/member`

Dark theme matching the coordinator dashboard. Mobile-optimized (large tap targets, readable text).

- [ ] **Step 2: Update server.py join route**

Modify the existing `/join` GET handler to render the full join.html template instead of the minimal HTML stub. Pass operation/session bootstrap state as template variables; do not re-expose the shared operation token in rendered HTML.

- [ ] **Step 3: Add `/member` route**

Add `GET /member` that serves the member.html template. Server-side auth should rely on the join/runtime cookies; client JS can still redirect back to `/join` if no valid member session is available.

- [ ] **Step 4: Test join page renders with valid token**
- [ ] **Step 5: Commit**

```bash
git add src/osk/templates/join.html src/osk/server.py tests/test_member_routes.py
git commit -m "feat: join flow page with display name entry and permission requests"
```

---

### Task 2: Member Mobile UI — Alert Feed + Actions

**Files:**
- Create: `src/osk/templates/member.html`
- Create: `src/osk/static/member.js`
- Create: `src/osk/static/member.css`

- [ ] **Step 1: Create member.html template**

Layout:
- Status bar: "OSK" logo, connection indicator (green dot = connected)
- Group status: member count, nearby count, trend indicator
- Main area: scrolling alert feed
- Bottom action bar: three buttons — snap photo, record clip, "I see something"
- Sensor panel (hidden for observers, shown for sensors): stream status with latency/fps/GPS indicators, pause/mute buttons

- [ ] **Step 2: Create member.js**

WebSocket connection:
- Read display name plus non-secret member identity/preferences from `sessionStorage`; resumable auth should come from the browser's `HttpOnly` member runtime cookie
- Connect to `wss://<host>/ws`
- Send auth message: `{"type":"auth", "name":"..."}` for the normal browser flow. Legacy non-browser clients may still include explicit token or resume credentials when needed.
- Handle `auth_ok` → store member_id and role, then exchange the returned short-lived `member_session_code` into the member runtime cookie
- Handle `role_change` → toggle sensor panel visibility
- Handle `alert` → prepend to alert feed, color-coded by severity
- Handle `status` → update group status bar
- Handle `ping` → respond with `pong`
- Handle `wipe` → clear sessionStorage, runtime cookies, indexedDB, cached shell assets, unregister the member service worker, and show a local "Operation ended" screen
- Handle `op_ended` → show "Operation ended" message

GPS tracking:
- `navigator.geolocation.watchPosition()`
- Send `{"type":"gps", "lat":N, "lon":N, "accuracy":N}` on change
- Adaptive interval: send if moved >5m or every 60s if stationary

Manual report:
- "I see something" button → text input modal → sends `{"type":"report", "text":"..."}`
- Current implementation should stay on the member WebSocket/auth surface; do not wire a member alert pin button to the current coordinator-only `/api/pin/<event_id>` route unless the auth model changes first

- [ ] **Step 3: Create member.css**

Mobile-first dark theme. Large touch targets (44px minimum). Alert cards with left border color by severity. Bottom action bar fixed to viewport bottom. Smooth scroll for alert feed.

- [ ] **Step 4: Test member page renders**
- [ ] **Step 5: Commit**

```bash
git add src/osk/templates/member.html src/osk/static/member.js src/osk/static/member.css
git commit -m "feat: member mobile UI with alert feed, GPS tracking, manual reports"
```

---

### Task 3: Audio Capture (Sensor)

**Files:**
- Create: `src/osk/static/audio-capture.js`

- [ ] **Step 1: Implement audio capture module**

Exported functions: `startAudioCapture(ws)`, `stopAudioCapture()`, `muteAudio()`, `unmuteAudio()`

Flow:
- `getUserMedia({ audio: true })` to get mic stream
- `MediaRecorder` with `timeslice` of 5000ms (5-second chunks)
- On `dataavailable`: send `{"type":"audio_meta", "duration_ms": N}` JSON, then send the blob as binary WebSocket frame
- Track streaming state and duration
- `stopAudioCapture()` stops the MediaRecorder and releases the stream

- [ ] **Step 2: Wire audio capture to member.js**

When role is "sensor", auto-start audio capture on auth_ok. Show streaming indicator. Pause/mute buttons call the exported functions.

- [ ] **Step 3: Test that audio_meta message format is correct (unit test in JS or manual)**
- [ ] **Step 4: Commit**

```bash
git add src/osk/static/audio-capture.js src/osk/static/member.js
git commit -m "feat: audio capture module for sensor streaming via MediaRecorder"
```

---

### Task 4: Edge Key Frame Sampling (Sensor)

**Files:**
- Create: `src/osk/static/frame-sampler.js`
- Create: `src/osk/static/sampling-worker.js`

- [ ] **Step 1: Implement sampling worker**

`sampling-worker.js` runs in a Web Worker. Receives `ImageBitmap` via `postMessage`. Computes mean absolute pixel difference against previous frame. Posts back `{changed: bool, score: float}`.

Algorithm:
- Draw ImageBitmap to OffscreenCanvas
- Get pixel data
- Compare to previous pixel data (stored in worker)
- Mean absolute difference across all pixels / 255.0
- If score > threshold (default 0.15), post `{changed: true, score: N}`
- Always post back (so caller can track baseline timing)

- [ ] **Step 2: Implement frame-sampler.js**

Exported functions: `startFrameSampling(ws, config)`, `stopFrameSampling()`

Flow:
- `getUserMedia({ video: true })` to get camera stream
- Create hidden `<video>` element and `<canvas>`
- Every 500ms (2 FPS): capture frame from video to canvas, create ImageBitmap, send to worker
- Worker responds: if changed or if >30s since last send → compress canvas to JPEG (quality 0.6), send `{"type":"frame_meta", "change_score": N}` JSON, then send JPEG blob as binary
- Track frames sent, last send time

Config object: `{ threshold: 0.15, fps: 2.0, baseline_interval_seconds: 30 }`

- [ ] **Step 3: Wire frame sampling to member.js**

When role is "sensor" and camera permission granted, auto-start frame sampling. Show frame rate indicator.

- [ ] **Step 4: Commit**

```bash
git add src/osk/static/frame-sampler.js src/osk/static/sampling-worker.js src/osk/static/member.js
git commit -m "feat: edge key frame sampling with Web Worker pixel difference detection"
```

---

### Task 5: Observer Manual Media (Photo + Clip)

**Files:**
- Modify: `src/osk/static/member.js`

- [ ] **Step 1: Implement snap photo**

"Snap Photo" button:
- `getUserMedia({ video: true })` briefly
- Capture single frame to canvas
- Compress as JPEG
- Send `{"type":"frame_meta", "change_score": 1.0}` (manual = always relevant) + binary
- Release camera stream

- [ ] **Step 2: Implement record clip**

"Record Clip" button:
- `getUserMedia({ audio: true })`
- `MediaRecorder` starts
- After 10 seconds (or user taps stop), send `{"type":"clip_meta", "duration_ms": N}` + binary
- Release mic
- Rate-limit: disable button for 20 seconds after each clip

- [ ] **Step 3: Commit**

```bash
git add src/osk/static/member.js
git commit -m "feat: observer manual photo snap and audio clip recording"
```

---

### Task 6: PWA Service Worker + Manifest

**Files:**
- Create: `src/osk/static/sw.js`
- Create: `src/osk/static/manifest.webmanifest`

- [ ] **Step 1: Create service worker**

Cache strategy: network-first for API calls, cache-first for static assets. On `wipe` message from main thread, clear all caches and unregister.

```javascript
// sw.js
const CACHE_NAME = 'osk-v1';
const STATIC_ASSETS = ['/member', '/static/member.js', '/static/member.css'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS))
  );
});

self.addEventListener('fetch', (event) => {
  if (event.request.url.includes('/api/')) {
    event.respondWith(fetch(event.request));
  } else {
    event.respondWith(
      caches.match(event.request).then(cached => cached || fetch(event.request))
    );
  }
});

self.addEventListener('message', (event) => {
  if (event.data === 'wipe') {
    caches.delete(CACHE_NAME);
    self.registration.unregister();
  }
});
```

- [ ] **Step 2: Create manifest.webmanifest**

```json
{
  "name": "Osk",
  "short_name": "Osk",
  "start_url": "/member",
  "display": "standalone",
  "background_color": "#0d0d1a",
  "theme_color": "#4ecdc4",
  "icons": []
}
```

- [ ] **Step 3: Register service worker in member.html**
- [ ] **Step 4: Commit**

```bash
git add src/osk/static/sw.js src/osk/static/manifest.webmanifest src/osk/templates/member.html
git commit -m "feat: PWA service worker and manifest for offline resilience"
```

---

### Task 7: Wipe Handler (Client-Side)

**Files:**
- Modify: `src/osk/static/member.js`

- [ ] **Step 1: Implement wipe handler**

On receiving `{"type":"wipe"}` via WebSocket:
1. Clear `sessionStorage`
2. Clear member auth cookies / runtime session state
3. Clear any `IndexedDB` databases
4. Send `wipe` message to service worker
5. Replace page content with "Operation ended" message
6. Close WebSocket

- [ ] **Step 2: Commit**

```bash
git add src/osk/static/member.js
git commit -m "feat: client-side wipe handler clears all local state"
```

---

### Task 8: Run Full Test Suite

- [ ] **Step 1: Run all tests**

Run: `pytest tests/ -v --tb=short`
Expected: all PASS

- [ ] **Step 2: Lint, format, commit, push**

```bash
ruff check src/ tests/ --fix && ruff format src/ tests/
git add -A && git commit -m "style: lint fixes" && git push origin main
```
