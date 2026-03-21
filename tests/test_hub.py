from __future__ import annotations

import asyncio
from pathlib import Path
import signal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from osk.config import OskConfig
from osk.hub import (
    HubBootstrapError,
    _find_compose_command,
    _compose_environment,
    default_storage_manager,
    ensure_local_services,
    ensure_hub_not_running,
    installation_issues,
    local_database_port,
    local_service_mode,
    read_hub_state,
    run_hub_sync,
    hub_status_snapshot,
    status_hub,
    stop_hub,
    uses_local_dev_services,
    wait_for_database,
    watch_for_stop_request,
)


def test_installation_issues_report_missing_assets(tmp_path: Path) -> None:
    config = OskConfig(
        tls_cert_path=str(tmp_path / "cert.pem"),
        tls_key_path=str(tmp_path / "key.pem"),
    )
    storage = default_storage_manager(config)
    storage.luks_image_path = tmp_path / "evidence.luks"
    issues = installation_issues(config, storage)
    assert len(issues) == 3
    assert any("missing TLS certificate" in issue for issue in issues)
    assert any("missing TLS key" in issue for issue in issues)
    assert any("missing encrypted evidence volume" in issue for issue in issues)


def test_installation_issues_skip_luks_requirement_for_directory_backend(tmp_path: Path) -> None:
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    cert_path.write_text("cert")
    key_path.write_text("key")
    config = OskConfig(
        tls_cert_path=str(cert_path),
        tls_key_path=str(key_path),
        storage_backend="directory",
    )
    storage = default_storage_manager(config)
    issues = installation_issues(config, storage)
    assert issues == []


def test_uses_local_dev_services_for_defaults() -> None:
    config = OskConfig()
    assert uses_local_dev_services(config) is True
    assert local_service_mode(config) == "compose-managed local services"


def test_uses_local_dev_services_false_for_external_database() -> None:
    config = OskConfig(database_url="postgresql://example.com:5432/osk")
    assert uses_local_dev_services(config) is False
    assert local_service_mode(config) == "externally managed services"


def test_uses_local_dev_services_true_for_localhost_alt_port() -> None:
    config = OskConfig(database_url="postgresql://osk:osk@localhost:55432/osk")
    assert uses_local_dev_services(config) is True
    assert local_database_port(config) == 55432


@patch("osk.hub.subprocess.run")
def test_ensure_local_services_skips_when_config_uses_external_services(mock_run: MagicMock) -> None:
    config = OskConfig(database_url="postgresql://db.internal:5432/osk")
    ensure_local_services(config)
    mock_run.assert_not_called()


@patch("osk.hub.subprocess.run")
@patch("osk.hub.shutil.which", return_value="/usr/bin/docker")
def test_ensure_local_services_starts_compose(mock_which: MagicMock, mock_run: MagicMock) -> None:
    ensure_local_services(OskConfig())
    mock_which.assert_called_once_with("docker")
    assert mock_run.call_args.args[0][-1:] == ["db"]
    assert mock_run.call_args.kwargs["env"]["OSK_POSTGRES_PORT"] == "5432"


@patch("osk.hub.shutil.which", side_effect=[None, "/usr/bin/podman"])
def test_find_compose_command_falls_back_to_podman(mock_which: MagicMock) -> None:
    assert _find_compose_command() == ["/usr/bin/podman", "compose"]
    assert mock_which.call_count == 2


@patch("osk.hub.shutil.which", side_effect=[None, None, "/usr/local/bin/docker-compose"])
def test_find_compose_command_falls_back_to_docker_compose(mock_which: MagicMock) -> None:
    assert _find_compose_command() == ["/usr/local/bin/docker-compose"]
    assert mock_which.call_count == 3


@patch("osk.hub.shutil.which", return_value=None)
def test_ensure_local_services_requires_compose_runtime(mock_which: MagicMock) -> None:
    with pytest.raises(HubBootstrapError):
        ensure_local_services(OskConfig())
    assert mock_which.call_count >= 1


@patch("osk.hub.asyncio.run", side_effect=HubBootstrapError("boom"))
def test_run_hub_sync_returns_error_code_on_bootstrap_failure(mock_run: MagicMock, capsys) -> None:
    code = run_hub_sync("Test Op")
    out = capsys.readouterr().out
    assert code == 1
    assert "boom" in out
    mock_run.assert_called_once()


