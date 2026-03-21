# AGENTS

This repository is maintained by a solo human maintainer with heavy AI-assisted
implementation. Agents are expected to move work forward quickly, but the repo
still has a few non-negotiable rules.

## Operating Model

- `main` should stay releasable and understandable.
- Most code changes should be small, single-concern changes.
- The human maintainer is the final decision-maker for product direction,
  privacy posture, licensing, and safety claims.
- Agents are implementation tools, not the authority on security guarantees or
  legal interpretation.

## Project Invariants

- Keep Osk local-first. Do not introduce required cloud APIs without an
  explicit design change.
- Keep privacy and safety claims truthful. Do not describe a behavior as
  implemented, verified, or benchmarked unless it actually is.
- Treat the existing design and plan documents as the current source of truth
  for intended behavior.
- Preserve `AGPL-3.0-only` licensing intent for code unless a file explicitly
  says otherwise.
- Record copied or adapted code, prompts, templates, or substantial text in
  `docs/PROVENANCE.md`.

## How Agents Should Work

- Start from the relevant plan document before changing code.
- Keep task scope narrow. Prefer one subsystem or one layer per change.
- Update docs when behavior or repo state changes.
- Add or update tests whenever behavior changes.
- Avoid speculative refactors while the codebase is still forming.

## Human Review Required

The maintainer should explicitly review changes that affect:

- Authentication or authorization
- Cryptography, key handling, or wipe behavior
- Privacy guarantees or data retention claims
- Threat model or trust boundary changes
- License, provenance, or attribution handling
- Network exposure, remote access, or cloud dependency

## Definition of Done

A change is not done until all of the following are true:

- The diff is scoped and coherent
- Tests pass, or the change clearly documents why tests are not applicable
- Public docs remain truthful
- Any copied/adapted material is reflected in `docs/PROVENANCE.md`
- The repo is in a clean state after verification

## Recommended Task Shape

Good agent-sized tasks:

- Add one module and its tests
- Implement one CLI subcommand skeleton
- Wire one dependency-free subsystem
- Tighten one doc set to match current behavior
- Add one CI or tooling improvement

Bad agent-sized tasks:

- "Implement Phase 1"
- "Build the whole dashboard"
- "Integrate everything from bodycam-summarizer"
- "Fix all docs and code issues"

## Workflow Reference

For the practical execution loop, see `docs/WORKFLOW.md`.
