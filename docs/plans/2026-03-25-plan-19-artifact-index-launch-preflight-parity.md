# Plan 19: Artifact Index Launch-Preflight Parity

## Goal

Keep generated artifact indexes such as `latest.json` on the same launch
preflight story as the canonical run payloads.

## Why

Both Chromebook wrappers merge `launch_preflight` into `result.json`, but the
shared run-index builder still drops that field when it writes `latest.json` and
`runs.jsonl`. That weakens the quick handoff surface for launch failures and
forces operators back into the full result artifact to inspect environment
capture data.

## Scope

- preserve `launch_preflight` in generated run index entries
- add wrapper tests that assert `latest.json` mirrors the run payload’s
  `launch_preflight`

## Out of Scope

- changing launch preflight capture itself
- redesigning the full index schema beyond this parity fix
- changing wrapper execution flow

## Acceptance Criteria

- `latest.json` includes `launch_preflight` when the run payload has it
- wrapper tests catch regressions for both real-hub and member-shell flows

## Verification

- `pytest tests/test_chromebook_real_hub_wrapper.py tests/test_chromebook_member_shell_wrapper.py -q`
- `pytest`



> Roadmap note: This file is a scoped implementation or historical planning document. Read it through [`2026-03-28-end-state-product-roadmap.md`](./2026-03-28-end-state-product-roadmap.md). If sequencing, priority, or scope conflict with the roadmap, follow the roadmap.
