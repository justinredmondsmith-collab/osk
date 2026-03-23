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

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _sha256_bytes(payload: bytes) -> str:
        return hashlib.sha256(payload).hexdigest()

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

    @classmethod
    def verify_export_bundle(
        cls,
        archive_path: Path,
        *,
        manifest_path: Path | None = None,
        checksum_path: Path | None = None,
    ) -> dict[str, object]:
        archive = Path(archive_path).expanduser()
        resolved_manifest = (
            Path(manifest_path).expanduser()
            if manifest_path is not None
            else archive.with_suffix(archive.suffix + ".manifest.json")
        )
        resolved_checksum = (
            Path(checksum_path).expanduser()
            if checksum_path is not None
            else archive.with_suffix(archive.suffix + ".sha256")
        )
        warnings: list[str] = []

        if not archive.exists():
            return {
                "ok": False,
                "error": f"Evidence archive not found at {archive}",
            }

        try:
            archive_sha256 = cls._sha256_file(archive)
            with zipfile.ZipFile(archive) as bundle:
                bundle_names = sorted(bundle.namelist())
                if EXPORT_MANIFEST_NAME not in bundle_names:
                    return {
                        "ok": False,
                        "error": (
                            f"Evidence archive {archive} does not contain {EXPORT_MANIFEST_NAME}."
                        ),
                    }

                embedded_manifest = json.loads(bundle.read(EXPORT_MANIFEST_NAME))
                items = embedded_manifest.get("items")
                if not isinstance(items, list):
                    return {
                        "ok": False,
                        "error": "Embedded export manifest is missing an items list.",
                    }

                archive_entries = sorted(
                    name for name in bundle_names if name != EXPORT_MANIFEST_NAME
                )
                manifest_entries: list[str] = []
                total_bytes = 0
                for item in items:
                    if not isinstance(item, dict):
                        return {
                            "ok": False,
                            "error": "Embedded export manifest contains a non-object item entry.",
                        }
                    relative_path = item.get("path")
                    size_bytes = item.get("size_bytes")
                    expected_sha256 = item.get("sha256")
                    if not isinstance(relative_path, str) or not relative_path:
                        return {
                            "ok": False,
                            "error": "Embedded export manifest contains an item without path.",
                        }
                    if not isinstance(size_bytes, int):
                        return {
                            "ok": False,
                            "error": (
                                f"Embedded export manifest item {relative_path} is missing "
                                "an integer size_bytes value."
                            ),
                        }
                    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
                        return {
                            "ok": False,
                            "error": (
                                f"Embedded export manifest item {relative_path} is missing "
                                "a SHA-256 digest."
                            ),
                        }
                    payload = bundle.read(relative_path)
                    actual_sha256 = cls._sha256_bytes(payload)
                    actual_size = len(payload)
                    if actual_size != size_bytes:
                        return {
                            "ok": False,
                            "error": (
                                f"Embedded export manifest size mismatch for {relative_path}: "
                                f"expected {size_bytes}, found {actual_size}."
                            ),
                        }
                    if actual_sha256 != expected_sha256:
                        return {
                            "ok": False,
                            "error": (
                                f"Embedded export manifest hash mismatch for {relative_path}: "
                                "archive contents do not match the recorded digest."
                            ),
                        }
                    manifest_entries.append(relative_path)
                    total_bytes += actual_size
        except zipfile.BadZipFile as exc:
            return {
                "ok": False,
                "error": f"Evidence archive at {archive} is not a valid zip file: {exc}",
            }
        except (KeyError, json.JSONDecodeError) as exc:
            return {
                "ok": False,
                "error": f"Evidence archive manifest could not be read: {exc}",
            }

        if archive_entries != sorted(manifest_entries):
            return {
                "ok": False,
                "error": (
                    "Evidence archive entries do not match the embedded export manifest inventory."
                ),
            }

        if embedded_manifest.get("file_count") != len(items):
            return {
                "ok": False,
                "error": (
                    "Embedded export manifest file_count does not match the archive inventory."
                ),
            }
        if embedded_manifest.get("total_bytes") != total_bytes:
            return {
                "ok": False,
                "error": "Embedded export manifest total_bytes does not match archive contents.",
            }
        if embedded_manifest.get("manifest_entry") != EXPORT_MANIFEST_NAME:
            return {
                "ok": False,
                "error": "Embedded export manifest advertises an unexpected manifest entry name.",
            }

        manifest_status = "missing"
        if resolved_manifest.exists():
            try:
                sidecar_manifest = json.loads(resolved_manifest.read_text())
            except json.JSONDecodeError as exc:
                return {
                    "ok": False,
                    "error": f"Sidecar manifest {resolved_manifest} is not valid JSON: {exc}",
                }
            if sidecar_manifest.get("archive_sha256") != archive_sha256:
                return {
                    "ok": False,
                    "error": (
                        f"Sidecar manifest {resolved_manifest} does not match the archive SHA-256."
                    ),
                }
            if sidecar_manifest.get("items") != items:
                return {
                    "ok": False,
                    "error": (
                        f"Sidecar manifest {resolved_manifest} does not match the embedded "
                        "archive manifest."
                    ),
                }
            if sidecar_manifest.get("file_count") != len(items):
                return {
                    "ok": False,
                    "error": (
                        f"Sidecar manifest {resolved_manifest} has an unexpected file_count value."
                    ),
                }
            if sidecar_manifest.get("total_bytes") != total_bytes:
                return {
                    "ok": False,
                    "error": (
                        f"Sidecar manifest {resolved_manifest} has an unexpected total_bytes value."
                    ),
                }
            manifest_status = "verified"
            archive_name = sidecar_manifest.get("archive_name")
            if isinstance(archive_name, str) and archive_name != archive.name:
                warnings.append(
                    "Sidecar manifest archive_name differs from the current archive filename."
                )
        elif manifest_path is not None:
            return {
                "ok": False,
                "error": f"Sidecar manifest not found at {resolved_manifest}",
            }
        else:
            warnings.append("Sidecar manifest file is missing; verified embedded manifest only.")

        checksum_status = "missing"
        if resolved_checksum.exists():
            checksum_line = resolved_checksum.read_text().strip()
            parts = checksum_line.split(maxsplit=1)
            if len(parts) != 2:
                return {
                    "ok": False,
                    "error": (
                        f"Checksum file {resolved_checksum} is not in sha256sum-compatible format."
                    ),
                }
            expected_sha256 = parts[0]
            referenced_name = parts[1].strip()
            if expected_sha256 != archive_sha256:
                return {
                    "ok": False,
                    "error": f"Checksum file {resolved_checksum} does not match the archive.",
                }
            checksum_status = "verified"
            if referenced_name.startswith("*") or referenced_name.startswith(" "):
                referenced_name = referenced_name[1:]
            if referenced_name != archive.name:
                warnings.append(
                    "Checksum file filename entry differs from the current archive filename."
                )
        elif checksum_path is not None:
            return {
                "ok": False,
                "error": f"Checksum file not found at {resolved_checksum}",
            }
        else:
            warnings.append("Checksum file is missing; archive digest verified without sidecar.")

        return {
            "ok": True,
            "archive_path": str(archive),
            "archive_sha256": archive_sha256,
            "file_count": len(items),
            "total_bytes": total_bytes,
            "embedded_manifest_status": "verified",
            "manifest_path": str(resolved_manifest),
            "manifest_status": manifest_status,
            "checksum_path": str(resolved_checksum),
            "checksum_status": checksum_status,
            "items": items,
            "warnings": warnings,
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
