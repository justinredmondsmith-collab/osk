# Plan 22: Historical Drift Retirement Workflow

## Goal

Stop reviewed stale follow-up from polluting current wipe readiness by adding
an explicit retirement workflow for historical-drift items.

## Why

The repo already distinguishes current cleanup follow-up from
`historical_drift`, and operators can record a review for that older drift.
But review is intentionally non-closing, which means long-dead follow-up can
remain unresolved forever even after an operator has inspected it and decided
it should no longer block the active cleanup boundary.

## Scope

- add an explicit historical-drift retirement action in the coordinator API
- teach wipe readiness to remove retired historical-drift items from current
  unresolved follow-up
- preserve the retirement decision in the audit trail and member detail view
- expose the retirement action and resulting state in the dashboard and shell
  audit filters
- document when operators should use review versus retire

## Out of Scope

- auto-retiring historical drift without an explicit operator action
- changing current follow-up verification semantics for active cleanup work
- claiming disconnected-device cleanup is now automated

## Acceptance Criteria

- operators can retire a `historical_drift` follow-up item without marking it
  as verified for the current cleanup boundary
- retired historical drift no longer counts toward unresolved wipe follow-up
  readiness
- the member-specific follow-up detail and audit trail retain the retirement
  record as handoff context
- tests cover readiness summarization, coordinator API behavior, audit filters,
  and dashboard/shell-facing history output

## Verification

- `pytest tests/test_wipe_readiness.py tests/test_server.py tests/test_hub.py tests/test_cli.py -q`
- `ruff check src/osk/wipe_readiness.py src/osk/server.py src/osk/hub.py tests/test_wipe_readiness.py tests/test_server.py tests/test_hub.py tests/test_cli.py`
- `pytest`



> Roadmap note: This file is a scoped implementation or historical planning document. Read it through [`2026-03-28-end-state-product-roadmap.md`](./2026-03-28-end-state-product-roadmap.md). If sequencing, priority, or scope conflict with the roadmap, follow the roadmap.
