from __future__ import annotations

from unittest.mock import MagicMock, patch

from osk.cli import main, parse_args


def test_parse_start() -> None:
    args = parse_args(["start", "My Operation"])
    assert args.command == "start"
    assert args.name == "My Operation"


def test_parse_stop() -> None:
    args = parse_args(["stop"])
    assert args.command == "stop"
    assert args.services is False
    assert args.timeout == 10.0


def test_parse_stop_with_options() -> None:
    args = parse_args(["stop", "--services", "--timeout", "5"])
    assert args.command == "stop"
    assert args.services is True
    assert args.timeout == 5.0


def test_parse_status() -> None:
    args = parse_args(["status"])
    assert args.command == "status"
    assert args.json_output is False


def test_parse_status_json() -> None:
    args = parse_args(["status", "--json"])
    assert args.command == "status"
    assert args.json_output is True


def test_parse_doctor_json() -> None:
    args = parse_args(["doctor", "--json"])
    assert args.command == "doctor"
    assert args.json_output is True


def test_parse_operator_login() -> None:
    args = parse_args(["operator", "login", "--ttl-minutes", "30", "--json"])
    assert args.command == "operator"
    assert args.operator_command == "login"
    assert args.ttl_minutes == 30
    assert args.json_output is True


def test_parse_operator_status() -> None:
    args = parse_args(["operator", "status", "--json"])
    assert args.command == "operator"
    assert args.operator_command == "status"
    assert args.json_output is True


def test_parse_operator_logout() -> None:
    args = parse_args(["operator", "logout"])
    assert args.command == "operator"
    assert args.operator_command == "logout"


def test_parse_audit() -> None:
    args = parse_args(["audit", "--limit", "5", "--json"])
    assert args.command == "audit"
    assert args.limit == 5
    assert args.json_output is True


def test_parse_logs() -> None:
    args = parse_args(["logs", "--tail", "25"])
    assert args.command == "logs"
    assert args.tail == 25


def test_parse_dashboard() -> None:
    args = parse_args(["dashboard", "--json"])
    assert args.command == "dashboard"
    assert args.json_output is True


def test_parse_members() -> None:
    args = parse_args(["members", "--json"])
    assert args.command == "members"
    assert args.json_output is True


def test_parse_review() -> None:
    args = parse_args(
        [
            "review",
            "--limit",
            "15",
            "--include",
            "finding",
            "--include",
            "event",
            "--status",
            "open",
            "--severity",
            "warning",
            "--category",
            "police_action",
            "--json",
        ]
    )
    assert args.command == "review"
    assert args.limit == 15
    assert args.include == ["finding", "event"]
    assert args.status == "open"
    assert args.severity == "warning"
    assert args.category == "police_action"
    assert args.json_output is True


def test_parse_install() -> None:
    args = parse_args(["install"])
    assert args.command == "install"


def test_parse_config() -> None:
    args = parse_args(["config", "--set", "max_sensors=5"])
    assert args.command == "config"
    assert args.set == "max_sensors=5"


def test_parse_evidence_unlock() -> None:
    args = parse_args(["evidence", "unlock", "--json"])
    assert args.command == "evidence"
    assert args.evidence_command == "unlock"
    assert args.json_output is True


def test_parse_evidence_export() -> None:
    args = parse_args(["evidence", "export", "--output", "bundle.zip", "--json"])
    assert args.evidence_command == "export"
    assert args.output == "bundle.zip"
    assert args.json_output is True


def test_parse_evidence_destroy() -> None:
    args = parse_args(["evidence", "destroy", "--yes", "--json"])
    assert args.evidence_command == "destroy"
    assert args.yes is True
    assert args.json_output is True


def test_parse_tiles_status() -> None:
    args = parse_args(["tiles", "status", "--json"])
    assert args.command == "tiles"
    assert args.tiles_command == "status"
    assert args.json_output is True


