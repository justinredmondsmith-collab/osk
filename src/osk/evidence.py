"""Standalone preserved-evidence access and export helpers."""

from __future__ import annotations

import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Literal

from osk.storage import LUKS_MAPPER_NAME, StorageManager


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
        items = self.list_items()
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
        total_bytes = 0
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for item in items:
                relative_path = Path(str(item["path"]))
                source_path = self.luks_mount_path / relative_path
                archive.write(source_path, arcname=str(relative_path))
                total_bytes += int(item["size_bytes"])

        return {
            "ok": True,
            "output_path": str(output),
            "file_count": len(items),
            "total_bytes": total_bytes,
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
