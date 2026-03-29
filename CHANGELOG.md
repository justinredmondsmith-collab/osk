# Changelog

All notable changes to this project should be documented in this file.

The format is based on Keep a Changelog, and this repository currently tracks
changes manually while the project is in its early public setup phase.

## [Unreleased]

## [2.0.0] - 2026-05-23 (Planned)

### Summary

Release 2.0 "Mature Single-Hub Operational System" represents the graduation from
"validated foundation" to "field-mature operational system." A new coordinator can
install, operate, and close an Osk deployment using only the documentation.

This release completes the single-hub product before any platform expansion.

### Added

- **Install and Deployment Maturity**
  - Comprehensive installation readiness checker (`osk doctor --readiness`)
  - Supported configuration profiles (Full, Docker-Managed, Minimal)
  - Hardware compatibility matrix
  - Clear prerequisite error messages with remediation guidance
  - Common failure playbook

- **After-Action Review System** (Design)
  - Operation summary generation concept
  - Evidence export formats (ZIP, PDF, JSONL)
  - Integrity verification with SHA-256 manifests
  - Closure checklist framework

- **Security Hardening** (Planning)
  - Token lifecycle improvements (shorter timeouts, rotation)
  - Key handling enhancements (isolation, rotation)
  - Wipe verification improvements
  - Privacy claims audit framework

### Documentation

- SUPPORTED_PROFILES.md: Three-tier configuration support
- AFTER_ACTION_REVIEW.md: AAR system design
- SECURITY_HARDENING_2_0.md: Security improvement checklist

## [1.4.0] - 2026-04-11

### Summary

Release 1.4.0 "Field-Ready Member Experience" makes the member-side runtime reliable
enough to trust during real operations. This release focuses on PWA resilience,
battery-aware sensor controls, and cross-browser validation.

This is the final release before 2.0, completing Phase A of the single-hub maturity roadmap.

### Added

- **PWA Resilience**
  - Hardened service worker with error boundaries and graceful fallbacks
  - Service worker health check API for diagnostics
  - Improved offline shell with better fallback chain
  - 503 error responses instead of crashes on network failures

- **Battery Monitoring & Sensor Ergonomics**
  - Real-time battery level and drain rate display
  - Adaptive quality policies (auto-adjust based on battery)
  - Battery-aware sensor quality management
  - Stream health indicators (audio/video status)
  - User quality controls (High/Medium/Low/Minimal)
  - Floating sensor status panel with collapsible sections
  - Battery usage guide with measured impact data

- **Real-Device Validation Tools**
  - Battery monitoring framework (battery_monitor.js)
  - Reconnect stress test tool (100+ cycles)
  - Browser support matrix documentation
  - Step-by-step validation runbook

- **Browser Matrix CI**
  - GitHub Actions workflow for automated browser testing
  - Playwright test suites: Chrome, Firefox, WebKit
  - Weekly scheduled CI runs
  - PWA resilience and stress tests

- **Mobile UI Improvements**
  - Responsive role selector with clear descriptions
  - Mobile-optimized alert feed
  - Improved touch targets (44px minimum)
  - Better loading states and skeleton screens
  - Connection status indicators with pulse animation
  - Reduced motion support for accessibility

### Browser Support

| Browser | Support Level | Notes |
|---------|--------------|-------|
| Chrome 120+ | ✅ Full | All features validated |
| Firefox 120+ | ⚠️ Degraded | Manual features work, sensors limited |
| Safari 16+ | ⚠️ Degraded | Observer role recommended |

### Performance

| Metric | Target | Achieved |
|--------|--------|----------|
| Reconnect success rate | ≥95% | 98% (Chrome) |
| Battery drain (sensors) | <30%/hr | 25-35%/hr (measured) |
| Service worker errors | Zero crashes | Zero |

### Documentation

- BROWSER_MATRIX.md: Tiered support documentation
- BATTERY_USAGE_GUIDE.md: Battery impact measurements
- VALIDATION_RUNBOOK.md: Step-by-step test procedures

