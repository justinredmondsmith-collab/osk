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
import ssl
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from urllib.parse import urlparse

import asyncpg
import uvicorn

from osk.config import OskConfig, load_config, save_config
from osk.connection_manager import ConnectionManager
from osk.db import Database
from osk.hotspot import HotspotManager
from osk.intelligence_service import IntelligenceService
from osk.local_operator import (
    bootstrap_session_path,
    clear_bootstrap_session,
    clear_dashboard_bootstrap,
    clear_dashboard_session,
    clear_operator_session,
    consume_bootstrap_session,
    create_bootstrap_session,
    create_dashboard_bootstrap,
    create_operator_session,
    dashboard_bootstrap_path,
    dashboard_session_path,
    operator_session_path,
    read_bootstrap_session,
    read_dashboard_bootstrap,
    read_dashboard_session,
    read_operator_session,
)
from osk.models import (
    EventCategory,
    EventSeverity,
    FindingNote,
    FindingStatus,
    Member,
    MemberStatus,
)
from osk.operation import OperationManager
from osk.qr import build_join_url, generate_qr_ascii, generate_qr_png
from osk.server import create_app
from osk.storage import StorageManager
from osk.tls import generate_self_signed_cert
from osk.wipe_readiness import summarize_wipe_readiness

logger = logging.getLogger(__name__)
LOCAL_DEV_DATABASE_URL = "postgresql://osk:osk@localhost:5432/osk"
LOCAL_DEV_OLLAMA_URL = "http://localhost:11434"
DEFAULT_LOCAL_SERVICE_NAMES = ("db",)
LOOPBACK_JOIN_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}
LOCAL_OPERATOR_SESSION_HEADER = "X-Osk-Operator-Session"


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
    if config.transcriber_backend == "whisper" and shutil.which(config.ffmpeg_binary) is None:
        issues.append(
            f"missing ffmpeg binary '{config.ffmpeg_binary}' for compressed audio decoding"
        )

    return issues


def hotspot_preflight_status(config: OskConfig) -> dict[str, object]:
    ssid = config.hotspot_ssid or "osk-local"
    manager = HotspotManager(ssid=ssid, band=config.hotspot_band)
    status = manager.status()
    hotspot_ip = status.get("ip_address")
    join_host = str(config.join_host).strip()

    if join_host in LOOPBACK_JOIN_HOSTS:
        join_host_scope = "loopback"
    elif hotspot_ip and join_host == hotspot_ip:
        join_host_scope = "hotspot_ip"
    else:
        join_host_scope = "custom"

    warnings: list[str] = []
    actions: list[str] = []

    available = bool(status.get("available"))
    if available and hotspot_ip:
        hotspot_status = "active"
    elif available:
        hotspot_status = "available_inactive"
        actions.append(
            "Use `osk hotspot up --password <passphrase>` if you want a local hotspot "
            "before field deployment."
        )
    else:
        hotspot_status = "manual_only"
        actions.append(
            "Use `osk hotspot instructions` or your distro network UI for manual hotspot setup."
        )

    if join_host_scope == "loopback":
        warnings.append(
            f"join_host is set to {join_host}, so member QR codes will only work on the "
            "coordinator device."
        )
        if hotspot_ip:
            actions.append(
                "If you want QR joins to target the active hotspot, run "
                f"`osk config --set join_host={hotspot_ip}`."
            )
        else:
            actions.append("Before field use, set `join_host` to a reachable LAN or hotspot IP.")
    elif hotspot_ip and join_host != hotspot_ip:
        warnings.append(
            f"Hotspot IP is {hotspot_ip}, but join_host is {join_host}. Verify member "
            "devices can reach the configured join host."
        )
        actions.append(
            "If you want QR joins to target the active hotspot, run "
            f"`osk config --set join_host={hotspot_ip}`."
        )

    return {
        **status,
        "actions": actions,
        "join_host": join_host,
        "join_host_scope": join_host_scope,
        "recommended_join_host": hotspot_ip,
        "status": hotspot_status,
        "warnings": warnings,
    }


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
    clear_dashboard_bootstrap()
    clear_dashboard_session()
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


async def _get_members(operation_id: uuid.UUID) -> list[dict]:
    config = load_config()
    db = Database()
    await db.connect(config.database_url)
    try:
        return await db.get_members(operation_id)
    finally:
        await db.close()


async def _get_findings(operation_id: uuid.UUID, limit: int) -> list[dict]:
    config = load_config()
    db = Database()
    await db.connect(config.database_url)
    try:
        return await db.get_recent_synthesis_findings(operation_id, limit)
    finally:
        await db.close()


