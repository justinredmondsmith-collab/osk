"""Tests for evidence export with media artifacts."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from uuid import uuid4

import pytest

from osk.evidence import EXPORT_MANIFEST_NAME, EvidenceManager


@pytest.fixture
def evidence_manager(tmp_path: Path):
    """Create an EvidenceManager with directory backend for testing."""
    mount_path = tmp_path / "evidence"
    mount_path.mkdir()

    return EvidenceManager(
        luks_image_path=tmp_path / "evidence.luks",
        luks_mount_path=mount_path,
        backend="directory",
    )


class TestEvidenceExport:
    """Tests for evidence export functionality."""

    def test_export_empty_store_fails(self, evidence_manager: EvidenceManager) -> None:
        """Export should fail when evidence store is empty."""
        result = evidence_manager.export(Path("/tmp/test-export.zip"))

        assert result["ok"] is False
        assert "No visible preserved evidence" in result["error"]

    def test_export_includes_media_files(self, evidence_manager: EvidenceManager) -> None:
        """Export should include audio and frame media files."""
        # Create mock media files
        op_id = str(uuid4())
        member_id = str(uuid4())

        audio_dir = evidence_manager.luks_mount_path / op_id / member_id / "audio"
        audio_dir.mkdir(parents=True)
        audio_file = audio_dir / "20260327_120000_000000.webm"
        audio_file.write_bytes(b"mock audio data")

        frames_dir = evidence_manager.luks_mount_path / op_id / member_id / "frames"
        frames_dir.mkdir(parents=True)
        frame_file = frames_dir / "20260327_120000_000000.jpg"
        frame_file.write_bytes(b"mock frame data")

        # Export
        export_path = evidence_manager.luks_mount_path.parent / "export.zip"
        result = evidence_manager.export(export_path)

        assert result["ok"] is True
        assert result["file_count"] == 2

        # Verify ZIP contents
        with zipfile.ZipFile(export_path, "r") as archive:
            namelist = archive.namelist()
            assert EXPORT_MANIFEST_NAME in namelist
            assert any("audio" in name for name in namelist)
            assert any("frames" in name for name in namelist)

    def test_export_creates_manifest_with_checksums(
        self, evidence_manager: EvidenceManager
    ) -> None:
        """Export manifest should include SHA256 checksums for all files."""
        # Create a test file
        op_id = str(uuid4())
        member_id = str(uuid4())

        audio_dir = evidence_manager.luks_mount_path / op_id / member_id / "audio"
        audio_dir.mkdir(parents=True)
        audio_file = audio_dir / "test.webm"
        audio_content = b"test audio content"
        audio_file.write_bytes(audio_content)

        # Export
        export_path = evidence_manager.luks_mount_path.parent / "export.zip"
        result = evidence_manager.export(export_path)

        assert result["ok"] is True

        # Read manifest from ZIP
        with zipfile.ZipFile(export_path, "r") as archive:
            manifest = json.loads(archive.read(EXPORT_MANIFEST_NAME))

        assert "items" in manifest
        assert len(manifest["items"]) == 1

        item = manifest["items"][0]
        assert "sha256" in item
        assert len(item["sha256"]) == 64  # SHA256 hex length
        assert item["size_bytes"] == len(audio_content)

    def test_verify_export_bundle_with_media(self, evidence_manager: EvidenceManager) -> None:
        """Verify should work with media files in export bundle."""
        # Create media files
        op_id = str(uuid4())
        member_id = str(uuid4())

        audio_dir = evidence_manager.luks_mount_path / op_id / member_id / "audio"
        audio_dir.mkdir(parents=True)
        (audio_dir / "test.webm").write_bytes(b"audio data")

        frames_dir = evidence_manager.luks_mount_path / op_id / member_id / "frames"
        frames_dir.mkdir(parents=True)
        (frames_dir / "test.jpg").write_bytes(b"frame data")

        # Export
        export_path = evidence_manager.luks_mount_path.parent / "export.zip"
        evidence_manager.export(export_path)

        # Verify
        result = EvidenceManager.verify_export_bundle(export_path)

        assert result["ok"] is True
        assert result["file_count"] == 2
        assert result["embedded_manifest_status"] == "verified"
        assert result["manifest_status"] == "verified"
        assert result["checksum_status"] == "verified"

    def test_verify_detects_tampered_media(self, evidence_manager: EvidenceManager) -> None:
        """Verify should detect tampered media files."""
        # Create and export
        op_id = str(uuid4())
        member_id = str(uuid4())

        audio_dir = evidence_manager.luks_mount_path / op_id / member_id / "audio"
        audio_dir.mkdir(parents=True)
        (audio_dir / "test.webm").write_bytes(b"original audio")

        export_path = evidence_manager.luks_mount_path.parent / "export.zip"
        evidence_manager.export(export_path)

        # Tamper with the archive
        tampered_path = evidence_manager.luks_mount_path.parent / "tampered.zip"
        with zipfile.ZipFile(export_path, "r") as src:
            with zipfile.ZipFile(tampered_path, "w") as dst:
                for item in src.namelist():
                    if item == EXPORT_MANIFEST_NAME:
                        dst.writestr(item, src.read(item))
                    else:
                        # Tamper with media file
                        dst.writestr(item, b"tampered content")

        # Verify should fail
        result = EvidenceManager.verify_export_bundle(tampered_path)

        assert result["ok"] is False
        # Verification catches tampering via size or hash mismatch
        assert "mismatch" in result["error"]

    def test_export_creates_sidecar_files(self, evidence_manager: EvidenceManager) -> None:
        """Export should create .manifest.json and .sha256 sidecar files."""
        # Create a test file
        op_id = str(uuid4())
        member_id = str(uuid4())

        audio_dir = evidence_manager.luks_mount_path / op_id / member_id / "audio"
        audio_dir.mkdir(parents=True)
        (audio_dir / "test.webm").write_bytes(b"test content")

        # Export
        export_path = evidence_manager.luks_mount_path.parent / "export.zip"
        result = evidence_manager.export(export_path)

        assert result["ok"] is True

        manifest_path = Path(result["manifest_path"])
        checksum_path = Path(result["checksum_path"])

        assert manifest_path.exists()
        assert checksum_path.exists()

        # Verify sidecar manifest content
        sidecar = json.loads(manifest_path.read_text())
        assert sidecar["archive_sha256"] == result["archive_sha256"]
        assert sidecar["file_count"] == 1

    def test_list_items_includes_media_paths(self, evidence_manager: EvidenceManager) -> None:
        """list_items should include paths to media files."""
        # Create nested media structure
        op_id = str(uuid4())
        member_id = str(uuid4())

        audio_dir = evidence_manager.luks_mount_path / op_id / member_id / "audio"
        audio_dir.mkdir(parents=True)
        (audio_dir / "test.webm").write_bytes(b"audio")

        frames_dir = evidence_manager.luks_mount_path / op_id / member_id / "frames"
        frames_dir.mkdir(parents=True)
        (frames_dir / "test.jpg").write_bytes(b"frame")

        items = evidence_manager.list_items()

        assert len(items) == 2
        paths = [str(item["path"]) for item in items]
        assert any("audio" in p for p in paths)
        assert any("frames" in p for p in paths)


class TestEvidenceWithStorageIntegration:
    """Integration tests with StorageManager."""

    def test_write_artifact_and_export(self, tmp_path: Path) -> None:
        """Test writing artifacts through StorageManager and exporting."""
        from osk.storage import StorageManager

        storage = StorageManager(
            tmpfs_path=tmp_path / "tmpfs",
            luks_image_path=tmp_path / "evidence.luks",
            luks_mount_path=tmp_path / "evidence",
            backend="directory",
        )
        storage.create_luks_volume("")
        storage.open_luks("")

        op_id = str(uuid4())
        member_id = str(uuid4())

        # Write audio artifact
        audio_path = storage.write_evidence_artifact(
            operation_id=op_id,
            member_id=member_id,
            artifact_type="audio",
            data=b"test audio data",
            extension="webm",
        )
        assert audio_path is not None
        assert audio_path.exists()

        # Write frame artifact
        frame_path = storage.write_evidence_artifact(
            operation_id=op_id,
            member_id=member_id,
            artifact_type="frames",
            data=b"test frame data",
            extension="jpg",
        )
        assert frame_path is not None
        assert frame_path.exists()

        # Export via EvidenceManager
        manager = EvidenceManager.from_storage(storage)
        export_path = tmp_path / "export.zip"
        result = manager.export(export_path)

        assert result["ok"] is True
        assert result["file_count"] == 2

        # Verify archive
        verify_result = EvidenceManager.verify_export_bundle(export_path)
        assert verify_result["ok"] is True
