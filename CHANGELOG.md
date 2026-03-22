# Changelog

All notable changes to this project should be documented in this file.

The format is based on Keep a Changelog, and this repository currently tracks
changes manually while the project is in its early public setup phase.

## [Unreleased]

### Added

- Foundational hardening: local-only admin HTTP access for coordinator routes,
  user-scoped runtime state paths, and Ruff lint/format enforcement in CI
- Public governance documents: code of conduct, contributing guide, security
  policy, safety limits, notice, and provenance tracking
- Explicit `AGPL-3.0-only` licensing language
- GitHub issue templates, pull request template, and `CODEOWNERS`
- Agent workflow guidance in `AGENTS.md` and `docs/WORKFLOW.md`
- Initial Python package scaffold, CLI skeleton, tests, and CI workflow
- Phase 1 foundations: core models, config, database layer, storage manager,
  and initial migration SQL
- Phase 1 operation and server slice: operation lifecycle, connection manager,
  and initial FastAPI REST/WebSocket wiring
- Phase 1 host-side setup: TLS certificate generation, QR generation, CLI
  command parsing, hub orchestration stub, and local compose files
- Phase 1 startup hardening: install readiness checks, tracked database
  migrations, and optional Docker Compose management for default local
  services
- Development-friendly host control: directory-backed storage mode, `osk stop`,
  hub state tracking, and configurable local Postgres port mapping for smoke
  runs on busy machines
- Graceful local runtime control: read-only `osk status`, file-based shutdown
  requests before SIGTERM fallback, and clean `osk start` exit on remote stop
- Status polish: human-readable uptime/UTC timestamps and machine-readable
  `osk status --json` output for agent workflows
- Separate coordinator API auth token, operation resume on restart, and
  persisted shutdown tracking for active operations
- Member reconnect tokens, reconnect-aware WebSocket auth, and audit event
  storage plus local admin audit retrieval
- Local operator sessions, CLI operator login/status/logout flows, member
  heartbeat tracking, and stale-connection disconnect handling
- One-time local operator bootstrap exchange, `osk audit`, `osk logs`,
  machine-readable `osk doctor --json`, and runtime log file visibility in
  hub status
- `osk members`, extra operator audit events for bootstrap expiry/session
  refresh/logout, and clearer startup failure logging with runtime log hints
- Phase 2 contract-first slice: intelligence contracts, deterministic fake
  adapters, and a normalization pipeline for audio, frame, and location inputs
- Phase 2 queue primitives: bounded audio ingest with priority backpressure and
  frame ingest with dedupe, observer rate limits, and per-member queue caps
- Phase 2 worker loops: fake-backed background transcription and vision workers
  with callback hooks, metrics, and queue-drain lifecycle tests
- Phase 2 runtime adapters: local Whisper profile fallback manager, transcript
  cleanup heuristics, and an Ollama vision analyzer behind the worker
  interfaces, with provenance recorded for adapted predecessor code
- Phase 2 hub-owned intelligence service: config-selectable fake or real
  transcript/vision adapters, worker lifecycle ownership in the hub, and an
  admin-visible runtime status endpoint
- Phase 2 live ingest and synthesis bridge: member GPS/audio/frame submission
  into the owned intelligence service, persisted intelligence observations,
  heuristic event synthesis, alert fan-out, and a local admin observations API
- Phase 2 media/runtime hardening: `ffmpeg`-backed compressed audio decode for
  real Whisper mode, transport payload ceilings, corroboration-aware synthesis,
  and rolling sitrep generation
- Phase 2 operator review slice: persisted synthesis findings, local
  `osk findings`, `/api/intelligence/findings`, and duplicate-safe media
  acknowledgements when clients reuse stable ingest keys across reconnects
- Phase 2 coordinator review actions: per-finding detail, acknowledge/resolve/
  escalate/note flows, local `osk finding ...` commands, and durable ingest
  receipts so duplicate detection survives hub restarts
- Dashboard-readiness review surfaces: filtered finding retrieval, mixed
  review-feed queries across findings/events/sitreps, finding reopen and
  correlation flows, and local `osk review` / `osk finding reopen|correlations`
  commands
- Thin coordinator review shell: local `/coordinator` UI, static dashboard
  assets, and `osk dashboard` for printing a session-backed local review URL
- Live coordinator review stream: same-origin dashboard-state/SSE endpoints,
  member health and ingest-pressure context, and an early relative-position
  field map in the local review shell
- Local cached-tile map path for the coordinator shell, including a protected
  `/tiles/{z}/{x}/{y}.png` endpoint, dashboard tile-cache status in the live
  snapshot, and relative-position fallback when cached map coverage is absent
- Thin member bootstrap shell: clean `/join` redirect flow, cookie-backed
  member browser session, `/member` runtime shell, and WebSocket auth that can
  bootstrap from the member cookie instead of JS-stored shared join token
- Early member runtime slice: live alert feed, opt-in GPS sharing with
  throttled browser updates, reconnect-aware member runtime state, and manual
  report acknowledgements over the member WebSocket
- Early sensor media capture slice: browser-side microphone capture,
  worker-backed key-frame sampling, dedicated capture modules, and member
  runtime wiring for live audio/frame ingest
- Hardened member runtime sessions: `/api/member/runtime-session`, short-lived
  browser `member_session_code` exchange into an `HttpOnly` runtime cookie,
  WebSocket resume from that cookie, and browser reconnect flow without a
  JS-stored member reconnect secret
- Observer media and first PWA layer: dedicated observer photo/audio-clip
  capture module, duplicate-safe ingest keys for manual media, root manifest
  and service worker routes, cached member shell/static assets, and offline
  fallback behavior for previously loaded join/member pages
