"""Hub orchestrator for Osk."""

from __future__ import annotations

import asyncio
import json
import getpass
import logging
import os
import signal
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

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
DEFAULT_LOCAL_SERVICE_NAMES = ("db",)


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
        backend=config.storage_backend,
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
    if storage.backend == "luks" and not storage.luks_image_path.exists():
        issues.append(f"missing encrypted evidence volume at {storage.luks_image_path}")

    return issues


def uses_local_dev_services(config: OskConfig) -> bool:
    if not config.auto_manage_local_services:
        return False
    db_url = urlparse(config.database_url)
    ollama_url = urlparse(config.ollama_base_url)
    return (
        db_url.scheme.startswith("postgres")
        and db_url.hostname in {"localhost", "127.0.0.1"}
        and ollama_url.hostname in {"localhost", "127.0.0.1"}
    )


def local_service_mode(config: OskConfig) -> str:
    if uses_local_dev_services(config):
        return "compose-managed local services"
    return "externally managed services"


def local_database_port(config: OskConfig) -> int:
    db_url = urlparse(config.database_url)
    if db_url.hostname not in {"localhost", "127.0.0.1"}:
        raise HubBootstrapError("Local database port requested for a non-local database URL.")
    return int(db_url.port or 5432)


def _compose_environment(config: OskConfig) -> dict[str, str]:
    env = dict(os.environ)
    env["OSK_POSTGRES_PORT"] = str(local_database_port(config))
    return env


def ensure_installation_ready(config: OskConfig, storage: StorageManager) -> None:
    issues = installation_issues(config, storage)
    if not issues:
        return

    details = "\n".join(f"- {issue}" for issue in issues)
    raise HubBootstrapError(f"Osk is not installed yet:\n{details}\nRun `osk install` first.")


def _hub_state_path() -> Path:
    return _config_root() / "hub-state.json"


def _hub_stop_request_path() -> Path:
    return _config_root() / "hub-stop-request.json"


def _find_compose_command() -> list[str]:
    if docker := shutil.which("docker"):
        return [docker, "compose"]
    if podman := shutil.which("podman"):
        return [podman, "compose"]
    if docker_compose := shutil.which("docker-compose"):
        return [docker_compose]
    if podman_compose := shutil.which("podman-compose"):
        return [podman_compose]
    raise HubBootstrapError(
        "No Compose-compatible runtime found. Install docker, podman, docker-compose, "
        "or set `database_url` and `ollama_base_url` to running services."
    )


def required_local_services(config: OskConfig) -> tuple[str, ...]:
    del config
    return DEFAULT_LOCAL_SERVICE_NAMES


def read_hub_state() -> dict | None:
    state_path = _hub_state_path()
    if not state_path.exists():
        return None
    return json.loads(state_path.read_text())


def _pid_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _write_hub_state(operation_name: str, port: int) -> None:
    state_path = _hub_state_path()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "operation_name": operation_name,
                "port": port,
                "started_at": int(time.time()),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _clear_hub_state() -> None:
    _hub_state_path().unlink(missing_ok=True)


def _request_hub_shutdown() -> None:
    request_path = _hub_stop_request_path()
    request_path.parent.mkdir(parents=True, exist_ok=True)
    request_path.write_text(json.dumps({"requested_at": int(time.time())}) + "\n")


def _clear_stop_request() -> None:
    _hub_stop_request_path().unlink(missing_ok=True)


def _shutdown_requested() -> bool:
    return _hub_stop_request_path().exists()


def ensure_hub_not_running() -> None:
    state = read_hub_state()
    if state is None:
        _clear_stop_request()
        return

    pid = int(state.get("pid", -1))
    if pid > 0 and _pid_is_running(pid):
        operation_name = state.get("operation_name", "unknown")
        raise HubBootstrapError(
            f"Osk hub is already running for operation '{operation_name}' (pid {pid}). "
            "Use `osk stop` before starting a new operation."
        )

    logger.warning("Removing stale hub state at %s", _hub_state_path())
    _clear_hub_state()
    _clear_stop_request()


def ensure_local_services(config: OskConfig) -> None:
    if not uses_local_dev_services(config):
        logger.info("Using externally managed services from config.")
        return

    compose_cmd = _find_compose_command()
    services = required_local_services(config)
    logger.info("Starting local development services with Docker Compose.")
    subprocess.run(
        [*compose_cmd, "up", "-d", *services],
        cwd=_repo_root(),
        check=True,
        env=_compose_environment(config),
    )


