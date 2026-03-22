# Osk — Civilian Situational Awareness Platform

**Date:** 2026-03-21
**Status:** Design-and-foundation, partially implemented
**Repository:** osk

## Overview

Osk is a civilian situational awareness platform that gives groups of people LEO/IC-grade intelligence capabilities for protests, gatherings, public meetings, large events, and personal safety. It uses a hub-and-spoke architecture where a coordinator runs a laptop-based intelligence hub and group members connect via their phones.

This specification should be read as a design target layered on top of a
partially implemented public foundation repository. The current repo already
contains early real slices of the host runtime, intelligence service,
heuristic synthesis/review path, coordinator dashboard shell, and member
join/runtime PWA shell, but not the full validated end-state described here.

The project is a new codebase that plans to transplant proven intelligence engines from the existing `bodycam-summarizer` project (Whisper transcription, Ollama vision analysis, AI summarization, temporal fusion) into a civilian-focused platform with fundamentally different data models, security posture, and user experience.

Unless stated otherwise in the repository root, all code added to Osk is intended to be released under `AGPL-3.0-only`. Any future copied or adapted code from predecessor repositories must retain required attribution and be recorded in `docs/PROVENANCE.md`.

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Architecture | Hub-and-spoke | Coordinator laptop runs the full AI stack locally; phones are lightweight sensors/displays. Matches LEO field operations model. Works on local WiFi with no internet. |
| Deployment model | Motivated coordinator, zero-friction members | Coordinator follows a setup guide and runs `osk start`. Members scan QR code and join via mobile browser. No app install. |
| Primary capabilities | Real-time audio intelligence + team coordination | Highest-value capabilities from bodycam-summarizer adapted for civilian group use. |
| Member roles | Tiered (Coordinator / Sensor / Observer) | Keeps hub processing load manageable at scale. 5-10 active sensor streams instead of 50+. |
| Group size | Up to 50+ members | Tiered roles make this feasible — most members are observers consuming alerts, not streaming. |
| Output model | Alert-driven for members, full picture for coordinator | Members get actionable alerts only. Coordinator sees full event timeline, map, and situation reports. |
| Storage | Ephemeral by default, selective pinning | PostgreSQL on tmpfs (RAM). Pinned evidence goes to LUKS-encrypted volume. Emergency wipe capability. |
| Cloud dependency | None — fully local | Ollama only, no cloud LLM APIs. No internet required. Data never leaves the hub. Security feature. |
| Mobile client | PWA in mobile browser | No app store dependency. Scan QR → open browser → join, with optional add-to-home-screen/install on supported browsers. Vanilla JS, no framework build step. |
| Codebase approach | New project, transplant engines | Clean data model and security posture. Proven engines (Whisper, CV, summarizer) copied and adapted. |
| Name | Osk | Three letters, one syllable, sounds like a command. Not an existing product. |

## Architecture

### High-Level

```
┌─────────────────────────────────────────────┐
│              EDGE (Member Phones)            │
│                                              │
│  ┌──────────────┐    ┌───────────────────┐   │
│  │   Sensors    │    │    Observers      │   │
│  │ (5-10 active)│    │   (40+ members)   │   │
│  │              │    │                   │   │
│  │ • Audio stream    │ • GPS broadcast   │   │
│  │ • Key frame   │   │ • Receive alerts  │   │
│  │   sampling    │   │ • Manual reports  │   │
│  │ • GPS broadcast   │ • Snap photo/clip │   │
│  └──────┬───────┘    └────────┬──────────┘   │
└─────────┼─────────────────────┼──────────────┘
          │   Local WiFi /      │
          │   Hotspot           │
          │   (no internet)     │
┌─────────┼─────────────────────┼──────────────┐
│         ▼         HUB         ▼              │
│  ┌─────────────────────────────────────────┐ │
│  │           INGEST LAYER                  │ │
│  │  Audio Queue │ Frame Queue │ GPS+Reports│ │
│  └──────┬───────────┬──────────────┬───────┘ │
│         ▼           ▼              ▼         │
│  ┌─────────────────────────────────────────┐ │
│  │       PROCESSING ENGINES (parallel)     │ │
│  │  Whisper │ Vision Engine │ Location Eng │ │
│  └──────┬───────────┬──────────────┬───────┘ │
│         ▼           ▼              ▼         │
│  ┌─────────────────────────────────────────┐ │
│  │          SYNTHESIS LAYER                │ │
│  │  Event Generator │ Alert Eng │ SitRep   │ │
│  └──────┬───────────┬──────────────┬───────┘ │
│         ▼           ▼              ▼         │
│  ┌─────────────────────────────────────────┐ │
│  │              OUTPUT                     │ │
│  │  Coordinator: full picture              │ │
│  │  Sensors: filtered alerts + stream info │ │
│  │  Observers: critical alerts only        │ │
│  └─────────────────────────────────────────┘ │
│                                              │
│  ┌─────────────────────────────────────────┐ │
│  │  STORAGE: tmpfs (ephemeral) + LUKS vol  │ │
│  └─────────────────────────────────────────┘ │
└──────────────────────────────────────────────┘
```

