# Plan 6: Operations Tooling

> **For agentic workers:** Start from `AGENTS.md` and `docs/WORKFLOW.md`. Treat checklist items as decomposable tasks, keep changes narrow, and verify each step before moving on.

**Goal:** Build the operational tools that make Osk field-ready — WiFi hotspot management, offline map tile caching, post-operation evidence viewer/exporter, sudoers configuration, and the install flow.

**Architecture:** Host-side Python modules that wrap system commands (nmcli, cryptsetup, keyctl). These run outside the Docker stack on the coordinator's Linux laptop. The CLI commands (`osk install`, `osk tiles cache`, `osk evidence`) invoke these modules.

**Current state:** The repo already has pieces of the operational boundary:
`osk install`, evidence-volume creation/open/close paths in `src/osk/storage.py`,
runtime preflight checks in `osk doctor`, a dashboard tile-consumption path
that reads cached local PNG tiles from `map_tile_cache_path`, the first
tile-cache CLI slice via `osk tiles status` and `osk tiles cache`, a
standalone `osk hotspot status|up|down|instructions` slice for
NetworkManager-based field setup, and a standalone
`osk evidence unlock|export|destroy` slice for preserved-evidence access. The
repo now also has conservative hotspot-aware guidance in `osk doctor` and
`osk start`, so field-network and `join_host` mismatches are surfaced without
automatically changing host networking. The missing work in this phase is
deeper hub orchestration, validated wipe/install operations, and field
validation. The repo now also has read-only `osk drill install|wipe` reports
to make the current install and wipe boundaries explicit, plus an explicit
coordinator-side `osk wipe` flow that broadcasts wipe and stops the hub
without destroying preserved evidence unless the operator opts in. Connected
member browsers now also clear queued browser state and unregister the cached
member shell on live wipe, but disconnected browsers and preserved evidence
destruction remain separate cleanup concerns. The repo now also exposes live
wipe-readiness summaries in `osk status --json`, human `osk members`, and the
coordinator dashboard so those cleanup gaps are visible before an operator
triggers `osk wipe`.

**Tech Stack:** Python, nmcli, cryptsetup, keyctl, zipfile, subprocess

**Spec:** `docs/specs/2026-03-21-osk-design.md` — "Coordinator Startup", "Operation Lifecycle", "Offline Map Tiles" sections
**Depends on:** Plan 1 (cli, storage, config)

---

## File Map

| File | Responsibility |
|---|---|
| `src/osk/hotspot.py` | WiFi hotspot management via nmcli |
| `src/osk/evidence.py` | Post-operation evidence viewer, exporter, destroyer |
| `src/osk/drills.py` | Read-only install and wipe drill reports |
| `src/osk/tiles.py` | Offline map tile download and caching |
| `scripts/setup-sudoers.sh` | Configure sudoers.d for cryptsetup/mount commands |
| Modify: `src/osk/cli.py` | Wire new commands (tiles, evidence subcommands) |
| `docs/runbooks/operations-drills.md` | Current install/wipe operator runbook |
| Modify: `src/osk/hub.py` | Surface hotspot/startup guidance and later runtime orchestration |
| `tests/test_hotspot.py` | Hotspot management tests (mocked nmcli) |
| `tests/test_evidence.py` | Evidence export/destroy tests |
| `tests/test_tiles.py` | Tile caching tests (mocked HTTP) |

---

### Task 1: WiFi Hotspot Management

**Files:**
- Create: `src/osk/hotspot.py`
- Create: `tests/test_hotspot.py`

- [ ] **Step 1: Write failing tests**

Test that the hotspot manager:
- Checks if NetworkManager is available
- Creates a WiFi hotspot with configurable SSID and band
- Returns the hotspot IP address
- Stops the hotspot cleanly
- Falls back to printing manual instructions if nmcli is not available

All subprocess calls mocked.