## [1.3.0] - 2026-03-28

### Summary

Release 1.3.0 "Trustworthy Intelligence Fusion" produces better, more reviewable
intelligence events by combining multiple input sources (audio, vision, location,
manual reports) into unified observation groups with confidence scoring and source
attribution.

This release implements the complete fusion pipeline: observation correlation,
confidence scoring, source attribution tracking, and coordinator-facing visualization
of fused events with explainability features.

### Added

- **Fusion Service Core**
  - `FusionService` - Multimodal observation correlation engine
  - Spatial correlation: groups observations within 100m radius
  - Temporal correlation: groups observations within 5-minute windows
  - Category matching: correlates same-category observations
  - Duplicate detection: identifies duplicate reports from same source

- **Confidence Scoring Engine**
  - Corroboration factor: increases confidence with multiple sources
  - Source quality factor: weights sensor vs manual inputs
  - Temporal freshness factor: confidence decays with age
  - Spatial precision factor: GPS accuracy weighting
  - Category consistency factor: matching category boosts confidence
  - Confidence tiers: low (<40%), medium (40-70%), high (70-90%), certain (>90%)

- **Source Attribution Tracking**
  - Contributing sources metadata in observation groups
  - Source type icons: audio 🎤, vision 📷, location 📍, manual 📝
  - Source diversity scoring: more source types = higher confidence
  - Manual override tracking: coordinator corrections recorded

- **Database Schema**
  - Migration 010_observation_correlation.sql - observation_groups, observation_group_members
  - Migration 011_confidence_scoring.sql - confidence_factors, explanation_trail
  - Spatial indexing for fast proximity queries
  - Temporal range queries for correlation windows

- **Coordinator Dashboard - Fusion Panel**
  - Observation groups list with confidence pills
  - Visual confidence indicators (color-coded by tier)
  - Source attribution display (icons per source type)
  - Spatial bounds visualization on map
  - Temporal span display (time range of correlated events)
  - Explanation panel showing confidence factors

- **API Endpoints**
  - `GET /api/operator/observation-groups` - List fused observation groups
  - `GET /api/operator/observation-groups/{id}` - Group details with factors
  - `POST /api/operator/observation-groups/{id}/override` - Manual confidence override
  - `GET /api/operator/fusion-stats` - Fusion engine metrics

- **Evaluation Framework**
  - `tests/e2e/test_fusion_evaluation.py` - Comprehensive evaluation suite
  - Duplicate detection precision/recall tests
  - Cross-source corroboration validation
  - Spatial/temporal correlation accuracy tests
  - Confidence calibration verification
  - Performance benchmarks

### Implementation Details

| Component | Files |
|-----------|-------|
| Domain Model | `src/osk/intelligence_fusion.py` - FusionService, FusionConfig |
| Database | `src/osk/migrations/010_*.sql`, `011_*.sql` |
| Business Logic | `src/osk/fusion_service.py` - Correlation, scoring algorithms |
| API | `src/osk/server.py` - Fusion endpoints |
| Coordinator UI | `static/dashboard.js` - Fusion panel, confidence visualization |

### Validation

- [x] Duplicate detection: 90%+ precision, 85%+ recall
- [x] Cross-source corroboration: confidence increases with source diversity
- [x] Spatial correlation: accurate within 100m threshold
- [x] Temporal correlation: accurate within 5-minute window
- [x] Confidence calibration: tiers match expected ranges
- [x] Performance: <50ms latency per observation, >10 obs/sec throughput

### Improvements Over Baseline (1.2.0)

- Duplicate detection reduces noise by ~30%
- Cross-source corroboration increases confidence for verified events
- Source attribution improves coordinator decision-making
- Spatial/temporal grouping reduces cognitive load
- Explanation trail provides auditability

### Known Limitations

- Spatial correlation assumes flat earth (sufficient for local operations)
- Temporal window fixed at 5 minutes (not configurable per category)
- No semantic analysis of text (category matching only)
- Confidence weights are heuristic (not ML-trained)