### Hub Components

**Ingest Layer:**
- **Audio Queue** — receives WebSocket binary frames from sensors. Per-member buffers with priority scheduling (sensors > manual clips). Backpressure: drop oldest if queue full.
- **Frame Queue** — receives JPEG key frames from edge-side sampling. Deduplicates near-identical frames. Priority: high-change frames > baseline frames. Max queue depth per member.
- **GPS + Reports** — location updates from all members (adaptive interval: 10s moving, 60s stationary) and manual "I see something" reports. Lightweight, no queuing needed.
- **Observer Media Queue** — manual photos and audio clips from observers are queued separately at lower priority than sensor streams. Rate-limited to `observer_clip_rate_limit` per minute per observer to prevent burst load from 40+ observers.

**Processing Engines (parallel):**
- **Whisper Engine** (transplanted from `transcriber.py` + `whisper_runtime.py`) — single GPU worker with a priority queue that multiplexes 5-10 input sensor streams. Audio chunks are processed sequentially (one at a time on the GPU) in priority order: oldest high-priority sensor chunk first, then manual observer clips. Adaptive model selection based on queue depth (smaller/faster model when backlogged). Expected latency: ~2-4 seconds per chunk at 5 sensors, ~5-8 seconds at 10 sensors. Output: timestamped transcript segments with confidence scores.
- **Vision Engine** (transplanted from `cv_worker.py` + `cv_fusion.py`) — Ollama vision model analyzes key frames. Scene classification, entity detection, threat-relevance scoring. Temporal fusion merges duplicate observations across time windows. Output: observations with scene descriptions.
- **Location Engine** (new) — tracks all member GPS positions. Cluster detection (automatic grouping). Movement vector analysis. Geofence triggers (configurable alert zones). Output: spatial events.

**Synthesis Layer:**
- **Event Generator** (adapted from `summarizer.py` + `alert_scanner.py`) — fuses transcripts + observations + spatial data + manual reports into unified Events. Classifies by category: crowd movement, police action, blocked route, escalation, medical, weather. Assigns severity (info / advisory / warning / critical) and location. Uses Ollama for AI synthesis with civilian-context prompt templates.
- **Alert Engine** (new) — filters events by severity threshold per role (observers see critical only, sensors see advisory+). Proximity-based targeting: alerts members near the event. Rate limiting to prevent alert fatigue. Escalation pattern detection (sequences of events that indicate worsening conditions).
- **SitRep Generator** (adapted from `summarizer.py`) — periodic AI situation reports every 5-15 minutes (configurable). Trend detection: escalating / de-escalating / stable. Route and exit status. Coordinator only.

### Edge Components (Mobile Browser PWA)

**Audio capture:**
- `MediaRecorder` API with `getUserMedia()`
- Records in 5-10 second chunks, streams to hub via WebSocket as binary frames
- Sensor role: continuous streaming. Observer role: short tap-to-record clips for manual context capture.

**Video/key frame sampling (on-device intelligence):**
- `getUserMedia()` for camera → hidden `<canvas>`
- Sampling runs in a **Web Worker** to avoid main-thread UI jank. Worker receives `ImageBitmap` from canvas, computes mean absolute pixel difference against the previous frame.
- Samples at ~2 FPS. Sends frame if mean pixel difference exceeds configurable threshold (default: 15% of max pixel value). Baseline key frame sent every 30 seconds regardless.
- Compressed JPEG blobs (quality 0.6) via WebSocket. Target: 5-10 key frames per minute per sensor.
- Battery impact: moderate. The 2 FPS sampling + Web Worker is comparable to a video call. Coordinator can reduce sampling rate per-sensor if battery is a concern.