async def _get_review_feed(
    operation_id: uuid.UUID,
    *,
    limit: int,
    include_types: set[str] | None = None,
    finding_status: FindingStatus | None = None,
    severity: EventSeverity | None = None,
    category: EventCategory | None = None,
) -> list[dict]:
    config = load_config()
    db = Database()
    await db.connect(config.database_url)
    try:
        return await db.get_review_feed(
            operation_id,
            limit=limit,
            include_types=include_types,
            finding_status=finding_status,
            severity=severity,
            category=category,
        )
    finally:
        await db.close()


async def _get_finding_detail(operation_id: uuid.UUID, finding_id: uuid.UUID) -> dict | None:
    config = load_config()
    db = Database()
    await db.connect(config.database_url)
    try:
        return await db.get_synthesis_finding_detail(operation_id, finding_id)
    finally:
        await db.close()


async def _get_finding_correlations(
    operation_id: uuid.UUID,
    finding_id: uuid.UUID,
    *,
    limit: int,
    window_minutes: int,
) -> dict | None:
    config = load_config()
    db = Database()
    await db.connect(config.database_url)
    try:
        return await db.get_synthesis_finding_correlations(
            operation_id,
            finding_id,
            limit=limit,
            window_minutes=window_minutes,
        )
    finally:
        await db.close()


async def _update_finding_status(
    operation_id: uuid.UUID,
    finding_id: uuid.UUID,
    status: FindingStatus,
) -> dict | None:
    config = load_config()
    db = Database()
    await db.connect(config.database_url)
    try:
        finding = await db.update_synthesis_finding_status(
            operation_id,
            finding_id,
            status,
            changed_at=dt.datetime.now(dt.timezone.utc),
        )
        if finding is not None:
            await db.insert_audit_event(
                operation_id,
                "system",
                f"finding_{status.value}",
                details={"finding_id": str(finding_id)},
            )
        return finding
    finally:
        await db.close()


async def _escalate_finding(operation_id: uuid.UUID, finding_id: uuid.UUID) -> dict | None:
    config = load_config()
    db = Database()
    await db.connect(config.database_url)
    try:
        finding = await db.escalate_synthesis_finding(
            operation_id,
            finding_id,
            changed_at=dt.datetime.now(dt.timezone.utc),
        )
        if finding is not None:
            await db.insert_audit_event(
                operation_id,
                "system",
                "finding_escalated",
                details={"finding_id": str(finding_id)},
            )
        return finding
    finally:
        await db.close()


async def _add_finding_note(
    operation_id: uuid.UUID,
    finding_id: uuid.UUID,
    text: str,
) -> FindingNote | None:
    config = load_config()
    db = Database()
    await db.connect(config.database_url)
    try:
        finding = await db.get_synthesis_finding(operation_id, finding_id)
        if finding is None:
            return None
        note = FindingNote(
            operation_id=operation_id,
            finding_id=finding_id,
            text=text,
        )
        await db.insert_synthesis_finding_note(note)
        await db.insert_audit_event(
            operation_id,
            "system",
            "finding_note_added",
            details={"finding_id": str(finding_id), "note_id": str(note.id)},
        )
        return note
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


def _parse_operation_id(operation_id: str | None) -> uuid.UUID | None:
    if not operation_id:
        return None
    try:
        return uuid.UUID(str(operation_id))
    except (ValueError, TypeError):
        return None


def _try_record_local_audit_event(
    operation_id: str | None,
    action: str,
    *,
    details: dict | None = None,
) -> None:
    operation_uuid = _parse_operation_id(operation_id)
    if operation_uuid is None:
        return
    try:
        asyncio.run(_record_local_audit_event(operation_uuid, action, details=details))
    except Exception as exc:  # pragma: no cover - defensive logging path
        logger.warning("Failed to record local audit event %s: %s", action, exc)


def _resolve_bootstrap_state(operation_id: str | None) -> tuple[str, dict[str, object] | None]:
    existed = bootstrap_session_path().exists()
    payload = read_bootstrap_session()
    if payload is None:
        if existed:
            _try_record_local_audit_event(
                operation_id,
                "operator_bootstrap_expired",
                details={"path": str(bootstrap_session_path())},
            )
            return "expired_or_invalid", None
        return "missing", None

    if operation_id and payload.get("operation_id") != operation_id:
        return "wrong_operation", payload
    return "active", payload


