# Plan 28: Real-Hub Gate Workflow

## Goal

Add a repo-owned `workflow_dispatch` GitHub Actions workflow that runs the
real-hub gate wrapper on a self-hosted runner and publishes the indexed
operator-handoff closure summary in the workflow run itself.

## Why

The repo now has:

- a real-hub validation wrapper
- a real-hub gate wrapper
- indexed `latest.json` and `operator_handoff` summary fields

Operators can run the gate locally, but there is still no repeatable GitHub-side
entrypoint that captures those indexed closure fields as the visible workflow
result. The member-shell smoke path already has a manual gate workflow; the
real-hub path needs the same automation surface.

## Scope

- add `.github/workflows/chromebook-real-hub-gate.yml`
- follow the existing `chromebook-lab-gate.yml` structure
- resolve workflow inputs and repo variables into gate-wrapper arguments
- run `scripts/chromebook_real_hub_gate.sh` on a self-hosted runner
- read `output/chromebook/real-hub-validation/latest.json`
- publish the indexed closure summary to `GITHUB_STEP_SUMMARY`
- upload the resolved run directory and `latest.json` as workflow artifacts
- document the workflow entrypoint in the real-hub runbook

## Out of Scope

- changing the real-hub gate wrapper contract
- adding hosted-runner compatibility
- changing indexed artifact schema beyond consuming existing fields

## Acceptance Criteria

- operators can manually launch the real-hub gate from GitHub Actions
- the workflow resolves a real hub URL, join URL, Chromebook host, and optional
  SSH/artifact overrides
- successful runs publish indexed `operator_handoff` closure, wipe, and
  follow-up fields to the job summary
- the workflow uploads the run directory and `latest.json`
- the runbook documents the new workflow and its self-hosted-runner constraint

## Verification

- `python - <<'PY'` YAML-parse `.github/workflows/chromebook-real-hub-gate.yml`
- `pytest tests/test_chromebook_real_hub_gate.py -q`
- `pytest`



> Roadmap note: This file is a scoped implementation or historical planning document. Read it through [`2026-03-28-end-state-product-roadmap.md`](./2026-03-28-end-state-product-roadmap.md). If sequencing, priority, or scope conflict with the roadmap, follow the roadmap.