- Member offline resilience slice: IndexedDB-backed browser outbox for manual
  reports/photos/clips, replay-safe `report_id` acknowledgements, install
  prompt wiring for the member shell, and offline/install status controls in
  the runtime UI
- Member-shell manual smoke helper for real browser/device testing outside the
  sandboxed CI/runtime environment, plus per-item outbox review controls for
  queued notes, photos, and audio clips
- Bounded sensor reconnect buffering in the member browser shell, reusing the
  local outbox for recent audio chunks and key frames instead of dropping all
  live capture during reconnects
- Coordinator visibility into member-side browser buffer pressure, plus a
  Playwright-driven member-shell smoke script for localhost-capable
  environments
- Rolling member-buffer trend history in the coordinator shell, built from
  live in-memory member state and exposed through the existing dashboard
  state/SSE surfaces
- Sustained member-buffer warning signals in the coordinator shell, surfaced as
  transient review-feed/current-pulse items without adding new DB persistence
- Local acknowledge/snooze controls for transient coordinator buffer signals,
  plus config-driven threshold and default snooze tuning
- First operations-tooling tile cache slice: `osk tiles status`,
  `osk tiles cache --bbox ... --zoom ...`, and a real local tile download/cache
  module for the dashboard map path
- Standalone hotspot-management slice: `osk hotspot status|up|down|instructions`
  and an `nmcli`-backed host-side hotspot manager with manual fallback copy
- Standalone preserved-evidence slice: `osk evidence unlock|export|destroy`
  and a host-side evidence manager for read-only unlock, zip export, and
  destructive cleanup flows
- Hotspot-aware preflight/startup guidance in `osk doctor` and `osk start`,
  including `join_host` mismatch warnings and field-network next-step hints
- Read-only `osk drill install|wipe` reports plus an operations runbook for
  install readiness and the current partial wipe boundary

### Changed

- README wording to better reflect the current design-stage status
- Design spec metadata and provenance guidance for future code transplants
- Contributor guidance now reflects the presence of the initial code scaffold
- Public docs and plan headers now reflect the current Phase 1 foundation state
  and the repo's current AI-agent workflow
- Phase 2 guidance now treats fake and real runtime adapters as interchangeable
  service-owned implementations instead of standalone experiments
- README and contributor docs now reflect live Phase 2 ingest wiring and the
  current heuristic synthesis bridge
- Docs now call out the current `ffmpeg` requirement for real Whisper browser
  audio ingest and the more stateful heuristic synthesis behavior
- Docs now call out the current local findings surface and the expectation that
  reconnecting clients preserve media ingest keys when resubmitting uploads
- Docs now reflect that findings have a real coordinator review lifecycle and
  that restart-safe ingest dedupe is persisted rather than memory-only
- Docs now call out the stable coordinator review/query surfaces intended to
  support the next dashboard phase
- Docs now distinguish the review-focused coordinator shell from the still
  planned fuller dashboard experience
- The dashboard shell now uses a clean local URL plus one-time dashboard code
  exchange into a short-lived `HttpOnly` cookie instead of URL or JS-stored
  steady-state auth tokens
- Dashboard review docs now distinguish the current live shell and
  relative-position field map from the still-planned fuller tiled/offline map
  experience
- Dashboard docs now reflect the tile-backed map surface more precisely:
  cached local geography when tiles exist, relative fallback when they do not
- Member join docs now reflect the current clean-URL cookie bootstrap instead
  of the old `sessionStorage` operation-token flow
- The thin `/member` shell now survives join-token rotation better by remaining
  loadable without the join cookie and reconnecting from member-scoped resume
  state instead of forcing an immediate redirect
- Member/browser docs now distinguish the current member-auth WebSocket report
  path from the coordinator-only REST report/pin routes
- Member-shell docs now point to the disposable mocked smoke helper for real
  `/join` -> `/member` testing, and the offline UI now lets users retry or
  discard one queued item instead of only replaying or clearing the full queue
- Member-shell docs now distinguish bounded sensor buffering from the larger
  manual-item outbox and no longer describe sensor capture as live-only during
  reconnects
- Dashboard/member docs now describe the new browser buffer-pressure surface
  and the automated Playwright smoke path alongside the existing manual helper
- Dashboard/member docs now describe the rolling member-buffer trend window in
  the coordinator shell instead of only the single-point buffer counts
- Dashboard docs now describe the coordinator shell's sustained buffer warning
  signal path in addition to the raw/trended buffer counts
- Dashboard/contributor docs now describe transient signal acknowledge/snooze
  behavior and the expectation that this state stays local/config-driven
- README/workflow/spec docs now distinguish the current partial Phase 2-5
  implementation state from the still-planned end-state platform and field
  tooling
- Member docs now reflect that the current sensor runtime includes early audio
  and key-frame capture, while fuller media and offline PWA work remain planned
- Member/browser docs now reflect that browser reload/reconnect auth is
  upgraded into a short-lived `HttpOnly` runtime cookie instead of relying on a
  JS-stored reconnect secret
- Member/browser docs now reflect observer manual photo/audio clip support and
  the first real manifest/service-worker/offline-shell PWA slice
- Member/browser docs now reflect reconnect-safe queued manual actions and the
  current installable/offline member shell behavior more precisely
- Operations-tooling docs now describe the conservative hotspot-aware
  doctor/start path instead of implying that the hub silently brings host
  networking up for the operator
- Operations docs now include explicit install/wipe drill guidance and a
  runbook rather than leaving those paths implicit