```python
# tests/test_hotspot.py
from __future__ import annotations
from unittest.mock import MagicMock, patch
import pytest
from osk.hotspot import HotspotManager

@pytest.fixture
def hotspot():
    return HotspotManager(ssid="osk-test", band="5GHz", password="osk-secure")

@patch("osk.hotspot.subprocess")
def test_check_nmcli_available(mock_sub, hotspot):
    mock_sub.run.return_value = MagicMock(returncode=0)
    assert hotspot.is_available() is True

@patch("osk.hotspot.subprocess")
def test_check_nmcli_unavailable(mock_sub, hotspot):
    mock_sub.run.side_effect = FileNotFoundError
    assert hotspot.is_available() is False

@patch("osk.hotspot.subprocess")
def test_start_hotspot(mock_sub, hotspot):
    mock_sub.run.return_value = MagicMock(returncode=0, stdout="Connection 'osk-test' activated\n")
    result = hotspot.start()
    assert result is True
    assert mock_sub.run.call_count >= 1

@patch("osk.hotspot.subprocess")
def test_stop_hotspot(mock_sub, hotspot):
    mock_sub.run.return_value = MagicMock(returncode=0)
    hotspot.stop()
    mock_sub.run.assert_called()

@patch("osk.hotspot.subprocess")
def test_get_ip(mock_sub, hotspot):
    mock_sub.run.return_value = MagicMock(
        returncode=0, stdout="IP4.ADDRESS[1]: 10.42.0.1/24\n"
    )
    ip = hotspot.get_ip()
    assert ip == "10.42.0.1"

def test_manual_instructions(hotspot):
    instructions = hotspot.get_manual_instructions()
    assert "nmcli" in instructions or "hotspot" in instructions.lower()
```

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement HotspotManager**

```python
# src/osk/hotspot.py
"""WiFi hotspot management via NetworkManager/nmcli."""
from __future__ import annotations
import logging
import re
import subprocess

logger = logging.getLogger(__name__)

class HotspotManager:
    def __init__(self, ssid: str, band: str = "5GHz", password: str = "") -> None:
        self.ssid = ssid
        self.band = band
        self.password = password
        self._connection_name = ssid

    def is_available(self) -> bool:
        try:
            result = subprocess.run(["nmcli", "--version"], capture_output=True, check=True)
            return result.returncode == 0
        except (FileNotFoundError, subprocess.CalledProcessError):
            return False

    def start(self) -> bool:
        cmd = [
            "nmcli", "device", "wifi", "hotspot",
            "ssid", self.ssid,
            "band", "a" if "5" in self.band else "bg",
        ]
        if self.password:
            cmd.extend(["password", self.password])
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            logger.info("Hotspot started: %s", self.ssid)
            return True
        logger.warning("Hotspot failed: %s", result.stderr)
        return False

    def stop(self) -> None:
        subprocess.run(
            ["nmcli", "connection", "down", self._connection_name],
            capture_output=True, check=False,
        )
        logger.info("Hotspot stopped")

    def get_ip(self) -> str | None:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "IP4.ADDRESS", "connection", "show", self._connection_name],
            capture_output=True, text=True, check=False,
        )
        match = re.search(r"(\d+\.\d+\.\d+\.\d+)", result.stdout)
        return match.group(1) if match else None

    def get_manual_instructions(self) -> str:
        return (
            "NetworkManager (nmcli) is not available.\n"
            "To create a WiFi hotspot manually:\n"
            f"  1. Create a hotspot with SSID: {self.ssid}\n"
            f"  2. Use WPA3 or WPA2 security\n"
            "  3. Note the IP address assigned to your WiFi interface\n"
            "  4. Run: osk start --host <your-ip>"
        )
```

- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit**

```bash
git add src/osk/hotspot.py tests/test_hotspot.py
git commit -m "feat: WiFi hotspot management via nmcli with fallback instructions"
```

---

### Task 2: Evidence Manager

**Files:**
- Create: `src/osk/evidence.py`
- Create: `tests/test_evidence.py`

- [ ] **Step 1: Write failing tests**

