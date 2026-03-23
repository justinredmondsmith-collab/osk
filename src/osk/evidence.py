"""Standalone preserved-evidence access and export helpers."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from osk.storage import LUKS_MAPPER_NAME, StorageManager

EXPORT_MANIFEST_NAME = "_osk_export_manifest.json"


class EvidenceManager:
    def __init__(
        self,
        *,
        luks_image_path: Path,
        luks_mount_path: Path,
        backend: Literal["luks", "directory"] = "luks",
        mapper_name: str = LUKS_MAPPER_NAME,
    ) -> None:
        self.luks_image_path = Path(luks_image_path)
        self.luks_mount_path = Path(luks_mount_path)
        self.backend = backend
        self.mapper_name = mapper_name

    @classmethod
    def from_storage(cls, storage: StorageManager) -> EvidenceManager:
        return cls(
            luks_image_path=storage.luks_image_path,
            luks_mount_path=storage.luks_mount_path,
            backend=storage.backend,
        )

    def _mapper_device(self) -> str:
        return f"/dev/mapper/{self.mapper_name}"

    def _sha256_file(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def list_items(self) -> list[dict[str, object]]:
        if not self.luks_mount_path.exists():
            return []

        items: list[dict[str, object]] = []
        for path in sorted(self.luks_mount_path.rglob("*")):
            if not path.is_file():
                continue
            relative_path = path.relative_to(self.luks_mount_path)
            items.append(
                {
                    "path": str(relative_path),
                    "size_bytes": path.stat().st_size,
                }
            )
        return items

    def _list_export_items(self) -> list[dict[str, object]]:
        items = self.list_items()
        export_items: list[dict[str, object]] = []
        for item in items:
            relative_path = Path(str(item["path"]))
            export_items.append(
                {
                    **item,
                    "sha256": self._sha256_file(self.luks_mount_path / relative_path),
                }
            )
        return export_items

    def _build_export_manifest(
        self,
        *,
        output_path: Path,
        items: list[dict[str, object]],
        total_bytes: int,
    ) -> dict[str, object]:
        return {
            "artifact_version": 1,
            "exported_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "backend": self.backend,
            "source_path": str(self.luks_mount_path),
            "archive_name": output_path.name,
            "manifest_entry": EXPORT_MANIFEST_NAME,
            "file_count": len(items),
            "total_bytes": total_bytes,
            "items": items,
        }

    def unlock(self, passphrase: str) -> dict[str, object]:
        if self.backend == "directory":
            self.luks_mount_path.mkdir(parents=True, exist_ok=True)
            items = self.list_items()
            return {
                "ok": True,
                "backend": self.backend,
                "mount_path": str(self.luks_mount_path),
                "item_count": len(items),
                "items": items,
            }

        if not self.luks_image_path.exists():
            return {
                "ok": False,
                "error": f"Evidence volume not found at {self.luks_image_path}",
            }

        self.luks_mount_path.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "sudo",
                "cryptsetup",
                "open",
                str(self.luks_image_path),
                self.mapper_name,
                "--type",
                "luks",
                "--readonly",
            ],
            input=passphrase.encode(),
            check=True,
        )
        subprocess.run(
            [
                "sudo",
                "mount",
                "-o",
                "ro",
                self._mapper_device(),
                str(self.luks_mount_path),
            ],
            check=True,
        )
        items = self.list_items()
        return {
            "ok": True,
            "backend": self.backend,
            "mount_path": str(self.luks_mount_path),
            "item_count": len(items),
            "items": items,
        }

    def export(self, output_path: Path) -> dict[str, object]:
        items = self._list_export_items()
        if not items:
            return {
                "ok": False,
                "error": (
                    f"No visible preserved evidence found under {self.luks_mount_path}. "
                    "Unlock evidence first if needed."
                ),
            }

        output = Path(output_path).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        total_bytes = sum(int(item["size_bytes"]) for item in items)
        manifest = self._build_export_manifest(
            output_path=output,
            items=items,
            total_bytes=total_bytes,
        )
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for item in items:
                relative_path = Path(str(item["path"]))
                source_path = self.luks_mount_path / relative_path
                archive.write(source_path, arcname=str(relative_path))
            archive.writestr(
                EXPORT_MANIFEST_NAME,
                json.dumps(manifest, indent=2, sort_keys=True),
            )

        archive_sha256 = self._sha256_file(output)
        manifest_path = output.with_suffix(output.suffix + ".manifest.json")
        manifest_path.write_text(
            json.dumps(
                {
                    **manifest,
                    "output_path": str(output),
                    "archive_sha256": archive_sha256,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )

        checksum_path = output.with_suffix(output.suffix + ".sha256")
        checksum_path.write_text(f"{archive_sha256}  {output.name}\n")

        return {
            "ok": True,
            "output_path": str(output),
            "file_count": len(items),
            "total_bytes": total_bytes,
            "manifest_path": str(manifest_path),
            "checksum_path": str(checksum_path),
            "archive_sha256": archive_sha256,
        }

    def destroy(self) -> dict[str, object]:
        if self.backend == "directory":
            if not self.luks_mount_path.exists():
                return {
                    "ok": False,
                    "error": f"Evidence directory not found at {self.luks_mount_path}",
                }
            shutil.rmtree(self.luks_mount_path)
            return {
                "ok": True,
                "destroyed_path": str(self.luks_mount_path),
                "backend": self.backend,
            }

        if not self.luks_image_path.exists():
            return {
                "ok": False,
                "error": f"Evidence volume not found at {self.luks_image_path}",
            }

        subprocess.run(["sudo", "umount", str(self.luks_mount_path)], check=False)
        subprocess.run(["sudo", "cryptsetup", "close", self.mapper_name], check=False)
        subprocess.run(["shred", "-u", str(self.luks_image_path)], check=True)
        return {
            "ok": True,
            "destroyed_path": str(self.luks_image_path),
            "backend": self.backend,
        }