def test_parse_tiles_cache() -> None:
    args = parse_args(
        ["tiles", "cache", "--bbox", "39.7,-104.9,39.8,-104.8", "--zoom", "13-15", "--json"]
    )
    assert args.command == "tiles"
    assert args.tiles_command == "cache"
    assert args.bbox == "39.7,-104.9,39.8,-104.8"
    assert args.zoom == "13-15"
    assert args.json_output is True


def test_parse_hotspot_status() -> None:
    args = parse_args(["hotspot", "status", "--json"])
    assert args.command == "hotspot"
    assert args.hotspot_command == "status"
    assert args.json_output is True


def test_parse_hotspot_up() -> None:
    args = parse_args(["hotspot", "up", "--password", "osk-secure"])
    assert args.command == "hotspot"
    assert args.hotspot_command == "up"
    assert args.password == "osk-secure"


def test_parse_hotspot_down() -> None:
    args = parse_args(["hotspot", "down"])
    assert args.command == "hotspot"
    assert args.hotspot_command == "down"


def test_parse_hotspot_instructions() -> None:
    args = parse_args(["hotspot", "instructions", "--ssid", "osk-local"])
    assert args.command == "hotspot"
    assert args.hotspot_command == "instructions"
    assert args.ssid == "osk-local"


def test_parse_rotate_token() -> None:
    args = parse_args(["rotate-token"])
    assert args.command == "rotate-token"


@patch("osk.cli.load_config")
def test_config_prints_values(mock_load_config: MagicMock, capsys) -> None:
    mock_load_config.return_value = MagicMock(
        model_dump=MagicMock(return_value={"max_sensors": 10})
    )
    code = main(["config"])
    out = capsys.readouterr().out
    assert code == 0
    assert "max_sensors = 10" in out


@patch("osk.cli.save_config")
@patch("osk.cli.load_config")
def test_config_set_updates_value(
    mock_load_config: MagicMock, mock_save_config: MagicMock, capsys
) -> None:
    cfg = MagicMock()
    cfg.model_fields = {"max_sensors": object()}
    cfg.max_sensors = 10
    cfg.model_copy.return_value = MagicMock(max_sensors=5)
    mock_load_config.return_value = cfg
    code = main(["config", "--set", "max_sensors=5"])
    out = capsys.readouterr().out
    assert code == 0
    assert "Set max_sensors = 5" in out
    mock_save_config.assert_called_once()


@patch("osk.cli.load_config")
@patch("osk.tiles.TileCacher.status")
def test_tiles_status_prints_summary(
    mock_status: MagicMock, mock_load_config: MagicMock, capsys
) -> None:
    mock_load_config.return_value = MagicMock(map_tile_cache_path="/tmp/osk-tiles")
    mock_status.return_value = {
        "cache_root": "/tmp/osk-tiles",
        "present": True,
        "tile_count": 3,
        "total_bytes": 2048,
        "zoom_levels": [13, 14],
    }

    code = main(["tiles", "status"])
    out = capsys.readouterr().out

    assert code == 0
    assert "cache_root = /tmp/osk-tiles" in out
    assert "tile_count = 3" in out
    assert "zoom_levels = 13, 14" in out


@patch("osk.cli.load_config")
@patch("osk.hotspot.HotspotManager.status")
def test_hotspot_status_prints_summary(
    mock_status: MagicMock, mock_load_config: MagicMock, capsys
) -> None:
    mock_load_config.return_value = MagicMock(hotspot_ssid="osk-local", hotspot_band="5GHz")
    mock_status.return_value = {
        "available": True,
        "ssid": "osk-local",
        "band": "5GHz",
        "connection_name": "osk-local",
        "ip_address": "10.42.0.1",
        "manual_instructions": None,
    }

    code = main(["hotspot", "status"])
    out = capsys.readouterr().out

    assert code == 0
    assert "available = True" in out
    assert "ip_address = 10.42.0.1" in out


