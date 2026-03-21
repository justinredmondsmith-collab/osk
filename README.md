# Osk

Civilian situational awareness platform. Hub-and-spoke architecture giving groups LEO/IC-grade intelligence capabilities for protests, gatherings, public meetings, large events, and personal safety.

## What It Does

A coordinator runs a laptop-based intelligence hub. Group members (50+) connect via their phones by scanning a QR code — no app install needed.

- **Real-time audio intelligence** — members stream audio to the hub for AI transcription and situational analysis
- **Edge computer vision** — phones do smart frame sampling locally, send key frames to the hub for vision AI analysis
- **Team coordination** — tiered roles (Coordinator / Sensor / Observer), GPS tracking, group status
- **Alert-driven** — members receive actionable alerts; coordinator sees the full intelligence picture
- **Ephemeral by default** — all data lives in RAM. Selective pinning to encrypted storage for evidence preservation. Emergency wipe capability.
- **Fully local** — runs on local WiFi with no internet dependency. No cloud APIs. Data never leaves the hub.

## Status

**Design phase.** See [docs/specs/2026-03-21-osk-design.md](docs/specs/2026-03-21-osk-design.md) for the full design specification.

## Hardware Requirements

| Component | Minimum | Recommended |
|---|---|---|
| GPU | NVIDIA, 6+ GB VRAM, CUDA | NVIDIA RTX 3060 or better |
| RAM | 16 GB | 32 GB |
| Storage | 20 GB free | 40 GB free |
| OS | Linux (Fedora, Ubuntu, Arch) | With NetworkManager |

## License

TBD
