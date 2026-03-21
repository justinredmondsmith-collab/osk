"""Hub orchestrator for Osk."""

from __future__ import annotations

import asyncio
import getpass
import logging
import subprocess
from pathlib import Path

import uvicorn

from osk.config import OskConfig, load_config, save_config
from osk.connection_manager import ConnectionManager
from osk.db import Database
from osk.operation import OperationManager
from osk.qr import build_join_url, generate_qr_ascii, generate_qr_png
from osk.server import create_app
from osk.storage import StorageManager
from osk.tls import generate_self_signed_cert


logger = logging.getLogger(__name__)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_storage_manager(config: OskConfig) -> StorageManager:
    config_root = Path.home() / ".config" / "osk"
    return StorageManager(
        tmpfs_path=Path("/tmp/osk-tmpfs"),
        luks_image_path=config_root / "evidence.luks",
        luks_mount_path=Path("/tmp/osk-evidence"),
        luks_size_gb=config.luks_volume_size_gb,
    )


def install() -> None:
    """One-time install for local development."""
    config = load_config()
    config_root = Path.home() / ".config" / "osk"
    config_root.mkdir(parents=True, exist_ok=True)

    cert_path = Path(config.tls_cert_path)
    key_path = Path(config.tls_key_path)

    print("=== Osk Install ===")
    print("Generating TLS certificate...")
    generate_self_signed_cert(cert_path, key_path)
    print(f"  Certificate: {cert_path}")

    passphrase = getpass.getpass("Set evidence encryption passphrase: ")
    passphrase_confirm = getpass.getpass("Confirm passphrase: ")
    if passphrase != passphrase_confirm:
        raise SystemExit("Passphrases do not match. Aborting.")

    storage = default_storage_manager(config)
    print("Creating encrypted evidence volume...")
    storage.create_luks_volume(passphrase)

    if not config.hotspot_ssid:
        cfg = config.model_copy(update={"hotspot_ssid": "osk-local"})
        save_config(cfg)

    print("Pulling container images...")
    subprocess.run(["docker", "compose", "pull"], check=False, cwd=_repo_root())

    print("\n=== Install complete ===")
    print('Run: osk start "Operation Name"')


async def run_hub(name: str) -> None:
    """Start the local hub and serve until interrupted."""
    config = load_config()
    storage = default_storage_manager(config)
    passphrase = getpass.getpass("Operation passphrase: ")

    print("Mounting ephemeral storage...")
    storage.mount_tmpfs()

    print("Opening encrypted evidence volume...")
    storage.open_luks(passphrase)

    db = Database()
    db_url = "postgresql://osk:osk@localhost:5432/osk"
    print("Connecting to database...")
    await db.connect(db_url)

    op_manager = OperationManager(db=db)
    operation = await op_manager.create(name)
    conn_manager = ConnectionManager()

    join_host = "127.0.0.1"
    join_url = build_join_url(join_host, config.hub_port, operation.token)
    qr_path = Path.home() / ".config" / "osk" / "join-qr.png"
    generate_qr_png(join_url, qr_path)

    print("\nOperation started.")
    print(f"Name: {name}")
    print(f"Join URL: {join_url}")
    print(generate_qr_ascii(join_url))
    print(f"PNG QR: {qr_path}\n")

    app = create_app(op_manager=op_manager, conn_manager=conn_manager, db=db)
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="0.0.0.0",
            port=config.hub_port,
            ssl_certfile=config.tls_cert_path,
            ssl_keyfile=config.tls_key_path,
            log_level="info",
        )
    )

    try:
        await server.serve()
    finally:
        print("\nShutting down...")
        await conn_manager.broadcast({"type": "op_ended"})
        await db.close()
        storage.revoke_keyring()
        storage.close_luks()
        try:
            storage.unmount_tmpfs()
        except subprocess.CalledProcessError:
            logger.warning("tmpfs already unmounted during shutdown")
        print("Operation ended.")


def run_hub_sync(name: str) -> int:
    asyncio.run(run_hub(name))
    return 0