@patch("osk.cli._evidence_manager")
@patch("osk.cli.getpass.getpass", return_value="secret")
def test_evidence_unlock_prints_items(
    _mock_getpass: MagicMock, mock_manager_factory: MagicMock, capsys
) -> None:
    manager = MagicMock()
    manager.backend = "luks"
    manager.unlock.return_value = {
        "ok": True,
        "mount_path": "/tmp/evidence",
        "item_count": 1,
        "items": [{"path": "event_001.json", "size_bytes": 16}],
    }
    mock_manager_factory.return_value = manager

    code = main(["evidence", "unlock"])
    out = capsys.readouterr().out

    assert code == 0
    assert "mount_path = /tmp/evidence" in out
    assert "event_001.json" in out


@patch("osk.cli._evidence_manager")
def test_evidence_export_prints_summary(mock_manager_factory: MagicMock, capsys) -> None:
    manager = MagicMock()
    manager.export.return_value = {
        "ok": True,
        "output_path": "/tmp/export.zip",
        "file_count": 2,
        "total_bytes": 2048,
    }
    mock_manager_factory.return_value = manager

    code = main(["evidence", "export", "--output", "/tmp/export.zip"])
    out = capsys.readouterr().out

    assert code == 0
    assert "output_path = /tmp/export.zip" in out
    assert "file_count = 2" in out


@patch("osk.cli._repo_root")
@patch("osk.hub.default_storage_manager")
@patch("osk.hub.installation_issues", return_value=[])
@patch("osk.hub.local_service_mode", return_value="compose-managed local services")
def test_doctor_reports_scaffold_ready(
    _: MagicMock,
    __: MagicMock,
    ___: MagicMock,
    mock_repo_root: MagicMock,
    tmp_path,
    capsys,
) -> None:
    root = tmp_path / "repo"
    (root / "src" / "osk").mkdir(parents=True)
    (root / "tests").mkdir(parents=True)
    (root / "docs" / "specs").mkdir(parents=True)
    (root / "docs" / "plans").mkdir(parents=True)
    (root / "pyproject.toml").write_text("")
    (root / "docs" / "specs" / "2026-03-21-osk-design.md").write_text("")
    mock_repo_root.return_value = root
    code = main(["doctor"])
    out = capsys.readouterr().out
    assert code == 0
    assert "Scaffold ready for Phase 1 implementation work." in out
    assert "Install readiness: ok" in out


@patch("osk.cli._repo_root")
@patch(
    "osk.hub.hub_status_snapshot",
    return_value=(
        1,
        {"message": "Osk hub is not running.", "status": "stopped", "stopping": False},
    ),
)
@patch("osk.hub.default_storage_manager")
@patch("osk.hub.installation_issues", return_value=[])
@patch("osk.hub.local_service_mode", return_value="compose-managed local services")
def test_doctor_json_output(
    _: MagicMock,
    __: MagicMock,
    ___: MagicMock,
    ____: MagicMock,
    mock_repo_root: MagicMock,
    tmp_path,
    capsys,
) -> None:
    root = tmp_path / "repo"
    (root / "src" / "osk").mkdir(parents=True)
    (root / "tests").mkdir(parents=True)
    (root / "docs" / "specs").mkdir(parents=True)
    (root / "docs" / "plans").mkdir(parents=True)
    (root / "pyproject.toml").write_text("")
    (root / "docs" / "specs" / "2026-03-21-osk-design.md").write_text("")
    mock_repo_root.return_value = root
    code = main(["doctor", "--json"])
    out = capsys.readouterr().out
    assert code == 0
    assert '"ready": true' in out
    assert '"service_mode": "compose-managed local services"' in out


