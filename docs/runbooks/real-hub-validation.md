# Real-Hub Validation Runbook

This runbook covers the repo-owned real-hub validation flow that uses this
workstation as the hub host and a real Chromebook as the remote member device.
It is the source of truth for running, interpreting, and following up on the
current Plan 8 validation path.

## Scope

This workflow validates the real Osk runtime path:

- real `/join` to `/member` flow
- live member session establishment on hardware
- reconnect and queued replay behavior
- coordinator restart with member session resume

This workflow does not yet automate:

- live wipe confirmation inside the same real-hub browser-driving slice
- operator-side closure capture after local bootstrap expiry or wrong-operation
  state
- cleanup of older unresolved wipe follow-up members left by prior runs

Keep those boundaries explicit in review notes, commit messages, and runtime
claims.

The current contract can now reuse the latest passing
[`output/chromebook/member-shell-smoke/latest.json`](/var/home/bazzite/osk/output/chromebook/member-shell-smoke/latest.json)
artifact for the same Chromebook when that companion flow already proved the
connected-browser `wipe-clear` step on hardware. Treat that as evidence reuse,
not as a same-run wipe probe.

The current contract can also attempt a repo-owned local operator bootstrap by
running `osk operator login --json` when closure capture needs workstation
credentials and the active hub still exposes a valid one-time bootstrap. Treat
that as automation of the existing local operator flow, not as a bypass around
expired or missing bootstrap state.

## Prerequisites

- Run from the repo root on the workstation host.
- Ensure `/var/home/bazzite/.config/osk/config.toml` points at the workstation
  hub settings used for real validation.
- The Chromebook control path must already work over SSH.
- The Chromebook browser must allow the self-signed workstation certificate.
- Local Compose-managed services must be available if the config uses local
  Postgres.

Current validated lab topology:

- Workstation hub host: `10.0.0.60:8444`
- Chromebook SSH target: `jrsmith@localhost`
- Chromebook SSH port: `22022`
- Chromebook SSH identity: `/var/home/bazzite/.ssh/osk_chromebook_lab`

## Commands

Start the workstation-hosted hub:

```bash
python -m osk start "Real Hub Restart Validation"
```

Run the real Chromebook validation wrapper:

```bash
bash scripts/chromebook_real_hub_validation.sh \
  --chromebook-host chromebook-lab \
  --hub-url https://10.0.0.60:8444 \
  --join-url 'https://10.0.0.60:8444/join?token=<token>' \
  --ssh-target jrsmith@localhost \
  --ssh-port 22022 \
  --ssh-identity /var/home/bazzite/.ssh/osk_chromebook_lab \
  --scenario restart
```

On successful runs the wrapper now prints the `operator-handoff.json` path
first. Use that as the first artifact to inspect from the shell before opening
`result.json` or the underlying closure and audit artifacts.

Run the repo-owned gate wrapper when you want the validation flow to stamp git
provenance and print the indexed closure summary immediately after the run:

```bash
bash scripts/chromebook_real_hub_gate.sh \
  --trigger workflow_dispatch \
  --chromebook-host chromebook-lab \
  --hub-url https://10.0.0.60:8444 \
  --join-url 'https://10.0.0.60:8444/join?token=<token>' \
  --ssh-target jrsmith@localhost \
  --ssh-port 22022 \
  --ssh-identity /var/home/bazzite/.ssh/osk_chromebook_lab \
  --scenario restart
```

The gate wrapper requires a clean git worktree unless you pass `--allow-dirty`.
After the wrapper finishes, it prints the indexed `latest.json` summary,
including `operator_handoff` closure and wipe status, so operators can see the
current boundary without manually opening run-local JSON files first.

For repeatable GitHub-side operation, the repo now includes a manual
`workflow_dispatch` workflow at
[`chromebook-real-hub-gate.yml`](../../.github/workflows/chromebook-real-hub-gate.yml).
That workflow is intended for a self-hosted runner with network reachability to
both the real hub target and the dedicated Chromebook. Operators should provide
the current real `join_url` as a workflow input for each run; the indexed
closure summary is then published back into the workflow job summary, surfaced
as a workflow annotation for clear/open/failed closure state, and the resolved
run artifacts are uploaded from the runner.

To inspect the latest indexed real-hub result without opening run-local JSON
files directly:

```bash
bash scripts/chromebook_real_hub_report.sh
```

Use `--json` when you want the same indexed summary in machine-readable form.

Stop the hub and local services after the run:

```bash
python -m osk stop --services --timeout 5
```

## Artifacts

Artifacts are written under:

- [`output/chromebook/real-hub-validation`](/var/home/bazzite/osk/output/chromebook/real-hub-validation)

Important files per run:

- `operator-handoff.json`
  Primary operator-facing handoff artifact. This consolidates the run status,
  wipe evidence status, closure state, step outcomes, and the capture paths
  operators should inspect next.
- `result.json`
  Final contract result for the run.
