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

- live wipe confirmation on the remote member device
- operator-side closure capture when no local operator session is available
- cleanup of older unresolved wipe follow-up members left by prior runs

Keep those boundaries explicit in review notes, commit messages, and runtime
claims.

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

Stop the hub and local services after the run:

```bash
python -m osk stop --services --timeout 5
```

## Artifacts

Artifacts are written under:

- [`output/chromebook/real-hub-validation`](/var/home/bazzite/osk/output/chromebook/real-hub-validation)

Important files per run:

- `result.json`
  Final contract result for the run.
- `hub-preflight.json`
  Host-side target and local snapshot metadata.
- `cdp-version.json`
  Chrome remote debugging metadata for the Chromebook browser.
- `restart-stop.json`
  The recorded `osk stop --restart` command result.
- `restart-start.stdout.log` and `restart-start.stderr.log`
  Restart boot logs from the workstation hub.
- `restart-resume-probe.json`
  Post-restart member runtime probe.

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

- `wipe_observed` remains `manual_follow_up`.
- `operator_closure_captured` remains `manual_follow_up` when no local operator
  session is present.
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