@patch("osk.cli._repo_root")
@patch("osk.hub.default_storage_manager")
@patch("osk.hub.installation_issues", return_value=["missing TLS certificate"])
@patch("osk.hub.local_service_mode", return_value="compose-managed local services")
def test_doctor_reports_missing_install_assets(
    _: MagicMock,
    __: MagicMock,
    ___: MagicMock,
    mock_repo_root: MagicMock,
    tmp_path,
    capsys,
) -> None:
    root = tmp_path / "repo"
    (root / "src" / "osk").mkdir(parents=True)
    (root / "tests").mkdir(parents=True)
    (root / "docs" / "specs").mkdir(parents=True)
    (root / "docs" / "plans").mkdir(parents=True)
    (root / "pyproject.toml").write_text("")
    (root / "docs" / "specs" / "2026-03-21-osk-design.md").write_text("")
    mock_repo_root.return_value = root
    code = main(["doctor"])
    out = capsys.readouterr().out
    assert code == 1
    assert "Install readiness: missing" in out
    assert "missing TLS certificate" in out


@patch("osk.hub.stop_hub", return_value=0)
def test_stop_command_invokes_hub_stop(mock_stop_hub: MagicMock) -> None:
    code = main(["stop", "--services", "--timeout", "3"])
    assert code == 0
    mock_stop_hub.assert_called_once_with(wait_seconds=3.0, stop_services=True)


@patch("osk.hub.status_hub", return_value=0)
def test_status_command_invokes_hub_status(mock_status_hub: MagicMock) -> None:
    code = main(["status"])
    assert code == 0
    mock_status_hub.assert_called_once_with(json_output=False)


@patch("osk.hub.status_hub", return_value=0)
def test_status_command_invokes_hub_status_json(mock_status_hub: MagicMock) -> None:
    code = main(["status", "--json"])
    assert code == 0
    mock_status_hub.assert_called_once_with(json_output=True)


@patch("osk.hub.login_operator_session", return_value=0)
def test_operator_login_command_invokes_hub_helper(mock_login_operator_session: MagicMock) -> None:
    code = main(["operator", "login", "--ttl-minutes", "30", "--json"])
    assert code == 0
    mock_login_operator_session.assert_called_once_with(ttl_minutes=30, json_output=True)


@patch("osk.hub.status_operator_session", return_value=0)
def test_operator_status_command_invokes_hub_helper(
    mock_status_operator_session: MagicMock,
) -> None:
    code = main(["operator", "status", "--json"])
    assert code == 0
    mock_status_operator_session.assert_called_once_with(json_output=True)


@patch("osk.hub.logout_operator_session", return_value=0)
def test_operator_logout_command_invokes_hub_helper(
    mock_logout_operator_session: MagicMock,
) -> None:
    code = main(["operator", "logout"])
    assert code == 0
    mock_logout_operator_session.assert_called_once_with()


@patch("osk.hub.show_audit_events", return_value=0)
def test_audit_command_invokes_hub_helper(mock_show_audit_events: MagicMock) -> None:
    code = main(["audit", "--limit", "5", "--json"])
    assert code == 0
    mock_show_audit_events.assert_called_once_with(limit=5, json_output=True)


@patch("osk.hub.show_runtime_logs", return_value=0)
def test_logs_command_invokes_hub_helper(mock_show_runtime_logs: MagicMock) -> None:
    code = main(["logs", "--tail", "25"])
    assert code == 0
    mock_show_runtime_logs.assert_called_once_with(tail=25)


@patch("osk.hub.show_dashboard_url", return_value=0)
def test_dashboard_command_invokes_hub_helper(mock_show_dashboard_url: MagicMock) -> None:
    code = main(["dashboard", "--json"])
    assert code == 0
    mock_show_dashboard_url.assert_called_once_with(json_output=True)


@patch("osk.hub.show_members", return_value=0)
def test_members_command_invokes_hub_helper(mock_show_members: MagicMock) -> None:
    code = main(["members", "--json"])
    assert code == 0
    mock_show_members.assert_called_once_with(json_output=True)


