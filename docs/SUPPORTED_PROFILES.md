# Osk Supported Deployment Profiles

**Version:** 2.0.0  
**Date:** 2026-03-28  
**Status:** Authoritative

---

## Overview

Osk 2.0.0 defines explicit **support profiles** that describe validated deployment configurations. These profiles help you understand:

1. What hardware/software combinations are supported
2. What features are available in each configuration
3. What validation evidence exists for each profile

---

## Profile Summary

| Profile | Use Case | Docker | PostgreSQL | FFmpeg | Validation |
|---------|----------|--------|------------|--------|------------|
| `supported-full` | Production deployment | Optional | Required | Required | ✅ Complete |
| `docker-managed` | Container isolation | Required | Included | Included | ✅ Complete |
| `supported-minimal` | Core functionality | No | SQLite | Optional | ✅ Complete |
| `unsupported` | Missing dependencies | - | - | - | ❌ Not supported |

---

## `supported-full`

**Best for:** Production operations requiring complete feature set

### Requirements

| Component | Minimum | Recommended | Check Command |
|-----------|---------|-------------|---------------|
| **OS** | Linux (Fedora 41, Ubuntu 22.04, Debian 12) | Latest stable | `cat /etc/os-release` |
| **Python** | 3.11.x | 3.13+ | `python --version` |
| **RAM** | 4 GB | 8 GB | `free -h` |
| **Storage** | 10 GB free | 50 GB+ | `df -h` |
| **PostgreSQL** | 14.x | 15.x+ | `psql --version` |
| **OpenSSL** | 3.0.x | 3.2.x+ | `openssl version` |
| **FFmpeg** | 5.0.x | 6.0.x+ | `ffmpeg -version` |
| **Network** | WiFi or Ethernet | Gigabit Ethernet | - |

### Available Features

- ✅ Full audio/video sensor streaming
- ✅ PostgreSQL-backed storage
- ✅ FFmpeg media processing
- ✅ TLS certificate management
- ✅ Complete AAR workflow
- ✅ All security hardening features
- ✅ Docker containers (optional)

### Installation

```bash
# Install system dependencies (Fedora)
sudo dnf install postgresql-server openssl ffmpeg python3.13

# Install Osk
pip install osk

# Verify profile
osk doctor
# Expected: Profile: supported-full
```

---

## `docker-managed`

**Best for:** Simplified deployment with container isolation

### Requirements

| Component | Specification | Check Command |
|-----------|---------------|---------------|
| **OS** | Linux with Docker/Podman | `docker --version` or `podman --version` |
| **Docker** | 20.10+ | `docker info` |
| **Podman** | 4.0+ (alternative) | `podman info` |
| **RAM** | 4 GB (includes overhead) | `free -h` |
| **Storage** | 15 GB free | `df -h` |

### Available Features

- ✅ Containerized PostgreSQL
- ✅ Containerized FFmpeg
- ✅ Isolated network stack
- ✅ Simple deployment/teardown
- ⚠️ Slightly higher resource usage (container overhead)

### Installation

```bash
# Install Docker (Fedora)
sudo dnf install docker
sudo systemctl enable --now docker

# Install Osk
pip install osk

# Deploy with Docker
osk deploy --profile docker-managed

# Verify profile
osk doctor
# Expected: Profile: docker-managed
```

### Docker Compose (Optional)

```yaml
# docker-compose.yml
version: '3.8'
services:
  osk:
    image: osk:2.0.0
    ports:
      - "8080:8080"
      - "8443:8443"
      - "8444:8444"
    volumes:
      - osk-data:/data
      - osk-evidence:/evidence
    environment:
      - OSK_PROFILE=docker-managed
    
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: osk
      POSTGRES_USER: osk
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres-data:/var/lib/postgresql/data

volumes:
  osk-data:
  osk-evidence:
  postgres-data:
```

---

## `supported-minimal`

**Best for:** Core functionality on limited hardware

### Requirements

| Component | Specification | Check Command |
|-----------|---------------|---------------|
| **OS** | Any Linux | `uname -a` |
| **Python** | 3.11+ | `python --version` |
| **RAM** | 4 GB | `free -h` |
| **Storage** | 10 GB free | `df -h` |
| **OpenSSL** | 3.0+ | `openssl version` |

### Available Features

- ✅ Core hub functionality
- ✅ SQLite database (included)
- ✅ Manual reporting
- ✅ Observation ingest
- ✅ Heuristic synthesis
- ⚠️ No media processing (FFmpeg optional)
- ⚠️ Limited sensor capacity

### Installation

```bash
# Install Python only
sudo dnf install python3.13 openssl

# Install Osk
pip install osk

# Verify profile
osk doctor
# Expected: Profile: supported-minimal
```

### When to Use Minimal Profile

- Older hardware
- Quick testing/development
- Low-bandwidth environments
- When media processing not required

---

## `unsupported`

**Trigger:** Missing critical dependencies

### Common Causes

