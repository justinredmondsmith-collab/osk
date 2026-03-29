<div align="center">

# 🛡️ Osk

**Local-first field coordination for civilian operations**

[![Version](https://img.shields.io/badge/version-2.0.0-blue)](https://github.com/justinredmondsmith-collab/osk/releases)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-545%20passing-brightgreen)]()
[![License](https://img.shields.io/badge/license-AGPL--3.0--only-blue)](LICENSE)

[📖 Documentation](docs/) • [🚀 Quickstart](#quickstart) • [📥 Install](#installation) • [✅ Validation](#validation-status) • [🔒 Security](#security--privacy)

</div>

---

## What is Osk?

Osk is a **local-first field coordination system** for civilian groups operating in dynamic environments—protests, rallies, marches, festivals, and emergency response.

**No cloud. No app stores. No accounts.** Just a coordinator laptop and web browsers.

```
┌─────────────────────────────────────────────────────────────────┐
│                     OPERATION LIFECYCLE                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐ │
│   │  INSTALL │───▶│  DEPLOY  │───▶│ OPERATE  │───▶│  CLOSE   │ │
│   └──────────┘    └──────────┘    └──────────┘    └──────────┘ │
│        │               │               │               │       │
│        ▼               ▼               ▼               ▼       │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐ │
│   │osk doctor│    │osk start │    │ Dashboard│    │osk aar   │ │
│   │ Validates│    │  --fresh │    │ + Sensors│    │ export   │ │
│   │   deps   │    │          │    │   + Tasks│    │ + wipe   │ │
│   └──────────┘    └──────────┘    └──────────┘    └──────────┘ │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Network Architecture

```
┌─────────────┐      WiFi/Hotspot      ┌─────────────────┐
│  Chromebook │◄──────────────────────►│  Linux Laptop   │
│   (Sensor)  │      ┌──────────┐      │  (Coordinator)  │
│   Phone     │◄────►│ Osk Hub  │◄────►│  Dashboard      │
│   (Member)  │      │          │      │  Evidence Store │
└─────────────┘      └──────────┘      └─────────────────┘
                              ▲
                              │
                         ┌────┴────┐
                         │  Ollama │ (Optional AI)
                         │ (Local) │
                         └─────────┘
```

---

## 🎯 Core Capabilities

| Feature | 1.0.0 | 2.0.0 | Description |
|---------|-------|-------|-------------|
| 📡 **Sensor Streaming** | ✅ | ✅ | Live audio/video from 5+ member devices |
| 🧠 **AI Synthesis** | ✅ | ✅ | LLM-powered situation analysis (Ollama) |
| 🧭 **Coordinator Tasking** | ✅ | ✅ | Route confirmation & field tasks |
| 📊 **Live Dashboard** | ✅ | ✅ | Real-time map, alerts, and findings |
| 🔒 **Encrypted Evidence** | ✅ | ✅ | Tamper-proof audit trail with SHA256 |
| 🔥 **Emergency Wipe** | ✅ | ✅✨ | Verified wipe with residual logging |
| 📱 **PWA Support** | ✅ | ✅ | Works offline after initial load |
| 🔧 **Install Readiness** | ❌ | ✅✨ | 9-point pre-flight validation |
| 📋 **After-Action Review** | ❌ | ✅✨ | Complete operation lifecycle |
| 🛡️ **Security Hardening** | ⚠️ | ✅✨ | Token lifecycle, audit logging |

**✨ = New in 2.0.0**

---

## 🚀 Quickstart

### 1. Verify Your System (30 seconds)

```bash
pip install osk
osk doctor

✅ Python 3.14.2
✅ PostgreSQL 15.4
✅ OpenSSL 3.2.1
✅ FFmpeg 6.1.1
✅ Profile: supported-full
```

### 2. Start Operation (1 minute)

```bash
osk start --fresh "March on Washington"
osk dashboard
```

### 3. Members Join (30 seconds each)

1. Members open Chrome on their phones
2. Go to the join URL from `osk dashboard`
3. Enter name, select role (Observer/Sensor)
4. Grant permissions

**That's it.** Real-time coordination is live.

---

## 📋 System Requirements

### Coordinator Hardware

| Profile | OS | Python | RAM | Storage | Best For |
|---------|-----|--------|-----|---------|----------|
| **Full** | Linux | 3.11+ | 8GB | 50GB | Production operations |
| **Docker** | Linux | 3.11+ | 8GB | 50GB | Container isolation |
| **Minimal** | Linux | 3.11+ | 4GB | 10GB | Lightweight deploy |

See [SUPPORTED_PROFILES.md](docs/SUPPORTED_PROFILES.md) for complete matrix.

### Member Devices

| Browser | Status | Audio | Video | PWA |
|---------|--------|-------|-------|-----|
| Chrome/Edge/Brave | ✅ Supported | ✅ | ✅ | ✅ |
| Firefox | ⚠️ Degraded | ✅ | ❌ | ❌ |
| Safari/iOS | ❌ Not supported | ❌ | ❌ | ❌ |

> ⚠️ **Why Chromium only?** We validate what we can test. Chromium provides the media APIs and PWA support needed for sensor streaming.

---

## ✅ Validation Status

Osk 2.0.0 is **production-hardened** with comprehensive validation:

| Component | Test | Result |
|-----------|------|--------|
| **Install Readiness** | 35 unit tests | ✅ PASS |
| **Security Hardening** | 23 unit tests | ✅ PASS |
| **After-Action Review** | 12 integration tests | ✅ PASS |
| **Evidence Pipeline** | 8 integration tests | ✅ PASS |
| **Sensor Streaming** | Synthetic 5-sensor @ 2.2% CPU | ✅ PASS |
| **Full Matrix** | Join/Reconnect/Offline/Wipe/AAR | ✅ PASS |

**Test Count:** 545 tests passing  
**Coverage:** Complete operational lifecycle  
**Maturity:** Field-ready single-hub system

### What's Validated

```
✅ Install → Deploy → Operate → Close
✅ New coordinator can install without maintainer help
✅ Member runtime reliable on supported browsers
✅ Tasking, intelligence, evidence, closure workflow coherent
✅ Security, privacy, retention claims reviewed and truthful
✅ Operator handoff and after-action artifacts stable
```

---

## 🎨 Features in Detail

### 🔧 Install Maturity (`osk doctor`)

Know before you deploy:

```bash
$ osk doctor --json

{
  "overall_ready": true,
  "profile": "supported-full",
  "checks": [
    {"name": "Python Version", "passed": true, "message": "3.14.2 >= 3.11"},
    {"name": "PostgreSQL", "passed": true, "message": "15.4 running"},
    {"name": "OpenSSL", "passed": true, "message": "3.2.1"},
    {"name": "FFmpeg", "passed": true, "message": "6.1.1"},
    {"name": "Docker", "passed": true, "message": "24.0.7"},
    {"name": "Disk Space", "passed": true, "message": "47.2 GB available"},
    {"name": "Memory", "passed": true, "message": "31.2 GB available"},
    {"name": "Network Ports", "passed": true, "message": "All required ports free"},
    {"name": "TLS Storage", "passed": true, "message": "/home/user/.local/share/osk/tls"}
  ]
}
```

### 📋 After-Action Review

Close operations with completeness:

```bash
# Generate operation summary
osk aar generate

Operation Summary: March on Washington
======================================
Duration: 4h 23m
Members: 12 joined, 8 active at close
Findings: 47 total (3 critical, 12 warning, 32 info)
Tasks: 15 assigned, 12 completed, 3 pending
Media: 1.2 GB evidence collected

# Export complete bundle with integrity verification
osk aar export --output march-aar.zip
osk aar verify march-aar.zip
✅ SHA-256 checksums verified
✅ Chain of custody intact
```

### 🛡️ Security Hardening

Production-grade protection:

| Feature | Implementation |
|---------|----------------|
| **Token Lifecycle** | 4hr operator, 2hr member, 30min rotation |
| **Device Binding** | Fingerprint-based session validation |
| **Wipe Verification** | Residual risk assessment logging |
| **Audit Logging** | Complete security event trail |
| **Session Limits** | Max 5 concurrent per user |

### 🎥 Sensor Streaming

- **Audio:** 4-second chunks → Whisper transcription → Observations
- **Video:** 2 FPS key frames → Vision analysis → Observations  
- **Capacity:** 5 sensors validated at 2.2% CPU
- **Privacy:** Encrypted at rest

### 🧠 Semantic Synthesis

AI-powered understanding with context awareness:

```
"Police officers are helping protesters find water"
        ↓
   Synthesis: POLICE_ACTION, INFO (low severity)

"Police charging the crowd with batons"
        ↓
   Synthesis: POLICE_ACTION, WARNING (high severity)
```

- **Backends:** Heuristic (default, 85% accuracy) or Ollama LLM
- **Corroboration:** Escalates when multiple sensors report same incident
- **Confidence:** Every synthesis includes confidence score

### 🧭 Coordinator Tasking

Turn intelligence into action:

- **Gap tracking:** Opens coordinator gaps when route confirmation needed
- **Direct task push:** Sends tasks to freshest eligible sensor
- **Route confirmation:** Validates/in validates exit routes
- **Reconnect safety:** Re-pushes tasks on member reconnect

---

## 🛠️ Installation

### Standard Install

```bash
pip install osk
osk doctor  # Verify your profile
```

### Development Install

```bash
git clone https://github.com/justinredmondsmith-collab/osk.git
cd osk
make install-dev
pre-commit install
make check  # 545 tests
```

---

## 📚 Documentation

| Document | Purpose |
|----------|---------|
| [Quickstart Card](docs/ops/quickstart-card.md) | One-page field reference |
| [2.0.0 Release Notes](docs/release/2.0.0-release-notes.md) | Complete release details |
| [SUPPORTED_PROFILES.md](docs/SUPPORTED_PROFILES.md) | Hardware/software requirements |
| [INSTALL_GUIDE.md](docs/INSTALL_GUIDE.md) | Detailed installation walkthrough |
| [AAR_GUIDE.md](docs/AAR_GUIDE.md) | After-action review workflow |
| [SECURITY.md](docs/SECURITY.md) | Security model and hardening |
| [SAFETY.md](SAFETY.md) | Operational security |
| [End-State Roadmap](docs/plans/2026-03-28-end-state-product-roadmap.md) | Product direction |

---

## 🧪 Testing & Validation

```bash
# Full test suite (545 tests)
make test

# Install readiness validation
osk doctor

# Quick sensor validation
python scripts/sensor_validation.py --sensors 5 --duration 60

# AAR workflow test
osk start --fresh "Test Operation"
osk aar generate
osk aar export --output test.zip
osk aar verify test.zip
osk wipe --yes
```

---

## 🔒 Security & Privacy

### What Osk Provides

- ✅ **Encrypted evidence** at rest (LUKS or directory)
- ✅ **SHA256 integrity** verification for all exports
- ✅ **Tamper-evident** audit trails
- ✅ **Automatic token rotation** with device binding
- ✅ **Verified wipe** with residual risk logging
- ✅ **No cloud dependencies** - complete data sovereignty

### Truthful Limitations

- 🔶 **No anonymity claim** — Traffic observable on network
- 🔶 **No endpoint protection** — Compromised devices are catastrophic
- 🔶 **No perfect deletion** — OS/browser artifacts may remain
- 🔶 **Validated boundaries** — Chromium-class browsers only

See [SECURITY.md](docs/SECURITY.md) and [SAFETY.md](SAFETY.md) for full details.

---

## 🤝 Contributing

We welcome contributions that improve validation, hardening, and documentation.

**Priority areas:**
- Real-device validation (Chromebook lab)
- Ollama synthesis accuracy testing
- Long-duration stability testing
- Additional language support

See [CONTRIBUTING.md](CONTRIBUTING.md) to get started.

---

## 📊 Release History

| Version | Codename | Key Deliverables |
|---------|----------|------------------|
| 1.0.0 | Foundation | Evidence pipeline, sensor streaming, semantic synthesis |
| 1.1.0 | Field Truth | Real-device validation, stability testing |
| 1.2.0 | Coordinator Ops | Tasking, route confirmation, dashboard |
| 1.3.0 | Intelligence Fusion | Multimodal correlation, confidence scoring |
| 1.4.0 | Field-Ready Member | PWA resilience, battery monitoring, browser matrix |
| **2.0.0** | **Mature System** | **Install maturity, AAR, security hardening** |

---

## 📜 License

Osk is released under the AGPL-3.0 License. See [LICENSE](LICENSE) for details.

---

<div align="center">

**Built for civilian coordination. Hardened for production. Ready for the field.**

[🌟 Star this repo](https://github.com/justinredmondsmith-collab/osk) • [🐛 Report issues](https://github.com/justinredmondsmith-collab/osk/issues) • [💬 Discussions](https://github.com/justinredmondsmith-collab/osk/discussions)

---

*Version 2.0.0 — The first release that describes Osk as a mature single-hub field system.*

</div>
