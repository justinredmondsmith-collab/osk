# Operations Drills

Read-only operator drills now exist for the two highest-risk operational paths:
install/start readiness and wipe/cleanup boundaries.

They support the repo's current field-validation and operational-hardening
phase: the goal is to make the real install/wipe boundary explicit before
anyone claims more than the implementation actually does today.

These drills are meant to answer:

- What will Osk touch on this machine?
- What is actually implemented today?
- What still requires a manual or separate step?

They do **not** mutate host networking, browser state, evidence storage, or the
running hub.

## Install Drill

Run:

```bash
osk drill install
```

Use this before field setup or before asking an agent to work on startup or
deployment issues. The report summarizes:

- current service mode
- TLS/evidence asset readiness
- local Compose runtime availability when local services are configured
- current hotspot and `join_host` guidance
- next operator steps

If you want machine-readable output:

```bash
osk drill install --json
```

This command returns non-zero when the local machine still needs attention.

## Wipe Drill

Run:

```bash
osk drill wipe
```

This is intentionally a reality check, not a wipe trigger. The report shows:

- whether a running hub is present for live member wipe broadcast
- which host paths are involved in runtime/evidence/session cleanup
- what the current member/browser wipe path does for connected browsers
- the current gaps in Osk's wipe story
- the safe operator sequence for export, wipe, shutdown, and evidence destroy

If you want machine-readable output:

```bash
osk drill wipe --json
```

If you already exported preserved evidence and want the drill to verify that
bundle before cleanup planning, include the archive:

```bash
osk drill wipe --export-bundle osk-evidence-export.zip
```

You can optionally point the drill at explicit sidecar paths with `--manifest`
and `--checksum`. Otherwise it checks for adjacent `.manifest.json` and
`.sha256` files next to the archive.

Today this drill is expected to report `partial`, because Osk does not yet have
a fully validated one-shot wipe across disconnected members and preserved
evidence destruction.

Today the connected-browser member path is stronger than it was earlier in the
repo history: a live wipe now clears queued browser data, member cookies,
service-worker caches, and the current installed member-shell registration on
the device that receives the broadcast. That is still not a full browser wipe.
Browser history, OS-level caches, disconnected devices, and preserved evidence
destruction remain outside that one live message.

That connected-browser path is no longer only theoretical: the disposable
member-shell smoke flow has now been exercised on a real WLAN browser for
join, offline queued field-note replay after reconnect, page reload/session
resume, and live wipe clearing. Keep the claim scoped to that path. It does
not mean disconnected browsers, preserved evidence destruction, or every mobile
browser variant are now fully validated.

While an operation is still live, check `osk status --json`, `osk members`, or
the coordinator dashboard's wipe-readiness panel before running `osk wipe`.
Those surfaces now call out stale/disconnected member browsers that may miss
the live broadcast path, plus unresolved follow-up entries that stay open until
the affected browsers are rechecked or manually verified. The dashboard panel
now renders the required action for each unresolved member directly in that
view.

When you do run `osk wipe`, the audit trail now records the same trigger-time
coverage snapshot: broadcast target count plus the stale/disconnected member
browsers already at risk. Use `osk audit --limit ... --json` if you need that
history after the fact.

## Current Safe Sequence

For now, the safe operator sequence is:

1. Export preserved evidence first if you need to keep pinned material.
   The export now emits the zip bundle plus adjacent `.manifest.json` and
   `.sha256` files so you retain file inventory and integrity metadata with the
   archive.
2. Run `osk evidence verify --input <bundle.zip>` against that archive before
   you hand it off or rely on it elsewhere, or pass the same archive to
   `osk drill wipe --export-bundle <bundle.zip>` so the wipe drill includes
   export verification in the same report.
3. Run `osk operator login` if no active local operator session exists.
4. Run `osk wipe --yes` from the coordinator host. That broadcasts wipe to
   connected members and stops the hub.
5. Run `osk evidence destroy --yes` only if permanent removal of preserved
   evidence storage is intended.

If you know member devices were offline or disconnected during step 3, treat
their local cleanup as unresolved until those browsers are manually checked or
rejoined.

That sequence is the current truth. Do not describe Osk as having a fully
validated one-shot emergency wipe until the code and drills actually support
it.
