# Workflow

This document describes the recommended development pattern for Osk while it is
primarily built by a solo maintainer with help from AI coding agents.

## Default Model

- The maintainer owns direction, review, and merge decisions.
- Agents handle well-scoped implementation tasks.
- `main` remains protected and should not become a staging branch for large,
  multi-concern changes.

## Recommended Loop

1. Start from a documented plan or an issue.
2. Define one narrow task with clear acceptance criteria.
3. Create a short-lived branch.
4. Let an agent implement the smallest complete version of that task.
5. Run local verification.
6. Review the diff for truthfulness, safety posture, and provenance.
7. Squash merge when the change is coherent and verified.

## Task Sizing Guidance

Prefer tasks that:

- Touch one subsystem
- Fit in one reviewable diff
- Have obvious acceptance criteria
- Can be validated with unit or smoke tests

Avoid tasks that:

- Span multiple phases
- Mix scaffolding, UI, database, and infrastructure in one change
- Introduce design changes without updating docs

## Review Checklist

Before merging, confirm:

- The change matches the relevant plan document
- Tests exist for behavior that changed
- README and contributor docs are still accurate
- No new security or privacy guarantee is stated without validation
- Any copied/adapted material is recorded in `docs/PROVENANCE.md`

## Current Gate

The repo now has meaningful implementation slices across Phases 1 through 5.
The next stage should stay disciplined in a different way:

- Prefer operational hardening and real-world validation over new surface area
- Keep fake and real adapters behind the same owned service boundary
- Keep Whisper/Ollama calls behind explicit interfaces rather than wiring them
  directly into route or WebSocket handlers
- Treat observability as part of the feature, not follow-up cleanup
- Preserve the current browser auth posture: one-time bootstrap inputs should
  exchange into short-lived `HttpOnly` cookie/session flows instead of
  long-lived browser-managed JS storage
- Keep reconnect/retry behavior explicit for ingest protocols rather than
  assuming lossy mobile transport will behave perfectly
- Keep transient coordinator telemetry and dashboard signals config-driven and
  local to runtime state unless there is a deliberate design change to persist
  them
- Prefer reviewable synthesized state over ephemeral-only outputs when adding
  new coordinator-facing intelligence features
- Validate real browser/device behavior outside the sandbox before claiming
  mobile or PWA flows are field-ready

## Suggested Order For The Next Stage

For the next implementation stage, follow this order:

1. Real browser/device validation for `/join` -> `/member`, offline/outbox
   replay, installability, and reconnect behavior
2. Operations tooling: hotspot control, tile caching, evidence/export, wipe
   drills, and the host-side install path that makes the current runtime more
   field-usable
3. Broader resend/session hardening across hub restarts so member/mobile
   capture survives more than transient reconnects
4. Higher-quality synthesis and review ergonomics beyond the current heuristic
   correlation model
5. Dashboard and mobile UX expansion on top of those hardened/runtime-validated
   surfaces

## When To Require Extra Human Attention

Pause and review carefully when a task touches:

- Auth and membership rules
- Key handling, encryption, or wipe logic
- Privacy guarantees
- Network transport assumptions
- Any transplant from predecessor repositories

## Direct Commits vs PRs

Docs and repo-governance updates can be committed directly when they are small
and obvious.

Code changes should usually still go through a branch and PR flow, even with a
single maintainer, because that gives AI-generated changes a clean review
boundary.
