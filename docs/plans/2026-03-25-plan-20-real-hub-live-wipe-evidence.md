# Plan 20: Real-Hub Live-Wipe Evidence Reuse

## Goal

Reduce the remaining manual gap in real-hub validation by reusing the latest
passing Chromebook member-shell smoke evidence for the same device when it
already proves the connected-browser live wipe path.

## Why

The repo now has a dedicated real-browser smoke flow that exercises join,
offline replay, reload resume, and live wipe clearing on the Chromebook lab
device. Real-hub validation still reports `wipe_observed` as
`manual_follow_up`, which leaves that proven hardware signal disconnected from
the main validation contract and forces operators to reconcile two artifact
trees by hand.

## Scope

- load the latest member-shell smoke artifact for the same Chromebook
- upgrade `wipe_observed` when that artifact shows a passing `wipe-clear` step
- preserve stable capture pointers to the reused smoke artifacts in the
  real-hub result contract
- keep wrapper-generated failure payloads on the same expanded capture key set
- document the exact claim boundary in the runbook

## Out of Scope

- adding a new wipe probe inside the real-hub browser-driving flow
- claiming full disconnected-device or evidence-destruction wipe automation
- redesigning the member-shell smoke result schema

## Acceptance Criteria

- real-hub validation marks `wipe_observed` as passed when qualifying
  member-shell smoke evidence exists for the same Chromebook
- the result payload exposes capture paths for the reused smoke artifacts
- wrapper failure payloads retain the same capture keys with `null` values when
  unavailable
- tests cover both qualifying and non-qualifying smoke evidence cases

## Verification

- `pytest tests/test_real_hub_validation_contract.py tests/test_chromebook_real_hub_wrapper.py -q`
- `bash -n scripts/chromebook_real_hub_validation.sh`
- `pytest`
