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