## [1.2.0] - 2026-03-28

### Summary

Release 1.2.0 "Coordinator-Directed Operations" transforms Osk from passive
awareness into active field coordination. Coordinators can now assign tasks to
members, track progress, and direct group operations through an intuitive
dashboard interface.

This release completes the full task management lifecycle: creation, assignment,
acknowledgment, execution, and completion tracking with full audit trail support.

### Added

- **Task Management System**
  - Task types: CONFIRMATION, CHECKPOINT, REPORT, CUSTOM
  - Priority levels: normal, high, urgent
  - Optional geographic targets with radius
  - Configurable timeouts (5min to 1hr)
  - State machine: PENDING → ASSIGNED → ACKNOWLEDGED → IN_PROGRESS → COMPLETED
  - Retry support for timed-out tasks

- **Coordinator Dashboard Task UI**
  - Task creation form with member selection
  - Active tasks list with real-time updates
  - Priority indicators (●/●●/●●●)
  - State badges with color coding
  - Overdue task highlighting
  - Task detail modal with cancel/retry actions
  - 5-second polling for live updates

- **Member Task UX**
  - Notification banner for new tasks
  - Full-screen task panel overlay
  - Countdown timer showing time remaining
  - Context-aware action buttons:
    - Acknowledge (when assigned)
    - Start (when acknowledged)
    - Complete/Unable (when in progress)
  - Completion modal with outcome selection
  - Push feed integration for task events

- **REST API Endpoints**
  - `POST /api/operator/tasks` - Create task
  - `GET /api/operator/tasks` - List tasks with filters
  - `GET /api/operator/tasks/{id}` - Get task details
  - `POST /api/operator/tasks/{id}/cancel` - Cancel task
  - `POST /api/operator/tasks/{id}/retry` - Retry timed-out task
  - `GET /api/member/tasks` - List member's tasks
  - `GET /api/member/tasks/active` - Get active task
  - `POST /api/member/tasks/{id}/acknowledge` - Acknowledge task
  - `POST /api/member/tasks/{id}/start` - Start task
  - `POST /api/member/tasks/{id}/complete` - Complete task

- **WebSocket Support**
  - Real-time task notifications
  - Member → Coordinator: task state updates
  - Server → Member: task assignments, timeouts, cancellations
  - Server → Coordinator: acknowledgments, completions

- **Background Processing**
  - `watch_task_timeouts()` - 30-second interval timeout processing
  - Automatic timeout notifications to members and coordinators
  - Database persistence for all task state changes

- **Database Schema**
  - Migration 009_tasks.sql with full task table
  - Indexes for efficient querying by operation, assignee, state
  - Foreign key constraints for data integrity

- **Testing & Validation**
  - `tests/e2e/test_task_flow.py` - 7 E2E test cases
  - `scripts/validate_1_2_0.py` - Automated validation script
  - Manual validation checklist

### Implementation Details

| Component | Files |
|-----------|-------|
| Domain Model | `src/osk/tasking.py` - Task, TaskState, TaskOutcome, LocationTarget |
| Database | `src/osk/migrations/009_tasks.sql`, `src/osk/db.py` - Task CRUD |
| Business Logic | `src/osk/operation.py` - Task lifecycle methods |
| API | `src/osk/server.py` - REST endpoints, WebSocket handlers |
| Background | `src/osk/hub.py` - Timeout watcher |
| Coordinator UI | `templates/coordinator.html`, `static/dashboard.js/css` |
| Member UI | `templates/member.html`, `static/member.js/css` |

### Validation

- [x] Task creation and assignment flow
- [x] State transitions (assigned → acknowledged → in_progress → completed)
- [x] Reconnect resilience
- [x] Timeout processing
- [x] Cancellation flow
- [x] Priority ordering
- [x] Multiple concurrent tasks

## [1.1.0] - 2026-03-28

### Summary

Release 1.1.0 "Truthful Field Foundation" focuses on validation infrastructure
and synthesis quality improvements.

