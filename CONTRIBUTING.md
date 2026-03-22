# Contributing to Osk

Thank you for your interest in contributing.

## Current Project State

Osk is currently a public design-plus-foundation repository. At this stage, the
repo contains architecture, governance, and planning documentation, plus an
early but real Phase 1 host/runtime implementation.

The repository now includes:

- A minimal Python package layout under `src/osk/`
- A working host/operator CLI (`python -m osk` / `osk`)
- Basic tests under `tests/`
- A lightweight GitHub Actions CI workflow
- Local hub runtime commands (`install`, `start`, `status`, `stop`)
- Local operator and observability commands (`operator`, `audit`, `logs`,
  `members`)
- A hub-owned Phase 2 intelligence service with config-selectable fake or real
  transcript/vision adapters

The repository does **not** yet contain the full intelligence pipeline,
synthesis layer, coordinator dashboard, or mobile client described in the
design documents.

That means the most useful contributions right now are:

- Documentation clarity and consistency
- Threat-model and privacy-model review
- Licensing, provenance, and repo-governance cleanup
- Design review grounded in the existing specs and plans
- Small, verified implementation steps that follow the phase plans

## Before You Start

- Read the [design specification](docs/specs/2026-03-21-osk-design.md)
- Review the [implementation plans](docs/plans/)
- Read [AGENTS.md](AGENTS.md) and [docs/WORKFLOW.md](docs/WORKFLOW.md)
- Check whether the topic is already covered by an issue, discussion, or plan
- Keep changes scoped to one concern per pull request

## Development Baseline

Install the package and test dependencies:

```bash
pip install -e ".[dev]"
```

If you are working on real Phase 2 runtime adapters instead of the default fake
backends, install the intelligence extras too:

```bash
pip install -e ".[dev,intelligence]"
```

Run tests:

```bash
pytest -q
```

Run lint and formatting checks:

```bash
ruff check src tests
ruff format --check src tests
```

Check the local scaffold:

```bash
python -m osk doctor --json
```

## Contribution Rules

### Documentation and Design Changes

- Keep the current repository state truthful. Do not document commands,
  behaviors, benchmarks, or guarantees as implemented if they are still
  planned.
- If you change architecture or behavior in a meaningful way, update the
  relevant spec or plan in the same pull request.
- If you change operator/runtime behavior, update the README and workflow docs
  in the same pull request.
- Prefer precise language over marketing language, especially for privacy,
  security, and safety claims.

### Provenance and Reuse

- Do not copy code, prompts, templates, or substantial text from another
  repository into Osk without recording it in [docs/PROVENANCE.md](docs/PROVENANCE.md).
- Preserve required copyright and license notices when adapting material from
  predecessor or third-party sources.
- Osk is intended to use `AGPL-3.0-only` for code unless a file says otherwise.

### Code Contributions

Code contributions should:

- Be discussed first if they are large or architectural
- Include tests for new behavior
- Update user-facing docs when behavior changes
- Avoid weakening the stated privacy and local-only design goals without an
  explicit design update
- For Phase 2 work, keep fake and real adapters behind the same
  service-owned interfaces, and do not wire model-specific behavior directly
  into routes or WebSocket handlers

## How to Contribute

### Reporting Bugs or Doc Problems

Open an [issue](https://github.com/justinredmondsmith-collab/osk/issues) for
non-sensitive bugs, contradictions, broken links, unclear docs, and design
feedback.

For sensitive security or privacy issues, follow [SECURITY.md](SECURITY.md)
instead of opening a public issue.

### Suggesting Features

Open an issue or discussion that explains:

- The problem you want to solve
- Why it fits Osk's goals
- Whether it changes the threat model, privacy model, or operational model

### Submitting a Pull Request

1. Fork the repository.
2. Create a branch from `main`.
3. Make one focused change.
4. Update related docs in the same branch when needed.
5. Open a pull request against `main` with a clear summary of what changed and why.

### Pull Request Guidelines

- One feature, fix, or document cleanup per PR
- Keep design changes internally consistent across README, specs, and plans
- Flag assumptions clearly when the repo does not yet have code to verify them
- Do not include unrelated formatting churn
- If you introduce copied/adapted material, update `docs/PROVENANCE.md`

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md).

## Questions?

Open a [discussion](https://github.com/justinredmondsmith-collab/osk/discussions) or an issue.