@patch("osk.hub.show_findings", return_value=0)
def test_findings_command_invokes_hub_helper(mock_show_findings: MagicMock) -> None:
    code = main(["findings", "--limit", "7", "--json"])
    assert code == 0
    mock_show_findings.assert_called_once_with(limit=7, json_output=True)


@patch("osk.hub.show_review_feed", return_value=0)
def test_review_command_invokes_hub_helper(mock_show_review_feed: MagicMock) -> None:
    code = main(
        [
            "review",
            "--limit",
            "9",
            "--include",
            "finding",
            "--include",
            "sitrep",
            "--status",
            "acknowledged",
            "--severity",
            "warning",
            "--category",
            "police_action",
            "--json",
        ]
    )
    assert code == 0
    mock_show_review_feed.assert_called_once()
    _, kwargs = mock_show_review_feed.call_args
    assert kwargs["limit"] == 9
    assert kwargs["include_types"] == {"finding", "sitrep"}
    assert kwargs["finding_status"].value == "acknowledged"
    assert kwargs["severity"].value == "warning"
    assert kwargs["category"].value == "police_action"
    assert kwargs["json_output"] is True


@patch("osk.hub.show_finding", return_value=0)
def test_finding_show_command_invokes_hub_helper(mock_show_finding: MagicMock) -> None:
    finding_id = "11111111-1111-1111-1111-111111111111"
    code = main(["finding", "show", finding_id, "--json"])
    assert code == 0
    mock_show_finding.assert_called_once_with(finding_id, json_output=True)


@patch("osk.hub.acknowledge_finding", return_value=0)
def test_finding_ack_command_invokes_hub_helper(mock_acknowledge_finding: MagicMock) -> None:
    finding_id = "11111111-1111-1111-1111-111111111111"
    code = main(["finding", "acknowledge", finding_id])
    assert code == 0
    mock_acknowledge_finding.assert_called_once_with(finding_id)


@patch("osk.hub.resolve_finding", return_value=0)
def test_finding_resolve_command_invokes_hub_helper(mock_resolve_finding: MagicMock) -> None:
    finding_id = "11111111-1111-1111-1111-111111111111"
    code = main(["finding", "resolve", finding_id])
    assert code == 0
    mock_resolve_finding.assert_called_once_with(finding_id)


@patch("osk.hub.reopen_finding", return_value=0)
def test_finding_reopen_command_invokes_hub_helper(mock_reopen_finding: MagicMock) -> None:
    finding_id = "11111111-1111-1111-1111-111111111111"
    code = main(["finding", "reopen", finding_id])
    assert code == 0
    mock_reopen_finding.assert_called_once_with(finding_id)


@patch("osk.hub.escalate_finding", return_value=0)
def test_finding_escalate_command_invokes_hub_helper(mock_escalate_finding: MagicMock) -> None:
    finding_id = "11111111-1111-1111-1111-111111111111"
    code = main(["finding", "escalate", finding_id])
    assert code == 0
    mock_escalate_finding.assert_called_once_with(finding_id)


@patch("osk.hub.show_finding_correlations", return_value=0)
def test_finding_correlations_command_invokes_hub_helper(
    mock_show_finding_correlations: MagicMock,
) -> None:
    finding_id = "11111111-1111-1111-1111-111111111111"
    code = main(["finding", "correlations", finding_id, "--limit", "4", "--window-minutes", "12"])
    assert code == 0
    mock_show_finding_correlations.assert_called_once_with(
        finding_id,
        limit=4,
        window_minutes=12,
        json_output=False,
    )


@patch("osk.hub.add_finding_note", return_value=0)
def test_finding_note_command_invokes_hub_helper(mock_add_finding_note: MagicMock) -> None:
    finding_id = "11111111-1111-1111-1111-111111111111"
    code = main(["finding", "note", finding_id, "Hold for dashboard review"])
    assert code == 0
    mock_add_finding_note.assert_called_once_with(finding_id, "Hold for dashboard review")