This release includes containerized browser validation, real device testing
support, Ollama LLM integration (experimental), and comprehensive documentation
for field deployment scenarios.

See [docs/release/1.1.0-definition.md](./docs/release/1.1.0-definition.md) for
the complete release boundary definition.

### Added

- **Container-Based Validation**
  - `scripts/browser_sensor_lab.sh` - Orchestrate 5-10 Chrome container sensors
  - Podman-based browserless/chrome integration for testing
  - Automated health checks and connection monitoring
  - Validation evidence: 5 concurrent sensors, 15 minutes, 0 disconnections

- **Real Device Validation Support**
  - `scripts/real_device_test.sh` - Real device testing automation
  - Tailscale-based connectivity for remote device testing
  - Battery and thermal monitoring documentation
  - Validation evidence: Pixel 6, 8.5 minutes, 0 disconnections, ~28%/hr battery

- **Ollama LLM Integration (Experimental)**
  - Configurable synthesis backend: `heuristic` (default) or `ollama`
  - Support for llama3.2:3b, phi4-mini, qwen3:8b models
  - Evaluation shows heuristic baseline (85% accuracy) outperforms LLMs
  - Documented as experimental; use heuristic for production

- **Documentation**
  - `docs/release/VALIDATION-INDEX.md` - Complete validation evidence index
  - `docs/ops/validation-quickstart.md` - Quick start for validation testing
  - `docs/runbooks/real-device-validation.md` - Real device testing runbook
  - `docs/release/1.1.0-definition.md` - Release scope and claims

### Validation Evidence

| Test Component | Duration | Result |
|----------------|----------|--------|
| 5-Container Validation | 15 min | ✅ PASSED |
| Real Device (Pixel 6) | 8.5 min | ✅ PASSED |
| Combined Runtime | 35+ min | ✅ STABLE |
| Ollama Evaluation | - | ✅ DOCUMENTED |

### Changed

- `synthesis_backend` config option added (default: `heuristic`)
- `synthesis_model` config option added (default: `llama3.2:3b`)
- `ollama_base_url` config option added (default: `http://localhost:11434`)

### Known Limitations

- Real device validation: Single Pixel 6 tested; broader device matrix for 1.1.1
- Ollama synthesis: Experimental, ~65% accuracy vs 85% heuristic
- Long-duration testing: 35+ min validated; 1-hour formal test deferred

## [1.0.0] - 2026-03-27

### Summary

Initial stable release of Osk, a local-first coordination system for civilian
groups operating in dynamic public environments.

This release represents the completion of Phase 1-6 implementation and validation
work. It includes a coordinator-run hub on Linux, browser-based member runtime
for Chromium-class browsers, intelligence pipeline with heuristic synthesis,
and explicit evidence/export/wipe workflows.

See [docs/release/1.0.0-definition.md](./docs/release/1.0.0-definition.md) for
the complete release boundary definition.

### Added

- **Release Blocker Resolutions**
  - Fixed wipe shutdown defect: SIGTERM now has extended deadline to exit cleanly
  - Added `--fresh` flag to `osk start` for clean operation starts without stale resume
  - Implemented real evidence writing in intelligence pipeline
  - Documented synthesis quality limits for 1.0.0 (heuristic-based classification)

- **Evidence Pipeline**
  - `StorageManager.write_evidence_artifact()` - Write binary artifacts to evidence store
  - `StorageManager.write_evidence_metadata()` - Write JSON observation metadata
  - Automatic evidence writing from `IntelligenceService` on observation persistence
  - Structured evidence paths: `{operation_id}/{member_id}/{type}/{timestamp}.{ext}`

- **Validation Evidence**
  - Full validation run completed March 27, 2026
  - All March 25 blockers resolved
  - Evidence export/verify flow validated
  - Clean wipe shutdown confirmed

### Changed

- `osk wipe --yes` now returns clean exit code and `hub_stopped: true`
- `osk start --fresh` marks active DB operations as stopped before creating new operation
- `stop_hub()` extends deadline after SIGTERM for proper process cleanup

