# Plan 27: Real-Hub Gate Wrapper

## Goal

Add a real-hub gate wrapper that runs the existing real-hub validation flow
with stamped provenance, clean-worktree enforcement, and indexed closure
reporting after each run.

## Why

The repo now has the real-hub validation wrapper, an indexed handoff summary,
and a latest-run report helper, but operators still need to glue them together
manually. The Chromebook member-shell path already has a gate wrapper for this
role; the real-hub path needs the same operational entrypoint.

## Scope

- add `chromebook_real_hub_gate.sh`
- mirror the clean-worktree and provenance behavior of
  `chromebook_lab_gate.sh`
- forward all non-gate arguments to `chromebook_real_hub_validation.sh`
- print indexed real-hub closure status after the run completes
- add gate tests for dirty-worktree rejection and successful provenance/report
  output
- document the new gate entrypoint in the real-hub runbook

## Out of Scope

- changing the real-hub validation runner contract
- adding new artifact formats beyond the existing wrapper and index outputs
- replacing the standalone real-hub report helper

## Acceptance Criteria

- the real-hub gate refuses a dirty worktree unless `--allow-dirty` is used
- gate runs stamp the same provenance environment fields as the member-shell
  gate path
- successful gate runs print indexed operator closure status from `latest.json`
- tests cover dirty-worktree rejection and successful summary output

## Verification

- `pytest tests/test_chromebook_real_hub_gate.py -q`
- `bash -n scripts/chromebook_real_hub_gate.sh`
- `pytest`
