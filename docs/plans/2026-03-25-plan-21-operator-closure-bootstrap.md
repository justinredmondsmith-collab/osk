# Plan 21: Operator Closure Bootstrap Automation

## Goal

Reduce the remaining manual gap in real-hub validation by automatically
bootstrapping a local operator session when closure capture needs one and the
current hub still exposes a valid one-time bootstrap.

## Why

Real-hub validation already knows how to capture operator-side wipe readiness
and audit closure once local credentials exist, but it still falls back to
`manual_follow_up` when the workstation has not run `osk operator login`
ahead of time. That keeps the validation result dependent on a prep step that
the repo itself can perform.

## Scope

- attempt `osk operator login --json` from the validation runner when local
  operator credentials are missing
- record that bootstrap attempt as a dedicated artifact
- reuse the newly created operator session for closure capture when bootstrap
  succeeds
- preserve stable capture-key parity for wrapper-generated failure payloads
- document the new bootstrap-backed closure behavior and remaining limits

## Out of Scope

- changing hub bootstrap semantics or TTL policy
- adding dashboard-session bootstrap flows to the validation runner
- claiming closure capture can succeed after bootstrap expiry or wrong-operation
  state

## Acceptance Criteria

- closure capture succeeds without a pre-existing local operator session when a
  valid local operator bootstrap is available
- the real-hub result payload exposes the bootstrap attempt artifact path
- wrapper failure payloads include the same capture key with `null` when absent
- tests cover both bootstrap-success and bootstrap-unavailable paths

## Verification

- `pytest tests/test_real_hub_validation_contract.py tests/test_chromebook_real_hub_wrapper.py -q`
- `bash -n scripts/chromebook_real_hub_validation.sh`
- `pytest`



> Roadmap note: This file is a scoped implementation or historical planning document. Read it through [`2026-03-28-end-state-product-roadmap.md`](./2026-03-28-end-state-product-roadmap.md). If sequencing, priority, or scope conflict with the roadmap, follow the roadmap.
