# Plan 17: Artifact Index Capture Parity

## Goal

Keep generated artifact indexes such as `latest.json` on the same capture-path
story as the underlying run `result.json`.

## Why

The real-hub runner and outer wrapper now emit richer `captures` metadata, but
`write_artifact_indexes()` still strips that block when it writes `latest.json`
and `runs.jsonl`. That makes the quick handoff surface weaker than the canonical
run artifact and forces operators to open the full result file for basic artifact
navigation.

## Scope

- preserve the `captures` block in generated run index entries
- add tests that assert `latest.json` retains the capture metadata for the
  real-hub wrapper path

## Out of Scope

- changing the capture values themselves
- changing wrapper or runner execution flow
- redesigning the full index schema beyond capture-path parity

## Acceptance Criteria

- `latest.json` includes the same `captures` block as the source run payload
- `runs.jsonl` entries inherit the same capture metadata
- wrapper tests catch future regressions in that parity

## Verification

- `pytest tests/test_chromebook_real_hub_wrapper.py -q`
- `pytest`



> Roadmap note: This file is a scoped implementation or historical planning document. Read it through [`2026-03-28-end-state-product-roadmap.md`](./2026-03-28-end-state-product-roadmap.md). If sequencing, priority, or scope conflict with the roadmap, follow the roadmap.
