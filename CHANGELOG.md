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

### Changed

- README wording to better reflect the current design-stage status
- Design spec metadata and provenance guidance for future code transplants
- Contributor guidance now reflects the presence of the initial code scaffold
- Public docs and plan headers now reflect the current Phase 1 foundation state
  and the repo's current AI-agent workflow