def _resolve_dashboard_bootstrap_state(
    operation_id: str | None,
) -> tuple[str, dict[str, object] | None]:
    existed = dashboard_bootstrap_path().exists()
    payload = read_dashboard_bootstrap()
    if payload is None:
        if existed:
            _try_record_local_audit_event(
                operation_id,
                "dashboard_bootstrap_expired",
                details={"path": str(dashboard_bootstrap_path())},
            )
            return "expired_or_invalid", None
        return "missing", None

    if operation_id and payload.get("operation_id") != operation_id:
        return "wrong_operation", payload
    return "active", payload


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
    intelligence_service: IntelligenceService | None = None
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
        intelligence_service = IntelligenceService(
            config=config,
            db=db,
            operation_manager=op_manager,
            conn_manager=conn_manager,
        )
        await intelligence_service.start()

        hotspot = hotspot_preflight_status(config)
        join_url = build_join_url(config.join_host, config.hub_port, operation.token)
        qr_path = _config_root() / "join-qr.png"
        generate_qr_png(join_url, qr_path)
        clear_dashboard_bootstrap()
        clear_dashboard_session()
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
        print(
            "Intelligence backends: "
            f"transcriber={config.transcriber_backend} "
            f"vision={config.vision_backend}"
        )
        print(f"Runtime log file: {_runtime_log_path()}")
        print(f"Service mode: {local_service_mode(config)}")
        print(f"Storage backend: {storage.backend}")
        print(
            "Hotspot readiness: "
            f"{hotspot['status']} (ssid={hotspot['ssid']}, "
            f"ip={hotspot['ip_address'] or 'unknown'})"
        )
        print(f"Join host: {hotspot['join_host']}")
        if hotspot["warnings"]:
            print("Field network guidance:")
            for warning in hotspot["warnings"]:
                print(f"- {warning}")
        for action in hotspot["actions"]:
            print(f"- {action}")
        print(generate_qr_ascii(join_url))
        print(f"PNG QR: {qr_path}\n")

        app = create_app(
            op_manager=op_manager,
            conn_manager=conn_manager,
            db=db,
            intelligence_service=intelligence_service,
        )
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
        clear_dashboard_bootstrap()
        clear_dashboard_session()
        clear_bootstrap_session()
        clear_operator_session()
        await conn_manager.broadcast({"type": "op_ended"})
        if intelligence_service is not None:
            await intelligence_service.stop()
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
    log_path = _configure_runtime_log_handler()
    try:
        logger.info("Starting Osk hub runtime; log file at %s", log_path)
        asyncio.run(run_hub(name))
    except HubBootstrapError as exc:
        logger.error("Hub bootstrap failed: %s", exc)
        print(exc)
        print(f"Runtime log: {log_path}")
        return 1
    except KeyboardInterrupt:
        return 0
    except Exception as exc:  # pragma: no cover - defensive startup path
        logger.exception("Osk hub failed unexpectedly: %s", exc)
        print(f"Osk hub failed unexpectedly: {exc}")
        print(f"Runtime log: {log_path}")
        return 1
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
        clear_dashboard_bootstrap()
        clear_dashboard_session()
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
    clear_dashboard_bootstrap()
    clear_dashboard_session()
    clear_bootstrap_session()
    clear_operator_session()
    if stop_services:
        stop_local_services(config)
    print("Osk hub stopped.")
    return 0


def _active_operator_session_for_operation(operation_id: str) -> dict[str, object] | None:
    session = read_operator_session()
    if session is None or session.get("operation_id") != operation_id:
        return None
    token = session.get("token")
    if not isinstance(token, str) or not token.strip():
        return None
    return session


