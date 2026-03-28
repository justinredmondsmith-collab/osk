# Plan 26: Real-Hub Latest Report

## Goal

Add a small real-hub report consumer that reads indexed `latest.json` output
and prints operator-facing closure status directly from the embedded
`operator_handoff` summary.

## Why

Phase 25 moved compact handoff data into artifact indexes, but there is still
no repo-owned consumer that turns that indexed data into a direct operational
summary. Operators still need to open JSON files by hand even when the index
already contains the closure state they need.

## Scope

- add a `chromebook_real_hub_report.sh` helper that reads
  `output/chromebook/real-hub-validation/latest.json` by default
- print run status, provenance, result path, handoff path, and indexed closure
  summary fields when present
- support an explicit `--artifact-root` override and a machine-readable
  `--json` mode
- add tests for indexed-handoff and no-handoff cases
- document the report helper in the real-hub runbook

## Out of Scope

- adding a full real-hub gate wrapper in this phase
- changing the structure of `latest.json` or `operator-handoff.json`
- replacing the existing validation wrapper output

## Acceptance Criteria

- operators can run one repo-owned command to inspect the latest real-hub run
  without opening run-local JSON files
- plain-text output includes indexed operator closure status and unresolved
  follow-up counts when the handoff summary exists
- `--json` returns the same summarized view for automation
- tests cover both indexed-handoff and no-handoff latest artifacts

## Verification

- `pytest tests/test_chromebook_real_hub_report.py -q`
- `bash -n scripts/chromebook_real_hub_report.sh`
- `pytest`



> Roadmap note: This file is a scoped implementation or historical planning document. Read it through [`2026-03-28-end-state-product-roadmap.md`](./2026-03-28-end-state-product-roadmap.md). If sequencing, priority, or scope conflict with the roadmap, follow the roadmap.
