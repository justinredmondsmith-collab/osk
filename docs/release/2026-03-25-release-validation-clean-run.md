# Release Validation Clean Run: 2026-03-25

This document records the clean release-validation run attempted on March 25,
2026 against a fresh `1.0.0`-scoped operation.

Artifacts retained from this run live under:

- `/var/home/bazzite/osk/output/release-validation/2026-03-25-clean-run`

Key browser artifacts:

- `screenshots/coordinator-auth-gate.png`
- `screenshots/coordinator-unlocked.png`
- `screenshots/member-join.png`
- `screenshots/member-joined.png`
- `screenshots/member-online-report.png`
- `screenshots/member-offline-queued.png`
- `screenshots/member-reconnected.png`
- `screenshots/member-reloaded.png`
- `screenshots/member-wiped.png`
- `browser-flow.json`

## Pre-Run Lifecycle Finding

Before this clean run could start, `osk start` resumed older operations twice:

1. `Graceful Smoke`
2. `Smoke Test`

The reason was not a broken resume decision. The database still contained older
rows with `stopped_at IS NULL`, so `get_active_operation()` correctly resumed
them in started-at order.

Operational effect:

- a supposedly fresh release-validation start required two stop cycles before
  the intended operation could be created

Release implication:

- clean release validation is currently vulnerable to stale active-operation
  state in the local database

## Clean Operation

After clearing the older active rows, Osk created a fresh operation:

- operation name: `Osk 1.0.0 Clean Validation 2026-03-25`
- operation id: `2b21047e-ad59-434c-9d08-ee1bfe8d6fb5`

Initial coordinator status on the clean run showed:

- hub running
- operator bootstrap active
- zero joined members
- wipe readiness `idle`
- no unresolved wipe follow-up

## Validated Coordinator and Browser Flow

The clean run successfully validated all of the following on a Chromium-class
browser path driven through Playwright against the live hub:

- local coordinator dashboard unlock
- member join from `/join`
- shared join token removed from the visible URL after join
- transition into `/member`
- online manual report delivery
- offline manual report queueing
- reconnect drain back to an empty outbox
- reload-based member session resume

Recorded browser checkpoint results from `browser-flow.json`:

- `coordinator_dashboard_unlock`: pass
- `member_join`: pass
- `online_report`: pass
- `offline_queue`: pass
- `reconnect_drain`: pass
- `reload_resume`: pass

## Live Wipe Result

The live wipe result was mixed:

- the connected member browser **did** receive the wipe and clear local state
- the coordinator `osk wipe --yes --json --services` command returned exit code
  `1`
- the returned payload reported `"hub_stopped": false`
- immediately after the wipe, `osk status --json` showed `status = state_only`
  and noted that the recorded PID was no longer visible while the state file
  remained in place
- a follow-up `osk stop --services` cleared the stale state and returned the
  host to `status = stopped`

This means the connected-browser wipe path is now validated at the browser UX
level, but not yet at the coordinator command/shutdown level.

## Likely Shutdown Defect

The current `stop_hub()` implementation in [`src/osk/hub.py`](../../src/osk/hub.py)
reuses the original shutdown deadline after sending `SIGTERM`
([`src/osk/hub.py:919`](../../src/osk/hub.py#L919), [`src/osk/hub.py:925`](../../src/osk/hub.py#L925), [`src/osk/hub.py:933`](../../src/osk/hub.py#L933)).

Inference from code plus observed behavior:

- once the graceful wait window is exhausted, the fallback `SIGTERM` path gets
  little or no additional time before the command returns failure
- that can produce a false-negative stop result where the process exits shortly
  after the CLI has already returned `1`
- when that happens, the local state file can remain behind until a later
  cleanup command removes it

This is an inference from the source and the observed run, not yet a unit test.

## Post-Wipe Follow-Up State

After the wipe timeout path, `osk status --json` reported:

- `status = state_only`
- one disconnected member follow-up item for `Release Chromium Member`

The browser had already shown `Local session cleared`, so this follow-up item
reflects command-level shutdown ambiguity rather than a browser that visibly
failed to wipe during the run.

## What This Run Proved

- the clean coordinator dashboard auth path works
- the clean Chromium member path works for join, online reporting, offline
  queueing, reconnect drain, and reload-based resume
- the visible URL can stay free of the shared join token after member join
- the connected member browser can receive a live wipe and clear local state

## What This Run Did Not Prove

- that `osk wipe --yes` completes as a clean command-level success on the same
  validated path
- that fresh release validation is protected from stale active-operation rows
- evidence export/verify on a real preserved bundle
- closure of the post-wipe follow-up item without manual/operator verification

## Release Impact

As of March 25, 2026:

- the bounded Chromium member flow is materially validated now
- Gate 2 remains open because the live wipe command/shutdown path is still not
  cleanly passing
- Gate 3 remains open because the matrix still contains a command-level wipe
  failure and evidence export/verify is still unvalidated
- Osk now has concrete retained artifacts showing that the remaining risk is
  not “member flow is unbuilt,” but “shutdown/lifecycle correctness is not yet
  release-grade”
