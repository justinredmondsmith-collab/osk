from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from osk.evidence import EvidenceManager


@pytest.fixture
def evidence(tmp_path: Path) -> EvidenceManager:
    return EvidenceManager(
        luks_image_path=tmp_path / "evidence.luks",
        luks_mount_path=tmp_path / "evidence",
    )


def test_unlock_missing_volume(evidence: EvidenceManager) -> None:
    result = evidence.unlock("passphrase")
    assert result["ok"] is False
    assert "Evidence volume not found" in str(result["error"])


@patch("osk.evidence.subprocess.run")
def test_unlock_existing_volume(mock_run: MagicMock, evidence: EvidenceManager) -> None:
    evidence.luks_image_path.touch()
    evidence.luks_mount_path.mkdir(parents=True, exist_ok=True)
    (evidence.luks_mount_path / "event_001.json").write_text('{"text":"test"}')
    mock_run.return_value = MagicMock(returncode=0)

    result = evidence.unlock("passphrase")

    assert result["ok"] is True
    assert result["item_count"] == 1
    assert mock_run.call_count == 2


def test_export_creates_zip(evidence: EvidenceManager, tmp_path: Path) -> None:
    evidence.luks_mount_path.mkdir(parents=True, exist_ok=True)
    (evidence.luks_mount_path / "event_001.json").write_text('{"text":"test"}')
    (evidence.luks_mount_path / "frames").mkdir()
    (evidence.luks_mount_path / "frames" / "frame_001.jpg").write_bytes(b"jpeg")
    output = tmp_path / "export.zip"

    result = evidence.export(output)

    assert result["ok"] is True
    assert output.exists()
    manifest_path = tmp_path / "export.zip.manifest.json"
    checksum_path = tmp_path / "export.zip.sha256"
    assert manifest_path.exists()
    assert checksum_path.exists()

    with zipfile.ZipFile(output) as archive:
        assert sorted(archive.namelist()) == [
            "_osk_export_manifest.json",
            "event_001.json",
            "frames/frame_001.jpg",
        ]
        export_manifest = json.loads(archive.read("_osk_export_manifest.json"))

    manifest_paths = [item["path"] for item in export_manifest["items"]]
    assert manifest_paths == ["event_001.json", "frames/frame_001.jpg"]
    assert export_manifest["file_count"] == 2
    assert export_manifest["total_bytes"] == 19

    sidecar_manifest = json.loads(manifest_path.read_text())
    assert sidecar_manifest["output_path"] == str(output)
    assert sidecar_manifest["manifest_entry"] == "_osk_export_manifest.json"
    assert sidecar_manifest["archive_sha256"] == result["archive_sha256"]

    archive_sha256 = hashlib.sha256(output.read_bytes()).hexdigest()
    assert archive_sha256 == result["archive_sha256"]
    assert checksum_path.read_text() == f"{archive_sha256}  export.zip\n"


@patch("os.path.expanduser", side_effect=lambda path: path)
@patch("os.getcwd", return_value="/tmp")
@patch("builtins.input", return_value="yes")
def test_destroy_directory_backend(
    _mock_input: MagicMock,
    _mock_getcwd: MagicMock,
    _mock_expanduser: MagicMock,
    tmp_path: Path,
) -> None:
    manager = EvidenceManager(
        luks_image_path=tmp_path / "unused.luks",
        luks_mount_path=tmp_path / "evidence",
        backend="directory",
    )
    manager.luks_mount_path.mkdir(parents=True, exist_ok=True)
    (manager.luks_mount_path / "event_001.json").write_text("{}")

    result = manager.destroy()

    assert result["ok"] is True
    assert not manager.luks_mount_path.exists()


@patch("osk.evidence.subprocess.run")
def test_destroy_removes_luks_volume(mock_run: MagicMock, evidence: EvidenceManager) -> None:
    evidence.luks_image_path.touch()
    mock_run.return_value = MagicMock(returncode=0)

    result = evidence.destroy()

    assert result["ok"] is True
    assert mock_run.call_count == 3
