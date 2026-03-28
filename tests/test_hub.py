from __future__ import annotations

import asyncio
import datetime as dt
import json
import signal
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from osk.config import OskConfig
from osk.hub import (
    HubBootstrapError,
    _compose_environment,
    _find_compose_command,
    _trigger_live_wipe_broadcast,
    _wipe_follow_up_history_line,
    default_storage_manager,
    ensure_hub_not_running,
    ensure_local_services,
    hotspot_preflight_status,
    hub_status_snapshot,
    installation_issues,
    local_database_port,
    local_service_mode,
    read_hub_state,
    run_hub_sync,
    status_hub,
    stop_hub,
    uses_local_dev_services,
    wait_for_database,
    watch_for_stop_request,
    watch_member_heartbeats,
    wipe_hub,
)
from osk.local_operator import create_bootstrap_session, create_operator_session


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


@patch("osk.hub.HotspotManager.status")
def test_hotspot_preflight_status_marks_active_hotspot(
    mock_status: MagicMock,
) -> None:
    mock_status.return_value = {
        "available": True,
        "ssid": "osk-local",
        "band": "5GHz",
        "connection_name": "osk-local",
        "ip_address": "10.42.0.1",
        "manual_instructions": None,
    }

    payload = hotspot_preflight_status(
        OskConfig(hotspot_ssid="osk-local", hotspot_band="5GHz", join_host="10.42.0.1")
    )

    assert payload["status"] == "active"
    assert payload["join_host_scope"] == "hotspot_ip"
    assert payload["warnings"] == []
    assert payload["actions"] == []


@patch("osk.hub.HotspotManager.status")
def test_hotspot_preflight_status_warns_for_loopback_join_host(
    mock_status: MagicMock,
) -> None:
    mock_status.return_value = {
        "available": True,
        "ssid": "osk-local",
        "band": "5GHz",
        "connection_name": "osk-local",
        "ip_address": None,
        "manual_instructions": None,
    }

    payload = hotspot_preflight_status(
        OskConfig(hotspot_ssid="osk-local", hotspot_band="5GHz", join_host="127.0.0.1")
    )

    assert payload["status"] == "available_inactive"
    assert payload["join_host_scope"] == "loopback"
    assert any(
        "member QR codes will only work on the coordinator device" in w for w in payload["warnings"]
    )
    assert any("osk hotspot up --password <passphrase>" in action for action in payload["actions"])
    assert any(
        "set `join_host` to a reachable LAN or hotspot IP" in action
        for action in payload["actions"]
    )


@patch("osk.hub.HotspotManager.status")
def test_hotspot_preflight_status_warns_when_join_host_mismatches_hotspot_ip(
    mock_status: MagicMock,
) -> None:
    mock_status.return_value = {
        "available": True,
        "ssid": "osk-local",
        "band": "5GHz",
        "connection_name": "osk-local",
        "ip_address": "10.42.0.1",
        "manual_instructions": None,
    }

    payload = hotspot_preflight_status(
        OskConfig(hotspot_ssid="osk-local", hotspot_band="5GHz", join_host="field.local")
    )

    assert payload["status"] == "active"
    assert payload["join_host_scope"] == "custom"
    assert any(
        "Verify member devices can reach the configured join host" in w for w in payload["warnings"]
    )
    assert any("osk config --set join_host=10.42.0.1" in action for action in payload["actions"])


@patch("osk.hub.shutil.which", return_value=None)
def test_installation_issues_require_ffmpeg_for_whisper_backend(
    mock_which: MagicMock,
    tmp_path: Path,
) -> None:
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    cert_path.write_text("cert")
    key_path.write_text("key")
    config = OskConfig(
        tls_cert_path=str(cert_path),
        tls_key_path=str(key_path),
        storage_backend="directory",
        transcriber_backend="whisper",
    )
    storage = default_storage_manager(config)

    issues = installation_issues(config, storage)

    assert any("missing ffmpeg binary" in issue for issue in issues)
    mock_which.assert_called_once_with("ffmpeg")


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
def test_ensure_local_services_skips_when_config_uses_external_services(
    mock_run: MagicMock,
) -> None:
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


@patch("osk.hub.asyncio.run")
def test_run_hub_sync_returns_error_code_on_bootstrap_failure(mock_run: MagicMock, capsys) -> None:
    def raise_bootstrap_error(coro) -> None:
        coro.close()
        raise HubBootstrapError("boom")

    mock_run.side_effect = raise_bootstrap_error
    code = run_hub_sync("Test Op")
    out = capsys.readouterr().out
    assert code == 1
    assert "boom" in out
    mock_run.assert_called_once()


@patch("osk.hub.asyncio.run")
def test_run_hub_sync_reports_unexpected_failure(mock_run: MagicMock, capsys) -> None:
    def raise_runtime_error(coro) -> None:
        coro.close()
        raise RuntimeError("kaboom")

    mock_run.side_effect = raise_runtime_error
    code = run_hub_sync("Test Op")
    out = capsys.readouterr().out
    assert code == 1
    assert "Osk hub failed unexpectedly: kaboom" in out
    assert "Runtime log:" in out


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
    bootstrap_path = tmp_path / "operator-bootstrap.json"
    session_path = tmp_path / "operator-session.json"
    state_path.write_text('{"pid": 999999, "operation_name": "Old Op"}\n')
    stop_path.write_text('{"requested_at": 1}\n')
    bootstrap_path.write_text("{}\n")
    session_path.write_text('{"token":"session"}\n')
    with (
        patch("osk.hub._config_root", return_value=tmp_path),
        patch("osk.local_operator._state_root", return_value=tmp_path),
    ):
        ensure_hub_not_running()
    assert not state_path.exists()
    assert not stop_path.exists()
    assert not bootstrap_path.exists()
    assert not session_path.exists()