| Cause | Fix |
|-------|-----|
| Python < 3.11 | Upgrade Python |
| No OpenSSL | Install OpenSSL |
| Insufficient disk | Free up space |
| Insufficient RAM | Close other applications |
| Port conflicts | Stop services on 8080, 8443, 8444 |

### Remediation

```bash
# Check what's missing
osk doctor --json

# Fix specific issues
sudo dnf install openssl    # Fedora
sudo apt install openssl    # Ubuntu/Debian

# Check again
osk doctor
```

---

## Hardware Matrix

### Validated Hardware

| Device | Profile | Use Case | Validation |
|--------|---------|----------|------------|
| ThinkPad X1 (i7, 16GB) | `supported-full` | Coordinator laptop | ✅ Daily driver |
| Dell XPS 13 (i5, 8GB) | `supported-full` | Field coordinator | ✅ Validated |
| Chromebook (i3, 4GB) | `supported-minimal` | Lightweight deploy | ✅ Tested |
| Raspberry Pi 4 (4GB) | `supported-minimal` | Edge deployment | ⚠️ Community tested |

### Performance Expectations

| Profile | Sensors | CPU @ 5 sensors | Memory @ 5 sensors |
|---------|---------|-----------------|-------------------|
| `supported-full` | 10 | <10% | <500 MB |
| `docker-managed` | 10 | <15% | <750 MB |
| `supported-minimal` | 5 | <15% | <400 MB |

---

## Browser Support Matrix

### Member Device Support

| Browser | OS | Status | Audio | Video | PWA |
|---------|-----|--------|-------|-------|-----|
| Chrome 120+ | Android | ✅ Supported | ✅ | ✅ | ✅ |
| Chrome 120+ | Desktop | ✅ Supported | ✅ | ✅ | ✅ |
| Edge 120+ | Desktop | ✅ Supported | ✅ | ✅ | ✅ |
| Brave 1.60+ | Android | ✅ Supported | ✅ | ✅ | ✅ |
| Chromium | Linux | ✅ Supported | ✅ | ✅ | ⚠️ |
| Firefox 121+ | Any | ⚠️ Degraded | ✅ | ❌ | ❌ |
| Safari | iOS/macOS | ❌ Not supported | ❌ | ❌ | ❌ |
| Chrome | iOS | ❌ Not supported | ❌ | ❌ | ❌ |

### Why Chromium-Only?

1. **WebRTC Implementation:** Chromium has the most mature WebRTC stack
2. **PWA Support:** Service workers, background sync work reliably
3. **Media APIs:** `getUserMedia`, `MediaRecorder` fully supported
4. **Validation Focus:** We test what we can validate thoroughly

---

## Migration Between Profiles

### Full → Minimal

```bash
# Export existing data
osk evidence export --output pre-migration.zip

# Reconfigure
# Edit ~/.config/osk/config.toml:
#   storage_backend = "directory"
#   synthesis_backend = "heuristic"

# Remove PostgreSQL dependency
osk doctor
# Expected: Profile: supported-minimal
```

### Minimal → Full

```bash
# Install PostgreSQL
sudo dnf install postgresql-server
sudo postgresql-setup --initdb
sudo systemctl enable --now postgresql

# Reconfigure
# Edit ~/.config/osk/config.toml:
#   storage_backend = "postgres"

# Verify
osk doctor
# Expected: Profile: supported-full
```

---

## Validation Evidence

### Automated Tests

| Profile | Tests | Coverage |
|---------|-------|----------|
| `supported-full` | 35 | All checks pass |
| `docker-managed` | 35 | Docker-specific paths |
| `supported-minimal` | 20 | Core functionality |

### Manual Validation

| Profile | Last Validated | Evidence |
|---------|----------------|----------|
| `supported-full` | 2026-03-28 | Daily usage |
| `docker-managed` | 2026-03-28 | CI/CD pipeline |
| `supported-minimal` | 2026-03-28 | VM testing |

---

## Getting Help

### Profile Detection Issues

```bash
# Verbose output
osk doctor --verbose

# JSON output for debugging
osk doctor --json | jq .

# Check specific component
python -c "import sys; print(sys.version_info)"
psql --version
ffmpeg -version
openssl version
```

### Reporting Profile Issues

When reporting issues, include:

```bash
# Generate system report
osk doctor --json > profile-report.json
uname -a >> profile-report.txt
cat /etc/os-release >> profile-report.txt
```

---

## Future Profiles

### Under Consideration

| Profile | Status | ETA |
|---------|--------|-----|
| `cloud-managed` | Research | 3.x |
| `embedded` | Research | 3.x |
| `federated-node` | Backlog | Post-3.0 |

---

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-03-28 | Defined 3 profiles | Clear support boundaries |
| 2026-03-28 | Chromium-only browser | Validation focus |
| 2026-03-28 | SQLite for minimal | Reduce dependencies |
| 2026-03-28 | PostgreSQL for full | Production features |

---

**Questions?** See [INSTALL_GUIDE.md](INSTALL_GUIDE.md) or open an issue.

**Updates:** This document is versioned with Osk releases.