async def test_wait_for_database_retries_until_ready() -> None:
    connection = MagicMock()
    connection.close = AsyncMock()
    connect = AsyncMock(side_effect=[RuntimeError("not ready"), connection])

    with patch("osk.hub.asyncpg.connect", connect), patch("osk.hub.asyncio.sleep", AsyncMock()):
        await wait_for_database("postgresql://osk:osk@localhost:5432/osk", timeout_seconds=2)

    assert connect.await_count == 2
    connection.close.assert_awaited_once()


def test_compose_environment_uses_database_port() -> None:
    config = OskConfig(database_url="postgresql://osk:osk@127.0.0.1:55432/osk")
    env = _compose_environment(config)
    assert env["OSK_POSTGRES_PORT"] == "55432"


def test_read_hub_state_missing(tmp_path: Path) -> None:
    with patch("osk.hub._config_root", return_value=tmp_path):
        assert read_hub_state() is None


def test_ensure_hub_not_running_cleans_stale_state(tmp_path: Path) -> None:
    state_path = tmp_path / "hub-state.json"
    stop_path = tmp_path / "hub-stop-request.json"
    state_path.write_text('{"pid": 999999, "operation_name": "Old Op"}\n')
    stop_path.write_text('{"requested_at": 1}\n')
    with patch("osk.hub._config_root", return_value=tmp_path):
        ensure_hub_not_running()
    assert not state_path.exists()
    assert not stop_path.exists()


def test_ensure_hub_not_running_raises_for_live_pid(tmp_path: Path) -> None:
    state_path = tmp_path / "hub-state.json"
    state_path.write_text('{"pid": 1234, "operation_name": "Live Op"}\n')
    with patch("osk.hub._config_root", return_value=tmp_path), patch(
        "osk.hub._pid_is_running",
        return_value=True,
    ):
        with pytest.raises(HubBootstrapError):
            ensure_hub_not_running()