def test_ensure_hub_not_running_raises_for_live_pid(tmp_path: Path) -> None:
    state_path = tmp_path / "hub-state.json"
    state_path.write_text('{"pid": 1234, "operation_name": "Live Op"}\n')
    with (
        patch("osk.hub._config_root", return_value=tmp_path),
        patch(
            "osk.hub._pid_is_running",
            return_value=True,
        ),
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
    with (
        patch("osk.hub._config_root", return_value=tmp_path),
        patch(
            "osk.hub._pid_is_running",
            side_effect=[True, True, False, False, False],
        ),
        patch("osk.hub.time.monotonic", side_effect=[0.0, 0.0, 0.1]),
        patch(
            "osk.hub.load_config",
            return_value=OskConfig(),
        ),
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
    with (
        patch("osk.hub._config_root", return_value=tmp_path),
        patch(
            "osk.hub._pid_is_running",
            side_effect=[True, True, True, False, False],
        ),
        # Extended monotonic sequence for: initial deadline, graceful loop (x2),
        # sigterm deadline, sigterm loop (x1)
        patch(
            "osk.hub.time.monotonic",
            side_effect=[0.0, 0.0, 0.3, 0.0, 0.1],
        ),
        patch(
            "osk.hub.load_config",
            return_value=OskConfig(),
        ),
    ):
        code = stop_hub(wait_seconds=0.2)

    assert code == 0
    mock_kill.assert_called_once_with(4321, signal.SIGTERM)
    assert not state_path.exists()
    assert not stop_path.exists()


def test_stop_hub_cleans_stale_state(tmp_path: Path) -> None:
    state_path = tmp_path / "hub-state.json"
    bootstrap_path = tmp_path / "operator-bootstrap.json"
    session_path = tmp_path / "operator-session.json"
    state_path.write_text('{"pid": 4321, "operation_name": "March"}\n')
    bootstrap_path.write_text("{}\n")
    session_path.write_text('{"token":"session"}\n')
    with (
        patch("osk.hub._config_root", return_value=tmp_path),
        patch("osk.local_operator._state_root", return_value=tmp_path),
        patch(
            "osk.hub._pid_is_running",
            return_value=False,
        ),
        patch("osk.hub.load_config", return_value=OskConfig()),
    ):
        code = stop_hub(wait_seconds=1)

    assert code == 0
    assert not state_path.exists()
    assert not bootstrap_path.exists()
    assert not session_path.exists()


@patch("osk.hub.time.sleep")
def test_stop_hub_preserves_operation_for_restart(
    mock_sleep: MagicMock,
    tmp_path: Path,
    capsys,
) -> None:
    state_path = tmp_path / "hub-state.json"
    stop_path = tmp_path / "hub-stop-request.json"
    state_path.write_text('{"pid": 4321, "operation_name": "March"}\n')
    with (
        patch("osk.hub._config_root", return_value=tmp_path),
        patch("osk.hub._pid_is_running", side_effect=[True, False, False, False]),
        patch("osk.hub.time.monotonic", side_effect=[0.0, 0.0, 0.1]),
        patch("osk.hub.load_config", return_value=OskConfig()),
    ):
        code = stop_hub(wait_seconds=1, preserve_operation=True)

    out = capsys.readouterr().out
    assert code == 0
    assert "Restarting Osk hub for 'March'" in out
    assert "without ending the operation" in out
    assert not state_path.exists()
    assert not stop_path.exists()


@patch("osk.hub.read_operator_session", return_value=None)
def test_trigger_live_wipe_broadcast_requires_operator_session(
    _mock_read_operator_session: MagicMock,
) -> None:
    result = _trigger_live_wipe_broadcast(8443, "op-123")

    assert result["ok"] is False
    assert "osk operator login" in str(result["error"])


@patch("osk.hub.read_operator_session")
@patch("osk.hub.urllib.request.urlopen")
def test_trigger_live_wipe_broadcast_uses_local_operator_session(
    mock_urlopen: MagicMock,
    mock_read_operator_session: MagicMock,
) -> None:
    mock_read_operator_session.return_value = {
        "operation_id": "op-123",
        "token": "operator-token",
        "expires_at": "2026-03-22T12:00:00+00:00",
    }
    response = MagicMock()
    response.status = 200
    response.read.return_value = (
        b'{"status":"wipe_initiated","broadcast_target_count":2,'
        b'"wipe_readiness":{"status":"blocked","summary":"1 member may miss a live wipe."}}'
    )
    mock_urlopen.return_value.__enter__.return_value = response

    result = _trigger_live_wipe_broadcast(8443, "op-123")

    assert result["ok"] is True
    assert result["response"]["status"] == "wipe_initiated"
    assert result["response"]["broadcast_target_count"] == 2
    request = mock_urlopen.call_args.args[0]
    assert request.full_url == "https://127.0.0.1:8443/api/wipe"
    assert dict(request.header_items())["X-osk-operator-session"] == "operator-token"


@patch("osk.hub.stop_hub", return_value=0)
@patch(
    "osk.hub._trigger_live_wipe_broadcast",
    return_value={"ok": True, "response": {"status": "wipe_initiated"}},
)
def test_wipe_hub_triggers_broadcast_and_stop(
    mock_trigger_live_wipe: MagicMock,
    mock_stop_hub: MagicMock,
    capsys,
) -> None:
    mock_trigger_live_wipe.return_value = {
        "ok": True,
        "response": {
            "status": "wipe_initiated",
            "broadcast_target_count": 2,
            "wipe_readiness": {
                "status": "blocked",
                "summary": "1 member browser may miss a live wipe.",
                "follow_up_required": True,
                "active_unresolved_follow_up_count": 1,
                "historical_drift_follow_up_count": 1,
                "reviewed_historical_drift_follow_up_count": 1,
                "verified_current_follow_up_count": 0,
                "follow_up_summary": (
                    "Resolve 2 unresolved member wipe follow-up items before closing the "
                    "cleanup boundary. 1 item may be historical drift. "
                    "1 historical-drift review recorded."
                ),
                "follow_up_history_count": 1,
                "follow_up_history_summary": "Recent follow-up trail: 1 reviewed.",
                "follow_up_history": [
                    {
                        "member_name": "Observer One",
                        "reason": "disconnected",
                        "status": "reviewed",
                        "action": "wipe_follow_up_historical_reviewed",
                        "reviewed_at": "2026-03-21T08:00:00Z",
                    }
                ],
                "follow_up": [
                    {
                        "name": "Sensor Two",
                        "reason": "disconnected",
                        "classification": "active_unresolved",
                        "last_seen_at": "2026-03-21T12:00:00Z",
                        "required_action": (
                            "Reconnect this member browser and confirm wipe, or record a "
                            "manual cleanup verification before closing the cleanup boundary."
                        ),
                    },
                    {
                        "name": "Observer One",
                        "reason": "disconnected",
                        "classification": "historical_drift",
                        "historical_reviewed": True,
                        "last_seen_at": "2026-03-21T03:00:00Z",
                        "required_action": (
                            "Reconnect this member browser and confirm wipe, or record a "
                            "manual cleanup verification before closing the cleanup boundary."
                        ),
                    },
                ],
            },
        },
    }
    with patch(
        "osk.hub.read_hub_state",
        return_value={"operation_id": "op-123", "operation_name": "March", "port": 8443},
    ):
        code = wipe_hub(wait_seconds=4.0, stop_services=True)

    out = capsys.readouterr().out
    assert code == 0
    assert "Live wipe broadcast sent" in out
    assert "broadcast_target_count = 2" in out
    assert "wipe_readiness = blocked" in out
    assert "wipe_follow_up_required = true" in out
    assert "Resolve 2 unresolved member wipe follow-up items" in out
    assert (
        "wipe_follow_up_counts active_unresolved=1 historical_drift=1 "
        "reviewed_historical_drift=1 retired_historical_drift=0 "
        "verified_current=0" in out
    )
    assert (
        "wipe_follow_up name=Sensor Two reason=disconnected classification=active_unresolved" in out
    )
    assert (
        "wipe_follow_up name=Observer One reason=disconnected "
        "classification=historical_drift reviewed=true" in out
    )
    assert "wipe_follow_up_history_summary = Recent follow-up trail: 1 reviewed." in out
    assert (
        "wipe_follow_up_history name=Observer One reason=disconnected "
        "status=reviewed action=reviewed" in out
    )
    assert "Preserved evidence retained" in out
    mock_trigger_live_wipe.assert_called_once_with(8443, "op-123")
    mock_stop_hub.assert_called_once_with(wait_seconds=4.0, stop_services=True)


@patch("osk.evidence.EvidenceManager.from_storage")
@patch("osk.hub.default_storage_manager")
@patch("osk.hub.load_config", return_value=OskConfig())
@patch("osk.hub.stop_hub", return_value=0)
@patch(
    "osk.hub._trigger_live_wipe_broadcast",
    return_value={"ok": True, "response": {"status": "wipe_initiated"}},
)
def test_wipe_hub_can_destroy_evidence(
    mock_trigger_live_wipe: MagicMock,
    mock_stop_hub: MagicMock,
    _mock_load_config: MagicMock,
    mock_default_storage_manager: MagicMock,
    mock_from_storage: MagicMock,
    capsys,
) -> None:
    manager = MagicMock()
    manager.destroy.return_value = {
        "ok": True,
        "destroyed_path": "/tmp/evidence.luks",
        "backend": "luks",
    }
    mock_from_storage.return_value = manager
    mock_default_storage_manager.return_value = MagicMock()

    with patch(
        "osk.hub.read_hub_state",
        return_value={"operation_id": "op-123", "operation_name": "March", "port": 8443},
    ):
        code = wipe_hub(destroy_evidence=True)

    out = capsys.readouterr().out
    assert code == 0
    assert "Preserved evidence destroyed at /tmp/evidence.luks." in out
    mock_trigger_live_wipe.assert_called_once_with(8443, "op-123")
    mock_stop_hub.assert_called_once_with(wait_seconds=10.0, stop_services=False)
    manager.destroy.assert_called_once_with()


@patch("osk.hub.stop_hub", return_value=0)
@patch(
    "osk.hub._trigger_live_wipe_broadcast",
    return_value={"ok": False, "error": "No active local operator session."},
)
def test_wipe_hub_stops_on_broadcast_failure(
    mock_trigger_live_wipe: MagicMock,
    mock_stop_hub: MagicMock,
    capsys,
) -> None:
    with patch(
        "osk.hub.read_hub_state",
        return_value={"operation_id": "op-123", "operation_name": "March", "port": 8443},
    ):
        code = wipe_hub()

    out = capsys.readouterr().out
    assert code == 1
    assert "Failed to trigger live wipe" in out
    mock_trigger_live_wipe.assert_called_once_with(8443, "op-123")
    mock_stop_hub.assert_not_called()


def test_status_hub_reports_running(tmp_path: Path, capsys) -> None:
    state_path = tmp_path / "hub-state.json"
    state_path.write_text(
        '{"pid": 4321, "operation_name": "March", "port": 8443, "started_at": 123}\n'
    )
    with (
        patch("osk.hub._config_root", return_value=tmp_path),
        patch(
            "osk.hub._pid_is_running",
            return_value=True,
        ),
        patch("osk.hub.time.time", return_value=130),
    ):
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
    state_path.write_text(
        '{"pid": 4321, "operation_name": "March", "port": 8443, "started_at": 123}\n'
    )
    stop_path.write_text('{"requested_at": 1}\n')
    with (
        patch("osk.hub._config_root", return_value=tmp_path),
        patch(
            "osk.hub._pid_is_running",
            return_value=True,
        ),
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
    with (
        patch("osk.hub._config_root", return_value=tmp_path),
        patch(
            "osk.hub._pid_is_running",
            return_value=False,
        ),
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
    bootstrap_path = tmp_path / "operator-bootstrap.json"
    session_path = tmp_path / "operator-session.json"
    state_path.write_text(
        '{"pid": 4321, "operation_name": "March", "port": 8443, "started_at": 123}\n'
    )
    stop_path.write_text('{"requested_at": 1}\n')
    with (
        patch("osk.hub._config_root", return_value=tmp_path),
        patch("osk.local_operator._state_root", return_value=tmp_path),
        patch(
            "osk.hub._pid_is_running",
            return_value=True,
        ),
    ):
        create_bootstrap_session("op-123", 15)
        create_operator_session("op-123", 60)
        code, snapshot = hub_status_snapshot(now=130)
    assert code == 0
    assert snapshot["message"] == "Osk hub is running."
    assert snapshot["operation_id"] is None
    assert snapshot["operation_name"] == "March"
    assert snapshot["operator_bootstrap_path"] == str(bootstrap_path)
    assert snapshot["operator_bootstrap_active"] is True
    assert snapshot["operator_bootstrap_expires_at"]
    assert snapshot["operator_bootstrap_status"] == "active"
    assert snapshot["operator_session_active"] is True
    assert snapshot["operator_session_expires_at"]
    assert snapshot["operator_session_path"] == str(session_path)
    assert snapshot["pid"] == 4321
    assert snapshot["port"] == 8443
    assert snapshot["started_at_iso"] == "1970-01-01T00:02:03Z"
    assert snapshot["started_at_unix"] == 123
    assert snapshot["status"] == "running"
    assert snapshot["stopping"] is True
    assert snapshot["uptime_human"] == "7s"
    assert snapshot["uptime_seconds"] == 7
    assert snapshot["runtime_log_path"].endswith("hub.log")


@patch("osk.hub.asyncio.run")
def test_login_operator_session_consumes_bootstrap(
    mock_asyncio_run: MagicMock,
    tmp_path: Path,
    capsys,
) -> None:
    def close_audit_coro(coro) -> None:
        coro.close()
        return None

    mock_asyncio_run.side_effect = close_audit_coro

    with (
        patch("osk.hub._config_root", return_value=tmp_path),
        patch("osk.local_operator._state_root", return_value=tmp_path),
        patch("osk.hub.load_config", return_value=OskConfig()),
    ):
        (tmp_path / "hub-state.json").write_text(
            '{"operation_id":"11111111-1111-1111-1111-111111111111"}\n'
        )
        create_bootstrap_session("11111111-1111-1111-1111-111111111111", 15)

        from osk.hub import login_operator_session

        code = login_operator_session()
        assert not (tmp_path / "operator-bootstrap.json").exists()

    out = capsys.readouterr().out
    assert code == 0
    assert "one-time bootstrap" in out
    mock_asyncio_run.assert_called_once()


@patch("osk.hub.asyncio.run")
def test_login_operator_session_reports_expired_bootstrap(
    mock_asyncio_run: MagicMock,
    tmp_path: Path,
    capsys,
) -> None:
    def close_audit_coro(coro) -> None:
        coro.close()
        return None

    mock_asyncio_run.side_effect = close_audit_coro

    expired_bootstrap = (
        "{\n"
        '  "operation_id": "11111111-1111-1111-1111-111111111111",\n'
        '  "bootstrap_token": "expired-token",\n'
        '  "created_at": "2026-03-21T00:00:00+00:00",\n'
        '  "expires_at": "2026-03-21T00:01:00+00:00"\n'
        "}\n"
    )

    with (
        patch("osk.hub._config_root", return_value=tmp_path),
        patch("osk.local_operator._state_root", return_value=tmp_path),
        patch(
            "osk.local_operator._utcnow",
            return_value=dt.datetime(2026, 3, 21, 0, 2, tzinfo=dt.timezone.utc),
        ),
    ):
        (tmp_path / "hub-state.json").write_text(
            '{"operation_id":"11111111-1111-1111-1111-111111111111"}\n'
        )
        (tmp_path / "operator-bootstrap.json").write_text(expired_bootstrap)

        from osk.hub import login_operator_session

        code = login_operator_session()

    out = capsys.readouterr().out
    assert code == 1
    assert "expired before it could be used" in out
    assert mock_asyncio_run.called


@patch("osk.hub.asyncio.run")
def test_show_audit_events_formats_rows(
    mock_asyncio_run: MagicMock,
    tmp_path: Path,
    capsys,
) -> None:
    audit_events = [
        {
            "timestamp": "2026-03-21T12:00:00Z",
            "actor_type": "system",
            "action": "operator_session_created",
            "details": {"issued_from": "bootstrap"},
        }
    ]

    def return_audit_events(coro):
        coro.close()
        return audit_events

    mock_asyncio_run.side_effect = return_audit_events

    with patch("osk.hub._config_root", return_value=tmp_path):
        (tmp_path / "hub-state.json").write_text(
            '{"operation_id":"11111111-1111-1111-1111-111111111111"}\n'
        )
        from osk.hub import show_audit_events

        code = show_audit_events(limit=5)

    out = capsys.readouterr().out
    assert code == 0
    assert "operator_session_created" in out
    assert '"issued_from": "bootstrap"' in out


def test_show_audit_events_filters_actions(tmp_path: Path) -> None:
    audit_events = [{"action": "wipe_follow_up_verified"}]

    def return_audit_events(coro):
        coro.close()
        return audit_events

    with (
        patch("osk.hub._config_root", return_value=tmp_path),
        patch("osk.hub._get_audit_events", new_callable=AsyncMock) as mock_get_audit_events,
        patch("osk.hub.asyncio.run", side_effect=return_audit_events),
    ):
        mock_get_audit_events.return_value = audit_events
        (tmp_path / "hub-state.json").write_text(
            '{"operation_id":"11111111-1111-1111-1111-111111111111"}\n'
        )
        from osk.hub import show_audit_events

        code = show_audit_events(
            limit=5,
            actions=["operator_session_created"],
            wipe_follow_up_only=True,
        )

    assert code == 0
    mock_get_audit_events.assert_called_once_with(
        uuid.UUID("11111111-1111-1111-1111-111111111111"),
        5,
        actions=[
            "operator_session_created",
            "wipe_follow_up_verified",
            "wipe_follow_up_reopened",
            "wipe_follow_up_historical_reviewed",
            "wipe_follow_up_historical_retired",
        ],
    )


def test_show_runtime_logs_returns_tail(tmp_path: Path, capsys) -> None:
    with patch("osk.hub._state_root", return_value=tmp_path):
        (tmp_path / "hub.log").write_text("one\ntwo\nthree\n")
        from osk.hub import show_runtime_logs

        code = show_runtime_logs(tail=2)

    out = capsys.readouterr().out
    assert code == 0
    assert out.splitlines() == ["two", "three"]


@patch("osk.hub.asyncio.run")
def test_logout_operator_session_records_audit_event(
    mock_asyncio_run: MagicMock,
    tmp_path: Path,
    capsys,
) -> None:
    def close_audit_coro(coro) -> None:
        coro.close()
        return None

    mock_asyncio_run.side_effect = close_audit_coro

    with (
        patch("osk.hub._config_root", return_value=tmp_path),
        patch("osk.local_operator._state_root", return_value=tmp_path),
    ):
        (tmp_path / "hub-state.json").write_text(
            '{"operation_id":"11111111-1111-1111-1111-111111111111"}\n'
        )
        create_operator_session("11111111-1111-1111-1111-111111111111", 60)

        from osk.hub import logout_operator_session

        code = logout_operator_session()

    out = capsys.readouterr().out
    assert code == 0
    assert "Local operator session removed." in out
    assert mock_asyncio_run.called


@patch("osk.hub.asyncio.run")
def test_show_members_formats_rows(mock_asyncio_run: MagicMock, tmp_path: Path, capsys) -> None:
    member_rows = [
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "name": "Jay",
            "role": "observer",
            "status": "connected",
            "reconnect_token": "resume-token",
            "connected_at": dt.datetime(2026, 3, 21, 12, 0, tzinfo=dt.timezone.utc),
            "last_seen_at": dt.datetime(2026, 3, 21, 12, 0, 30, tzinfo=dt.timezone.utc),
            "last_gps_at": None,
            "latitude": 39.75,
            "longitude": -104.99,
        }
    ]
    audit_events = [
        {
            "action": "wipe_follow_up_historical_reviewed",
            "timestamp": dt.datetime(2026, 3, 21, 8, 0, tzinfo=dt.timezone.utc),
            "details": {
                "member_id": "11111111-1111-1111-1111-111111111111",
                "member_name": "Jay",
                "reason": "stale",
                "classification": "historical_drift",
                "last_seen_at": "2026-03-21T07:30:00Z",
            },
        }
    ]

    def return_member_rows(coro):
        coro_name = coro.cr_code.co_name
        coro.close()
        if coro_name == "_get_members":
            return member_rows
        if coro_name == "_get_audit_events":
            return audit_events
        raise AssertionError(f"Unexpected coroutine: {coro_name}")

    mock_asyncio_run.side_effect = return_member_rows

    with (
        patch("osk.hub._config_root", return_value=tmp_path),
        patch("osk.hub.load_config", return_value=OskConfig(member_heartbeat_timeout_seconds=45)),
        patch("osk.hub.dt.datetime") as mock_datetime,
    ):
        mock_datetime.now.return_value = dt.datetime(2026, 3, 21, 12, 1, tzinfo=dt.timezone.utc)
        mock_datetime.side_effect = lambda *args, **kwargs: dt.datetime(*args, **kwargs)
        (tmp_path / "hub-state.json").write_text(
            '{"operation_id":"11111111-1111-1111-1111-111111111111"}\n'
        )

        from osk.hub import show_members

        code = show_members()

    out = capsys.readouterr().out
    assert code == 0
    assert "Jay" in out
    assert "heartbeat=fresh" in out
    assert "gps=39.75,-104.99" in out
    assert "wipe_readiness = ready" in out
    assert "All 1 current member browsers are reachable for a live wipe." in out
    assert "wipe_follow_up_history_summary = Recent follow-up trail: 1 reviewed." in out


@patch("osk.hub.asyncio.run")
def test_show_members_json_includes_wipe_readiness(
    mock_asyncio_run: MagicMock,
    tmp_path: Path,
    capsys,
) -> None:
    member_rows = [
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "name": "Jay",
            "role": "observer",
            "status": "connected",
            "reconnect_token": "resume-token",
            "connected_at": dt.datetime(2026, 3, 21, 12, 0, tzinfo=dt.timezone.utc),
            "last_seen_at": dt.datetime(2026, 3, 21, 12, 0, 30, tzinfo=dt.timezone.utc),
            "last_gps_at": None,
            "latitude": 39.75,
            "longitude": -104.99,
        }
    ]
    audit_events = [
        {
            "action": "wipe_follow_up_historical_reviewed",
            "timestamp": dt.datetime(2026, 3, 21, 8, 0, tzinfo=dt.timezone.utc),
            "details": {
                "member_id": "11111111-1111-1111-1111-111111111111",
                "member_name": "Jay",
                "reason": "stale",
                "classification": "historical_drift",
                "last_seen_at": "2026-03-21T07:30:00Z",
            },
        }
    ]

    def return_member_rows(coro):
        coro_name = coro.cr_code.co_name
        coro.close()
        if coro_name == "_get_members":
            return member_rows
        if coro_name == "_get_audit_events":
            return audit_events
        raise AssertionError(f"Unexpected coroutine: {coro_name}")

    mock_asyncio_run.side_effect = return_member_rows

    with (
        patch("osk.hub._config_root", return_value=tmp_path),
        patch("osk.hub.load_config", return_value=OskConfig(member_heartbeat_timeout_seconds=45)),
        patch("osk.hub.dt.datetime") as mock_datetime,
    ):
        mock_datetime.now.return_value = dt.datetime(2026, 3, 21, 12, 1, tzinfo=dt.timezone.utc)
        mock_datetime.side_effect = lambda *args, **kwargs: dt.datetime(*args, **kwargs)
        (tmp_path / "hub-state.json").write_text(
            '{"operation_id":"11111111-1111-1111-1111-111111111111"}\n'
        )

        from osk.hub import show_members

        code = show_members(json_output=True)

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["members"][0]["name"] == "Jay"
    assert payload["wipe_readiness"]["status"] == "ready"
    assert payload["wipe_readiness"]["follow_up_history_count"] == 1
    assert payload["wipe_readiness"]["follow_up_history_summary"].startswith(
        "Recent follow-up trail:"
    )


@patch("osk.hub.asyncio.run")
def test_show_members_idle_still_reports_wipe_readiness(
    mock_asyncio_run: MagicMock,
    tmp_path: Path,
    capsys,
) -> None:
    def return_member_rows(coro):
        coro_name = coro.cr_code.co_name
        coro.close()
        if coro_name == "_get_members":
            return []
        if coro_name == "_get_audit_events":
            return []
        raise AssertionError(f"Unexpected coroutine: {coro_name}")

    mock_asyncio_run.side_effect = return_member_rows

    with (
        patch("osk.hub._config_root", return_value=tmp_path),
        patch("osk.hub.load_config", return_value=OskConfig(member_heartbeat_timeout_seconds=45)),
    ):
        (tmp_path / "hub-state.json").write_text(
            '{"operation_id":"11111111-1111-1111-1111-111111111111"}\n'
        )

        from osk.hub import show_members

        code = show_members()

    out = capsys.readouterr().out
    assert code == 0
    assert "No members recorded." in out
    assert "wipe_readiness = idle" in out
    assert "No member browsers are currently joined." in out


@patch("osk.hub.asyncio.run")
def test_status_hub_reports_wipe_readiness(
    mock_asyncio_run: MagicMock,
    tmp_path: Path,
    capsys,
) -> None:
    member_rows = [
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "name": "Observer One",
            "role": "observer",
            "status": "connected",
            "reconnect_token": "resume-token",
            "connected_at": dt.datetime(2026, 3, 21, 12, 0, tzinfo=dt.timezone.utc),
            "last_seen_at": dt.datetime(2026, 3, 21, 12, 0, 30, tzinfo=dt.timezone.utc),
            "last_gps_at": None,
            "latitude": None,
            "longitude": None,
        },
        {
            "id": "22222222-2222-2222-2222-222222222222",
            "name": "Sensor Two",
            "role": "sensor",
            "status": "disconnected",
            "reconnect_token": "resume-token-2",
            "connected_at": dt.datetime(2026, 3, 21, 12, 0, tzinfo=dt.timezone.utc),
            "last_seen_at": dt.datetime(2026, 3, 21, 11, 54, tzinfo=dt.timezone.utc),
            "last_gps_at": None,
            "latitude": None,
            "longitude": None,
        },
    ]
    audit_events = [
        {
            "action": "wipe_follow_up_historical_reviewed",
            "timestamp": dt.datetime(2026, 3, 21, 8, 0, tzinfo=dt.timezone.utc),
            "details": {
                "member_id": "22222222-2222-2222-2222-222222222222",
                "member_name": "Sensor Two",
                "reason": "disconnected",
                "classification": "historical_drift",
                "last_seen_at": "2026-03-21T03:00:00Z",
            },
        }
    ]

    def return_member_rows(coro):
        coro_name = coro.cr_code.co_name
        coro.close()
        if coro_name == "_get_members":
            return member_rows
        if coro_name == "_get_audit_events":
            return audit_events
        raise AssertionError(f"Unexpected coroutine: {coro_name}")

    mock_asyncio_run.side_effect = return_member_rows

    with (
        patch("osk.hub._config_root", return_value=tmp_path),
        patch("osk.hub._pid_is_running", return_value=True),
        patch("osk.hub.load_config", return_value=OskConfig(member_heartbeat_timeout_seconds=60)),
        patch("osk.hub.dt.datetime") as mock_datetime,
    ):
        mock_datetime.now.return_value = dt.datetime(2026, 3, 21, 12, 1, tzinfo=dt.timezone.utc)
        mock_datetime.side_effect = lambda *args, **kwargs: dt.datetime(*args, **kwargs)
        (tmp_path / "hub-state.json").write_text(
            '{"pid":4321,"operation_name":"March","operation_id":"11111111-1111-1111-1111-111111111111"}\n'
        )

        from osk.hub import status_hub

        code = status_hub()

    out = capsys.readouterr().out
    assert code == 0
    assert "wipe_readiness = blocked" in out
    assert "wipe_at_risk_members = 1" in out
    assert "wipe_follow_up_required = true" in out
    assert "Resolve 1 unresolved member wipe follow-up item" in out
    assert (
        "wipe_follow_up_counts active_unresolved=1 historical_drift=0 "
        "reviewed_historical_drift=0 retired_historical_drift=0 "
        "verified_current=0" in out
    )
    assert "wipe_follow_up_history_summary = Recent follow-up trail: 1 reviewed." in out


def test_status_hub_excludes_retired_historical_drift_from_current_counts(
    tmp_path: Path,
    capsys,
) -> None:
    current = dt.datetime.now(dt.timezone.utc)
    historical_seen = current - dt.timedelta(hours=9)
    retired_at = current - dt.timedelta(hours=4)
    member_rows = [
        {
            "id": "22222222-2222-2222-2222-222222222222",
            "name": "Sensor Two",
            "role": "sensor",
            "status": "disconnected",
            "reconnect_token": "resume-token-2",
            "connected_at": current,
            "last_seen_at": historical_seen,
            "last_gps_at": None,
            "latitude": None,
            "longitude": None,
        },
    ]
    audit_events = [
        {
            "action": "wipe_follow_up_historical_retired",
            "timestamp": retired_at,
            "details": {
                "member_id": "22222222-2222-2222-2222-222222222222",
                "member_name": "Sensor Two",
                "reason": "disconnected",
                "classification": "historical_drift",
                "last_seen_at": historical_seen.isoformat().replace("+00:00", "Z"),
            },
        }
    ]

    with (
        patch("osk.hub._get_members", AsyncMock(return_value=member_rows)),
        patch("osk.hub._get_audit_events", AsyncMock(return_value=audit_events)),
        patch("osk.hub._config_root", return_value=tmp_path),
        patch("osk.hub._pid_is_running", return_value=True),
        patch("osk.hub.load_config", return_value=OskConfig(member_heartbeat_timeout_seconds=60)),
    ):
        (tmp_path / "hub-state.json").write_text(
            '{"pid":4321,"operation_name":"March","operation_id":"11111111-1111-1111-1111-111111111111"}\n'
        )

        from osk.hub import status_hub

        code = status_hub()

    out = capsys.readouterr().out
    assert code == 0
    assert "wipe_follow_up_required = false" in out
    assert (
        "wipe_follow_up_counts active_unresolved=0 historical_drift=0 "
        "reviewed_historical_drift=0 retired_historical_drift=1 "
        "verified_current=0" in out
    )
    assert "wipe_follow_up_history_summary = Recent follow-up trail: 1 retired." in out


def test_wipe_follow_up_history_line_formats_retired_action() -> None:
    line = _wipe_follow_up_history_line(
        {
            "member_name": "Observer Retired",
            "reason": "disconnected",
            "status": "retired",
            "action": "wipe_follow_up_historical_retired",
            "retired_at": "2026-03-23T08:05:00Z",
        }
    )

    assert "action=retired" in line
    assert "at=2026-03-23T08:05:00Z" in line


@patch("osk.hub.asyncio.run")
def test_show_findings_formats_rows(mock_asyncio_run: MagicMock, tmp_path: Path, capsys) -> None:
    finding_rows = [
        {
            "title": "Police Action",
            "severity": "warning",
            "status": "open",
            "corroborated": True,
            "last_seen_at": "2026-03-21T12:03:00Z",
            "summary": "Police advancing north. Corroborated by 2 sources across 2 signals.",
        }
    ]

    def return_findings(coro):
        coro.close()
        return finding_rows

    mock_asyncio_run.side_effect = return_findings

    with patch("osk.hub._config_root", return_value=tmp_path):
        (tmp_path / "hub-state.json").write_text(
            '{"operation_id":"11111111-1111-1111-1111-111111111111"}\n'
        )
        from osk.hub import show_findings

        code = show_findings(limit=5)

    out = capsys.readouterr().out
    assert code == 0
    assert "Police Action" in out
    assert "corroborated" in out
    assert "severity=warning" in out


@patch("osk.hub.create_dashboard_bootstrap")
@patch("osk.hub.read_operator_session")
def test_show_dashboard_url_formats_link(
    mock_read_operator_session: MagicMock,
    mock_create_dashboard_bootstrap: MagicMock,
    tmp_path: Path,
    capsys,
) -> None:
    mock_read_operator_session.return_value = {
        "operation_id": "11111111-1111-1111-1111-111111111111",
        "token": "session-token",
        "expires_at": "2026-03-21T19:30:00Z",
    }
    mock_create_dashboard_bootstrap.return_value = {
        "dashboard_code": "one-time-code",
        "expires_at": "2026-03-21T18:05:00Z",
    }

    with patch("osk.hub._config_root", return_value=tmp_path):
        (tmp_path / "hub-state.json").write_text(
            json.dumps(
                {
                    "operation_id": "11111111-1111-1111-1111-111111111111",
                    "operation_name": "March",
                    "port": 18443,
                }
            )
            + "\n"
        )
        from osk.hub import show_dashboard_url

        code = show_dashboard_url()

    out = capsys.readouterr().out
    assert code == 0
    assert "https://127.0.0.1:18443/coordinator" in out
    assert "dashboard_code = one-time-code" in out


@patch("osk.hub.asyncio.run")
def test_show_review_feed_formats_rows(mock_asyncio_run: MagicMock, tmp_path: Path, capsys) -> None:
    review_items = [
        {
            "type": "finding",
            "timestamp": "2026-03-21T12:03:00Z",
            "title": "Police Action",
            "summary": "Police advancing north.",
            "severity": "warning",
            "status": "open",
        },
        {
            "type": "sitrep",
            "timestamp": "2026-03-21T12:05:00Z",
            "summary": "Two police-action findings remain active near the east route.",
            "trend": "escalating",
        },
    ]

    def return_review(coro):
        coro.close()
        return review_items

    mock_asyncio_run.side_effect = return_review

    with patch("osk.hub._config_root", return_value=tmp_path):
        (tmp_path / "hub-state.json").write_text(
            '{"operation_id":"11111111-1111-1111-1111-111111111111"}\n'
        )
        from osk.hub import show_review_feed

        code = show_review_feed(limit=5)

    out = capsys.readouterr().out
    assert code == 0
    assert "[finding]" in out
    assert "[sitrep]" in out
    assert "Police Action" in out


@patch("osk.hub.asyncio.run")
def test_show_finding_formats_detail(mock_asyncio_run: MagicMock, tmp_path: Path, capsys) -> None:
    detail = {
        "finding": {
            "id": "11111111-1111-1111-1111-111111111111",
            "title": "Police Action",
            "severity": "warning",
            "status": "acknowledged",
            "last_seen_at": "2026-03-21T12:03:00Z",
            "summary": "Police advancing north.",
            "source_count": 2,
            "signal_count": 2,
            "observation_count": 3,
            "notes_count": 1,
        },
        "events": [
            {"category": "police_action", "severity": "warning", "text": "Police advancing"}
        ],
        "observations": [],
        "notes": [{"created_at": "2026-03-21T12:04:00Z", "text": "Watching east entrance."}],
    }

    def return_detail(coro):
        coro.close()
        return detail

    mock_asyncio_run.side_effect = return_detail

    with patch("osk.hub._config_root", return_value=tmp_path):
        (tmp_path / "hub-state.json").write_text(
            '{"operation_id":"11111111-1111-1111-1111-111111111111"}\n'
        )
        from osk.hub import show_finding

        code = show_finding("11111111-1111-1111-1111-111111111111")

    out = capsys.readouterr().out
    assert code == 0
    assert "Police Action" in out
    assert "latest_event=police_action:warning" in out
    assert "note[" in out


@patch("osk.hub.asyncio.run")
def test_show_finding_correlations_formats_rows(
    mock_asyncio_run: MagicMock, tmp_path: Path, capsys
) -> None:
    correlations = {
        "finding": {"title": "Police Action"},
        "related_findings": [
            {
                "title": "Blocked Route",
                "severity": "warning",
                "status": "open",
                "correlation_reasons": ["shared_member_context"],
            }
        ],
        "related_events": [
            {
                "text": "Police advancing north",
                "severity": "warning",
                "category": "police_action",
                "correlation_reasons": ["linked_event"],
            }
        ],
        "window_minutes": 30,
    }

    def return_correlations(coro):
        coro.close()
        return correlations

    mock_asyncio_run.side_effect = return_correlations

    with patch("osk.hub._config_root", return_value=tmp_path):
        (tmp_path / "hub-state.json").write_text(
            '{"operation_id":"11111111-1111-1111-1111-111111111111"}\n'
        )
        from osk.hub import show_finding_correlations

        code = show_finding_correlations("11111111-1111-1111-1111-111111111111")

    out = capsys.readouterr().out
    assert code == 0
    assert "Correlations for Police Action" in out
    assert "Blocked Route" in out
    assert "linked_event" in out


@patch("osk.hub.asyncio.run")
def test_acknowledge_finding_updates_state(
    mock_asyncio_run: MagicMock, tmp_path: Path, capsys
) -> None:
    def return_ack(coro):
        coro.close()
        return {"title": "Police Action", "status": "acknowledged"}

    mock_asyncio_run.side_effect = return_ack

    with patch("osk.hub._config_root", return_value=tmp_path):
        (tmp_path / "hub-state.json").write_text(
            '{"operation_id":"11111111-1111-1111-1111-111111111111"}\n'
        )
        from osk.hub import acknowledge_finding

        code = acknowledge_finding("11111111-1111-1111-1111-111111111111")

    out = capsys.readouterr().out
    assert code == 0
    assert "Acknowledged Police Action." in out


@patch("osk.hub.asyncio.run")
def test_reopen_finding_updates_state(mock_asyncio_run: MagicMock, tmp_path: Path, capsys) -> None:
    def return_reopen(coro):
        coro.close()
        return {"title": "Police Action", "status": "open"}

    mock_asyncio_run.side_effect = return_reopen

    with patch("osk.hub._config_root", return_value=tmp_path):
        (tmp_path / "hub-state.json").write_text(
            '{"operation_id":"11111111-1111-1111-1111-111111111111"}\n'
        )
        from osk.hub import reopen_finding

        code = reopen_finding("11111111-1111-1111-1111-111111111111")

    out = capsys.readouterr().out
    assert code == 0
    assert "Reopened Police Action." in out


@patch("osk.hub.asyncio.run")
def test_add_finding_note_reports_success(
    mock_asyncio_run: MagicMock, tmp_path: Path, capsys
) -> None:
    note_id = "11111111-1111-1111-1111-111111111112"

    def return_note(coro):
        coro.close()
        return SimpleNamespace(id=note_id)

    mock_asyncio_run.side_effect = return_note

    with patch("osk.hub._config_root", return_value=tmp_path):
        (tmp_path / "hub-state.json").write_text(
            '{"operation_id":"11111111-1111-1111-1111-111111111111"}\n'
        )
        from osk.hub import add_finding_note

        code = add_finding_note(
            "11111111-1111-1111-1111-111111111111",
            "Hold for dashboard review.",
        )

    out = capsys.readouterr().out
    assert code == 0
    assert note_id in out


async def test_watch_member_heartbeats_disconnects_stale_members() -> None:
    op_manager = MagicMock()
    op_manager.mark_disconnected = AsyncMock()
    conn_manager = MagicMock()
    stale_member_id = "member-1"
    conn_manager.stale_member_ids.side_effect = [[stale_member_id], []]
    conn_manager.disconnect = AsyncMock()

    async def stop_after_first_sleep(_: float) -> None:
        raise asyncio.CancelledError

    with patch("osk.hub.asyncio.sleep", side_effect=stop_after_first_sleep):
        with pytest.raises(asyncio.CancelledError):
            await watch_member_heartbeats(
                op_manager,
                conn_manager,
                timeout_seconds=45,
                poll_seconds=1,
            )

    conn_manager.stale_member_ids.assert_called_once_with(45)
    conn_manager.disconnect.assert_awaited_once_with(stale_member_id)
    op_manager.mark_disconnected.assert_awaited_once_with(stale_member_id)


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


async def test_watch_for_stop_request_drains_connections_before_exit(tmp_path: Path) -> None:
    class DummyServer:
        should_exit = False

    server = DummyServer()
    conn_manager = SimpleNamespace(connected_count=2, disconnect_all=AsyncMock())
    stop_path = tmp_path / "hub-stop-request.json"
    with patch("osk.hub._config_root", return_value=tmp_path):
        task = asyncio.create_task(
            watch_for_stop_request(server, conn_manager=conn_manager, poll_seconds=0.01)
        )
        await asyncio.sleep(0.02)
        stop_path.write_text('{"requested_at": 1, "preserve_operation": true}\n')
        await task

    assert server.should_exit is True
    conn_manager.disconnect_all.assert_awaited_once()


async def test_watch_for_stop_request_broadcasts_op_ended_before_disconnect_on_full_stop(
    tmp_path: Path,
) -> None:
    class DummyServer:
        should_exit = False

    server = DummyServer()
    conn_manager = SimpleNamespace(
        connected_count=2,
        broadcast=AsyncMock(),
        disconnect_all=AsyncMock(),
    )
    stop_path = tmp_path / "hub-stop-request.json"
    with patch("osk.hub._config_root", return_value=tmp_path):
        task = asyncio.create_task(
            watch_for_stop_request(server, conn_manager=conn_manager, poll_seconds=0.01)
        )
        await asyncio.sleep(0.02)
        stop_path.write_text('{"requested_at": 1, "preserve_operation": false}\n')
        await task

    assert server.should_exit is True
    conn_manager.broadcast.assert_awaited_once_with({"type": "op_ended"})
    conn_manager.disconnect_all.assert_awaited_once()
