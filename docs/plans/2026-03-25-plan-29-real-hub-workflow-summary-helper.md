# Plan 29: Real-Hub Workflow Summary Helper

## Goal

Extract the real-hub GitHub Actions summary logic into a repo-owned helper that
can write safe workflow outputs, append a job summary, and emit a concise
annotation about closure state.

## Why

The new real-hub gate workflow works, but its summary logic still lives as an
embedded Python block inside YAML. That makes the behavior harder to test,
review, and reuse. The workflow also needs a stable, repo-owned place to decide
when a run should show a notice, warning, or error annotation for operators.

## Scope

- add a Python helper for reading indexed `latest.json`
- make the helper write structured GitHub outputs only for safe machine fields
- make the helper write the markdown workflow summary
- make the helper emit a GitHub annotation based on gate status and closure state
- switch `chromebook-real-hub-gate.yml` to call the helper
- add tests for warning, notice, and failure annotation behavior
- document that the workflow now surfaces closure state in annotations as well as
  the job summary

## Out of Scope

- changing indexed artifact schema
- changing the real-hub gate wrapper output format
- adding pull-request comments or external notifications

## Acceptance Criteria

- the workflow no longer embeds the real-hub summary Python block inline
- a repo-owned helper writes the workflow summary and safe outputs
- open follow-up runs emit a warning annotation
- clear passing runs emit a notice annotation
- failed runs emit an error annotation
- tests cover the helper’s annotation and output behavior

## Verification

- `pytest tests/test_chromebook_real_hub_workflow_summary.py -q`
- `python - <<'PY'` YAML-parse `.github/workflows/chromebook-real-hub-gate.yml`
- `pytest`



> Roadmap note: This file is a scoped implementation or historical planning document. Read it through [`2026-03-28-end-state-product-roadmap.md`](./2026-03-28-end-state-product-roadmap.md). If sequencing, priority, or scope conflict with the roadmap, follow the roadmap.
