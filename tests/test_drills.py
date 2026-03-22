from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from osk.config import OskConfig
from osk.drills import install_drill_report, wipe_drill_report


@patch(
    "osk.drills.hotspot_preflight_status",
    return_value={
        "actions": [],
        "available": True,
        "band": "5GHz",
        "connection_name": "osk-local",
        "ip_address": "10.42.0.1",
        "join_host": "10.42.0.1",
        "join_host_scope": "hotspot_ip",
        "manual_instructions": None,
        "recommended_join_host": "10.42.0.1",
        "ssid": "osk-local",
        "status": "active",
        "warnings": [],
    },
)
@patch("osk.drills._find_compose_command", return_value=["docker", "compose"])
def test_install_drill_report_ready(
    _mock_compose: MagicMock,
    _mock_hotspot: MagicMock,
    tmp_path: Path,
) -> None:
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    evidence_path = tmp_path / "evidence.luks"
    cert_path.write_text("cert")
    key_path.write_text("key")
    evidence_path.write_text("evidence")

    config = OskConfig(
        tls_cert_path=str(cert_path),
        tls_key_path=str(key_path),
        hotspot_ssid="osk-local",
        join_host="10.42.0.1",
    )

    with patch("osk.drills.default_storage_manager") as mock_storage:
        storage = MagicMock()
        storage.backend = "luks"
        storage.tmpfs_path = tmp_path / "runtime"
        storage.luks_mount_path = tmp_path / "evidence"
        storage.luks_image_path = evidence_path
        mock_storage.return_value = storage

        report = install_drill_report(config)

    assert report["status"] == "ready"
    assert report["install_ready"] is True
    assert report["compose"]["available"] is True
    assert report["issues"] == []


@patch(
    "osk.drills.hotspot_preflight_status",
    return_value={
        "actions": ["Use `osk hotspot up --password <passphrase>` if needed."],
        "available": True,
        "band": "5GHz",
        "connection_name": "osk-local",
        "ip_address": None,
        "join_host": "127.0.0.1",
        "join_host_scope": "loopback",
        "manual_instructions": None,
        "recommended_join_host": None,
        "ssid": "osk-local",
        "status": "available_inactive",
        "warnings": ["join_host loopback warning"],
    },
)
@patch("osk.drills._find_compose_command", side_effect=RuntimeError("no compose"))
def test_install_drill_report_surfaces_compose_gap(
    _mock_compose: MagicMock,
    _mock_hotspot: MagicMock,
    tmp_path: Path,
) -> None:
    config = OskConfig(
        tls_cert_path=str(tmp_path / "cert.pem"),
        tls_key_path=str(tmp_path / "key.pem"),
    )
    with patch("osk.drills.default_storage_manager") as mock_storage:
        storage = MagicMock()
        storage.backend = "luks"
        storage.tmpfs_path = tmp_path / "runtime"
        storage.luks_mount_path = tmp_path / "evidence"
        storage.luks_image_path = tmp_path / "evidence.luks"
        mock_storage.return_value = storage

        report = install_drill_report(config)

    assert report["status"] == "needs_attention"
    assert any("missing Compose-compatible runtime" in issue for issue in report["issues"])
    assert any("Install docker/podman support" in step for step in report["next_steps"])


def test_wipe_drill_report_surfaces_current_partial_state(tmp_path: Path) -> None:
    config = OskConfig(storage_backend="directory")

    with (
        patch("osk.drills.default_storage_manager") as mock_storage,
        patch("osk.drills.read_hub_state", return_value=None),
        patch("osk.drills.read_operator_session", return_value=None),
        patch(
            "osk.drills.bootstrap_session_path",
            return_value=tmp_path / "operator-bootstrap.json",
        ),
        patch(
            "osk.drills.operator_session_path",
            return_value=tmp_path / "operator-session.json",
        ),
        patch(
            "osk.drills.dashboard_bootstrap_path",
            return_value=tmp_path / "dashboard-bootstrap.json",
        ),
        patch(
            "osk.drills.dashboard_session_path",
            return_value=tmp_path / "dashboard-session.json",
        ),
    ):
        storage = MagicMock()
        storage.backend = "directory"
        storage.tmpfs_path = tmp_path / "runtime"
        storage.luks_mount_path = tmp_path / "evidence"
        storage.luks_image_path = tmp_path / "unused.luks"
        mock_storage.return_value = storage

        report = wipe_drill_report(config)

    assert report["status"] == "partial"
    assert report["hub_running"] is False
    assert report["operator_session_active"] is False
    assert any("No running hub state was found" in gap for gap in report["gaps"])
    assert any(
        capability["name"] == "coordinator_wipe_command" for capability in report["capabilities"]
    )
    assert any("Run `osk wipe --yes`" in step for step in report["next_steps"])
    assert any("directory-backed development storage" in step for step in report["next_steps"])
