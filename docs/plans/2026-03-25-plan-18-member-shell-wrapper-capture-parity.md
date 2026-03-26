# Plan 18: Member-Shell Wrapper Capture Parity

## Goal

Bring the Chromebook member-shell wrapper failure contract up to the same
artifact-capture story as the real-hub wrapper and generated artifact indexes.

## Why

`chromebook_member_shell_smoke.sh` still writes failure `result.json` payloads
without a `captures` block. That means `latest.json` and `runs.jsonl` cannot
surface artifact pointers for those failure paths even after Plan 17 preserved
capture metadata in the shared index builder.

## Scope

- add an explicit `captures` block to member-shell wrapper failure payloads
- include the launch-preflight artifact path where it is already known
- add test assertions for both wrapper payload and `latest.json`

## Out of Scope

- redesigning the member-shell smoke runner payload
- changing smoke execution flow or launch behavior
- adding new artifacts beyond contract metadata for files already produced

## Acceptance Criteria

- member-shell wrapper failure payloads include a stable `captures` block
- `latest.json` mirrors the same capture metadata for those failures
- focused wrapper tests assert the contract

## Verification

- `pytest tests/test_chromebook_member_shell_wrapper.py -q`
- `bash -n scripts/chromebook_member_shell_smoke.sh`
- `pytest`