def stop_local_services(config: OskConfig) -> None:
    if not uses_local_dev_services(config):
        return

    compose_cmd = _find_compose_command()
    services = required_local_services(config)
    logger.info("Stopping local development services managed by Compose.")
    subprocess.run(
        [*compose_cmd, "stop", *services],
        cwd=_repo_root(),
        check=False,
        env=_compose_environment(config),
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


async def watch_for_stop_request(server: uvicorn.Server, poll_seconds: float = 0.2) -> None:
    while not server.should_exit:
        if _shutdown_requested():
            logger.info("Received graceful hub shutdown request.")
            server.should_exit = True
            return
        await asyncio.sleep(poll_seconds)


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

    storage = default_storage_manager(config)
    if storage.backend == "luks":
        print("Creating encrypted evidence volume...")
        passphrase = getpass.getpass("Set evidence encryption passphrase: ")
        passphrase_confirm = getpass.getpass("Confirm passphrase: ")
        if passphrase != passphrase_confirm:
            raise SystemExit("Passphrases do not match. Aborting.")
        storage.create_luks_volume(passphrase)
    else:
        print("Using directory-backed development storage.")
        storage.create_luks_volume("")

    if not config.hotspot_ssid:
        cfg = config.model_copy(update={"hotspot_ssid": "osk-local"})
        save_config(cfg)

    if uses_local_dev_services(config):
        try:
            compose_cmd = _find_compose_command()
        except HubBootstrapError:
            compose_cmd = []

        if compose_cmd:
            print("Pulling local development service images...")
            subprocess.run(
                [*compose_cmd, "pull", *required_local_services(config)],
                check=False,
                cwd=_repo_root(),
            )
        else:
            print("No Compose-compatible runtime found. Skipping local service image pull.")
            print("Set database_url/ollama_base_url to external services or install Docker later.")

    print("\n=== Install complete ===")
    print('Run: osk start "Operation Name"')


async def run_hub(name: str) -> None:
    """Start the local hub and serve until interrupted."""
    config = load_config()
    storage = default_storage_manager(config)
    ensure_installation_ready(config, storage)
    ensure_hub_not_running()
    _clear_stop_request()
    ensure_local_services(config)
    await wait_for_database(config.database_url)

    passphrase = ""
    if storage.backend == "luks":
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
        _write_hub_state(name, config.hub_port)

        print("\nOperation started.")
        print(f"Name: {name}")
        print(f"Join URL: {join_url}")
        print(f"Service mode: {local_service_mode(config)}")
        print(f"Storage backend: {storage.backend}")
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
        stop_watcher = asyncio.create_task(watch_for_stop_request(server))
        try:
            await server.serve()
        finally:
            stop_watcher.cancel()
            await asyncio.gather(stop_watcher, return_exceptions=True)
    finally:
        print("\nShutting down...")
        _clear_hub_state()
        _clear_stop_request()
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
    except KeyboardInterrupt:
        return 0
    return 0


def stop_hub(wait_seconds: float = 10.0, *, stop_services: bool = False) -> int:
    config = load_config()
    state = read_hub_state()
    if state is None:
        print("No running Osk hub state found.")
        if stop_services:
            stop_local_services(config)
        return 0

    pid = int(state.get("pid", -1))
    if pid <= 0 or not _pid_is_running(pid):
        print("Found stale Osk hub state; cleaning it up.")
        _clear_hub_state()
        if stop_services:
            stop_local_services(config)
        return 0

    operation_name = state.get("operation_name", "unknown")
    print(f"Stopping Osk hub for '{operation_name}' (pid {pid})...")
    _request_hub_shutdown()

    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        if not _pid_is_running(pid):
            break
        time.sleep(0.2)

    if _pid_is_running(pid):
        logger.warning("Graceful shutdown timed out; sending SIGTERM to pid %s", pid)
        os.kill(pid, signal.SIGTERM)
        while time.monotonic() < deadline:
            if not _pid_is_running(pid):
                break
            time.sleep(0.2)

    if _pid_is_running(pid):
        print(f"Hub process {pid} did not exit within {wait_seconds:.1f}s.")
        return 1

    _clear_hub_state()
    _clear_stop_request()
    if stop_services:
        stop_local_services(config)
    print("Osk hub stopped.")
    return 0


def status_hub() -> int:
    state = read_hub_state()
    if state is None:
        _clear_stop_request()
        print("Osk hub is not running.")
        return 1

    pid = int(state.get("pid", -1))
    operation_name = state.get("operation_name", "unknown")
    port = state.get("port", "unknown")
    started_at = state.get("started_at", "unknown")
    stopping = _shutdown_requested()

    if pid > 0 and _pid_is_running(pid):
        print("Osk hub is running.")
        print(f"operation = {operation_name}")
        print(f"pid = {pid}")
        print(f"port = {port}")
        print(f"started_at = {started_at}")
        print(f"stopping = {str(stopping).lower()}")
        return 0

    print("Osk hub state is present but the recorded PID is not visible.")
    print(f"operation = {operation_name}")
    print(f"pid = {pid}")
    print(f"port = {port}")
    print(f"started_at = {started_at}")
    print(f"stopping = {str(stopping).lower()}")
    print("The state file was left in place so it can be inspected or stopped from the same host context.")
    return 1