**GPS:**
- `navigator.geolocation.watchPosition()` — continuous updates
- Adaptive interval: 10 seconds when moving (>5m displacement), 60 seconds when stationary. Configurable.
- All roles broadcast location

## Data Model

Core entities — all ephemeral (RAM-only) unless explicitly pinned:

**Operation** — a single deployment of Osk. Created on `osk start`. Has a name, start time, configuration (alert sensitivity, max sensors, etc.). Everything else belongs to an operation.

**Member** — someone who joins via QR code. Display name only (no real names required). Assigned role: observer / sensor / coordinator. Connection status and last-known GPS. No persistent identity across operations.

**Stream** — an active audio or video feed from a sensor. Links to member. Tracks type (audio/video), status (active/paused/ended), processing metrics (latency, queue depth).

**Transcript** — Whisper output for an audio stream. Timestamped text segments with confidence scores. Linked to stream and member.

**Observation** — Vision engine output for a key frame. Scene description, detected entities, threat-relevance score. Linked to member.

**Event** — the unified intelligence unit. Generated by synthesizing transcripts, observations, manual reports, and spatial data. Has severity (info/advisory/warning/critical), category (crowd movement, police action, blocked route, escalation, medical, weather), location (from member GPS), timestamp, and source attribution.

**Alert** — an event that crossed the notification threshold for a member. Pushed via WebSocket. Short, actionable text.

**Pin** — marks an event for preservation. The event and its source data (transcript segments, frames) get written to the LUKS encrypted volume.

**SitRep** — periodic AI situation report. Coordinator only. Summary text, trend indicator, route/exit status.

## Security & Privacy

This section describes the intended security model for a future implementation.
It should be read as a design target, not as a statement that the current
repository has already implemented or validated these properties.

### Threat Model

Users may face real consequences if their data is accessed by adversaries (law enforcement, counter-protesters, bad actors). The security model prioritizes data minimization and operator control.

### Ephemeral-by-Default Storage

- PostgreSQL is intended to run on **tmpfs** (RAM filesystem) so operational
  data does not rely on normal disk persistence.
- Transcripts, observations, events, GPS data, and member info are intended to
  remain RAM-only during operation unless explicitly preserved.

### Selective Pinning

- Members or coordinator explicitly pin events for preservation.
- Pinned items (event + source transcript segments + key frames) are written to a **LUKS-encrypted volume**.
- The current design uses a sparse LUKS volume created during `osk install`
  (default 1 GB, configurable). The planned flow is for `cryptsetup luksFormat`
  to run at install time and `cryptsetup luksOpen` to unlock it at operation
  start.
- The current design assumes the passphrase is handled via the **Linux kernel
  keyring** (`keyctl` / `KEY_SPEC_SESSION_KEYRING`) rather than normal app
  config or process environment.
- A future implementation is intended to preserve transcript text rather than
  raw audio when events are pinned.
- GPS data is intended to remain unpinned unless explicitly included with a
  preserved event.

### Emergency Wipe

