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
- Local dashboard URL command (`dashboard`)
- Local operator and observability commands (`operator`, `audit`, `logs`,
  `members`, `findings`, `review`)
- Local finding review commands (`finding show`, `finding acknowledge`,
  `finding resolve`, `finding reopen`, `finding escalate`,
  `finding correlations`, `finding note`)
- A hub-owned Phase 2 intelligence service with config-selectable fake or real
  transcript/vision adapters, live GPS/audio/frame ingest wiring, persisted
  intelligence observations, persisted reviewable findings, `ffmpeg`-backed
  compressed audio decode, durable ingest receipts for restart-safe dedupe, and
  a heuristic synthesis layer with corroboration, sitrep output, and
  coordinator review actions
- A thin local coordinator review shell served from FastAPI with static
  HTML/CSS/JS under `src/osk/templates/` and `src/osk/static/`; the shell uses
  a one-time dashboard code to mint a short-lived local `HttpOnly` cookie
  instead of keeping a steady-state token in the request URL or JS storage, and
  it now consumes a same-origin live dashboard stream plus current member
  health/ingest context, a rolling member-buffer trend view, sustained buffer
  warning signals in the local review feed/current pulse, local
  acknowledge/snooze controls for those transient signals, and a local
  tile-backed map surface with an explicit relative fallback when the tile
  cache is empty
- A first operations-tooling slice for the dashboard map path:
  `osk tiles status` and `osk tiles cache --bbox ... --zoom ...`
- A standalone hotspot-management slice for NetworkManager environments:
  `osk hotspot status|up|down|instructions`
- Hotspot-aware runtime guidance in `osk doctor` and `osk start`, so field
  operators can see `join_host`/hotspot readiness without the hub silently
  mutating host networking
- A standalone preserved-evidence slice:
  `osk evidence unlock|export|destroy`
- A thin member join/runtime shell under `src/osk/templates/join.html`,
  `src/osk/templates/member.html`, and `src/osk/static/member.*`; it now uses
  a clean cookie-backed join flow so the shared operation token is not kept in
  the post-QR URL or browser JavaScript storage, upgrades browser members into
  a short-lived `HttpOnly` runtime cookie after auth, and the current runtime
  shell already includes reconnect-aware WebSocket state, live alerts, opt-in
  GPS sharing, manual report submission, observer-side photo/audio clip
  capture, early sensor-side audio/key-frame capture on the member WebSocket
  path, a browser outbox for reconnect-safe manual report/media retries with
  per-item review controls, bounded sensor-side reconnect buffering for recent
  audio/key-frame capture, and a first manifest/service-worker/installable
  offline PWA layer
- A manual browser/device smoke helper at `scripts/member_shell_smoke.py` for
  testing the member shell against a disposable mocked hub outside CI/sandboxed
  environments
- A Playwright-driven browser smoke helper at
  `scripts/member_shell_playwright_smoke.sh` for environments where localhost
  is reachable from the browser runtime

The repository does **not** yet contain the full production-grade or full
planned versions of the intelligence pipeline, synthesis/review system,
coordinator dashboard, mobile client, or operations tooling described in the
design documents. It does contain early real slices of those phases, so
contributions should extend the current surfaces rather than assuming they do
not exist.

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

Real Whisper mode also expects `ffmpeg` to be available in `PATH` so compressed
browser audio uploads can be decoded locally.

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

The doctor output now includes hotspot readiness and `join_host` guidance in
addition to install-readiness checks. Those hotspot warnings are advisory; they
should not be turned into hard install failures unless the design changes.

Start the disposable member-shell smoke helper on a real machine if you want to
exercise `/join` -> `/member`, offline queueing, replay, and installability in
an actual browser or phone:

```bash
PYTHONPATH=src python scripts/member_shell_smoke.py --host 0.0.0.0 --advertise-host <lan-ip>
```

Run the browser-driven smoke path if you have a local Playwright-capable
environment and want an automated `/join` -> `/member` pass:

```bash
scripts/member_shell_playwright_smoke.sh --headed
```

Inspect the current local tile cache:

```bash
osk tiles status
```

Populate the cache for a local area:

```bash
osk tiles cache --bbox "39.7,-104.9,39.8,-104.8" --zoom 13-15
```

Inspect hotspot availability and the current hotspot IP:

```bash
osk hotspot status
```

The runtime path now surfaces the same hotspot/join-host guidance during
`osk start`, but startup remains conservative: it does not automatically bring
up a hotspot or rewrite `join_host`.

Export the currently visible preserved-evidence mount into a zip:

```bash
osk evidence export --output osk-evidence-export.zip
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
- Extend the owned service boundary rather than making the server responsible
  for persistence, synthesis, or alert heuristics
- Treat mobile/browser media formats as first-class inputs; avoid narrowing the
  runtime back down to raw PCM-only happy paths
- Preserve reconnect-safe ingest semantics: if client code resends media after
  a transport break, reuse the same `chunk_id`, `frame_id`, or `ingest_key`
  instead of generating a fresh key for the retry
- Preserve review-state semantics: do not let new synth output silently erase a
  coordinator’s acknowledged or resolved finding state
- Keep coordinator review surfaces aligned: if you change finding/event/sitrep
  retrieval or review semantics, update both the local CLI flow and the admin
  API/query surfaces used by future dashboard work
- Keep browser auth bootstrap non-secret on the server side: do not put
  operator/coordinator tokens in request query strings, rendered HTML, or
  long-lived browser-managed JS storage when extending the dashboard flow
- Keep the member join bootstrap on the same standard: the shared operation
  token should remain a one-time QR bootstrap input, and member reconnect or
  runtime-session secrets should remain on `HttpOnly` cookie/session-exchange
  paths instead of long-lived browser-managed JS storage
- Keep member-initiated actions on the member auth boundary: if the member
  browser can do something directly, prefer the member cookie/WebSocket flow
  over coordinator-only REST routes unless the auth model is intentionally
  changing
- Keep host-network changes explicit: if you extend hotspot/startup behavior,
  prefer operator-visible guidance and opt-in actions over silent network
  mutation unless the design/spec is explicitly updated to make that automatic
- Keep browser media capture modular: add mic/camera/client-side analysis work
  behind dedicated static modules instead of folding codec/capture logic
  directly into the main member runtime script
- Keep PWA/offline behavior honest: cache only what the current member flow can
  really resume, and make sure wipe/logout flows clear service-worker caches
  and other browser-managed offline state when the docs say they do
- Keep queued member actions durable and replay-safe: if notes or manual media
  are stored locally for reconnect, scope them to the current operation/member,
  keep their stable IDs across replay, and clear them on logout/wipe when the
  docs say local state is cleared
- Keep dashboard map/status surfaces truthful: the current field map is a
  local cached-tile surface driven by member GPS, with an explicit
  relative-position fallback when no cached tiles cover the current area; docs
  and UI copy should not imply broader map capabilities than that
- Keep transient coordinator telemetry in the right place: member-side browser
  buffer pressure and similar fast-changing dashboard context should come from
  live in-memory operation state, not only the persisted database snapshot
- Keep transient dashboard signals configurable and ephemeral: threshold/snooze
  tuning belongs in config, while acknowledge/snooze state should stay local to
  the coordinator runtime unless there is a deliberate design change to persist
  it

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
