# Operations Drills

Read-only operator drills now exist for the two highest-risk operational paths:
install/start readiness and wipe/cleanup boundaries.

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
- what the current member/browser wipe path does
- the current gaps in Osk's wipe story
- the safe operator sequence for export, wipe, shutdown, and evidence destroy

If you want machine-readable output:

```bash
osk drill wipe --json
```

Today this drill is expected to report `partial`, because Osk does not yet have
a fully validated one-shot wipe across disconnected members and preserved
evidence destruction.

## Current Safe Sequence

For now, the safe operator sequence is:

1. Export preserved evidence first if you need to keep pinned material.
2. Run `osk operator login` if no active local operator session exists.
3. Run `osk wipe --yes` from the coordinator host. That broadcasts wipe to
   connected members and stops the hub.
4. Run `osk evidence destroy --yes` only if permanent removal of preserved
   evidence storage is intended.

That sequence is the current truth. Do not describe Osk as having a fully
validated one-shot emergency wipe until the code and drills actually support
it.
