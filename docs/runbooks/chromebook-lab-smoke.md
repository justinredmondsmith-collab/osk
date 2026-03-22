# Chromebook Lab Smoke

This runbook covers the dedicated Chromebook test path for Osk's mocked member
shell smoke flow.

It is intentionally a **lab workflow**, not a statement about normal member
devices or about the full real-hub runtime. The current target is:

- one dedicated Chromebook
- Crostini Debian container
- `chromium` launched in a disposable lab profile
- host-driven automation over SSH + CDP
- the existing mocked `/join` -> `/member` smoke helper

Use this runbook when you want fast, repeatable real-device validation for the
member PWA without mixing in hotspot setup, the real hub runtime, or wider
field-network complexity.

## What This Validates

The current Chromebook lab smoke path is meant to validate only the mocked
member-shell path on a real external browser:

- `/join` loads
- join submits and reaches `/member`
- an offline field note queues locally
- reconnect drains the outbox
- reload resumes the member session
- a live wipe clears the local member session

Keep the claim scoped to that path. It does **not** validate:

- the real hub runtime
- hotspot orchestration
- disconnected-device wipe cleanup
- every ChromeOS browser mode
- every mobile/browser variant

## Current Components

- [chromebook_member_shell_smoke.sh](/var/home/bazzite/osk/scripts/chromebook_member_shell_smoke.sh)
  Host-side entrypoint that starts the mocked smoke helper, prepares the
  Chromebook browser, and runs the real smoke flow.
- [chromebook_lab_control.sh](/var/home/bazzite/osk/scripts/chromebook_lab_control.sh)
  SSH-based Chromebook helper for `prepare`, `launch`, and `cleanup`.
- [chromebook_member_shell_smoke.py](/var/home/bazzite/osk/scripts/chromebook_member_shell_smoke.py)
  Host-side CDP runner that performs the actual browser assertions and writes
  artifacts.
- [member_shell_smoke.py](/var/home/bazzite/osk/scripts/member_shell_smoke.py)
  Mocked Osk member-shell helper used as the smoke target.

## One-Time Chromebook Setup

These steps apply to the Crostini Debian container on the dedicated
Chromebook, not to the host ChromeOS session.

### 1. Install Chromium

```bash
sudo apt-get update
sudo apt-get install -y chromium
```

Verify:

```bash
command -v chromium
chromium --version
```

### 2. Repair and Enable SSH in Crostini

Some Crostini images ship with `openssh-server` installed but not runnable yet.
If `sshd` fails because `/etc/ssh/sshd_not_to_be_run` exists or host keys are
missing, repair it explicitly:

```bash
sudo rm -f /etc/ssh/sshd_not_to_be_run
sudo ssh-keygen -A
sudo systemctl enable --now ssh
```

Verify:

```bash
/usr/sbin/sshd -t
ss -ltnp | grep ':22 '
hostname
whoami
hostname -I
```

The host-side automation expects an SSH target like:

```bash
ssh jrsmith@<reachable-chromebook-ip>
```

If the Crostini container IP is not directly reachable from the host, do not
force the repo scripts to pretend otherwise. Use a reachable SSH endpoint
instead, such as a reverse tunnel described below.

### 2a. Enable Host Authentication for Reverse Tunnels

If you plan to use a reverse SSH tunnel from Crostini back to the host, the
Chromebook container must also be able to authenticate to the host account
running the Osk repo.

The simplest lab-safe path is a dedicated SSH key used only for this testing
workflow.

From the Chromebook container:

```bash
mkdir -p ~/.ssh
chmod 700 ~/.ssh
ssh-keygen -t ed25519 -f ~/.ssh/osk_lab_reverse_tunnel -N ""
cat ~/.ssh/osk_lab_reverse_tunnel.pub
```

Add the printed public key to the host account that will own the reverse
tunnel, typically:

```bash
/var/home/bazzite/.ssh/authorized_keys
```

Recommended restriction for a lab-only key:

```text
restrict,port-forwarding ssh-ed25519 AAAA...
```

Then verify from the Chromebook container:

```bash
ssh -F /dev/null \
  -i ~/.ssh/osk_lab_reverse_tunnel \
  -o BatchMode=yes \
  -o StrictHostKeyChecking=accept-new \
  bazzite@<host-ip-visible-from-chromebook> \
  true
```

Expected: exit code `0`.

### 3. Confirm the Disposable Profile Path

The lab browser profile should remain disposable and isolated from any normal
browser profile.

Expected default:

```bash
/var/tmp/osk-chromebook-lab
```

Verify it is writable:

```bash
mkdir -p /var/tmp/osk-chromebook-lab
touch /var/tmp/osk-chromebook-lab/.writetest
ls -ld /var/tmp/osk-chromebook-lab
```

## Manual Browser Validation

Before relying on the host automation, verify the Crostini browser can launch
with the same flags the helper will use.

Launch:

```bash
chromium \
  --user-data-dir=/var/tmp/osk-chromebook-lab \
  --remote-debugging-port=9222 \
  --no-first-run \
  --no-default-browser-check \
  --disable-sync \
  --disable-background-networking \
  --window-size=1440,900 \
  about:blank
```

Verify CDP locally inside the Chromebook container:

```bash
curl -s http://127.0.0.1:9222/json/version
```

Expected: JSON including `webSocketDebuggerUrl`.

Observed on the current dedicated Chromebook:

- `chromium` in Crostini launches successfully
- CDP responds on `127.0.0.1:9222`
- Wayland/DRM warnings may appear, but CDP can still come up

## Safe Cleanup Command

Use an anchored cleanup command so the profile path does not accidentally match
the shell command line or unrelated Chromium processes.

Known-good cleanup on the current Chromebook:

```bash
pkill -u "$(id -un)" -f '^/usr/lib/chromium/chromium .*--user-data-dir=/var/tmp/osk-chromebook-lab'
```

The helper also tracks a PID file at:

```bash
/var/tmp/osk-chromebook-lab.pid
```

## Host Prerequisites

On the host machine running this repo:

- Python Playwright package must be installed in the active environment
- the host must be able to reach the Chromebook SSH target
- the Chromebook must be able to reach the host IP you advertise for the smoke
  helper

The current automation uses hermetic SSH invocation:

```bash
ssh -F /dev/null ...
```

That is deliberate. It avoids host-specific SSH config problems affecting the
lab run.

## Crostini Reachability Reality

Many Crostini containers use an internal `100.115.92.x` address that is
visible inside ChromeOS but not directly reachable from another machine on the
LAN. If direct host-to-Crostini SSH times out, prefer a reachable control path
instead of trying to special-case the repo around one network topology.

The host-side scripts now support:

- `--ssh-target`
- `--ssh-port`
- `--ssh-identity`

That means the Chromebook control path can be:

- a directly reachable Crostini SSH server
- a forwarded SSH port on the ChromeOS host
- a reverse tunnel endpoint bound on the development host

## Reverse SSH Tunnel Fallback

If the Chromebook can reach the host, but the host cannot reach Crostini
directly, establish a reverse tunnel from the Chromebook container back to the
host.

From the Chromebook container:

```bash
ssh -F /dev/null \
  -i ~/.ssh/osk_lab_reverse_tunnel \
  -N \
  -R 22022:localhost:22 \
  <host-user>@<host-ip-visible-from-chromebook>
```

That exposes the Chromebook container's SSH server on the host as
`localhost:22022` for as long as the tunnel stays open.

Verify from the host:

```bash
ssh -F /dev/null -p 22022 localhost true
```

Then run the repo smoke using that reachable control endpoint:

```bash
./scripts/chromebook_member_shell_smoke.sh \
  --chromebook-host chromebook-lab \
  --ssh-target jrsmith@localhost \
  --ssh-port 22022 \
  --ssh-identity /var/home/bazzite/.ssh/osk_chromebook_lab \
  --advertise-host <host-ip-visible-from-chromebook>
```

This keeps the repo-owned automation unchanged at the behavioral level while
sidestepping Crostini's non-routable container address.

## Host-To-Chromebook Auth For The Reverse Tunnel

The reverse tunnel only solves reachability. The host still needs a private key
that the Chromebook container accepts for `jrsmith@localhost:22022`.

Generate a dedicated host-side key:

```bash
ssh-keygen -t ed25519 -f /var/home/bazzite/.ssh/osk_chromebook_lab -N ""
cat /var/home/bazzite/.ssh/osk_chromebook_lab.pub
```

Add that host public key to the Chromebook container's
`/home/jrsmith/.ssh/authorized_keys`. A lab-safe entry is:

```text
restrict,port-forwarding ssh-ed25519 AAAA...
```

Then run the host-side smoke with the explicit identity:

```bash
./scripts/chromebook_member_shell_smoke.sh \
  --chromebook-host chromebook-lab \
  --ssh-target jrsmith@localhost \
  --ssh-port 22022 \
  --ssh-identity /var/home/bazzite/.ssh/osk_chromebook_lab \
  --advertise-host <host-ip-visible-from-chromebook>
```

## Persistent Reverse Tunnel

For a real one-command developer loop, keep the reverse tunnel alive with a
Chromebook-side `systemd --user` service.

Repo helper:

- [chromebook_reverse_tunnel.sh](/var/home/bazzite/osk/scripts/chromebook_reverse_tunnel.sh)

Run a quick preflight before installing or restarting the service:

```bash
cd /path/to/osk
./scripts/chromebook_reverse_tunnel.sh preflight \
  --host-target bazzite@10.0.0.60 \
  --identity /home/jrsmith/.ssh/id_ed25519 \
  --remote-port 22022
```

This verifies:

- Chromebook-to-host SSH auth works
- the chosen host port is not already occupied by an older manual tunnel

Install it on the Chromebook container from the repo checkout there:

```bash
cd /path/to/osk
./scripts/chromebook_reverse_tunnel.sh install-user-service \
  --host-target bazzite@10.0.0.60 \
  --identity /home/jrsmith/.ssh/id_ed25519 \
  --remote-port 22022
```

Check status:

```bash
cd /path/to/osk
./scripts/chromebook_reverse_tunnel.sh service-status
```

Remove it later:

```bash
cd /path/to/osk
./scripts/chromebook_reverse_tunnel.sh uninstall-user-service
```

Once that service is healthy, the host-side smoke command stays:

```bash
cd /var/home/bazzite/osk
./scripts/chromebook_member_shell_smoke.sh \
  --chromebook-host chromebook-lab \
  --ssh-target jrsmith@localhost \
  --ssh-port 22022 \
  --ssh-identity /var/home/bazzite/.ssh/osk_chromebook_lab \
  --advertise-host 10.0.0.60
```

## Choosing `--advertise-host`

`--advertise-host` must be an IP or hostname that the Chromebook can reach for
the mocked smoke helper.

Do not guess. Verify from the Chromebook container once the host smoke helper
is running:

```bash
curl -I http://<advertise-host>:8123/join
```

If this fails, the browser can launch but the test will never reach the host
smoke helper.

## Normal Run

From the host:

```bash
cd /var/home/bazzite/osk
./scripts/chromebook_member_shell_smoke.sh \
  --chromebook-host <chromebook-host-or-ip> \
  --ssh-target <user@chromebook-ip> \
  --ssh-port <optional-port> \
  --advertise-host <host-ip-visible-from-chromebook>
```

Example shape:

```bash
./scripts/chromebook_member_shell_smoke.sh \
  --chromebook-host 100.115.92.200 \
  --ssh-target jrsmith@100.115.92.200 \
  --advertise-host 10.0.0.60
```

Artifacts are written under:

```bash
output/chromebook/member-shell-smoke/<timestamp>/
```

Expected files include:

- `metadata.json`
- `helper.log`
- `smoke-metadata.json`
- `cdp-version.json`
- `result.json`
- checkpoint screenshots
- `console-events.json`
- `network-failures.json`
- `page-errors.json`

## Debug Run

If you want to leave the Chromebook browser or the host smoke helper running
after the test:

```bash
./scripts/chromebook_member_shell_smoke.sh \
  --chromebook-host <chromebook-host-or-ip> \
  --ssh-target <user@chromebook-ip> \
  --ssh-port <optional-port> \
  --advertise-host <host-ip-visible-from-chromebook> \
  --keep-browser \
  --keep-server
```

This is useful when you want to inspect the lab browser state after a failure.

## Current Blocking Check

The most important real-world gate is simple:

1. Can the host reach the Chromebook over SSH?
2. Can the Chromebook reach the host smoke helper over `--advertise-host`?

The current repo automation is ready for the Crostini Chromium path, but a full
end-to-end run should not be described as validated until both of those
network-reachability checks succeed from the actual machines involved.

## Troubleshooting

### `ssh: connect to host ... port 22: Connection timed out`

The Chromebook SSH target is not reachable from the host yet. Check:

- Crostini `sshd` is listening
- the chosen SSH target and optional SSH port are actually reachable from the host
- firewalls or local network isolation are not blocking the path

If the target was a Crostini `100.115.92.x` address, a reverse tunnel is often
the simpler fix.

This is a real environment issue, not an Osk smoke-helper bug.

### `osk-chromebook-reverse-tunnel.service` exits immediately with status `255`

The most common cause is a port collision on the host because an older manual
reverse tunnel is still holding `22022`.

Run the Chromebook-side preflight:

```bash
cd /path/to/osk
./scripts/chromebook_reverse_tunnel.sh preflight \
  --host-target bazzite@10.0.0.60 \
  --identity /home/jrsmith/.ssh/id_ed25519 \
  --remote-port 22022
```

If it reports that the host port is already accepting connections, stop the
manual tunnel first or choose a different `--remote-port`.

### `CDP version endpoint did not become ready`

The browser launched poorly or not at all. Re-test manually on the Chromebook:

```bash
chromium \
  --user-data-dir=/var/tmp/osk-chromebook-lab \
  --remote-debugging-port=9222 \
  --no-first-run \
  --no-default-browser-check \
  --disable-sync \
  --disable-background-networking \
  --window-size=1440,900 \
  about:blank
curl -s http://127.0.0.1:9222/json/version
```

### `Smoke metadata file does not exist`

The host-side mocked smoke helper never wrote its metadata file. Inspect the
artifact directory's `helper.log`.

### The browser launches but `/join` never loads

`--advertise-host` is probably wrong for the Chromebook's network view. Verify
from the Chromebook container with `curl` before re-running.