- **Triggers:** keyboard shortcut (Ctrl+Alt+W), hardware button (if configured), or dashboard button.
- **Action sequence:**
  1. Hub broadcasts `{"type": "wipe"}` to all connected members. The PWA client responds by clearing browser-managed member state, including `sessionStorage`, member auth cookies, service-worker cache, any `IndexedDB` data, and the installed member-shell service-worker registration on the current device, then falls back to a local cleared screen. (Browser history, disconnected clients, and OS-level caches are outside the app's control — documented as accepted risk.)
  2. Kernel keyring passphrase entry revoked (`keyctl revoke`).
  3. LUKS volume closed (`cryptsetup luksClose`) — the design assumes that once
     the key is no longer available through the keyring, the encrypted data is
     not practically accessible without the passphrase.
  4. tmpfs unmounted (all ephemeral data vanishes).
  5. Docker containers killed, all network connections dropped.
- **Target:** under 3 seconds from trigger to clean state. This is a design
  goal that must be benchmarked and validated in implementation.
- **Privilege model:** the current design assumes limited privileged operations
  for `cryptsetup` and `tmpfs` management rather than running the whole
  application as root.

### Member Privacy

- No real names required — display names only.
- No persistent identity across operations is intended in the current design.
- No account system is planned for the baseline join flow.

### Authentication Protocol

- On `osk start`, the hub generates a cryptographically random 32-byte **operation token** (base64url-encoded).
- The QR code encodes a URL: `http://<hub-ip>:<port>/join?token=<operation-token>`
- When a member opens this URL, the hub now exchanges the token into a clean browser session by setting an `HttpOnly` cookie and redirecting back to `/join` without the token in the visible URL.
- The current thin member shell can bootstrap initial WebSocket auth from that join cookie. After `auth_ok`, the browser exchanges a short-lived `member_session_code` into a short-lived `HttpOnly` member runtime cookie, so reload/reconnect no longer depend on a reconnect secret in browser JavaScript storage.
- The current browser shell also keeps a scoped IndexedDB outbox for manual reports and observer photo/audio-clip submissions. Queued items keep their stable IDs across replay so reconnect-driven resubmission stays duplicate-safe against the hub.
- On WebSocket upgrade, the first JSON message is still `{"type": "auth", "name": "<display-name>"}` for the normal browser flow, or `{"type": "auth", "token": "<token>", "name": "<display-name>"}` when a non-browser client is used. The hub currently accepts browser reconnects from the member runtime cookie, while legacy explicit `resume_member_id` + `resume_token` support remains available for non-browser/compatibility use. Invalid auth gets an immediate close frame.
- Tokens are planned to be per-operation shared secrets, with all members in an
  operation using the same token.
- **Token rotation:** Coordinator can run `osk rotate-token` or tap "New QR" in the dashboard. This generates a new token; existing authenticated members stay connected, but new joins require the new QR code.
- **Kick:** The current design allows the coordinator to kick individual
  members, but because the token is shared, a determined user could rejoin with
  a new display name until the token is rotated. Per-member tokens remain a
  possible future hardening step.

### Network Security

- The design currently assumes **self-signed TLS** for local transport, with
  the QR URL using `https://`. This choice still needs usability validation on
  target mobile browsers.
- Hub operation is intended to work on local WiFi / hotspot without an internet
  requirement.
- WPA3 on the hotspot is a recommended defense-in-depth measure in the planned
  setup guide.
- **Accepted risk:** A member who has joined can still proxy, record, or relay
  what they receive. The trust boundary in the baseline design is the
  operation-level shared token.

## User Experience

### Coordinator Startup

```bash
# One-time install
git clone <repo> && cd osk
./osk install    # pulls containers, downloads models, validates GPU

# Start an operation
./osk start "March for Justice — Downtown"
# intended flow:
# → prompt for operation passphrase
# → launch Docker stack (PostgreSQL on tmpfs)
# → start WiFi hotspot (or print manual config instructions)
# → generate QR code (ASCII in terminal + PNG file)
# → open coordinator dashboard in browser
```

### Member Join Flow

1. Scan QR code shown by coordinator
2. Browser opens to the Osk join page bootstrap URL (served from hub)
3. Hub exchanges the shared operation token into a clean browser session and redirects back to `/join`
4. Enter a display name
5. Browser authenticates the member WebSocket, upgrades into the short-lived member runtime cookie, and continues into the current member shell with live alerts, opt-in GPS sharing, manual report controls, and early sensor capture when promoted
6. Coordinator can promote to Sensor from dashboard

### Coordinator Dashboard (Desktop)

Three-panel layout:

**Left — Member Map:**
- GPS-positioned member clusters with counts
- Individual sensor positions highlighted
- Alert zones overlaid (dashed boundaries where events detected)
- Offline map tiles (Leaflet.js with pre-cached tiles for no-internet operation)

**Center — SitRep + Event Timeline:**
- Top: latest AI situation report with trend indicator (escalating/stable/de-escalating)
- Below: chronological event feed, color-coded by severity
- Source attribution on each event (which sensor/member)
- Pin button per event

**Right — Sensor Management + Stats:**
- Active sensor cards: stream status, latency, frame rate, location
- Controls: pause stream, demote to observer
- Operation stats: uptime, transcript count, frames analyzed, events, alerts, pins, GPU utilization

**Top bar:**
- Operation name and live timer
- Member/sensor count
- QR code button (show for new joiners)
- Emergency wipe button (prominent, always visible)

### Member Mobile UI

**Observer view:**
- Alert feed (color-coded by severity, relative timestamps)
- Group status bar (member count, nearby count, trend indicator)
- Action bar: snap photo, record audio clip, "I see something" report button
- Current implementation: live alert feed, opt-in GPS sharing, manual report submission, observer-side snap photo, short audio clip capture, and reconnect-safe browser queueing for those manual actions are present; alert pinning UI and richer review affordances are still planned

**Sensor view:**
- Same alert feed as observer
- Stream status panel: audio latency, video frame rate, GPS lock
- Source attribution on alerts generated from their data
- Action bar: pause stream, mute audio, "I see something"
- Current implementation: early live microphone capture and worker-backed key-frame sampling are present in the member shell, and the first manifest/service-worker/offline-shell PWA layer now includes install prompting plus a browser outbox for reconnect-safe manual actions, but richer sensor controls and fuller resilient offline behavior are still planned

### Operation Lifecycle

```bash
# Normal shutdown
./osk stop
# → closes WebSocket connections (members see "Operation ended")
# → revokes kernel keyring passphrase entry
# → unmounts tmpfs (all unpinned data vanishes)
# → closes LUKS volume (encrypted at rest, requires passphrase to reopen)
# → stops containers

# Post-operation evidence access
./osk evidence unlock    # prompts for passphrase, read-only viewer
./osk evidence export    # creates zip of all pinned items
./osk evidence destroy   # shreds the encrypted volume permanently
```

## API Contract

### REST Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/join?token=<token>` | Token in query | Serves the join page |
| GET | `/join` | Join or member runtime cookie | Serves the clean join page after QR bootstrap |
| GET | `/member` | Join or member runtime cookie | Serves the thin member runtime shell |
| GET | `/api/member/session` | Join or member runtime cookie | Reports current member browser-session status |
| POST | `/api/member/runtime-session` | Short-lived member session code | Exchanges a post-auth browser code into the member runtime cookie |
| DELETE | `/api/member/session` | Join or member runtime cookie | Clears the current member browser-session cookies |
| GET | `/api/operation/status` | Coordinator only | Operation metadata and stats |
| GET | `/api/members` | Coordinator only | List all members with roles and status |
| POST | `/api/members/<id>/promote` | Coordinator only | Promote observer to sensor |
| POST | `/api/members/<id>/demote` | Coordinator only | Demote sensor to observer |
| POST | `/api/members/<id>/kick` | Coordinator only | Kick member from operation |
| POST | `/api/pin/<event_id>` | Coordinator only in the current implementation | Pin an event for preservation |
| POST | `/api/report` | Coordinator only in the current implementation | Direct REST manual report path; member browsers currently submit manual reports over the member WebSocket |
| POST | `/api/rotate-token` | Coordinator only | Generate new operation token |
| POST | `/api/wipe` | Coordinator only | Trigger emergency wipe |
| GET | `/api/sitrep/latest` | Coordinator only | Latest situation report |
| GET | `/api/events?since=<timestamp>` | Coordinator only | Event timeline with filtering |

### WebSocket Messages

Single WebSocket endpoint: `wss://<hub>/ws`

**Member → Hub:**

| Type | Format | Roles | Description |
|---|---|---|---|
| `auth` | `{"type":"auth", "name":"<name>"}` or `{"type":"auth", "token":"<token>", "name":"<name>"}` | All | First message after connect. Browser members can authenticate from the cookie-backed join/runtime sessions; non-browser clients can still send the token explicitly. Hub responds with `auth_ok` including `member_id`, `role`, and a short-lived `member_session_code` for browser runtime-session upgrade, or closes the connection. |
| `audio` | Binary frame (PCM 16-bit, 16kHz) | Sensor | Audio chunk. Preceded by `{"type":"audio_meta", "duration_ms": N}` JSON frame. |
| `key_frame` | Binary frame (JPEG) | Sensor | Key frame from edge sampling. Preceded by `{"type":"frame_meta", "change_score": 0.0-1.0}` JSON frame. |
| `gps` | `{"type":"gps", "lat": N, "lon": N, "accuracy": N}` | All | Location update. |
| `report` | `{"type":"report", "text":"<description>"}` | All | Manual "I see something" report. |
| `clip` | Binary frame (audio) | Observer | Manual audio clip. Preceded by `{"type":"clip_meta", "duration_ms": N}`. |
| `photo` | Binary frame (JPEG) | Observer | Manual photo snap. |
| `pong` | `{"type":"pong"}` | All | Response to hub ping. |

**Hub → Member:**

| Type | Format | Roles | Description |
|---|---|---|---|
| `auth_ok` | `{"type":"auth_ok", "member_id":"<id>", "role":"<role>"}` | All | Authentication success. |
| `alert` | `{"type":"alert", "severity":"<level>", "category":"<cat>", "text":"<msg>", "event_id":"<id>", "timestamp":"<iso>"}` | All (filtered by role) | Alert notification. |
| `role_change` | `{"type":"role_change", "role":"<new_role>"}` | All | Coordinator changed your role. |
| `status` | `{"type":"status", "members": N, "nearby": N, "trend":"<trend>"}` | All | Periodic group status update (every 30s). |
| `wipe` | `{"type":"wipe"}` | All | Emergency wipe — client clears all local state. |
| `op_ended` | `{"type":"op_ended"}` | All | Operation has ended, disconnect. |
| `ping` | `{"type":"ping"}` | All | Heartbeat every 15 seconds. Member must respond with `pong` within 5 seconds or connection is considered dead. |

**Hub → Coordinator (additional):**

| Type | Format | Description |
|---|---|---|
| `event` | `{"type":"event", "severity":"...", "category":"...", "text":"...", "source":"...", "location":{...}, "event_id":"...", "timestamp":"..."}` | Full event for timeline. |
| `sitrep` | `{"type":"sitrep", "text":"...", "trend":"...", "timestamp":"..."}` | New situation report. |
| `member_update` | `{"type":"member_update", "member_id":"...", "name":"...", "role":"...", "status":"...", "location":{...}, "stream_metrics":{...}}` | Member status change or GPS update. |

## Hardware Requirements

These are expected requirements for the planned local-first deployment model.

| Component | Minimum | Recommended |
|---|---|---|
| GPU | NVIDIA with 6+ GB VRAM, CUDA support | NVIDIA with 8+ GB VRAM (RTX 3060 or better) |
| RAM | 16 GB | 32 GB (tmpfs PostgreSQL + Docker overhead) |
| Storage | 20 GB free (models + LUKS volume) | 40 GB free |
| CPU | 4 cores | 8+ cores (audio ingest + WebSocket handling) |
| WiFi | Capable of AP mode (hostapd/nmcli) | Dual-band (5 GHz for less interference in crowds) |
| OS | **Linux only** (required for tmpfs, LUKS, nmcli, NVIDIA Docker) | Fedora, Ubuntu, or Arch with NetworkManager |

The current design assumes hotspot management runs on the **host Linux OS** and
not purely inside a container. It also assumes coordinator hardware with an
NVIDIA GPU and proprietary drivers for the intended accelerated workloads.

## Configuration

The repo now has a real `~/.config/osk/config.toml` surface backed by
`src/osk/config.py`. The table below calls out representative implemented
settings plus a few still-planned operational knobs. `src/osk/config.py`
should be treated as the authoritative current list.

| Parameter | Default | Description |
|---|---|---|
| `max_sensors` | 10 | Maximum simultaneous sensor streams |
| `transcriber_backend` | `fake` | Transcript backend (`fake` or `whisper`) |
| `whisper_model` | `small` | Whisper model size (tiny/base/small/medium/large-v3) |
| `vision_backend` | `fake` | Vision backend (`fake` or `ollama`) |
| `vision_model` | `llama3.2-vision:11b-instruct-q4_K_M` | Ollama vision model |
| `synthesis_backend` | `heuristic` | Current synthesis backend; heuristic today |
| `summarizer_model` | `mistral` | Ollama model for event generation and SitReps |
| `sitrep_interval_minutes` | 10 | Minutes between automatic SitReps |
| `alert_cooldown_seconds` | 60 | Minimum seconds between alerts of same category |
| `audio_queue_size` | 128 | Max queued audio chunks before backpressure |
| `frame_queue_size` | 64 | Max queued key frames before backpressure |
| `max_audio_payload_bytes` | 2000000 | Member audio payload ceiling |
| `max_frame_payload_bytes` | 4000000 | Member frame payload ceiling |
| `ingest_idempotency_window_seconds` | 900 | Duplicate-safe ingest receipt window |
| `gps_interval_moving_seconds` | 10 | GPS broadcast interval when member is moving |
| `gps_interval_stationary_seconds` | 60 | GPS broadcast interval when member is stationary |
| `frame_change_threshold` | 0.15 | Key frame pixel-difference threshold (0.0-1.0) |
| `frame_baseline_interval_seconds` | 30 | Force a key frame even without change |
| `frame_sampling_fps` | 2.0 | Edge-side video sampling rate |
| `observer_clip_rate_limit` | 3 | Max manual clips per minute per observer |
| `member_outbox_max_items` | 12 | Max queued manual browser outbox items |
| `sensor_audio_buffer_limit` | 3 | Max bounded audio chunks buffered in-browser on reconnect |
| `sensor_frame_buffer_limit` | 4 | Max bounded key frames buffered in-browser on reconnect |
| `dashboard_buffer_signal_min_items` | 2 | Minimum buffered items before sustained dashboard signal tracking starts |
| `dashboard_buffer_signal_warning_items` | 5 | Warning threshold for sustained member-buffer dashboard signals |
| `dashboard_buffer_signal_critical_items` | 9 | Critical threshold for sustained member-buffer dashboard signals |
| `dashboard_buffer_signal_snooze_minutes` | 15 | Default snooze duration for transient coordinator dashboard signals |
| `luks_volume_size_gb` | 1 | Size of the encrypted evidence volume |
| `tls_cert_path` | `~/.config/osk/cert.pem` | Self-signed TLS certificate |
| `tls_key_path` | `~/.config/osk/key.pem` | Self-signed TLS private key |
| `hub_host` | `0.0.0.0` | Local bind host for the hub server |
| `hub_port` | 8443 | Local bind port for the hub server |
| `join_host` | `127.0.0.1` | Advertised host for generated join links/QRs |
| `database_url` | `postgresql://osk:osk@localhost:5432/osk` | Local Postgres connection string |
| `hotspot_ssid` | `osk-<random>` | WiFi hotspot SSID |
| `hotspot_band` | `5GHz` | WiFi band (2.4GHz/5GHz) |
| `map_tile_cache_path` | `~/.config/osk/tiles/` | Offline map tile cache location |
| `storage_backend` | `luks` | Evidence storage mode (`luks` or dev-only `directory`) |

## Offline Map Tiles

- Tile source: OpenStreetMap (default) or any XYZ tile server.
- Pre-caching via CLI: `osk tiles cache --area "39.7,-104.9,39.8,-104.8" --zoom 13-17`
  - Area specified as bounding box (south,west,north,east) or by place name with geocoding.
  - Zoom levels 13-17 cover neighborhood to street level.
  - Approximate size: ~50-100 MB per square mile at zoom 13-17.
- Tiles stored as a directory of PBF/PNG files in `map_tile_cache_path`.
- Leaflet.js on the coordinator dashboard loads tiles from the hub's HTTP server (which serves cached tiles), falling back to placeholder grid if tiles are missing.
- Members do not see the map — only the coordinator dashboard uses it.

## Tech Stack

Current and planned stack for the implementation track:

| Layer | Technology | Source |
|---|---|---|
| API server | FastAPI + Uvicorn | Carry over from bodycam-summarizer |
| Real-time comms | WebSockets (binary audio + JSON control) | Carry over, adapt for member roles |
| Transcription | faster-whisper (GPU accelerated) | Transplant `transcriber.py` + `whisper_runtime.py` |
| Vision analysis | Ollama (llama3.2-vision) | Transplant `cv_worker.py` + `cv_fusion.py` |
| AI summarization | Ollama (local models only) | Adapt `summarizer.py`, new prompt templates |
| Database | PostgreSQL on tmpfs | Carry over `db.py`, new schema |
| Encrypted storage | LUKS via `cryptsetup` | New |
| Mobile client | Vanilla JS PWA | New |
| Hotspot management | `nmcli` / NetworkManager | New |
| CLI | Python CLI (`osk` command) | New |
| Containers | Docker/Podman compose | Carry over, adapt |
| Testing | pytest + pytest-asyncio | Carry over patterns |
| Map tiles | Leaflet.js with offline tile cache | New |

## Project Structure

Intended repository/application structure once implementation begins:

```
osk/
├── src/osk/
│   ├── __main__.py              # CLI entry (osk start/stop/config/evidence)
│   ├── cli.py                   # Argument parsing and command dispatch
│   ├── hub.py                   # Orchestrator — starts/stops all subsystems
│   ├── server.py                # FastAPI app, WebSocket handler, REST routes
│   ├── connection_manager.py    # Member connections, roles, auth tokens
│   ├── operation.py             # Operation lifecycle (create/join/stop)
│   │
│   ├── # Intelligence engines
│   ├── audio_ingest.py          # Audio stream buffering and queue management
│   ├── transcriber.py           # Whisper engine (transplanted + adapted)
│   ├── whisper_runtime.py       # Adaptive model selection (transplanted)
│   ├── frame_ingest.py          # Key frame receiving and deduplication
│   ├── vision_engine.py         # Ollama vision analysis (transplanted + adapted)
│   ├── vision_fusion.py         # Temporal fusion (transplanted)
│   ├── location_engine.py       # GPS tracking, clustering, geofence
│   │
│   ├── # Synthesis layer
│   ├── event_generator.py       # Fuse sources → Events
│   ├── alert_engine.py          # Events → filtered Alerts to members
│   ├── sitrep_generator.py      # Periodic situation reports
│   │
│   ├── # Data & storage
│   ├── db.py                    # asyncpg layer (adapted for new schema)
│   ├── models.py                # Pydantic models (Operation, Member, Event, etc.)
│   ├── storage.py               # Ephemeral/pin/LUKS management
│   ├── migrations/              # SQL migrations for new schema
│   │
│   ├── # Client
│   ├── static/                  # PWA assets (JS, manifest, service worker)
│   ├── templates/
│   │   ├── coordinator.html     # Coordinator dashboard
│   │   ├── member.html          # Observer/Sensor mobile UI
│   │   └── join.html            # QR join flow
│   │
│   └── # Operations
│       ├── hotspot.py           # WiFi hotspot setup via nmcli
│       ├── qr.py                # QR code generation
│       └── evidence.py          # Post-op evidence viewer/exporter
│
├── tests/
├── scripts/
├── compose.yml
├── Dockerfile
├── pyproject.toml
└── README.md
```

## Transplant Map

Modules carried from bodycam-summarizer with adaptations:

| bodycam-summarizer | Osk | Adaptations |
|---|---|---|
| `transcriber.py` | `transcriber.py` | Queue-based multi-stream scheduling, priority by role |
| `whisper_runtime.py` | `whisper_runtime.py` | Minimal changes — adaptive model selection works as-is |
| `cv_worker.py` | `vision_engine.py` | Receives pre-sampled key frames (edge sampling replaces hub-side sampling) |
| `cv_schema.py` | `models.py` | CV event/observation types folded into unified Pydantic models |
| `cv_fusion.py` | `vision_fusion.py` | Same temporal fusion logic, new observation categories |
| `cv_sampling.py` | `static/sampling.js` | Moved to edge — JS implementation of frame differencing |
| `summarizer.py` | `event_generator.py` + `sitrep_generator.py` | Split into event generation and periodic SitReps. New civilian-context prompts. Ollama only. |
| `alert_scanner.py` | `alert_engine.py` | New alert rules for civilian patterns. Proximity targeting. Rate limiting. |
| `server.py` (WebSocket) | `server.py` + `connection_manager.py` | Role-based connections, binary audio streams, member auth |
| `db.py` | `db.py` | New schema, tmpfs-aware connection management |
