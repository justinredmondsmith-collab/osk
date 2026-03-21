from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from osk.config import OskConfig
from osk.hub import (
    HubBootstrapError,
    default_storage_manager,
    ensure_local_services,
    installation_issues,
    local_service_mode,
    run_hub_sync,
    uses_local_dev_services,
    wait_for_database,
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


def test_uses_local_dev_services_for_defaults() -> None:
    config = OskConfig()
    assert uses_local_dev_services(config) is True
    assert local_service_mode(config) == "compose-managed local services"


def test_uses_local_dev_services_false_for_external_database() -> None:
    config = OskConfig(database_url="postgresql://example.com:5432/osk")
    assert uses_local_dev_services(config) is False
    assert local_service_mode(config) == "externally managed services"


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
    assert mock_run.call_args.args[0][-2:] == ["db", "ollama"]


@patch("osk.hub.shutil.which", return_value=None)
def test_ensure_local_services_requires_docker(mock_which: MagicMock) -> None:
    with pytest.raises(HubBootstrapError):
        ensure_local_services(OskConfig())
    mock_which.assert_called_once_with("docker")


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
