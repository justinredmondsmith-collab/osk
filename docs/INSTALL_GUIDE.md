# Osk Installation Guide

**Version:** 2.0.0  
**Date:** 2026-03-28  
**Estimated Time:** 15-30 minutes

---

## Quick Start

```bash
# 1. Verify system requirements
python3 --version  # Need 3.11+

# 2. Install Osk
pip install osk

# 3. Verify installation
osk doctor

# 4. Start your first operation
osk start --fresh "My First Operation"
osk dashboard
```

---

## System Requirements

### Coordinator Machine

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| OS | Linux (Fedora 41, Ubuntu 22.04, Debian 12) | Latest stable |
| Python | 3.11 | 3.13+ |
| RAM | 4 GB | 8 GB |
| Storage | 10 GB free | 50 GB+ |
| Network | WiFi or Ethernet | Gigabit Ethernet |

### Dependencies by Profile

#### Full Deployment (`supported-full`)

```bash
# Fedora
sudo dnf install postgresql-server openssl ffmpeg python3.13

# Ubuntu/Debian
sudo apt install postgresql openssl ffmpeg python3.11
```

#### Docker Deployment (`docker-managed`)

```bash
# Fedora
sudo dnf install docker
sudo systemctl enable --now docker

# Ubuntu/Debian
sudo apt install docker.io
sudo systemctl enable --now docker
```

#### Minimal Deployment (`supported-minimal`)

```bash
# Just Python and OpenSSL
sudo dnf install python3.13 openssl  # Fedora
sudo apt install python3.11 openssl   # Ubuntu/Debian
```

---

## Step-by-Step Installation

### Step 1: System Preparation (5 minutes)

```bash
# Update your system
sudo dnf update  # Fedora
sudo apt update && sudo apt upgrade  # Ubuntu/Debian

# Check Python version
python3 --version
# Should show 3.11 or higher

# If Python is older, install newer version
sudo dnf install python3.13 python3.13-pip  # Fedora
sudo apt install python3.11 python3.11-venv  # Ubuntu/Debian
```

### Step 2: Install Dependencies (5-10 minutes)

**Option A: Full Deployment**

```bash
# Install PostgreSQL
sudo dnf install postgresql-server postgresql-contrib
sudo postgresql-setup --initdb
sudo systemctl enable --now postgresql

# Create database user
sudo -u postgres createuser -s $USER
sudo -u postgres createdb osk

# Install FFmpeg
sudo dnf install ffmpeg ffmpeg-devel

# Install OpenSSL (usually present)
openssl version
```

**Option B: Docker Deployment**

```bash
# Install Docker
sudo dnf install docker docker-compose
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
# Log out and back in for group changes
```

**Option C: Minimal Deployment**

```bash
# Just ensure Python and OpenSSL are present
python3 --version
openssl version
# That's it!
```

### Step 3: Install Osk (2 minutes)

```bash
# Create virtual environment (recommended)
python3 -m venv ~/.venv/osk
source ~/.venv/osk/bin/activate

# Install Osk
pip install osk

# Verify installation
osk --version
# Should show 2.0.0
```

### Step 4: Verify Installation (2 minutes)

```bash
# Run comprehensive readiness check
osk doctor

# Expected output for supported-full:
# ✅ Python 3.14.2
# ✅ PostgreSQL 15.4
# ✅ OpenSSL 3.2.1
# ✅ FFmpeg 6.1.1
# ✅ Docker 24.0.7
# ✅ Disk space: 47.2 GB available
# ✅ Memory: 31.2 GB available
# ✅ Network ports: All required ports free
# ✅ TLS storage: /home/user/.local/share/osk/tls
# Profile: supported-full

# If any checks fail, follow the remediation guidance provided
```

### Step 5: Initial Configuration (3 minutes)

