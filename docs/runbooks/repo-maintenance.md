# Repository Maintenance

This runbook captures the local and GitHub-side settings that keep the Osk
repository healthy.

## Local Baseline

The current supported CI-tested Python matrix is 3.11 through 3.13.
Python 3.14 may be useful for forward-compatibility checking, but it is not yet
part of the supported CI baseline.

Install the development baseline:

```bash
make install-dev
pre-commit install
```

If you are working on the real intelligence adapters too:

```bash
make install-all
pre-commit install
```

The `dev` extra now includes the repo-maintenance tools used by this runbook:
`pre-commit` and `build`.

Run the standard repo checks before pushing:

```bash
make check
```

If you want the same checks separately:

```bash
make lint
make test
make build
```

## Required GitHub Settings

The following settings should be enforced on the GitHub repository, not just
documented in local convention.

### Branch Protection / Ruleset

Protect `main` with a ruleset or classic branch protection that requires:

- Pull requests for all code changes
- Required status checks:
  - `CI / lint-test-build (3.11)`
  - `CI / lint-test-build (3.12)`
  - `CI / lint-test-build (3.13)`
- Up-to-date branch before merge
- Required review from code owners
- Dismiss stale approvals on new commits
- Block force pushes
- Block branch deletion

### Merge Strategy

Recommended repository settings:

- Allow squash merge
- Disable merge commits
- Disable rebase merge unless there is a specific need for it
- Auto-delete head branches after merge

### Security / Automation

Enable:

- Dependabot version updates
- Dependabot security updates
- Secret scanning
- Push protection for secrets
- Private vulnerability reporting

### Review Discipline

Keep `CODEOWNERS` current and require CODEOWNERS review for:

- `src/osk/**`
- `.github/workflows/**`
- `docs/release/**`
- `docs/runbooks/**`

## Release Hygiene

Before cutting a release:

1. Confirm package version and docs agree.
2. Move the relevant `CHANGELOG.md` entries out of `Unreleased`.
3. Create and push an annotated git tag.
4. Verify CI is green on `main`.
5. Confirm release docs and blockers reflect current evidence.

## Warning Debt

The current local test suite passes, but Python 3.14 surfaces a large
deprecation-warning set from transitive dependencies such as `pytest-asyncio`,
`starlette`, and `fastapi`. Track that as maintenance debt and re-evaluate when
upgrading dependencies or widening the supported Python matrix.
