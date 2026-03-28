# Plan 23: Operator Artifact Bundle

## Goal

Collapse the real-hub validation handoff into one operator-facing bundle
artifact that summarizes the run outcome, closure state, and follow-up detail
paths without forcing operators to reconcile multiple JSON files by hand.

## Why

The current validation runner already emits the raw ingredients an operator
needs: `result.json`, `closure-summary.json`, local snapshots, audit slice, and
member-scoped follow-up detail files. But the handoff still spans several
artifacts with duplicated counts and no single index for the closure boundary.
That increases review friction and makes it easy to miss the current cleanup
state during restart and wipe follow-up drills.

## Scope

- add a dedicated operator-facing bundle artifact to `real_hub_validation.py`
- populate it from existing run artifacts instead of recomputing a parallel
  readiness model
- expose the new bundle path in `result.json` captures with stable key parity
- document how operators should use the bundle as the primary handoff artifact
- add contract tests for dry-run, unavailable-closure, and captured-closure
  paths

## Out of Scope

- changing the meaning of `result.json` as the top-level contract artifact
- replacing `closure-summary.json`, `wipe-readiness.json`, or member detail
  artifacts
- adding new coordinator APIs or changing wipe-follow-up semantics

## Acceptance Criteria

- each real-hub validation run writes one operator-facing bundle artifact
- the bundle summarizes run metadata, closure state, wipe evidence status, and
  all existing capture paths relevant to operator handoff
- the bundle points at member-scoped follow-up detail artifacts when they exist
- `result.json` exposes the bundle path for both dry-run and runtime flows,
  using `null` when the bundle is unavailable
- tests cover the bundle contract for dry-run, unavailable closure, and
  captured closure outputs

## Verification

- `pytest tests/test_real_hub_validation_contract.py -q`
- `ruff check scripts/real_hub_validation.py tests/test_real_hub_validation_contract.py`
- `pytest`



> Roadmap note: This file is a scoped implementation or historical planning document. Read it through [`2026-03-28-end-state-product-roadmap.md`](./2026-03-28-end-state-product-roadmap.md). If sequencing, priority, or scope conflict with the roadmap, follow the roadmap.
