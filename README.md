# Osk

Design-stage civilian situational awareness platform. Osk is intended to use a
hub-and-spoke architecture to help groups coordinate during protests,
gatherings, public meetings, large events, travel, and personal safety
scenarios.

## Why Osk Exists

When you attend a protest, a large public event, or travel in an unfamiliar area, you're operating blind. You don't know what's happening three blocks away. You don't know if an exit route just got blocked. You don't know if the situation is escalating until it's too late.

Law enforcement and intelligence agencies have had real-time situational
awareness tools for decades — live audio feeds, computer vision, team
coordination, AI-powered analysis. Osk is intended to bring similar local-first
coordination capabilities to everyday people without requiring a cloud service.

## Planned Architecture

```
                    EDGE (Member Phones)
     ┌──────────────┐    ┌───────────────────┐
     │   Sensors     │    │    Observers       │
     │  (5-10 active)│    │   (40+ members)    │
     │               │    │                    │
     │  Audio stream  │    │  GPS broadcast     │
     │  Key frame     │    │  Receive alerts    │
     │   sampling     │    │  Manual reports    │
     │  GPS broadcast  │    │  Snap photo/clip   │
     └──────┬────────┘    └────────┬───────────┘
            │   Local WiFi /       │
            │   Hotspot            │
            │   (no internet)      │
     ┌──────┼──────────────────────┼───────────┐
     │      ▼          HUB         ▼           │
     │                                         │
     │  Whisper ── AI Summarizer ── Alerts     │
     │  Vision  ── Event Fusion  ── SitReps    │
     │  Location ── Escalation Detection       │
     │                                         │
     │  Coordinator Dashboard (full picture)   │
     │  PostgreSQL on tmpfs (ephemeral)        │
     │  LUKS encrypted volume (pinned evidence)│
     └─────────────────────────────────────────┘
```

In the planned design, **a coordinator** runs a laptop-based intelligence hub
and **group members** (50+) connect via their phones by scanning a QR code.

- **Sensors** (5-10 designated members) would stream audio and video to the hub
  for local analysis
- **Observers** (everyone else) would share GPS location, receive alerts, and
  submit manual reports
- **The hub** is intended to run Whisper, local vision models, and synthesis
  logic to fuse events into a unified picture
- **The coordinator** would see the event timeline, member map, and periodic
  situation reports
- **Members** would receive severity-filtered alerts rather than the full feed

## Planned Capabilities

### Real-Time Audio Intelligence
Members would stream audio to the hub. Whisper would transcribe it in
real-time. Analysis pipelines would look for events such as crowd movements,
route changes, and escalation patterns.

### Edge Computer Vision
Phones would do smart frame sampling locally using a Web Worker so the hub only
receives key frames when the scene changes materially.

### Ephemeral by Default
Operational data is intended to live in RAM by default, with selective pinning
to encrypted storage for preserved evidence.

### Emergency Wipe
A design goal is a fast emergency wipe path that revokes keys, unmounts
storage, and drops active connections. This has not been implemented or
validated in this repository yet.

### Fully Local
The system is intended to run without cloud APIs or internet dependency,
serving members over a local network from coordinator-controlled hardware.

### Zero-Friction Join
The planned join flow is QR-based in a mobile browser, with no account system
and no app-store installation requirement.

## Intended Use Cases

- **Protests and marches** — know where police are staging, which exits are clear, when the situation is escalating
- **Public meetings and hearings** — coordinate a group attending a contentious meeting, document what happens
- **Large events** — keep track of your group at festivals, conferences, or rallies
- **Travel** — groups traveling in unfamiliar or potentially hostile environments
- **Community safety** — neighborhood watch with real-time intelligence instead of a group chat

## Design Summary

| Layer | What It Does |
|---|---|
| **Edge (phones)** | Audio capture, key frame sampling, GPS, manual reports. PWA in mobile browser. |
| **Ingest** | Receives streams, queues by priority, deduplicates frames, rate-limits observers |
| **Processing** | Whisper (audio → text), Ollama Vision (frames → descriptions), Location Engine (GPS → clusters) |
| **Synthesis** | Event Generator (fuse sources → events), Alert Engine (filter + push), SitRep Generator (periodic summaries) |
| **Output** | Coordinator: full dashboard. Sensors: filtered alerts. Observers: critical alerts only. |
| **Storage** | tmpfs (ephemeral), LUKS volume (pinned evidence), kernel keyring (passphrase) |

