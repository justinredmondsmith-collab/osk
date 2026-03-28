"""Ephemeral storage and preserved evidence management."""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

LUKS_MAPPER_NAME = "osk-evidence"


class StorageManager:
    def __init__(
        self,
        tmpfs_path: Path,
        luks_image_path: Path,
        luks_mount_path: Path,
        luks_size_gb: int = 1,
        backend: Literal["luks", "directory"] = "luks",
    ) -> None:
        self.tmpfs_path = tmpfs_path
        self.luks_image_path = luks_image_path
        self.luks_mount_path = luks_mount_path
        self.luks_size_gb = luks_size_gb
        self.backend = backend
        self._keyring_id: str | None = None

    def mount_tmpfs(self) -> None:
        self.tmpfs_path.mkdir(parents=True, exist_ok=True)
        if self.backend == "directory":
            logger.warning("Using directory-backed runtime storage at %s", self.tmpfs_path)
            return
        subprocess.run(
            ["sudo", "mount", "-t", "tmpfs", "-o", "size=512M", "tmpfs", str(self.tmpfs_path)],
            check=True,
        )
        logger.info("Mounted tmpfs at %s", self.tmpfs_path)

    def unmount_tmpfs(self) -> None:
        if self.backend == "directory":
            logger.info("Directory-backed runtime storage does not require tmpfs unmount.")
            return
        subprocess.run(["sudo", "umount", str(self.tmpfs_path)], check=True)
        logger.info("Unmounted tmpfs at %s", self.tmpfs_path)

    def create_luks_volume(self, passphrase: str) -> None:
        if self.backend == "directory":
            self.luks_mount_path.mkdir(parents=True, exist_ok=True)
            logger.warning("Using directory-backed evidence storage at %s", self.luks_mount_path)
            return
        if self.luks_image_path.exists():
            logger.info("LUKS volume already exists at %s", self.luks_image_path)
            return

        self.luks_image_path.parent.mkdir(parents=True, exist_ok=True)
        size_bytes = self.luks_size_gb * 1024 * 1024 * 1024
        subprocess.run(["truncate", "-s", str(size_bytes), str(self.luks_image_path)], check=True)
        subprocess.run(
            ["sudo", "cryptsetup", "luksFormat", "--batch-mode", str(self.luks_image_path)],
            input=passphrase.encode(),
            check=True,
        )
        subprocess.run(
            [
                "sudo",
                "cryptsetup",
                "open",
                str(self.luks_image_path),
                LUKS_MAPPER_NAME,
                "--type",
                "luks",
            ],
            input=passphrase.encode(),
            check=True,
        )
        subprocess.run(["sudo", "mkfs.ext4", f"/dev/mapper/{LUKS_MAPPER_NAME}"], check=True)
        subprocess.run(["sudo", "cryptsetup", "close", LUKS_MAPPER_NAME], check=True)
        logger.info("Created LUKS volume at %s", self.luks_image_path)

    def open_luks(self, passphrase: str) -> None:
        if self.backend == "directory":
            self.luks_mount_path.mkdir(parents=True, exist_ok=True)
            logger.info("Opened directory-backed evidence storage at %s", self.luks_mount_path)
            return
        subprocess.run(
            [
                "sudo",
                "cryptsetup",
                "open",
                str(self.luks_image_path),
                LUKS_MAPPER_NAME,
                "--type",
                "luks",
            ],
            input=passphrase.encode(),
            check=True,
        )
        self.luks_mount_path.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["sudo", "mount", f"/dev/mapper/{LUKS_MAPPER_NAME}", str(self.luks_mount_path)],
            check=True,
        )
        self.store_passphrase_in_keyring(passphrase)
        logger.info("Opened LUKS volume at %s", self.luks_mount_path)

    def close_luks(self) -> None:
        if self.backend == "directory":
            logger.info("Directory-backed evidence storage does not require close.")
            return
        subprocess.run(["sudo", "umount", str(self.luks_mount_path)], check=False)
        subprocess.run(["sudo", "cryptsetup", "close", LUKS_MAPPER_NAME], check=False)
        logger.info("Closed LUKS volume")

    def store_passphrase_in_keyring(self, passphrase: str) -> None:
        if self.backend == "directory":
            logger.info("Directory-backed storage does not persist a passphrase in kernel keyring.")
            return
        result = subprocess.run(
            ["keyctl", "add", "user", "osk-passphrase", passphrase, "@s"],
            capture_output=True,
            text=True,
            check=True,
        )
        self._keyring_id = result.stdout.strip()
        logger.info("Stored passphrase in kernel keyring")

    def revoke_keyring(self) -> None:
        if self.backend == "directory":
            self._keyring_id = None
            logger.info("Directory-backed storage does not require keyring revocation.")
            return
        if self._keyring_id:
            subprocess.run(["keyctl", "revoke", self._keyring_id], check=False)
            self._keyring_id = None
            logger.info("Revoked kernel keyring entry")

    def emergency_wipe(self) -> None:
        logger.warning("EMERGENCY WIPE initiated")
        self.revoke_keyring()
        self.close_luks()
        try:
            self.unmount_tmpfs()
        except subprocess.CalledProcessError:
            logger.warning("tmpfs unmount failed during wipe")
        logger.warning("EMERGENCY WIPE complete")

    def write_evidence_artifact(
        self,
        operation_id: str,
        member_id: str,
        artifact_type: str,
        data: bytes,
        extension: str = "bin",
    ) -> Path | None:
        """Write an evidence artifact to the preserved evidence store.

        Creates a structured path: {operation_id}/{member_id}/{type}/{timestamp}.{ext}
        Returns the full path to the written file, or None if evidence store not available.
        """
        if not self.luks_mount_path.exists():
            logger.warning("Evidence mount path does not exist, skipping artifact write")
            return None

        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
        artifact_dir = self.luks_mount_path / operation_id / member_id / artifact_type
        artifact_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{timestamp}.{extension}"
        artifact_path = artifact_dir / filename
        artifact_path.write_bytes(data)

        logger.info(
            "Wrote evidence artifact: %s (%d bytes)",
            artifact_path.relative_to(self.luks_mount_path),
            len(data),
        )
        return artifact_path

    def write_evidence_metadata(
        self,
        operation_id: str,
        member_id: str,
        metadata: dict,
    ) -> Path | None:
        """Write JSON metadata for an evidence artifact.

        Creates a parallel .json file in the metadata directory.
        Returns the path to the written file, or None if evidence store not available.
        """
        if not self.luks_mount_path.exists():
            logger.warning("Evidence mount path does not exist, skipping metadata write")
            return None

        metadata_path = (
            self.luks_mount_path / operation_id / member_id / "metadata" / f"{metadata['id']}.json"
        )
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(json.dumps(metadata, indent=2, default=str))
        return metadata_path