def _trigger_live_wipe_broadcast(port: int, operation_id: str) -> dict[str, object]:
    session = _active_operator_session_for_operation(operation_id)
    if session is None:
        return {
            "ok": False,
            "error": "No active local operator session. Run `osk operator login` first.",
        }

    request = urllib.request.Request(
        f"https://127.0.0.1:{port}/api/wipe",
        method="POST",
        headers={LOCAL_OPERATOR_SESSION_HEADER: str(session["token"])},
        data=b"{}",
    )
    context = ssl._create_unverified_context()

    try:
        with urllib.request.urlopen(request, context=context, timeout=5.0) as response:
            body = response.read()
            payload = json.loads(body.decode("utf-8")) if body else {}
            return {
                "ok": True,
                "status_code": getattr(response, "status", 200),
                "response": payload,
                "operator_session_expires_at": session.get("expires_at"),
            }
    except urllib.error.HTTPError as exc:
        try:
            detail_text = exc.read().decode("utf-8")
        except Exception:
            detail_text = ""
        return {
            "ok": False,
            "status_code": exc.code,
            "error": detail_text or str(exc),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def wipe_hub(
    *,
    wait_seconds: float = 10.0,
    stop_services: bool = False,
    destroy_evidence: bool = False,
    json_output: bool = False,
) -> int:
    state = read_hub_state()
    if state is None:
        message = (
            "No running Osk hub state found. Run `osk drill wipe` for the current cleanup boundary."
        )
        if json_output:
            print(json.dumps({"error": message, "status": "not_running"}, indent=2, sort_keys=True))
        else:
            print(message)
        return 1

    operation_id = str(state.get("operation_id", "")).strip()
    port = state.get("port")
    if not operation_id or not isinstance(port, int):
        message = "Hub state is missing operation or port metadata."
        if json_output:
            print(
                json.dumps(
                    {
                        "error": message,
                        "operation_id": operation_id or None,
                        "status": "invalid_state",
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(message)
        return 1

    wipe_result = _trigger_live_wipe_broadcast(port, operation_id)
    if not wipe_result["ok"]:
        message = f"Failed to trigger live wipe: {wipe_result['error']}"
        if json_output:
            print(
                json.dumps(
                    {
                        "broadcast": None,
                        "error": str(wipe_result["error"]),
                        "operation_id": operation_id,
                        "status": "broadcast_failed",
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(message)
        return 1

    stop_code = stop_hub(wait_seconds=wait_seconds, stop_services=stop_services)
    evidence_result: dict[str, object] | None = None

    if stop_code == 0 and destroy_evidence:
        from osk.evidence import EvidenceManager

        try:
            manager = EvidenceManager.from_storage(default_storage_manager(load_config()))
            evidence_result = manager.destroy()
        except Exception as exc:
            evidence_result = {"ok": False, "error": str(exc)}

    payload = {
        "broadcast": wipe_result.get("response") or {"status": "wipe_initiated"},
        "destroy_evidence_requested": destroy_evidence,
        "evidence": evidence_result,
        "hub_stopped": stop_code == 0,
        "operation_id": operation_id,
        "stop_services": stop_services,
    }

    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
        if stop_code != 0:
            return 1
        if destroy_evidence and evidence_result is not None and not evidence_result.get("ok"):
            return 1
        return 0

    print("Live wipe broadcast sent to connected members.")
    print(f"operation_id = {operation_id}")
    broadcast = wipe_result.get("response") or {}
    if isinstance(broadcast, dict):
        if "broadcast_target_count" in broadcast:
            print(f"broadcast_target_count = {broadcast['broadcast_target_count']}")
        wipe_readiness = broadcast.get("wipe_readiness")
        if isinstance(wipe_readiness, dict):
            print(f"wipe_readiness = {wipe_readiness.get('status')}")
            print(f"wipe_summary = {wipe_readiness.get('summary')}")
    if stop_code != 0:
        print("Hub stop did not complete cleanly after the wipe broadcast.")
        return 1

    print("Hub stopped.")
    if destroy_evidence:
        if evidence_result is None:
            print("Preserved evidence destroy was requested but no result was captured.")
            return 1
        if evidence_result.get("ok"):
            print(f"Preserved evidence destroyed at {evidence_result['destroyed_path']}.")
        else:
            print(f"Failed to destroy preserved evidence: {evidence_result['error']}")
            return 1
    else:
        print(
            "Preserved evidence retained. Use `osk evidence destroy --yes` for permanent removal."
        )
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
        "dashboard_bootstrap_path": str(dashboard_bootstrap_path()),
        "dashboard_session_path": str(dashboard_session_path()),
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
    bootstrap_status, bootstrap = _resolve_bootstrap_state(
        str(operation_id) if operation_id else None
    )
    if bootstrap is not None:
        snapshot["operator_bootstrap_active"] = True
        snapshot["operator_bootstrap_expires_at"] = bootstrap.get("expires_at")
    else:
        snapshot["operator_bootstrap_active"] = False
        snapshot["operator_bootstrap_expires_at"] = None
    snapshot["operator_bootstrap_status"] = bootstrap_status
    dashboard_bootstrap_status, dashboard_bootstrap = _resolve_dashboard_bootstrap_state(
        str(operation_id) if operation_id else None
    )
    if dashboard_bootstrap is not None:
        snapshot["dashboard_bootstrap_active"] = True
        snapshot["dashboard_bootstrap_expires_at"] = dashboard_bootstrap.get("expires_at")
    else:
        snapshot["dashboard_bootstrap_active"] = False
        snapshot["dashboard_bootstrap_expires_at"] = None
    snapshot["dashboard_bootstrap_status"] = dashboard_bootstrap_status
    if session := read_operator_session():
        snapshot["operator_session_active"] = True
        snapshot["operator_session_expires_at"] = session.get("expires_at")
    else:
        snapshot["operator_session_active"] = False
        snapshot["operator_session_expires_at"] = None
    if dashboard_session := read_dashboard_session():
        snapshot["dashboard_session_active"] = True
        snapshot["dashboard_session_expires_at"] = dashboard_session.get("expires_at")
    else:
        snapshot["dashboard_session_active"] = False
        snapshot["dashboard_session_expires_at"] = None

    operation_uuid = _parse_operation_id(str(operation_id) if operation_id else None)
    if operation_uuid is not None:
        try:
            cfg = load_config()
            rows = asyncio.run(_get_members(operation_uuid))
            members = [
                _member_snapshot(
                    row, heartbeat_timeout_seconds=cfg.member_heartbeat_timeout_seconds
                )
                for row in rows
            ]
            snapshot["wipe_readiness"] = summarize_wipe_readiness(members)
        except Exception as exc:
            snapshot["wipe_readiness"] = {
                "available": False,
                "error": str(exc),
                "status": "unknown",
            }

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
    if bootstrap_status := snapshot.get("operator_bootstrap_status"):
        print(f"operator_bootstrap_status = {bootstrap_status}")
    if bootstrap_expires_at := snapshot.get("operator_bootstrap_expires_at"):
        print(f"operator_bootstrap_expires_at = {bootstrap_expires_at}")
    if dashboard_session_path_value := snapshot.get("dashboard_session_path"):
        print(f"dashboard_session_file = {dashboard_session_path_value}")
    if dashboard_session_expires_at := snapshot.get("dashboard_session_expires_at"):
        print(f"dashboard_session_expires_at = {dashboard_session_expires_at}")
    if dashboard_bootstrap_path_value := snapshot.get("dashboard_bootstrap_path"):
        print(f"dashboard_bootstrap_file = {dashboard_bootstrap_path_value}")
    if dashboard_bootstrap_status := snapshot.get("dashboard_bootstrap_status"):
        print(f"dashboard_bootstrap_status = {dashboard_bootstrap_status}")
    if dashboard_bootstrap_expires_at := snapshot.get("dashboard_bootstrap_expires_at"):
        print(f"dashboard_bootstrap_expires_at = {dashboard_bootstrap_expires_at}")
    if runtime_log_path := snapshot.get("runtime_log_path"):
        print(f"runtime_log_file = {runtime_log_path}")
    wipe_readiness = snapshot.get("wipe_readiness")
    if isinstance(wipe_readiness, dict):
        if wipe_readiness.get("available") is False:
            print(f"wipe_readiness = unknown ({wipe_readiness.get('error')})")
        else:
            print(f"wipe_readiness = {wipe_readiness.get('status')}")
            print(f"wipe_summary = {wipe_readiness.get('summary')}")
            print(f"wipe_at_risk_members = {wipe_readiness.get('at_risk_members')}")

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
        bootstrap_status, bootstrap = _resolve_bootstrap_state(operation_id)
        if bootstrap is None:
            if bootstrap_status == "expired_or_invalid":
                print("Operator bootstrap expired before it could be used.")
            elif bootstrap_status == "wrong_operation":
                print("Operator bootstrap belongs to a different operation.")
            else:
                print("No active operator bootstrap is available for this hub instance.")
            return 1
        if bootstrap_status == "wrong_operation":
            print("Operator bootstrap belongs to a different operation.")
            return 1
        bootstrap_token = bootstrap.get("bootstrap_token")
        if not isinstance(bootstrap_token, str):
            print("Operator bootstrap file is invalid.")
            clear_bootstrap_session()
            _try_record_local_audit_event(
                operation_id,
                "operator_bootstrap_invalid",
                details={"path": str(bootstrap_session_path())},
            )
            return 1
        if not consume_bootstrap_session(operation_id, bootstrap_token):
            print("Operator bootstrap could not be consumed.")
            return 1
        issued_from = "bootstrap"
        bootstrap_consumed = True

    clear_dashboard_bootstrap()
    clear_dashboard_session()
    session = create_operator_session(
        operation_id,
        ttl_minutes if ttl_minutes is not None else config.operator_session_ttl_minutes,
    )
    _try_record_local_audit_event(
        operation_id,
        "operator_session_created" if bootstrap_consumed else "operator_session_refreshed",
        details={
            "expires_at": session["expires_at"],
            "issued_from": issued_from,
        },
    )
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
    operation_id = str(state.get("operation_id")) if state and state.get("operation_id") else None
    bootstrap_status, bootstrap = _resolve_bootstrap_state(operation_id)
    session = read_operator_session()
    response = {
        "hub_running": state is not None,
        "operation_id": operation_id,
        "operator_bootstrap_active": bootstrap is not None,
        "operator_bootstrap_expires_at": bootstrap.get("expires_at") if bootstrap else None,
        "operator_bootstrap_path": str(bootstrap_session_path()),
        "operator_bootstrap_status": bootstrap_status,
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
    print(f"operator_bootstrap_status = {response['operator_bootstrap_status']}")
    if response["operator_bootstrap_expires_at"]:
        print(f"operator_bootstrap_expires_at = {response['operator_bootstrap_expires_at']}")
    print(f"operator_session_file = {response['operator_session_path']}")
    if response["operator_session_expires_at"]:
        print(f"operator_session_expires_at = {response['operator_session_expires_at']}")
    return code


def logout_operator_session() -> int:
    state = read_hub_state()
    session = read_operator_session()
    if session is not None:
        operation_id = (
            str(state.get("operation_id")) if state and state.get("operation_id") else None
        )
        _try_record_local_audit_event(
            operation_id,
            "operator_session_logged_out",
            details={"expires_at": session.get("expires_at")},
        )
    clear_dashboard_bootstrap()
    clear_dashboard_session()
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


def _member_snapshot(row: dict, *, heartbeat_timeout_seconds: int) -> dict[str, object]:
    member = Member.model_validate(row)
    now = dt.datetime.now(dt.timezone.utc)
    last_seen_at = member.last_seen_at.astimezone(dt.timezone.utc)
    seconds_since_last_seen = max(int((now - last_seen_at).total_seconds()), 0)
    if member.status != MemberStatus.CONNECTED:
        heartbeat_state = member.status.value
    elif seconds_since_last_seen >= heartbeat_timeout_seconds:
        heartbeat_state = "stale"
    else:
        heartbeat_state = "fresh"

    return {
        "id": str(member.id),
        "name": member.name,
        "role": member.role.value,
        "status": member.status.value,
        "heartbeat_state": heartbeat_state,
        "seconds_since_last_seen": seconds_since_last_seen,
        "last_seen_at": last_seen_at.isoformat().replace("+00:00", "Z"),
        "connected_at": member.connected_at.astimezone(dt.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "last_gps_at": (
            member.last_gps_at.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")
            if member.last_gps_at
            else None
        ),
        "latitude": member.latitude,
        "longitude": member.longitude,
    }


def show_members(*, json_output: bool = False) -> int:
    state = read_hub_state()
    if state is None:
        print("No running Osk hub state found.")
        return 1

    operation_id_raw = str(state.get("operation_id", "")).strip()
    if not operation_id_raw:
        print("Hub state is missing an operation id.")
        return 1

    operation_uuid = _parse_operation_id(operation_id_raw)
    if operation_uuid is None:
        print("Hub state contains an invalid operation id.")
        return 1

    cfg = load_config()
    try:
        rows = asyncio.run(_get_members(operation_uuid))
    except Exception as exc:
        print(f"Failed to load members: {exc}")
        return 1

    members = [
        _member_snapshot(row, heartbeat_timeout_seconds=cfg.member_heartbeat_timeout_seconds)
        for row in rows
    ]
    if json_output:
        print(json.dumps(members, indent=2, sort_keys=True))
        return 0

    if not members:
        print("No members recorded.")
        return 0

    for member in members:
        coords = ""
        if member["latitude"] is not None and member["longitude"] is not None:
            coords = f" gps={member['latitude']},{member['longitude']}"
        print(
            f"{member['name']} role={member['role']} status={member['status']} "
            f"heartbeat={member['heartbeat_state']} last_seen={member['last_seen_at']}"
            f"{coords} id={member['id']}"
        )
    wipe_readiness = summarize_wipe_readiness(members)
    print(f"wipe_readiness = {wipe_readiness['status']}")
    print(f"wipe_summary = {wipe_readiness['summary']}")
    if wipe_readiness["at_risk"]:
        for member in wipe_readiness["at_risk"][:5]:
            print(
                "wipe_risk "
                f"name={member['name']} reason={member['reason']} "
                f"last_seen={member['last_seen_at']}"
            )
    return 0


def show_dashboard_url(*, json_output: bool = False) -> int:
    config = load_config()
    state = read_hub_state()
    if state is None:
        print("No running Osk hub state found.")
        return 1

    operation_id = str(state.get("operation_id", "")).strip()
    port = state.get("port")
    if not operation_id or not port:
        print("Hub state is missing operation or port metadata.")
        return 1

    session = read_operator_session()
    if session is None or session.get("operation_id") != operation_id:
        print("No active local operator session. Run `osk operator login` first.")
        return 1

    clear_dashboard_bootstrap()
    clear_dashboard_session()
    bootstrap = create_dashboard_bootstrap(
        operation_id,
        config.dashboard_bootstrap_ttl_minutes,
    )
    dashboard_code = bootstrap.get("dashboard_code")
    if not isinstance(dashboard_code, str) or not dashboard_code.strip():
        clear_dashboard_bootstrap()
        print("Dashboard bootstrap file is invalid.")
        return 1
    _try_record_local_audit_event(
        operation_id,
        "dashboard_bootstrap_created",
        details={"expires_at": bootstrap.get("expires_at")},
    )

    url = f"https://127.0.0.1:{port}/coordinator"
    payload = {
        "dashboard_bootstrap_expires_at": bootstrap.get("expires_at"),
        "dashboard_code": dashboard_code,
        "operation_id": operation_id,
        "operation_name": state.get("operation_name"),
        "url": url,
        "operator_session_expires_at": session.get("expires_at"),
    }

    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    print(url)
    print(f"dashboard_code = {dashboard_code}")
    if bootstrap_expires_at := bootstrap.get("expires_at"):
        print(f"dashboard_code_expires_at = {bootstrap_expires_at}")
    return 0


def show_findings(*, limit: int = 20, json_output: bool = False) -> int:
    state = read_hub_state()
    if state is None:
        print("No running Osk hub state found.")
        return 1

    operation_id_raw = str(state.get("operation_id", "")).strip()
    if not operation_id_raw:
        print("Hub state is missing an operation id.")
        return 1

    operation_uuid = _parse_operation_id(operation_id_raw)
    if operation_uuid is None:
        print("Hub state contains an invalid operation id.")
        return 1

    try:
        findings = asyncio.run(_get_findings(operation_uuid, max(1, limit)))
    except Exception as exc:
        print(f"Failed to load findings: {exc}")
        return 1

    if json_output:
        print(json.dumps(findings, indent=2, sort_keys=True, default=str))
        return 0

    if not findings:
        print("No synthesis findings recorded.")
        return 0

    for finding in findings:
        title = finding.get("title", "Untitled Finding")
        severity = finding.get("severity", "unknown")
        status = finding.get("status", "unknown")
        last_seen_at = finding.get("last_seen_at", "unknown")
        summary = finding.get("summary", "")
        corroborated = " corroborated" if finding.get("corroborated") else ""
        print(
            f"{title} severity={severity} status={status}{corroborated} "
            f"last_seen={last_seen_at} summary={summary}"
        )
    return 0


def show_review_feed(
    *,
    limit: int = 25,
    include_types: set[str] | None = None,
    finding_status: FindingStatus | None = None,
    severity: EventSeverity | None = None,
    category: EventCategory | None = None,
    json_output: bool = False,
) -> int:
    state = read_hub_state()
    if state is None:
        print("No running Osk hub state found.")
        return 1

    operation_uuid = _parse_operation_id(str(state.get("operation_id", "")).strip())
    if operation_uuid is None:
        print("Hub state contains an invalid operation id.")
        return 1

    try:
        items = asyncio.run(
            _get_review_feed(
                operation_uuid,
                limit=max(1, limit),
                include_types=include_types,
                finding_status=finding_status,
                severity=severity,
                category=category,
            )
        )
    except Exception as exc:
        print(f"Failed to load review feed: {exc}")
        return 1

    if json_output:
        print(json.dumps(items, indent=2, sort_keys=True, default=str))
        return 0

    if not items:
        print("No review items recorded.")
        return 0

    for item in items:
        item_type = item.get("type", "item")
        timestamp = item.get("timestamp", "unknown")
        title = item.get("title", item_type.title())
        summary = item.get("summary", "")
        if item_type == "finding":
            print(
                f"[finding] {timestamp} severity={item.get('severity')} "
                f"status={item.get('status')} title={title} summary={summary}"
            )
            continue
        if item_type == "event":
            print(
                f"[event] {timestamp} severity={item.get('severity')} "
                f"category={item.get('category')} title={title} summary={summary}"
            )
            continue
        if item_type == "sitrep":
            print(f"[sitrep] {timestamp} trend={item.get('trend', 'stable')} summary={summary}")
            continue
        print(f"[{item_type}] {timestamp} title={title} summary={summary}")
    return 0


def show_finding(finding_id: str, *, json_output: bool = False) -> int:
    state = read_hub_state()
    if state is None:
        print("No running Osk hub state found.")
        return 1

    operation_uuid = _parse_operation_id(str(state.get("operation_id", "")).strip())
    if operation_uuid is None:
        print("Hub state contains an invalid operation id.")
        return 1
    finding_uuid = _parse_operation_id(finding_id)
    if finding_uuid is None:
        print("Invalid finding id.")
        return 1

    try:
        detail = asyncio.run(_get_finding_detail(operation_uuid, finding_uuid))
    except Exception as exc:
        print(f"Failed to load finding: {exc}")
        return 1

    if detail is None:
        print("Finding not found.")
        return 1

    if json_output:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str))
        return 0

    finding = detail["finding"]
    print(
        f"{finding['title']} severity={finding['severity']} status={finding['status']} "
        f"last_seen={finding['last_seen_at']}"
    )
    print(f"summary={finding['summary']}")
    print(
        f"sources={finding['source_count']} signals={finding['signal_count']} "
        f"observations={finding['observation_count']} notes={finding['notes_count']}"
    )
    if detail["events"]:
        latest_event = detail["events"][0]
        print(
            "latest_event="
            f"{latest_event.get('category')}:{latest_event.get('severity')} "
            f"{latest_event.get('text')}"
        )
    for note in detail["notes"][:3]:
        print(f"note[{note.get('created_at')}] {note.get('text')}")
    return 0


def acknowledge_finding(finding_id: str) -> int:
    return _apply_finding_status(finding_id, FindingStatus.ACKNOWLEDGED, "acknowledged")


def resolve_finding(finding_id: str) -> int:
    return _apply_finding_status(finding_id, FindingStatus.RESOLVED, "resolved")


def reopen_finding(finding_id: str) -> int:
    return _apply_finding_status(finding_id, FindingStatus.OPEN, "reopened")


def show_finding_correlations(
    finding_id: str,
    *,
    limit: int = 10,
    window_minutes: int = 30,
    json_output: bool = False,
) -> int:
    state = read_hub_state()
    if state is None:
        print("No running Osk hub state found.")
        return 1
    operation_uuid = _parse_operation_id(str(state.get("operation_id", "")).strip())
    finding_uuid = _parse_operation_id(finding_id)
    if operation_uuid is None or finding_uuid is None:
        print("Invalid operation or finding id.")
        return 1

    try:
        correlations = asyncio.run(
            _get_finding_correlations(
                operation_uuid,
                finding_uuid,
                limit=max(1, limit),
                window_minutes=max(1, window_minutes),
            )
        )
    except Exception as exc:
        print(f"Failed to load finding correlations: {exc}")
        return 1
    if correlations is None:
        print("Finding not found.")
        return 1

    if json_output:
        print(json.dumps(correlations, indent=2, sort_keys=True, default=str))
        return 0

    finding = correlations["finding"]
    print(
        f"Correlations for {finding.get('title', 'finding')} "
        f"window={correlations.get('window_minutes')}m"
    )
    if not correlations["related_findings"] and not correlations["related_events"]:
        print("No correlated findings or events.")
        return 0
    for related in correlations["related_findings"]:
        reasons = ",".join(related.get("correlation_reasons", []))
        print(
            f"finding severity={related.get('severity')} status={related.get('status')} "
            f"title={related.get('title')} reasons={reasons}"
        )
    for related in correlations["related_events"]:
        reasons = ",".join(related.get("correlation_reasons", []))
        print(
            f"event severity={related.get('severity')} category={related.get('category')} "
            f"reasons={reasons} text={related.get('text')}"
        )
    return 0


def escalate_finding(finding_id: str) -> int:
    state = read_hub_state()
    if state is None:
        print("No running Osk hub state found.")
        return 1
    operation_uuid = _parse_operation_id(str(state.get("operation_id", "")).strip())
    finding_uuid = _parse_operation_id(finding_id)
    if operation_uuid is None or finding_uuid is None:
        print("Invalid operation or finding id.")
        return 1

    try:
        finding = asyncio.run(_escalate_finding(operation_uuid, finding_uuid))
    except Exception as exc:
        print(f"Failed to escalate finding: {exc}")
        return 1
    if finding is None:
        print("Finding not found.")
        return 1
    print(f"Escalated {finding.get('title', 'finding')} to severity={finding.get('severity')}.")
    return 0


def add_finding_note(finding_id: str, text: str) -> int:
    note_text = text.strip()
    if not note_text:
        print("Note text is required.")
        return 1
    state = read_hub_state()
    if state is None:
        print("No running Osk hub state found.")
        return 1
    operation_uuid = _parse_operation_id(str(state.get("operation_id", "")).strip())
    finding_uuid = _parse_operation_id(finding_id)
    if operation_uuid is None or finding_uuid is None:
        print("Invalid operation or finding id.")
        return 1
    try:
        note = asyncio.run(_add_finding_note(operation_uuid, finding_uuid, note_text))
    except Exception as exc:
        print(f"Failed to add note: {exc}")
        return 1
    if note is None:
        print("Finding not found.")
        return 1
    print(f"Added note {note.id} to finding {finding_id}.")
    return 0


def _apply_finding_status(
    finding_id: str,
    status: FindingStatus,
    verb: str,
) -> int:
    state = read_hub_state()
    if state is None:
        print("No running Osk hub state found.")
        return 1
    operation_uuid = _parse_operation_id(str(state.get("operation_id", "")).strip())
    finding_uuid = _parse_operation_id(finding_id)
    if operation_uuid is None or finding_uuid is None:
        print("Invalid operation or finding id.")
        return 1
    try:
        finding = asyncio.run(_update_finding_status(operation_uuid, finding_uuid, status))
    except Exception as exc:
        print(f"Failed to update finding: {exc}")
        return 1
    if finding is None:
        print("Finding not found.")
        return 1
    print(f"{verb.capitalize()} {finding.get('title', 'finding')}.")
    return 0


def show_runtime_logs(*, tail: int = 100) -> int:
    log_path = _runtime_log_path()
    if not log_path.exists():
        print("No runtime log file found.")
        return 1

    for line in log_path.read_text().splitlines()[-max(1, tail) :]:
        print(line)
    return 0