### Member Roles

| Role | Count | Streams | Receives | Can Do |
|---|---|---|---|---|
| **Coordinator** | 1 | — | Everything | Full dashboard, role management, emergency controls |
| **Sensor** | 5-10 | Audio + video continuously | Advisory+ alerts | Pause/mute stream, pin events, manual reports |
| **Observer** | 40+ | GPS only | Critical alerts only | Snap photo, record clip, pin events, manual reports |

## Hardware Requirements

| Component | Minimum | Recommended |
|---|---|---|
| GPU | NVIDIA, 6+ GB VRAM, CUDA | NVIDIA RTX 3060 or better (8+ GB VRAM) |
| RAM | 16 GB | 32 GB |
| Storage | 20 GB free | 40 GB free |
| CPU | 4 cores | 8+ cores |
| WiFi | AP mode capable | Dual-band 5 GHz |
| OS | **Linux** (Fedora, Ubuntu, Arch) | With NetworkManager |

## Quick Start

> Osk is currently in the **design phase**. The commands below describe the intended workflow — implementation is in progress.

```bash
# One-time setup
git clone https://github.com/justinredmondsmith-collab/osk.git
cd osk
./osk install

# Start an operation
./osk start "Saturday March — Downtown"

# Share the QR code with your group
# Members scan → join via phone browser → done

# When finished
./osk stop
```

## Project Status

**Phase: Design Complete, Implementation Starting**

- Current repository contents: design docs, planning docs, and public project governance files. Runnable application code has not landed yet.
- [Design Specification](docs/specs/2026-03-21-osk-design.md) — full architecture, data model, API contract, security model
- [Implementation Plans](docs/plans/) — 6-phase build plan with TDD steps
- [Changelog](CHANGELOG.md) — public-facing repo and documentation changes

| Plan | Scope | Status |
|---|---|---|
| 1. Core Hub + Connection | Scaffolding, models, DB, auth, server, CLI | Planned |
| 2. Intelligence Pipeline | Whisper, vision, location engines | Planned |
| 3. Synthesis Layer | Events, alerts, SitReps | Planned |
| 4. Coordinator Dashboard | Map, timeline, sensor management | Planned |
| 5. Mobile PWA | Join flow, alert feed, edge sampling | Planned |
| 6. Operations Tooling | Hotspot, evidence, tile caching | Planned |

## Security Principles

Osk is being designed for environments where data compromise can have real
consequences. The items below are design goals and intended properties, not
validated guarantees in the current repository state.

- **Ephemeral by default** — the planned storage model keeps operational data in
  RAM and treats shutdown as data disposal
- **Selective pinning** — only explicitly preserved evidence should go to
  encrypted storage
- **LUKS encryption** — preserved evidence is intended to use an encrypted
  volume with a key-handling path outside normal app config
- **Emergency wipe** — a fast wipe path is a design goal, but not yet
  implemented or benchmarked here
- **No persistent identity** — the planned join model uses display names rather
  than persistent accounts
- **Local-network encryption** — encrypted local transport is planned, including
  self-signed TLS in the current design
- **No cloud dependency** — the design aims to keep core operation on
  coordinator-controlled local hardware

See [SECURITY.md](SECURITY.md) for responsible disclosure and [SAFETY.md](SAFETY.md) for current limitations and non-guarantees.

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md).

## License

Osk is licensed under the [GNU Affero General Public License v3.0 only](LICENSE) (`AGPL-3.0-only`).

AGPL ensures that Osk and derivative networked deployments remain open source. This is a deliberate choice: a civilian safety tool should not be co-opted into proprietary products.

See [NOTICE](NOTICE) for copyright and attribution guidance, and [docs/PROVENANCE.md](docs/PROVENANCE.md) for the spin-off and code-transplant record.
