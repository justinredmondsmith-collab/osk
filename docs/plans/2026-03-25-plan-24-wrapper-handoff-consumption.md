# Plan 24: Wrapper Handoff Consumption

## Goal

Make the Chromebook real-hub wrapper consume and surface the Phase 23 operator
handoff artifact so wrapper-generated results and operator-facing shell output
stay aligned with the new bundle contract.

## Why

Phase 23 added `captures.operator_handoff_path` and `operator-handoff.json` to
the real-hub validation runner, but the wrapper still synthesizes failure
payloads without that capture key and still points operators at `result.json`
first. That leaves contract parity gaps in early wrapper failures and weakens
the operator-facing value of the new bundle.

## Scope

- add `operator_handoff_path` to wrapper-generated fallback result payloads
- update wrapper test stubs and capture expectations for the new key
- print the handoff artifact path in wrapper completion output when present
- update runbook guidance for the wrapper-facing handoff-first path

## Out of Scope

- changing the real-hub runner contract again
- adding new shell commands beyond the existing wrapper output
- changing artifact index semantics outside the wrapper flow

## Acceptance Criteria

- wrapper-generated failure payloads include `captures.operator_handoff_path`
  with `null` when no handoff file exists
- wrapper success-path tests expect and preserve the handoff capture path
- wrapper terminal output points operators at `operator-handoff.json` before
  falling back to `result.json`
- verification covers the wrapper contract and shell script syntax

## Verification

- `pytest tests/test_chromebook_real_hub_wrapper.py -q`
- `bash -n scripts/chromebook_real_hub_validation.sh`
- `pytest`



> Roadmap note: This file is a scoped implementation or historical planning document. Read it through [`2026-03-28-end-state-product-roadmap.md`](./2026-03-28-end-state-product-roadmap.md). If sequencing, priority, or scope conflict with the roadmap, follow the roadmap.
