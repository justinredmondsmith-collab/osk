# Plan 25: Artifact Index Handoff Summary

## Goal

Teach shared Chromebook artifact indexes to include a compact operator handoff
summary so `latest.json` and `runs.jsonl` can expose real-hub closure state
without reopening per-run JSON artifacts.

## Why

Phase 23 added `operator-handoff.json`, and Phase 24 surfaced it in the
wrapper, but the shared artifact index still only mirrors top-level result
fields and capture paths. Any consumer that wants the closure state still has
to follow the handoff path and parse another file manually.

## Scope

- extend `build_run_index_entry()` to load `captures.operator_handoff_path`
  when present
- store a compact `operator_handoff` section in `latest.json` and `runs.jsonl`
- keep non-real-hub flows unchanged when no handoff artifact exists
- update wrapper tests to verify indexed handoff fields are preserved

## Out of Scope

- changing the structure of `operator-handoff.json`
- adding a new gate wrapper for real-hub validation
- expanding the index with every nested artifact field

## Acceptance Criteria

- indexed run entries include `operator_handoff.path` and compact closure/status
  fields when `operator-handoff.json` exists
- indexed run entries keep `operator_handoff: null` when the handoff artifact is
  absent
- wrapper tests cover both indexed-presence and indexed-absence paths

## Verification

- `pytest tests/test_chromebook_real_hub_wrapper.py -q`
- `ruff check src/osk/chromebook_smoke_artifacts.py tests/test_chromebook_real_hub_wrapper.py`
- `pytest`
