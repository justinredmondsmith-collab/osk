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


def test_parse_install() -> None:
    args = parse_args(["install"])
    assert args.command == "install"


def test_parse_config() -> None:
    args = parse_args(["config", "--set", "max_sensors=5"])
    assert args.command == "config"
    assert args.set == "max_sensors=5"


def test_parse_evidence_unlock() -> None:
    args = parse_args(["evidence", "unlock"])
    assert args.command == "evidence"
    assert args.evidence_command == "unlock"


def test_parse_evidence_export() -> None:
    args = parse_args(["evidence", "export"])
    assert args.evidence_command == "export"


def test_parse_evidence_destroy() -> None:
    args = parse_args(["evidence", "destroy"])
    assert args.evidence_command == "destroy"


def test_parse_rotate_token() -> None:
    args = parse_args(["rotate-token"])
    assert args.command == "rotate-token"


@patch("osk.cli.load_config")
def test_config_prints_values(mock_load_config: MagicMock, capsys) -> None:
    mock_load_config.return_value = MagicMock(model_dump=MagicMock(return_value={"max_sensors": 10}))
    code = main(["config"])
    out = capsys.readouterr().out
    assert code == 0
    assert "max_sensors = 10" in out


@patch("osk.cli.save_config")
@patch("osk.cli.load_config")
def test_config_set_updates_value(mock_load_config: MagicMock, mock_save_config: MagicMock, capsys) -> None:
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