Test that the evidence manager:
- `unlock()`: opens LUKS volume read-only, lists pinned items
- `export()`: creates a zip file of all pinned events + source data
- `destroy()`: shreds the LUKS volume file permanently
- Handles missing LUKS volume gracefully (prints error, doesn't crash)

```python
# tests/test_evidence.py
from __future__ import annotations
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from osk.evidence import EvidenceManager

@pytest.fixture
def evidence(tmp_path):
    return EvidenceManager(
        luks_image_path=tmp_path / "evidence.luks",
        luks_mount_path=tmp_path / "evidence",
    )

def test_unlock_missing_volume(evidence):
    result = evidence.unlock("passphrase")
    assert result is False  # volume doesn't exist

@patch("osk.evidence.subprocess")
def test_unlock_existing_volume(mock_sub, evidence):
    evidence.luks_image_path.touch()  # create fake volume
    mock_sub.run.return_value = MagicMock(returncode=0)
    result = evidence.unlock("passphrase")
    assert result is True

@patch("osk.evidence.subprocess")
def test_export_creates_zip(mock_sub, evidence, tmp_path):
    mock_sub.run.return_value = MagicMock(returncode=0)
    # Create fake pinned files
    evidence.luks_mount_path.mkdir(parents=True, exist_ok=True)
    (evidence.luks_mount_path / "event_001.json").write_text('{"text": "test"}')
    output = tmp_path / "export.zip"
    evidence.export(output)
    assert output.exists()

@patch("osk.evidence.subprocess")
def test_destroy_removes_volume(mock_sub, evidence):
    evidence.luks_image_path.touch()
    mock_sub.run.return_value = MagicMock(returncode=0)
    evidence.destroy()
    # Should call shred or rm on the volume file
    assert mock_sub.run.called
```

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement EvidenceManager**

Handles `unlock` (cryptsetup open + mount read-only), `export` (walk mount dir, create zip), `destroy` (shred LUKS image file, confirm before proceeding). Uses subprocess for cryptsetup, zipfile stdlib for export.

- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit**

```bash
git add src/osk/evidence.py tests/test_evidence.py
git commit -m "feat: evidence manager — unlock, export, destroy pinned evidence"
```

---

### Task 3: Offline Map Tile Caching

**Files:**
- Create: `src/osk/tiles.py`
- Create: `tests/test_tiles.py`

- [ ] **Step 1: Write failing tests**

Test that the tile cacher:
- Parses bounding box from CLI args
- Calculates tile coordinates for a given bounding box + zoom range
- Downloads tiles from OSM (mocked HTTP)
- Saves tiles in `{z}/{x}/{y}.png` directory structure
- Reports progress (tiles downloaded / total)
- Skips already-cached tiles

```python
# tests/test_tiles.py
from __future__ import annotations
from pathlib import Path
from unittest.mock import AsyncMock, patch
import pytest
from osk.tiles import TileCacher, parse_bbox, bbox_to_tiles

def test_parse_bbox():
    south, west, north, east = parse_bbox("39.7,-104.9,39.8,-104.8")
    assert south == 39.7
    assert east == -104.8

def test_bbox_to_tiles():
    tiles = bbox_to_tiles(39.7, -104.9, 39.8, -104.8, zoom=15)
    assert len(tiles) > 0
    assert all(isinstance(t, tuple) and len(t) == 3 for t in tiles)  # (z, x, y)

def test_skip_cached_tiles(tmp_path):
    cacher = TileCacher(cache_dir=tmp_path)
    # Pre-create a tile
    tile_dir = tmp_path / "15" / "6827"
    tile_dir.mkdir(parents=True)
    (tile_dir / "12345.png").write_bytes(b"\x89PNG")
    assert cacher.is_cached(15, 6827, 12345)

async def test_download_tile(tmp_path):
    cacher = TileCacher(cache_dir=tmp_path)
    with patch("osk.tiles.httpx.AsyncClient") as MockClient:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.content = b"\x89PNG fake tile"
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
        await cacher.download_tile(mock_client, 15, 6827, 12345)
        assert (tmp_path / "15" / "6827" / "12345.png").exists()
```

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement TileCacher**

Utility functions: `parse_bbox(s)` → (south, west, north, east), `bbox_to_tiles(s, w, n, e, zoom)` → list of (z, x, y) tuples using the standard OSM slippy map tile calculation. `TileCacher` class: `is_cached(z, x, y)`, `async download_tile(client, z, x, y)`, `async cache_area(bbox, zoom_range)`. Downloads from `https://tile.openstreetmap.org/{z}/{x}/{y}.png` with proper User-Agent header. Progress reporting via callback.

- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit**

```bash
git add src/osk/tiles.py tests/test_tiles.py
git commit -m "feat: offline map tile caching from OpenStreetMap"
```

---

### Task 4: Sudoers Configuration Script

**Files:**
- Create: `scripts/setup-sudoers.sh`

- [ ] **Step 1: Create sudoers script**

```bash
#!/usr/bin/env bash
# scripts/setup-sudoers.sh
# Configures passwordless sudo for specific Osk commands.
# Run as root: sudo bash scripts/setup-sudoers.sh <username>

set -euo pipefail

USERNAME="${1:?Usage: setup-sudoers.sh <username>}"

cat > /etc/sudoers.d/osk << EOF
# Osk: allow $USERNAME to manage tmpfs and LUKS without password
$USERNAME ALL=(root) NOPASSWD: /usr/bin/mount -t tmpfs *
$USERNAME ALL=(root) NOPASSWD: /usr/bin/umount /tmp/osk-*
$USERNAME ALL=(root) NOPASSWD: /usr/sbin/cryptsetup open *
$USERNAME ALL=(root) NOPASSWD: /usr/sbin/cryptsetup close osk-evidence
$USERNAME ALL=(root) NOPASSWD: /usr/sbin/cryptsetup luksFormat *
$USERNAME ALL=(root) NOPASSWD: /sbin/mkfs.ext4 /dev/mapper/osk-evidence
EOF

chmod 0440 /etc/sudoers.d/osk
echo "Sudoers configured for user: $USERNAME"
```

- [ ] **Step 2: Commit**

```bash
chmod +x scripts/setup-sudoers.sh
git add scripts/setup-sudoers.sh
git commit -m "feat: sudoers configuration script for Osk privileged operations"
```

---

### Task 5: Wire Operations into CLI + Hub

**Files:**
- Modify: `src/osk/cli.py` — add `osk tiles cache` command
- Modify: `src/osk/hub.py` — wire hotspot into startup, evidence into shutdown

- [ ] **Step 1: Add tiles command to CLI**

```python
# Add to cli.py parse_args:
tiles_p = sub.add_parser("tiles", help="Manage offline map tiles")
tiles_sub = tiles_p.add_subparsers(dest="tiles_command")
cache_p = tiles_sub.add_parser("cache", help="Cache tiles for an area")
cache_p.add_argument("--area", required=True, help="Bounding box: south,west,north,east")
cache_p.add_argument("--zoom", default="13-17", help="Zoom range (default: 13-17)")
```

- [ ] **Step 2: Wire hotspot awareness into hub.py startup**

In `run_hub()`, after storage setup:
- Create HotspotManager with config SSID and band
- Surface hotspot availability, current hotspot IP, and `join_host` guidance in
  the startup banner
- Do not silently start or stop host networking by default
- If future automatic hotspot startup is added, make it explicit and opt-in

- [ ] **Step 3: Wire evidence commands in CLI**

In the `evidence` handler, instantiate EvidenceManager and call `unlock()`, `export()`, or `destroy()` based on the subcommand.

- [ ] **Step 4: Test CLI parses new commands**
- [ ] **Step 5: Commit**

```bash
git add src/osk/cli.py src/osk/hub.py tests/test_cli.py
git commit -m "feat: wire hotspot, tiles, and evidence commands into CLI and hub"
```

---

### Task 6: Complete Install Flow

**Files:**
- Modify: `src/osk/hub.py` — finalize `install()` function

- [ ] **Step 1: Finalize install()**

The install function should:
1. Generate TLS cert (already done)
2. Create LUKS volume (already done)
3. Pull Docker images
4. Pull Ollama models (via `docker compose run ollama-init`)
5. Run sudoers setup script (with confirmation prompt)
6. Validate GPU availability (`nvidia-smi`)
7. Print summary of what's ready

- [ ] **Step 2: Test install with mocked subprocess**
- [ ] **Step 3: Commit**

```bash
git add src/osk/hub.py tests/
git commit -m "feat: complete install flow with GPU validation and model download"
```

---

### Current Operations Gap

The repo now has read-only install and wipe drills:

- `osk drill install`
- `osk drill wipe`

Those commands are intentionally conservative. They make the current install and
wipe boundaries explicit, including partial wipe behavior and separate preserved
evidence destruction. Keep them truthful until a single integrated wipe path is
actually validated.

---

### Task 7: Final Integration Test + Push

- [ ] **Step 1: Run all tests**

Run: `pytest tests/ -v --tb=short`
Expected: all PASS

- [ ] **Step 2: Lint and format**

Run: `ruff check src/ tests/ --fix && ruff format src/ tests/`

- [ ] **Step 3: Final commit and push**

```bash
git add -A
git commit -m "Osk v0.1.0: all 6 implementation plans complete"
git push origin main
```
