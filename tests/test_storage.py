"""Tests for ephemeral storage and LUKS management."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from osk.storage import StorageManager


@pytest.fixture
def storage(tmp_path: Path) -> StorageManager:
    return StorageManager(
        tmpfs_path=tmp_path / "tmpfs",
        luks_image_path=tmp_path / "osk.luks",
        luks_mount_path=tmp_path / "evidence",
        luks_size_gb=1,
    )


def test_storage_init(storage: StorageManager) -> None:
    assert storage.tmpfs_path is not None
    assert storage.luks_image_path is not None


@patch("osk.storage.subprocess")
def test_create_luks_volume(mock_subprocess: MagicMock, storage: StorageManager) -> None:
    mock_subprocess.run.return_value = MagicMock(returncode=0)
    storage.create_luks_volume("test-passphrase")
    assert mock_subprocess.run.call_count >= 3


@patch("osk.storage.subprocess")
def test_mount_tmpfs(mock_subprocess: MagicMock, storage: StorageManager) -> None:
    mock_subprocess.run.return_value = MagicMock(returncode=0)
    storage.mount_tmpfs()
    cmd = mock_subprocess.run.call_args[0][0]
    assert "mount" in cmd
    assert "tmpfs" in cmd


@patch("osk.storage.subprocess")
def test_unmount_tmpfs(mock_subprocess: MagicMock, storage: StorageManager) -> None:
    mock_subprocess.run.return_value = MagicMock(returncode=0)
    storage.unmount_tmpfs()
    cmd = mock_subprocess.run.call_args[0][0]
    assert "umount" in cmd


@patch("osk.storage.subprocess")
def test_open_luks(mock_subprocess: MagicMock, storage: StorageManager) -> None:
    mock_subprocess.run.return_value = MagicMock(returncode=0)
    storage.open_luks("test-passphrase")
    assert mock_subprocess.run.call_count >= 2


@patch("osk.storage.subprocess")
def test_close_luks(mock_subprocess: MagicMock, storage: StorageManager) -> None:
    mock_subprocess.run.return_value = MagicMock(returncode=0)
    storage.close_luks()
    cmd = mock_subprocess.run.call_args_list[-1][0][0]
    assert "cryptsetup" in cmd


@patch("osk.storage.subprocess")
def test_emergency_wipe(mock_subprocess: MagicMock, storage: StorageManager) -> None:
    mock_subprocess.run.return_value = MagicMock(returncode=0)
    storage.emergency_wipe()
    assert mock_subprocess.run.call_count >= 2


@patch("osk.storage.subprocess")
def test_store_passphrase_in_keyring(mock_subprocess: MagicMock, storage: StorageManager) -> None:
    mock_subprocess.run.return_value = MagicMock(returncode=0, stdout="12345\n")
    storage.store_passphrase_in_keyring("test-passphrase")
    assert storage._keyring_id == "12345"


@patch("osk.storage.subprocess")
def test_revoke_keyring(mock_subprocess: MagicMock, storage: StorageManager) -> None:
    mock_subprocess.run.return_value = MagicMock(returncode=0)
    storage._keyring_id = "12345"
    storage.revoke_keyring()
    cmd = mock_subprocess.run.call_args[0][0]
    assert "keyctl" in cmd
    assert "revoke" in cmd
