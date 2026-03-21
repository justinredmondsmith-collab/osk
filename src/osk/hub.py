"""Hub orchestrator for Osk."""

from __future__ import annotations

import asyncio
import datetime as dt
import getpass
import json
import logging
import os
import shutil
import signal
import subprocess
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

import asyncpg
import uvicorn

from osk.config import OskConfig, load_config, save_config
from osk.connection_manager import ConnectionManager
from osk.db import Database
from osk.local_operator import (
    bootstrap_session_path,
    clear_bootstrap_session,
    clear_operator_session,
    consume_bootstrap_session,
    create_bootstrap_session,
    create_operator_session,
    operator_session_path,
    read_bootstrap_session,
    read_operator_session,
)
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


def _state_root() -> Path:
    return Path.home() / ".local" / "state" / "osk"


def _runtime_log_path() -> Path:
    return _state_root() / "hub.log"


def default_storage_manager(config: OskConfig) -> StorageManager:
    state_root = _state_root()
    return StorageManager(
        tmpfs_path=state_root / "runtime",
        luks_image_path=state_root / "evidence.luks",
        luks_mount_path=state_root / "evidence",
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


def _configure_runtime_log_handler() -> Path:
    log_path = _runtime_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if getattr(handler, "_osk_runtime_log", False):
            return log_path

    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler._osk_runtime_log = True  # type: ignore[attr-defined]
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    root_logger.addHandler(handler)
    return log_path


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


def _write_hub_state(operation_id: str, operation_name: str, port: int) -> None:
    state_path = _hub_state_path()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "operation_id": operation_id,
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
    clear_bootstrap_session()
    clear_operator_session()


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


async def watch_member_heartbeats(
    op_manager: OperationManager,
    conn_manager: ConnectionManager,
    *,
    timeout_seconds: float,
    poll_seconds: float,
) -> None:
    while True:
        for member_id in conn_manager.stale_member_ids(timeout_seconds):
            logger.warning("Heartbeat timeout for member %s", member_id)
            await conn_manager.disconnect(member_id)
            try:
                await op_manager.mark_disconnected(member_id)
            except KeyError:
                continue
        await asyncio.sleep(poll_seconds)


async def _get_audit_events(operation_id: uuid.UUID, limit: int) -> list[dict]:
    config = load_config()
    db = Database()
    await db.connect(config.database_url)
    try:
        return await db.get_audit_events(operation_id, limit)
    finally:
        await db.close()


async def _record_local_audit_event(
    operation_id: uuid.UUID,
    action: str,
    *,
    details: dict | None = None,
) -> None:
    config = load_config()
    db = Database()
    await db.connect(config.database_url)
    try:
        await db.insert_audit_event(
            operation_id,
            "system",
            action,
            details=details,
        )
    finally:
        await db.close()


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
    db_connected = False
    db = Database()
    conn_manager = ConnectionManager()
    op_manager: OperationManager | None = None

    try:
        print("Mounting ephemeral storage...")
        storage.mount_tmpfs()
        mounted_tmpfs = True

        print("Opening encrypted evidence volume...")
        storage.open_luks(passphrase)
        luks_open = True

        print("Connecting to database...")
        await db.connect(config.database_url)
        db_connected = True

        op_manager = OperationManager(db=db)
        operation, resumed = await op_manager.create_or_resume(name)

        join_url = build_join_url(config.join_host, config.hub_port, operation.token)
        qr_path = _config_root() / "join-qr.png"
        generate_qr_png(join_url, qr_path)
        clear_operator_session()
        bootstrap = create_bootstrap_session(
            str(operation.id),
            config.operator_bootstrap_ttl_minutes,
        )
        _write_hub_state(str(operation.id), operation.name, config.hub_port)

        if resumed:
            print("\nOperation resumed.")
            if name != operation.name:
                print(f'Requested name "{name}" ignored; resuming "{operation.name}".')
        else:
            print("\nOperation started.")
        print(f"Name: {operation.name}")
        print(f"Operation ID: {operation.id}")
        print(f"Join URL: {join_url}")
        print(f"Operator bootstrap file: {bootstrap_session_path()}")
        print(f"Operator bootstrap expires: {bootstrap['expires_at']}")
        print(f"Runtime log file: {_runtime_log_path()}")
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
        heartbeat_watcher = asyncio.create_task(
            watch_member_heartbeats(
                op_manager,
                conn_manager,
                timeout_seconds=config.member_heartbeat_timeout_seconds,
                poll_seconds=config.member_heartbeat_check_interval_seconds,
            )
        )
        try:
            await server.serve()
        finally:
            stop_watcher.cancel()
            heartbeat_watcher.cancel()
            await asyncio.gather(stop_watcher, heartbeat_watcher, return_exceptions=True)
    finally:
        print("\nShutting down...")
        _clear_hub_state()
        _clear_stop_request()
        clear_bootstrap_session()
        clear_operator_session()
        await conn_manager.broadcast({"type": "op_ended"})
        if db_connected and op_manager is not None and op_manager.operation is not None:
            await op_manager.stop()
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
        log_path = _configure_runtime_log_handler()
        logger.info("Starting Osk hub runtime; log file at %s", log_path)
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
        clear_bootstrap_session()
        clear_operator_session()
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
    clear_bootstrap_session()
    clear_operator_session()
    if stop_services:
        stop_local_services(config)
    print("Osk hub stopped.")
    return 0


def _format_timestamp(timestamp: object) -> tuple[int | None, str | None]:
    if not isinstance(timestamp, (int, float)):
        return None, None
    dt_value = dt.datetime.fromtimestamp(float(timestamp), tz=dt.timezone.utc)
    return int(timestamp), dt_value.isoformat(timespec="seconds").replace("+00:00", "Z")


def _format_uptime(seconds: object) -> str | None:
    if not isinstance(seconds, (int, float)):
        return None

    remaining = max(int(seconds), 0)
    if remaining == 0:
        return "0s"

    parts: list[str] = []
    for suffix, unit_seconds in (("d", 86400), ("h", 3600), ("m", 60), ("s", 1)):
        value, remaining = divmod(remaining, unit_seconds)
        if value:
            parts.append(f"{value}{suffix}")
    return " ".join(parts)


def hub_status_snapshot(now: float | None = None) -> tuple[int, dict[str, object]]:
    if now is None:
        now = time.time()

    state = read_hub_state()
    if state is None:
        _clear_stop_request()
        return 1, {
            "status": "stopped",
            "message": "Osk hub is not running.",
            "stopping": False,
        }

    pid = int(state.get("pid", -1))
    operation_name = state.get("operation_name", "unknown")
    operation_id = state.get("operation_id")
    port = state.get("port", "unknown")
    started_at = state.get("started_at")
    stopping = _shutdown_requested()
    started_at_unix, started_at_iso = _format_timestamp(started_at)
    uptime_seconds = None
    uptime_human = None
    if started_at_unix is not None:
        uptime_seconds = max(int(now) - started_at_unix, 0)
        uptime_human = _format_uptime(uptime_seconds)

    snapshot: dict[str, object] = {
        "operator_bootstrap_path": str(bootstrap_session_path()),
        "operation_id": operation_id,
        "operation_name": operation_name,
        "operator_session_path": str(operator_session_path()),
        "pid": pid,
        "port": port,
        "runtime_log_path": str(_runtime_log_path()),
        "started_at_unix": started_at_unix,
        "started_at_iso": started_at_iso,
        "uptime_seconds": uptime_seconds,
        "uptime_human": uptime_human,
        "stopping": stopping,
    }
    if bootstrap := read_bootstrap_session():
        snapshot["operator_bootstrap_active"] = True
        snapshot["operator_bootstrap_expires_at"] = bootstrap.get("expires_at")
    else:
        snapshot["operator_bootstrap_active"] = False
        snapshot["operator_bootstrap_expires_at"] = None
    if session := read_operator_session():
        snapshot["operator_session_active"] = True
        snapshot["operator_session_expires_at"] = session.get("expires_at")
    else:
        snapshot["operator_session_active"] = False
        snapshot["operator_session_expires_at"] = None

    if pid > 0 and _pid_is_running(pid):
        snapshot["status"] = "running"
        snapshot["message"] = "Osk hub is running."
        return 0, snapshot

    snapshot["status"] = "state_only"
    snapshot["message"] = "Osk hub state is present but the recorded PID is not visible."
    snapshot["note"] = (
        "The state file was left in place so it can be inspected or stopped "
        "from the same host context."
    )
    return 1, snapshot


def status_hub(*, json_output: bool = False) -> int:
    code, snapshot = hub_status_snapshot()
    if json_output:
        print(json.dumps(snapshot, indent=2, sort_keys=True))
        return code

    print(snapshot["message"])
    print(f"status = {snapshot['status']}")

    if snapshot["status"] == "stopped":
        return code

    print(f"operation = {snapshot['operation_name']}")
    if operation_id := snapshot.get("operation_id"):
        print(f"operation_id = {operation_id}")
    print(f"pid = {snapshot['pid']}")
    print(f"port = {snapshot['port']}")
    started_at_iso = snapshot.get("started_at_iso") or "unknown"
    print(f"started_at = {started_at_iso}")
    uptime_human = snapshot.get("uptime_human")
    if uptime_human is not None:
        print(f"uptime = {uptime_human}")
    print(f"stopping = {str(snapshot['stopping']).lower()}")

    if note := snapshot.get("note"):
        print(f"note = {note}")
    if session_path := snapshot.get("operator_session_path"):
        print(f"operator_session_file = {session_path}")
    if session_expires_at := snapshot.get("operator_session_expires_at"):
        print(f"operator_session_expires_at = {session_expires_at}")
    if bootstrap_path := snapshot.get("operator_bootstrap_path"):
        print(f"operator_bootstrap_file = {bootstrap_path}")
    if bootstrap_expires_at := snapshot.get("operator_bootstrap_expires_at"):
        print(f"operator_bootstrap_expires_at = {bootstrap_expires_at}")
    if runtime_log_path := snapshot.get("runtime_log_path"):
        print(f"runtime_log_file = {runtime_log_path}")

    return code


def login_operator_session(*, ttl_minutes: int | None = None, json_output: bool = False) -> int:
    config = load_config()
    state = read_hub_state()
    if state is None:
        print("No running Osk hub state found.")
        return 1

    operation_id = str(state.get("operation_id", "")).strip()
    if not operation_id:
        print("Hub state is missing an operation id.")
        return 1

    issued_from = "session_refresh"
    bootstrap_consumed = False
    existing_session = read_operator_session()
    if existing_session is None or existing_session.get("operation_id") != operation_id:
        bootstrap = read_bootstrap_session()
        if bootstrap is None:
            print("No active operator bootstrap is available for this hub instance.")
            return 1
        bootstrap_token = bootstrap.get("bootstrap_token")
        if not isinstance(bootstrap_token, str):
            print("Operator bootstrap file is invalid.")
            clear_bootstrap_session()
            return 1
        if not consume_bootstrap_session(operation_id, bootstrap_token):
            print("Operator bootstrap could not be consumed.")
            return 1
        issued_from = "bootstrap"
        bootstrap_consumed = True

    session = create_operator_session(
        operation_id,
        ttl_minutes if ttl_minutes is not None else config.operator_session_ttl_minutes,
    )
    try:
        asyncio.run(
            _record_local_audit_event(
                uuid.UUID(operation_id),
                "operator_session_created",
                details={
                    "expires_at": session["expires_at"],
                    "issued_from": issued_from,
                },
            )
        )
    except Exception as exc:  # pragma: no cover - defensive logging path
        logger.warning("Failed to record operator session audit event: %s", exc)
    response = {
        "bootstrap_consumed": bootstrap_consumed,
        "issued_from": issued_from,
        "operation_id": operation_id,
        "operator_session_active": True,
        "operator_session_path": str(operator_session_path()),
        "operator_session_expires_at": session["expires_at"],
    }
    if json_output:
        print(json.dumps(response, indent=2, sort_keys=True))
        return 0

    if bootstrap_consumed:
        print("Created local operator session from one-time bootstrap.")
    else:
        print("Refreshed local operator session.")
    print(f"operation_id = {response['operation_id']}")
    print(f"issued_from = {response['issued_from']}")
    print(f"operator_session_file = {response['operator_session_path']}")
    print(f"operator_session_expires_at = {response['operator_session_expires_at']}")
    return 0


def status_operator_session(*, json_output: bool = False) -> int:
    state = read_hub_state()
    bootstrap = read_bootstrap_session()
    session = read_operator_session()
    response = {
        "hub_running": state is not None,
        "operation_id": state.get("operation_id") if state else None,
        "operator_bootstrap_active": bootstrap is not None,
        "operator_bootstrap_expires_at": bootstrap.get("expires_at") if bootstrap else None,
        "operator_bootstrap_path": str(bootstrap_session_path()),
        "operator_session_active": session is not None,
        "operator_session_expires_at": session.get("expires_at") if session else None,
        "operator_session_path": str(operator_session_path()),
    }
    code = 0 if session is not None else 1
    if json_output:
        print(json.dumps(response, indent=2, sort_keys=True))
        return code

    if session is None:
        print("No active local operator session.")
    else:
        print("Local operator session is active.")
    print(f"hub_running = {str(response['hub_running']).lower()}")
    if response["operation_id"]:
        print(f"operation_id = {response['operation_id']}")
    print(f"operator_bootstrap_active = {str(response['operator_bootstrap_active']).lower()}")
    print(f"operator_bootstrap_file = {response['operator_bootstrap_path']}")
    if response["operator_bootstrap_expires_at"]:
        print(f"operator_bootstrap_expires_at = {response['operator_bootstrap_expires_at']}")
    print(f"operator_session_file = {response['operator_session_path']}")
    if response["operator_session_expires_at"]:
        print(f"operator_session_expires_at = {response['operator_session_expires_at']}")
    return code


def logout_operator_session() -> int:
    clear_operator_session()
    print("Local operator session removed.")
    return 0


def show_audit_events(*, limit: int = 20, json_output: bool = False) -> int:
    state = read_hub_state()
    if state is None:
        print("No running Osk hub state found.")
        return 1

    operation_id_raw = str(state.get("operation_id", "")).strip()
    if not operation_id_raw:
        print("Hub state is missing an operation id.")
        return 1

    try:
        events = asyncio.run(_get_audit_events(uuid.UUID(operation_id_raw), max(1, limit)))
    except Exception as exc:
        print(f"Failed to load audit events: {exc}")
        return 1

    if json_output:
        print(json.dumps(events, indent=2, sort_keys=True, default=str))
        return 0

    if not events:
        print("No audit events recorded.")
        return 0

    for event in events:
        timestamp = event.get("timestamp", "unknown")
        actor_type = event.get("actor_type", "unknown")
        action = event.get("action", "unknown")
        actor_member_id = event.get("actor_member_id")
        details = event.get("details") or {}
        detail_text = ""
        if details:
            detail_text = f" details={json.dumps(details, sort_keys=True)}"
        actor_text = f" actor_member_id={actor_member_id}" if actor_member_id else ""
        print(f"{timestamp} {actor_type} {action}{actor_text}{detail_text}")
    return 0


def show_runtime_logs(*, tail: int = 100) -> int:
    log_path = _runtime_log_path()
    if not log_path.exists():
        print("No runtime log file found.")
        return 1

    for line in log_path.read_text().splitlines()[-max(1, tail) :]:
        print(line)
    return 0