```bash
# Create config directory
mkdir -p ~/.config/osk

# Create initial config
cat > ~/.config/osk/config.toml << 'EOF'
[hub]
host = "0.0.0.0"
port = 8080

[storage]
backend = "postgresql"  # or "sqlite" for minimal
url = "postgresql://localhost/osk"

[security]
operator_session_hours = 4
member_session_hours = 2

[synthesis]
backend = "heuristic"  # or "ollama" if available

[evidence]
storage_path = "/var/lib/osk/evidence"
EOF
```

### Step 6: Test Operation (5 minutes)

```bash
# Start a test operation
osk start --fresh "Installation Test"

# Check status
osk status

# Get dashboard URL
osk dashboard
# Open the URL in your browser

# Wipe the test operation
osk drill wipe
osk wipe --yes
```

---

## Troubleshooting

### Common Issues

#### "Python version too old"

```bash
# Install Python 3.11+
sudo dnf install python3.13 python3.13-pip  # Fedora
sudo apt install python3.11 python3.11-venv  # Ubuntu/Debian

# Use specific Python version
python3.13 -m pip install osk
```

#### "PostgreSQL not running"

```bash
# Start PostgreSQL
sudo systemctl start postgresql

# Check status
sudo systemctl status postgresql

# Initialize if needed
sudo postgresql-setup --initdb  # Fedora
```

#### "Port already in use"

```bash
# Check what's using port 8080
sudo lsof -i :8080

# Kill the process or change Osk port
# Edit ~/.config/osk/config.toml:
# [hub]
# port = 8081
```

#### "Permission denied for evidence storage"

```bash
# Create evidence directory with proper permissions
sudo mkdir -p /var/lib/osk/evidence
sudo chown -R $USER:$USER /var/lib/osk
chmod 750 /var/lib/osk/evidence
```

### Getting Help

If `osk doctor` shows failures:

1. Read the specific error message
2. Check the remediation guidance provided
3. Consult `docs/SUPPORTED_PROFILES.md` for profile-specific requirements
4. Open an issue at https://github.com/justinredmondsmith-collab/osk/issues

---

## Post-Installation

### Verify Full Functionality

```bash
# 1. Start operation
osk start --fresh "Validation Test"

# 2. In another terminal, simulate a member join
# (Use the join URL from `osk dashboard`)

# 3. Test AAR workflow
osk aar generate
osk aar export --output test-aar.zip
osk aar verify test-aar.zip

# 4. Clean up
osk wipe --yes
```

### Update Osk

```bash
# Activate virtual environment
source ~/.venv/osk/bin/activate

# Update to latest version
pip install --upgrade osk

# Verify update
osk --version
osk doctor
```

### Uninstall Osk

```bash
# Deactivate virtual environment
deactivate

# Remove virtual environment
rm -rf ~/.venv/osk

# Remove config and data (optional)
rm -rf ~/.config/osk
rm -rf ~/.local/share/osk
```

---

## Profile-Specific Guides

### Full Deployment (`supported-full`)

Best for: Production operations with complete feature set

See `docs/SUPPORTED_PROFILES.md` for detailed requirements.

### Docker Deployment (`docker-managed`)

Best for: Simplified deployment with container isolation

```bash
# Using Docker Compose
docker-compose up -d

# Or using Osk's built-in Docker support
osk deploy --profile docker-managed
```

### Minimal Deployment (`supported-minimal`)

Best for: Testing, development, or limited hardware

```bash
# Use SQLite instead of PostgreSQL
# Edit ~/.config/osk/config.toml:
[storage]
backend = "sqlite"
path = "~/.local/share/osk/osk.db"
```

---

## Next Steps

1. **Read the Quickstart Card:** `docs/ops/quickstart-card.md`
2. **Review Safety Information:** `SAFETY.md`
3. **Run Validation:** `python scripts/sensor_validation.py --sensors 5 --duration 60`
4. **Plan Your First Operation:** See field deployment guide

---

**Need Help?** 
- GitHub Issues: https://github.com/justinredmondsmith-collab/osk/issues
- Documentation: `docs/` directory
- Validation Reports: `docs/release/`
