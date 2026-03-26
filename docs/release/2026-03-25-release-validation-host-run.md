# Release Validation Host Run: 2026-03-25

This document records the first coordinator-host release-validation run for the
bounded `1.0.0` scope on March 25, 2026.

It is evidence for the coordinator-side path only. It does **not** close the
live Chromium member-flow or connected-browser wipe blockers.

## Environment

- host: Linux coordinator
- repo: `main`
- Python: `3.14.3`
- service mode: `compose-managed local services`
- CLI: `/home/bazzite/.local/bin/osk`

## Commands Run

### Coordinator preflight

- `osk doctor --json`
- `osk drill install`

Observed result:

- install readiness reported `true`
- hotspot surfaced as `available_inactive`
- join host surfaced as `10.0.0.60`

### Runtime bring-up

- `osk start "Osk 1.0.0 Release Validation"`
- `osk status --json`

Observed result:

- runtime started successfully on the host
- local database service started through Compose
- hub served on `https://127.0.0.1:8444`

Important note:

- the requested operation name was **not** used for a clean run
- the hub resumed the existing operation `Graceful Smoke`
- operation id: `9bf06f42-cb32-4741-a125-3b60091da68a`

This means the host-run evidence is valid for coordinator startup and dashboard
reachability, but it is **not** a clean-room release run.

### Operator and dashboard session flow

- `osk operator login --json`
- `osk dashboard --json`
- host-side `curl` exchange against `/api/operator/dashboard-session`
- host-side `curl` request against `/api/coordinator/dashboard-state`

Observed result:

- local operator session creation succeeded
- dashboard bootstrap code exchange succeeded
- dashboard URL resolved to `https://127.0.0.1:8444/coordinator`
- coordinator dashboard-state API returned live runtime state

### Wipe readiness and follow-up visibility

- `osk status --json`
- dashboard-state `wipe_readiness`
- `osk audit --wipe-follow-up-only --json`

Observed result:

- wipe readiness was `blocked`
- unresolved disconnected-member follow-up count was `3`
- all three unresolved members were historical `Chromebook Validation ...`
  observers last seen on March 23-24, 2026
- wipe follow-up audit history was empty (`[]`)

This confirms that the current runtime surfaces unresolved disconnected-browser
cleanup risk correctly, but it also means the release run is carrying prior
state that still blocks cleanup closure.

### Evidence export

- `osk evidence export --output /var/home/bazzite/osk/output/release-validation-evidence.zip --json`

Observed result:

- export failed with:
  `No visible preserved evidence found under /home/bazzite/.local/state/osk/evidence. Unlock evidence first if needed.`

This host run does **not** validate the export/verify path. It only shows the
current runtime had no visible preserved evidence to export.

## What This Run Proved

- Linux coordinator preflight is truthful enough to report install readiness on
  this host
- host-side runtime startup works on the bounded local-service path
- local operator login works
- dashboard bootstrap and dashboard session exchange work
- coordinator dashboard state exposes wipe-readiness and disconnected-member
  follow-up status

## What This Run Did Not Prove

- clean release validation on a fresh operation
- live Chromium member join, reconnect, offline replay, reload, and wipe flow
- connected-browser wipe validation on the minimum supported browser path
- evidence export and verify on a real preserved bundle
- closure of unresolved wipe follow-up items

## Release Impact

As of March 25, 2026:

- the coordinator-side launch path is materially stronger than it was before
  this run
- Gate 3 is still open because the required Chromium member path has not yet
  been exercised and retained
- Gate 2 wipe confidence is still open because connected-browser wipe on the
  supported browser path is not yet retained as evidence
- evidence export/verify is still open because no exportable preserved bundle
  was available during this run
- release validation should prefer a clean operation state, or explicitly
  record when inherited state contaminates the run
