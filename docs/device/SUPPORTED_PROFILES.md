# Osk Supported Configuration Profiles

**Version:** 2.0  
**Last Updated:** 2026-04-11

---

## Overview

Osk supports three configuration profiles, from full-featured to minimal. Choose the profile that matches your hardware and requirements.

## Profile Summary

| Profile | Requirements | Use Case | Battery Life* |
|---------|-------------|----------|---------------|
| **Full** | 4 GB RAM, Docker, FFmpeg | Production operations | 3-4 hours (sensor) |
| **Docker-Managed** | 4 GB RAM, Docker | Simplified deployment | 3-4 hours (sensor) |
| **Minimal** | 2 GB RAM, no Docker | Resource-constrained | 4-5 hours (sensor) |

*Sensor mode with High quality, from 100% charge. Observer mode extends to 8-12 hours.

---

## Profile 1: Full (Recommended)

**Best for:** Production field operations with full feature set

### Requirements

| Component | Requirement | Notes |
|-----------|-------------|-------|
| **OS** | Linux (Ubuntu 22.04+, Debian 12+, Fedora 38+) | Native support |
| **RAM** | 4 GB minimum | 8 GB recommended for large ops |
| **Disk** | 10 GB free | Evidence storage can grow quickly |
| **Python** | 3.11+ | Required for runtime |
| **PostgreSQL** | 14+ | System install or Docker |
| **Docker** | 24+ | Recommended for Postgres management |
| **FFmpeg** | 5.0+ | Required for audio transcription |
| **OpenSSL** | 3.0+ | For TLS certificate generation |
| **Network** | WiFi hotspot capable | For member devices |

### Features Available

- ✅ All sensor features (audio, video)
- ✅ Automatic PostgreSQL management via Docker
- ✅ Audio transcription (Whisper)
- ✅ Full PWA offline support
- ✅ Evidence export and preservation
- ✅ Complete coordinator dashboard

### Installation

```bash
# Run readiness check
osk doctor --readiness

# If ready, install
osk install

# Start hub
osk start
```

---

## Profile 2: Docker-Managed

**Best for:** Simplified deployment with Docker

### Requirements

| Component | Requirement | Notes |
|-----------|-------------|-------|
| **OS** | Linux with Docker | Ubuntu, Debian, Fedora, etc. |
| **RAM** | 4 GB minimum | Docker overhead included |
| **Disk** | 10 GB free | Includes Docker images |
| **Python** | 3.11+ | Host system |
| **Docker** | 24+ | Required - manages PostgreSQL |
| **FFmpeg** | 5.0+ | Host system |
| **OpenSSL** | 3.0+ | Host system |
| **PostgreSQL** | None | Managed by Docker |

### Features Available

- ✅ All sensor features
- ✅ Managed PostgreSQL (no system install needed)
- ✅ Audio transcription
- ✅ Full PWA support
- ✅ Complete feature set

### Limitations

- Slightly higher memory usage (Docker overhead)
- Docker required (may not suit all security profiles)

### Installation

```bash
# Docker will be used automatically for Postgres
osk install
osk start
```

---

## Profile 3: Minimal

**Best for:** Resource-constrained environments or testing

### Requirements

| Component | Requirement | Notes |
|-----------|-------------|-------|
| **OS** | Linux | Any modern distribution |
| **RAM** | 2 GB minimum | Tight but functional |
| **Disk** | 5 GB free | Minimal evidence storage |
| **Python** | 3.11+ | Required |
| **PostgreSQL** | 14+ | System install required |
| **OpenSSL** | 3.0+ | Required |
| **Docker** | None | Not used |
| **FFmpeg** | None | Audio transcription disabled |

### Features Available

- ✅ Manual reports and GPS
- ✅ Photo/audio clip capture
- ✅ Sensor streaming (no transcription)
- ✅ Coordinator dashboard
- ✅ Evidence export

### Limitations

- ❌ Audio transcription (requires FFmpeg)
- ❌ Automatic Postgres management
- ⚠️ Shorter evidence retention (disk space)
- ⚠️ No Docker-based services

