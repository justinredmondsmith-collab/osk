# Release Validation

**Version:** 1.0.0  
**Last Updated:** 2026-03-27

This runbook documents the minimum manual validation flow for the bounded
`1.0.0` release target.

Use it together with:

- [`docs/release/1.0.0-definition.md`](../release/1.0.0-definition.md)
- [`docs/release/1.0.0-validation-matrix.md`](../release/1.0.0-validation-matrix.md)
- [`docs/release/1.0.0-synthesis-limits.md`](../release/1.0.0-synthesis-limits.md)
- [`docs/runbooks/chromebook-lab-smoke.md`](./chromebook-lab-smoke.md)
- [`docs/runbooks/operations-drills.md`](./operations-drills.md)

The purpose of this runbook is not to prove broad compatibility. The purpose is
to gather retained evidence for the narrow Linux + Chromium release boundary.

---

## Release Boundary Reminder

For the first release:

- coordinator host: Linux only
- member browsers: Chromium-class only
- disconnected-device wipe cleanup is still outside any live-wipe guarantee

Do not use this runbook to imply support for Firefox, Safari, or iOS.

---

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

---

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

---

## Part 2: Runtime Bring-Up

### Fresh Operation Start (Recommended)

To ensure a clean validation run without resuming stale operations:

```bash
osk start --fresh "Osk 1.0.0 Release Validation"
osk status --json
```

The `--fresh` flag will:
1. Stop any currently running hub process
2. Mark active database operations as stopped
3. Create a new operation with the requested name

### Without --fresh (Legacy)

```bash
osk start "Osk 1.0.0 Release Validation"
osk status --json
```

**Note:** Without `--fresh`, if an operation with `stopped_at IS NULL` exists
in the database, it will be resumed instead of creating a new operation.

### Validation Checklist

Retain:

- the `osk status --json` output
- the printed join URL / QR target

Also confirm:

- [ ] the active operation id and name in `osk status --json` match the intended
  release-validation run
- [ ] the operation was created fresh (not resumed from a previous run)
- [ ] wipe_readiness status is `idle` (no stale member state from prior runs)

If `osk start` resumes an older operation instead of creating the intended
release-validation run, use `osk start --fresh` instead.

If the release run uses the dashboard, also open:

```bash
osk dashboard
```

Retain:

- the browser screenshot showing the local dashboard session

---

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

---

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

---

## Part 5: Evidence Export and Verify

The intelligence pipeline automatically writes observation metadata and
artifacts to the evidence store during operation. Evidence is stored at:
`~/.local/state/osk/evidence/{operation_id}/{member_id}/`

On the coordinator host:

```bash
osk evidence export --output osk-evidence-export.zip
osk evidence verify --input osk-evidence-export.zip
osk drill wipe --export-bundle osk-evidence-export.zip
```

Retain:

- archive path
- manifest path (`osk-evidence-export.zip.manifest.json`)
- checksum path (`osk-evidence-export.zip.sha256`)
- verify output
- wipe drill output

### Expected Export Output

A successful export produces:
```json
{
  "ok": true,
  "output_path": "osk-evidence-export.zip",
  "file_count": N,
  "total_bytes": B,
  "archive_sha256": "...",
  "manifest_path": "osk-evidence-export.zip.manifest.json",
  "checksum_path": "osk-evidence-export.zip.sha256"
}
```

### Expected Verify Output

A successful verification shows:
```json
{
  "ok": true,
  "embedded_manifest_status": "verified",
  "manifest_status": "verified",
  "checksum_status": "verified",
  "warnings": []
}
```

If export fails because no visible preserved evidence exists, this indicates
no intelligence observations were generated during the validation run. Record
this as a validation gap only if the member validation flow (Part 4) was
expected to produce observations.

---

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

### Wipe Command Expected Behavior

As of the March 27, 2026 validation run, the wipe command should:

1. Return exit code 0 (not 1)
2. Show `"hub_stopped": true` in JSON output
3. Result in `osk status --json` showing `"status": "stopped"` (not `state_only`)

Example successful wipe output:
```json
{
  "broadcast": {
    "status": "wipe_initiated",
    "wipe_readiness": {
      "status": "idle",
      "ready": true
    }
  },
  "hub_stopped": true,
  "operation_id": "..."
}
```

If the member browser visibly clears but `osk wipe` returns non-zero or
leaves `status = state_only`, record that as a command-level wipe/shutdown
failure. Do not mark the wipe path complete just because the browser UI cleared.

---

## Pass Condition

This runbook is satisfied only when:

- [ ] the coordinator preflight and runtime steps complete on the Linux host
- [ ] the runtime started with `--fresh` or explicitly verified as a new operation
- [ ] the mocked Chromebook regression path remains green
- [ ] at least one supported Chromium browser completes the live-hub member flow
- [ ] evidence export/verify succeeds (or explicitly documented why no evidence was produced)
- [ ] `osk wipe --yes` returns clean exit and `hub_stopped: true`
- [ ] wipe-readiness and post-wipe audit evidence are retained

If any step fails, record the failure and keep the corresponding release
blocker open.

---

## Reference Validation Runs

- March 27, 2026: [`docs/release/2026-03-27-release-validation-final-run.md`](../release/2026-03-27-release-validation-final-run.md)
  - First fully successful validation with all blockers resolved
  - Validated: `--fresh` flag, evidence pipeline, clean wipe shutdown

- March 25, 2026: [`docs/release/2026-03-25-release-validation-clean-run.md`](../release/2026-03-25-release-validation-clean-run.md)
  - Exposed shutdown and lifecycle blockers
  - Browser-side wipe validated but command-level wipe failed
