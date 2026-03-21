"""Hub orchestrator for Osk."""

from __future__ import annotations

import asyncio
import getpass
import logging
import shutil
import subprocess
import time
from pathlib import Path

import asyncpg
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
LOCAL_DEV_DATABASE_URL = "postgresql://osk:osk@localhost:5432/osk"
LOCAL_DEV_OLLAMA_URL = "http://localhost:11434"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _config_root() -> Path:
    return Path.home() / ".config" / "osk"


def default_storage_manager(config: OskConfig) -> StorageManager:
    config_root = _config_root()
    return StorageManager(
        tmpfs_path=Path("/tmp/osk-tmpfs"),
        luks_image_path=config_root / "evidence.luks",
        luks_mount_path=Path("/tmp/osk-evidence"),
        luks_size_gb=config.luks_volume_size_gb,
    )


class HubBootstrapError(RuntimeError):
    """Raised when local prerequisites are incomplete."""


def installation_issues(config: OskConfig, storage: StorageManager) -> list[str]:
    issues: list[str] = []
    cert_path = Path(config.tls_cert_path)
    key_path = Path(config.tls_key_path)

    if not cert_path.exists():
        issues.append(f"missing TLS certificate at {cert_path}")
    if not key_path.exists():
        issues.append(f"missing TLS key at {key_path}")
    if not storage.luks_image_path.exists():
        issues.append(f"missing encrypted evidence volume at {storage.luks_image_path}")

    return issues


def uses_local_dev_services(config: OskConfig) -> bool:
    return (
        config.auto_manage_local_services
        and config.database_url == LOCAL_DEV_DATABASE_URL
        and config.ollama_base_url == LOCAL_DEV_OLLAMA_URL
    )


def local_service_mode(config: OskConfig) -> str:
    if uses_local_dev_services(config):
        return "compose-managed local services"
    return "externally managed services"


def ensure_installation_ready(config: OskConfig, storage: StorageManager) -> None:
    issues = installation_issues(config, storage)
    if not issues:
        return

    details = "\n".join(f"- {issue}" for issue in issues)
    raise HubBootstrapError(f"Osk is not installed yet:\n{details}\nRun `osk install` first.")


def _require_docker_compose() -> list[str]:
    docker = shutil.which("docker")
    if not docker:
        raise HubBootstrapError(
            "Docker is not available. Install Docker with Compose support, "
            "or set `database_url` and `ollama_base_url` to running services."
        )
    return [docker, "compose"]


def ensure_local_services(config: OskConfig) -> None:
    if not uses_local_dev_services(config):
        logger.info("Using externally managed services from config.")
        return

    compose_cmd = _require_docker_compose()
    logger.info("Starting local development services with Docker Compose.")
    subprocess.run(
        [*compose_cmd, "up", "-d", "db", "ollama"],
        cwd=_repo_root(),
        check=True,
    )


async def wait_for_database(database_url: str, timeout_seconds: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        try:
            conn = await asyncpg.connect(database_url)
        except Exception as exc:  # pragma: no cover - exercised through timeout path
            last_error = exc
            await asyncio.sleep(1)
            continue

        await conn.close()
        return

    detail = f": {last_error}" if last_error else ""
    raise HubBootstrapError(f"Database did not become ready within {timeout_seconds:.0f}s{detail}")


def install() -> None:
    """One-time install for local development."""
    config = load_config()
    config_root = _config_root()
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

    if uses_local_dev_services(config):
        docker = shutil.which("docker")
        if docker:
            print("Pulling local development service images...")
            subprocess.run([docker, "compose", "pull"], check=False, cwd=_repo_root())
        else:
            print("Docker not found. Skipping local service image pull.")
            print("Set database_url/ollama_base_url to external services or install Docker later.")

    print("\n=== Install complete ===")
    print('Run: osk start "Operation Name"')


async def run_hub(name: str) -> None:
    """Start the local hub and serve until interrupted."""
    config = load_config()
    storage = default_storage_manager(config)
    ensure_installation_ready(config, storage)
    ensure_local_services(config)
    await wait_for_database(config.database_url)

    passphrase = getpass.getpass("Operation passphrase: ")
    mounted_tmpfs = False
    luks_open = False
    db = Database()
    conn_manager = ConnectionManager()

    try:
        print("Mounting ephemeral storage...")
        storage.mount_tmpfs()
        mounted_tmpfs = True

        print("Opening encrypted evidence volume...")
        storage.open_luks(passphrase)
        luks_open = True

        print("Connecting to database...")
        await db.connect(config.database_url)

        op_manager = OperationManager(db=db)
        operation = await op_manager.create(name)

        join_url = build_join_url(config.join_host, config.hub_port, operation.token)
        qr_path = _config_root() / "join-qr.png"
        generate_qr_png(join_url, qr_path)

        print("\nOperation started.")
        print(f"Name: {name}")
        print(f"Join URL: {join_url}")
        print(f"Service mode: {local_service_mode(config)}")
        print(generate_qr_ascii(join_url))
        print(f"PNG QR: {qr_path}\n")

        app = create_app(op_manager=op_manager, conn_manager=conn_manager, db=db)
        server = uvicorn.Server(
            uvicorn.Config(
                app,
                host=config.hub_host,
                port=config.hub_port,
                ssl_certfile=config.tls_cert_path,
                ssl_keyfile=config.tls_key_path,
                log_level="info",
            )
        )
        await server.serve()
    finally:
        print("\nShutting down...")
        await conn_manager.broadcast({"type": "op_ended"})
        await db.close()
        if luks_open:
            storage.revoke_keyring()
            storage.close_luks()
        if mounted_tmpfs:
            try:
                storage.unmount_tmpfs()
            except subprocess.CalledProcessError:
                logger.warning("tmpfs already unmounted during shutdown")
        print("Operation ended.")


def run_hub_sync(name: str) -> int:
    try:
        asyncio.run(run_hub(name))
    except HubBootstrapError as exc:
        print(exc)
        return 1
    return 0