### Installation

```bash
# Install system PostgreSQL manually
sudo apt install postgresql-14 postgresql-contrib

# Run minimal readiness check
osk doctor --readiness

# Install with minimal profile
osk install --profile minimal
osk start
```

---

## Unsupported Configurations

The following are explicitly **not supported**:

| Configuration | Reason |
|---------------|--------|
| **Windows** | No native support (use WSL2 for testing only) |
| **macOS** | Development/testing only, not production |
| **Python < 3.11** | Language features required |
| **PostgreSQL < 14** | Performance and feature requirements |
| **ARM32 / 32-bit** | Memory constraints |
| **Containers only** | Osk needs host network access |

---

## Hardware Recommendations

### Coordinator Laptop

| Spec | Minimum | Recommended |
|------|---------|-------------|
| CPU | 2 cores | 4 cores (Intel i5/AMD Ryzen 5) |
| RAM | 4 GB | 8 GB |
| Disk | 128 GB SSD | 256 GB+ SSD |
| WiFi | 802.11n | 802.11ac (5 GHz) |
| Battery | 4 hours | 8+ hours |

### Tested Hardware

| Device | Profile | Notes |
|--------|---------|-------|
| ThinkPad T14 Gen 3 | Full | Excellent performance |
| ThinkPad X1 Carbon | Full | Portable, good battery |
| Dell Latitude 5430 | Full | Solid mid-range |
| Chromebook (i5) | Docker-Managed | Budget option |
| Raspberry Pi 4 (8GB) | Minimal | Tested but not recommended |

---

## Pre-Installation Checklist

Before running `osk install`:

- [ ] Check profile requirements match your hardware
- [ ] Run `osk doctor --readiness` and fix any errors
- [ ] Ensure 10 GB disk space available
- [ ] Verify WiFi hotspot capability (via NetworkManager)
- [ ] Test in your target environment if possible

---

## Troubleshooting by Profile

### Full Profile Issues

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| PostgreSQL won't start | Port 5432 in use | Stop existing Postgres or use Docker profile |
| FFmpeg errors | Missing codec | Install full FFmpeg: `sudo apt install ffmpeg` |
| Docker permission denied | User not in docker group | `sudo usermod -aG docker $USER` |

### Docker-Managed Issues

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| Docker not running | Service stopped | `sudo systemctl start docker` |
| Port conflicts | Existing services | Stop services or change ports |
| Image pull fails | No internet | Check connection, retry |

### Minimal Profile Issues

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| PostgreSQL not found | Not installed | `sudo apt install postgresql-14` |
| Disk full quickly | Limited space | Clear evidence regularly |
| Audio not transcribed | No FFmpeg | Expected - install FFmpeg for feature |

---

## Migration Between Profiles

### Upgrading: Minimal → Full

```bash
# Stop hub
osk stop

# Install FFmpeg
sudo apt install ffmpeg

# Verify readiness
osk doctor --readiness

# Restart
osk start
```

### Downgrading: Full → Minimal

```bash
# Stop hub
osk stop

# Note: Transcription will stop working
# This is not recommended for production

osk start
```

---

## Validation

After installation, validate your profile:

```bash
# Check all components
osk doctor

# Test with single member
# (Use test browser or second device)

# Run validation suite
osk validate --profile <profile-name>
```

---

## Support Matrix

| Profile | Community Support | Commercial Support | Issue Priority |
|---------|------------------|-------------------|----------------|
| Full | ✅ Full | ✅ Available | P1 |
| Docker-Managed | ✅ Full | ✅ Available | P1 |
| Minimal | ⚠️ Best effort | ⚠️ Limited | P2 |

---

## References

- [INSTALL.md](../INSTALL.md) - Detailed installation instructions
- [VALIDATION_RUNBOOK.md](VALIDATION_RUNBOOK.md) - Testing procedures
- [BROWSER_MATRIX.md](BROWSER_MATRIX.md) - Browser compatibility
- [BATTERY_USAGE_GUIDE.md](BATTERY_USAGE_GUIDE.md) - Power consumption
