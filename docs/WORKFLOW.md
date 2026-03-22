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

The repo now has enough Phase 1 foundation to start Phase 2 work, but the next
stage should still stay disciplined:

- Keep fake and real adapters behind the same owned service boundary
- Add operator-visible diagnostics for new subsystems when practical
- Keep Whisper/Ollama calls behind explicit interfaces rather than wiring them
  directly into route or WebSocket handlers
- Treat observability as part of the feature, not follow-up cleanup

## Suggested Order For The Next Stage

For the next implementation stage, follow this order:

1. Queue and service boundaries
2. Live member ingest wiring
3. Location engine
4. Observation persistence and synthesis layer
5. Coordinator dashboard
6. Mobile client
7. Operations tooling

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
