# Plan 16: Chromebook Wrapper Contract Parity

## Goal

Keep the outer Chromebook real-hub wrapper on the same result-contract shape as
`real_hub_validation.py`, even when the wrapper fails before the Python runner
can execute.

## Why

Plan 15 extended the runner payload with `members_snapshot_path`, but the
wrapper-generated fallback `result.json` and the wrapper test stub still emit an
older `captures` shape. That leaves pre-launch failures and test doubles on a
different contract than successful runs.

## Scope

- add the missing capture keys to wrapper-generated failure payloads
- align the wrapper test stub with the current runner payload shape
- add contract assertions in wrapper tests so future runner-shape changes are
  caught at the wrapper boundary too

## Out of Scope

- changing runtime behavior of the validation runner itself
- changing live browser orchestration steps
- changing artifact contents beyond contract-key parity

## Acceptance Criteria

- wrapper-generated pre-launch failure results include the same `captures` keys
  as the runner payload, with unavailable paths set to `null`
- wrapper success-path test stub mirrors the same capture-key set
- wrapper tests assert the new contract shape

## Verification

- `pytest tests/test_chromebook_real_hub_wrapper.py -q`
- `bash -n scripts/chromebook_real_hub_validation.sh`
- `pytest`



> Roadmap note: This file is a scoped implementation or historical planning document. Read it through [`2026-03-28-end-state-product-roadmap.md`](./2026-03-28-end-state-product-roadmap.md). If sequencing, priority, or scope conflict with the roadmap, follow the roadmap.