@patch("osk.hub.stop_local_services")
@patch("osk.hub.os.kill")
@patch("osk.hub.time.sleep")
def test_stop_hub_requests_graceful_shutdown(
    mock_sleep: MagicMock,
    mock_kill: MagicMock,
    mock_stop_local_services: MagicMock,
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "hub-state.json"
    stop_path = tmp_path / "hub-stop-request.json"
    state_path.write_text('{"pid": 4321, "operation_name": "March"}\n')
    with patch("osk.hub._config_root", return_value=tmp_path), patch(
        "osk.hub._pid_is_running",
        side_effect=[True, True, False, False, False],
    ), patch("osk.hub.time.monotonic", side_effect=[0.0, 0.0, 0.1]), patch(
        "osk.hub.load_config",
        return_value=OskConfig(),
    ):
        code = stop_hub(wait_seconds=1, stop_services=True)

    assert code == 0
    mock_kill.assert_not_called()
    mock_stop_local_services.assert_called_once()
    assert not state_path.exists()
    assert not stop_path.exists()


@patch("osk.hub.os.kill")
@patch("osk.hub.time.sleep")
def test_stop_hub_falls_back_to_sigterm(
    mock_sleep: MagicMock,
    mock_kill: MagicMock,
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "hub-state.json"
    stop_path = tmp_path / "hub-stop-request.json"
    state_path.write_text('{"pid": 4321, "operation_name": "March"}\n')
    with patch("osk.hub._config_root", return_value=tmp_path), patch(
        "osk.hub._pid_is_running",
        side_effect=[True, True, True, False, False],
    ), patch("osk.hub.time.monotonic", side_effect=[0.0, 0.0, 0.3, 0.1]), patch(
        "osk.hub.load_config",
        return_value=OskConfig(),
    ):
        code = stop_hub(wait_seconds=0.2)

    assert code == 0
    mock_kill.assert_called_once_with(4321, signal.SIGTERM)
    assert not state_path.exists()
    assert not stop_path.exists()


def test_stop_hub_cleans_stale_state(tmp_path: Path) -> None:
    state_path = tmp_path / "hub-state.json"
    state_path.write_text('{"pid": 4321, "operation_name": "March"}\n')
    with patch("osk.hub._config_root", return_value=tmp_path), patch(
        "osk.hub._pid_is_running",
        return_value=False,
    ), patch("osk.hub.load_config", return_value=OskConfig()):
        code = stop_hub(wait_seconds=1)

    assert code == 0
    assert not state_path.exists()


def test_status_hub_reports_running(tmp_path: Path, capsys) -> None:
    state_path = tmp_path / "hub-state.json"
    state_path.write_text('{"pid": 4321, "operation_name": "March", "port": 8443, "started_at": 123}\n')
    with patch("osk.hub._config_root", return_value=tmp_path), patch(
        "osk.hub._pid_is_running",
        return_value=True,
    ), patch("osk.hub.time.time", return_value=130):
        code = status_hub()
    out = capsys.readouterr().out
    assert code == 0
    assert "Osk hub is running." in out
    assert "status = running" in out
    assert "operation = March" in out
    assert "started_at = 1970-01-01T00:02:03Z" in out
    assert "uptime = 7s" in out
    assert "stopping = false" in out


def test_status_hub_reports_stopping(tmp_path: Path, capsys) -> None:
    state_path = tmp_path / "hub-state.json"
    stop_path = tmp_path / "hub-stop-request.json"
    state_path.write_text('{"pid": 4321, "operation_name": "March", "port": 8443, "started_at": 123}\n')
    stop_path.write_text('{"requested_at": 1}\n')
    with patch("osk.hub._config_root", return_value=tmp_path), patch(
        "osk.hub._pid_is_running",
        return_value=True,
    ):
        code = status_hub()
    out = capsys.readouterr().out
    assert code == 0
    assert "stopping = true" in out


def test_status_hub_reports_unverifiable_state_without_cleanup(tmp_path: Path, capsys) -> None:
    state_path = tmp_path / "hub-state.json"
    stop_path = tmp_path / "hub-stop-request.json"
    state_path.write_text('{"pid": 4321, "operation_name": "March"}\n')
    stop_path.write_text('{"requested_at": 1}\n')
    with patch("osk.hub._config_root", return_value=tmp_path), patch(
        "osk.hub._pid_is_running",
        return_value=False,
    ):
        code = status_hub()
    out = capsys.readouterr().out
    assert code == 1
    assert "status = state_only" in out
    assert "not visible" in out.lower()
    assert state_path.exists()
    assert stop_path.exists()


def test_status_hub_reports_not_running(tmp_path: Path, capsys) -> None:
    stop_path = tmp_path / "hub-stop-request.json"
    stop_path.write_text('{"requested_at": 1}\n')
    with patch("osk.hub._config_root", return_value=tmp_path):
        code = status_hub()
    out = capsys.readouterr().out
    assert code == 1
    assert "not running" in out.lower()
    assert "status = stopped" in out
    assert not stop_path.exists()


def test_hub_status_snapshot_json_payload(tmp_path: Path) -> None:
    state_path = tmp_path / "hub-state.json"
    stop_path = tmp_path / "hub-stop-request.json"
    state_path.write_text('{"pid": 4321, "operation_name": "March", "port": 8443, "started_at": 123}\n')
    stop_path.write_text('{"requested_at": 1}\n')
    with patch("osk.hub._config_root", return_value=tmp_path), patch(
        "osk.hub._pid_is_running",
        return_value=True,
    ):
        code, snapshot = hub_status_snapshot(now=130)
    assert code == 0
    assert snapshot == {
        "message": "Osk hub is running.",
        "operation_name": "March",
        "pid": 4321,
        "port": 8443,
        "started_at_iso": "1970-01-01T00:02:03Z",
        "started_at_unix": 123,
        "status": "running",
        "stopping": True,
        "uptime_human": "7s",
        "uptime_seconds": 7,
    }


async def test_watch_for_stop_request_sets_server_should_exit(tmp_path: Path) -> None:
    class DummyServer:
        should_exit = False

    server = DummyServer()
    stop_path = tmp_path / "hub-stop-request.json"
    with patch("osk.hub._config_root", return_value=tmp_path):
        task = asyncio.create_task(watch_for_stop_request(server, poll_seconds=0.01))
        await asyncio.sleep(0.02)
        stop_path.write_text('{"requested_at": 1}\n')
        await task

    assert server.should_exit is True
