from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from osk.hotspot import HotspotManager


@pytest.fixture
def hotspot() -> HotspotManager:
    return HotspotManager(ssid="osk-test", band="5GHz", password="osk-secure")


@patch("osk.hotspot.subprocess.run")
def test_check_nmcli_available(mock_run: MagicMock, hotspot: HotspotManager) -> None:
    mock_run.return_value = MagicMock(returncode=0)
    assert hotspot.is_available() is True


@patch("osk.hotspot.subprocess.run")
def test_check_nmcli_unavailable(mock_run: MagicMock, hotspot: HotspotManager) -> None:
    mock_run.side_effect = FileNotFoundError
    assert hotspot.is_available() is False


@patch("osk.hotspot.subprocess.run")
def test_start_hotspot(mock_run: MagicMock, hotspot: HotspotManager) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="Connection activated\n", stderr="")

    result = hotspot.start()

    assert result is True
    command = mock_run.call_args.args[0]
    assert command[:4] == ["nmcli", "device", "wifi", "hotspot"]
    assert "con-name" in command
    assert "osk-test" in command


@patch("osk.hotspot.subprocess.run")
def test_stop_hotspot(mock_run: MagicMock, hotspot: HotspotManager) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

    assert hotspot.stop() is True
    mock_run.assert_called_once()


@patch("osk.hotspot.subprocess.run")
def test_get_ip(mock_run: MagicMock, hotspot: HotspotManager) -> None:
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="IP4.ADDRESS:10.42.0.1/24\n",
        stderr="",
    )

    assert hotspot.get_ip() == "10.42.0.1"


@patch.object(HotspotManager, "is_available", return_value=False)
def test_hotspot_status_includes_manual_instructions(
    _mock_available: MagicMock, hotspot: HotspotManager
) -> None:
    payload = hotspot.status()
    assert payload["available"] is False
    assert "manual_instructions" in payload
    assert "create a wifi hotspot manually" in str(payload["manual_instructions"]).lower()


def test_manual_instructions(hotspot: HotspotManager) -> None:
    instructions = hotspot.get_manual_instructions()
    assert "hotspot" in instructions.lower()
    assert "osk-test" in instructions