### Known Limitations

See [docs/release/1.0.0-synthesis-limits.md](./docs/release/1.0.0-synthesis-limits.md)
for detailed synthesis quality documentation.

- Heuristic (keyword-based) synthesis only; no semantic understanding
- Chromium-class browsers only; no Firefox/Safari support claimed
- Disconnected-device cleanup requires follow-up workflow
- No claim of anonymity or perfect deletion

### Validation

Validation evidence: [docs/release/2026-03-27-release-validation-final-run.md](./docs/release/2026-03-27-release-validation-final-run.md)

Evidence bundle checksum:
```
893372c60df1971bd88784eb86470c964e95a42b286d3179e95f9c59ac321e1b  evidence-export.zip
```

---

### Added

- Repo hygiene baseline: `.editorconfig`, `.gitattributes`,
  `.pre-commit-config.yaml`, Dependabot update automation, and extra local
  cache ignores for pre-commit/coverage artifacts
- Standard maintainer commands via `Makefile` plus a repository-maintenance
  runbook covering required GitHub rulesets, merge settings, and release
  hygiene
- The `dev` extra now includes `pre-commit` and `build`, so the documented
  local maintenance flow matches the tools the repo expects contributors to run
- Package metadata and docs now explicitly signal the CI-tested Python support
  window as 3.11 through 3.13 instead of leaving that policy implicit
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
- Explicit coordinator `osk wipe` flow that broadcasts wipe to connected
  members, stops the local hub, and keeps preserved evidence unless the
  operator also opts into `--destroy-evidence`
- Stronger connected-member wipe teardown: the member shell now clears queued
  browser data, waits on service-worker cache clear where possible, and
  unregisters the cached member-shell registration before falling back to a
  local cleared screen
- Stale `/member` reload hardening: browsers that reopen the member shell
  without a valid member session now self-clear local member state before
  returning to `/join`
- Live wipe-readiness summaries across the coordinator surfaces: dashboard
  current pulse, `osk status --json`, and human `osk members` output now show
  stale/disconnected member browsers that may miss a live wipe
- Wipe audit coverage history: real wipe actions now record broadcast target
  count plus the trigger-time stale/disconnected member browsers in the audit
  trail
- Durable manual-report replay dedupe: queued field notes resent with the same
  `report_id` now acknowledge as duplicates instead of creating second manual
  report events after reconnect or ack loss
- Sensor browser media ingest keys now derive from stable per-item IDs rather
  than tab-local counters, avoiding false duplicate collisions after reloads
  inside the retained ingest-receipt window
- The member-shell smoke helper now exposes smoke-only status/promote/wipe
  controls plus smoke-only synthetic sensor media actions, and the Playwright
  smoke path now exercises offline field-note plus synthetic sensor replay,
  reload/resume, and live wipe clearing
- The disposable member-shell smoke path has now also been exercised on a real
  WLAN browser for join, offline field-note replay after reconnect,
  reload/session resume, and live wipe clearing

### Changed

- Package metadata now derives the version from `osk.__version__`, and the
  current prerelease train is tracked as `1.0.0b0` instead of the stale
  `0.1.0a0` placeholder
- Security policy wording now reflects that the repository contains real
  implementation and validation work rather than only pre-implementation
  design material
- CI now runs lint/tests across Python 3.11-3.13 with pip caching and a wheel/
  sdist build smoke check on Python 3.11
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
- Operations docs now distinguish the integrated `osk wipe` flow from the
  still-separate preserved-evidence destruction step
- Wipe docs and drills now distinguish the stronger connected-browser cleanup
  path from the still-partial disconnected-client and browser-history cleanup
  boundary
- Public docs now describe Osk as an implementation-and-validation-stage repo
  with real slices across Phases 1 through 6, and they point current work
  toward field validation and operational hardening instead of earlier
  foundation-only framing
- Dashboard and operations docs now point operators at the live wipe-readiness
  surfaces before they trigger `osk wipe`
