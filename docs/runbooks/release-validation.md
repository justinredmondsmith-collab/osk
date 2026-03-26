# Release Validation

This runbook documents the minimum manual validation flow for the bounded
`1.0.0` release target.

Use it together with:

- [`docs/release/1.0.0-definition.md`](../release/1.0.0-definition.md)
- [`docs/release/1.0.0-validation-matrix.md`](../release/1.0.0-validation-matrix.md)
- [`docs/runbooks/chromebook-lab-smoke.md`](./chromebook-lab-smoke.md)
- [`docs/runbooks/operations-drills.md`](./operations-drills.md)

The purpose of this runbook is not to prove broad compatibility. The purpose is
to gather retained evidence for the narrow Linux + Chromium release boundary.

## Release Boundary Reminder

For the first release:

- coordinator host: Linux only
- member browsers: Chromium-class only
- disconnected-device wipe cleanup is still outside any live-wipe guarantee

Do not use this runbook to imply support for Firefox, Safari, or iOS.

## Required Evidence Set

For each run, retain at least:

- `osk doctor --json` output
- `osk drill install` output
- `osk status --json` output before and after the member validation flow
- relevant `osk audit --json` output after wipe/follow-up
- screenshots or photos of the supported Chromium member/browser flow
- if using the dedicated Chromebook lab, the artifact directory produced by the
  lab smoke workflow

Store those artifacts under a stable release-evidence directory outside the
temporary browser session.

## Part 1: Coordinator Preflight

On the Linux coordinator host:

```bash
osk doctor --json
osk drill install
osk operator login
```

Confirm:

- install prerequisites are visible and truthful
- hotspot/join-host guidance is legible
- the coordinator session is active before runtime validation begins

## Part 2: Runtime Bring-Up

Start the local runtime:

```bash
osk start "Osk 1.0.0 Release Validation"
osk status --json
```

Retain:

- the `osk status --json` output
- the printed join URL / QR target

Also confirm:

- the active operation id and name in `osk status --json` match the intended
  release-validation run

If `osk start` resumes an older operation instead of creating the intended
release-validation run, record that explicitly and do not treat the result as a
clean release-validation pass.

If the release run uses the dashboard, also open:

```bash
osk dashboard
```

Retain:

- the browser screenshot showing the local dashboard session

## Part 3: External-Browser Regression Baseline

Run the dedicated Chromebook mocked member-shell path as the stable
external-browser regression baseline:

```bash
scripts/chromebook_member_shell_smoke.sh ...
```

Retain:

- the run artifact directory
- `result.json`
- failure screenshots/logs if any checkpoint fails

This run does **not** replace live-hub validation. It remains the regression
baseline for the mocked member-shell path only.

## Part 4: Live Hub Chromium Member Validation

Use a supported Chromium-class browser against the actual Osk hub runtime.

Minimum checks:

1. Open the real join URL from the running coordinator.
2. Complete join and reach `/member`.
3. Confirm the member runtime loads without leaving the shared token in the
   visible URL.
4. Submit at least one launch-supported manual item while online.
5. Temporarily break connectivity, create an offline manual note, then restore
   connectivity and confirm the queue drains.
6. Reload the page and confirm the runtime session resumes through the current
   cookie-backed path.
7. Trigger a live wipe from the coordinator and confirm the connected browser
   clears local member state as expected for the supported path.

Recommended retained evidence:

- screenshot of `/join`
- screenshot of `/member`
- screenshot or photo of queued offline item before reconnect
- screenshot after reconnect confirms the item drains
- screenshot after reload confirms resumed runtime
- screenshot after wipe confirms the member state clears

## Part 5: Evidence Export and Verify

On the coordinator host:

```bash
osk evidence export --output osk-evidence-export.zip
osk evidence verify --input osk-evidence-export.zip
osk drill wipe --export-bundle osk-evidence-export.zip
```

Retain:

- archive path
- manifest path
- checksum path
- verify output
- wipe drill output

If export fails because no visible preserved evidence exists, record that as an
open release-validation gap. Do not mark the export/verify path complete.

## Part 6: Wipe Readiness and Audit Evidence

Before wipe:

```bash
osk status --json
osk members
```

After wipe:

```bash
osk audit --wipe-follow-up-only --json
```

Retain:

- wipe-readiness state before the wipe
- audit output for follow-up verification or reopen events after the wipe

If disconnected or stale members existed during the run, keep explicit notes on
how those members were handled. Do not treat the release run as a clean wipe
success until that follow-up is documented.

If the member browser visibly clears but `osk wipe` still returns non-zero or
leaves `status = state_only`, record that as a command-level wipe/shutdown
failure. Do not mark the wipe path complete just because the browser UI cleared.

## Pass Condition

This runbook is satisfied only when:

- the coordinator preflight and runtime steps complete on the Linux host
- the mocked Chromebook regression path remains green
- at least one supported Chromium browser completes the live-hub member flow
- evidence export/verify succeeds
- wipe-readiness and post-wipe audit evidence are retained

If any step fails, record the failure and keep the corresponding release
blocker open.