- `closure-summary.json`
  Operator-closure artifact summarizing whether closure capture was unavailable,
  captured with open follow-up, or captured with a clear current boundary.
  It now also carries review-aware follow-up counts so reviewed historical
  drift is visible separately from active unresolved follow-up, plus
  follow-up-trail count and summary fields so recent member-scoped history is
  preserved in the handoff artifact.
- `hub-preflight.json`
  Host-side target and local snapshot metadata. Local snapshots now include
  `doctor --json`, `status --json`, and `members --json`.
- `captures.member_shell_smoke_latest_path` and
  `captures.member_shell_smoke_result_path`
  Optional pointers to the latest passing companion member-shell smoke artifact
  reused to satisfy `wipe_observed` for the same Chromebook.
- `operator-session-bootstrap.json`
  Captured result of any runner-owned `osk operator login --json` attempt used
  to bootstrap local closure capture when no operator session was already
  present.
- `cdp-version.json`
  Chrome remote debugging metadata for the Chromebook browser.
- `restart-stop.json`
  The recorded `osk stop --restart` command result.
- `restart-start.stdout.log` and `restart-start.stderr.log`
  Restart boot logs from the workstation hub.
- `restart-resume-probe.json`
  Post-restart member runtime probe.
- `wipe-follow-up-<member-id>.json`
  Member-scoped follow-up detail captured for unresolved items and recent
  follow-up-trail members when local operator credentials are available.
  A captured file may therefore show `follow_up: null` with retained history
  when the current boundary has already cleared.

The `members.json` local snapshot now mirrors the live shell parity work by
capturing both the member list and the decorated `wipe_readiness` payload, so
artifact-only review can see recent follow-up trail context without separately
recomputing it from status output.

Start artifact-only review from `operator-handoff.json`, then follow its
`recommended_artifacts` and `closure.follow_up_detail_paths` pointers for the
underlying detail files.

Latest successful restart-validation run:

- [`result.json`](/var/home/bazzite/osk/output/chromebook/real-hub-validation/20260324T003546Z/result.json)
- [`restart-resume-probe.json`](/var/home/bazzite/osk/output/chromebook/real-hub-validation/20260324T003546Z/restart-resume-probe.json)

## Pass Criteria

For `--scenario restart`, the current real pass means all of the following are
true:

- `hub_reachable` is `passed`
- `join_loads` is `passed`
- `member_session_establishes` is `passed`
- `disconnect_reconnect_observed` is `passed`
- `hub_restart_resume_observed` is `passed`

The restart step is specifically considered verified when:

- `restart-stop.json` has `returncode: 0`
- the restarted hub reports `status: "running"`
- `restart-resume-probe.json` shows:
  `resume_detected: true`
- the resumed browser keeps the same `member_id`
- `outbox_count` returns to `"0"`

## Known Limits

- `wipe_observed` remains `manual_follow_up` when no qualifying companion
  member-shell smoke artifact exists for the same Chromebook.
- When `wipe_observed` is satisfied from companion smoke evidence, the claim is
  still scoped to the connected-browser live wipe path previously exercised on
  that hardware. It is not a same-run wipe probe and it does not prove cleanup
  for disconnected browsers, OS-level browser data, or preserved evidence
  destruction.
- `operator_closure_captured` remains `manual_follow_up` when no local operator
  session is present and the runner cannot bootstrap one from the active local
  operator bootstrap.
- Automatic closure bootstrap only covers the existing local operator session
  path. If the bootstrap file is expired, belongs to a different operation, or
  has already been consumed without a replacement, closure capture still falls
  back to `manual_follow_up`.
- `closure-summary.json` now distinguishes capture success from closure state.
  `captured_open_follow_up` means the runner reached the operator surfaces but
  the cleanup boundary is still open. Treat that as incomplete closure, not as
  a pass on member cleanup.
- Historical-drift review markers can now be recorded on old unresolved
  follow-up items, but those markers do not close the boundary by themselves.
  Treat them as operator handoff evidence, not as wipe verification.
- Member-scoped wipe follow-up detail now retains those review events in the
  same follow-up trail used for verification and reopen entries, so handoff
  artifacts can reconstruct why an old unresolved item was inspected without
  overstating closure.
- `closure-summary.json` now mirrors that distinction explicitly with separate
  active-unresolved, historical-drift, reviewed-historical-drift, and
  verified-current follow-up counts so terminal and artifact handoff stay in
  sync with the dashboard view.
- `python -m osk status --json` may show `state_only` from this sandboxed host
  context after a live host-launched restart. Treat the run artifact and
  restart logs as the source of truth for the live pass.
- Older disconnected members remain in wipe-readiness follow-up until they are
  manually resolved or explicitly cleaned up.

## Review Notes

When reviewing future changes in this area, check these two failure classes
separately:

- Host-side restart control
  This includes `osk stop --restart`, uvicorn shutdown timing, and hub process
  restart behavior.
- Member-session resume
  This includes the Chromebook browser session, reconnect cookies, outbox
  replay, and the post-restart CDP probe.

Do not collapse them into one generic "restart failed" finding unless the
artifacts really do not distinguish them.
