from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from osk.local_operator import (
    clear_bootstrap_token,
    clear_operator_session,
    create_operator_session,
    read_bootstrap_token,
    read_operator_session,
    validate_operator_session,
    write_bootstrap_token,
)


def test_bootstrap_token_round_trip(tmp_path: Path) -> None:
    with patch("osk.local_operator._state_root", return_value=tmp_path):
        write_bootstrap_token("bootstrap-secret")

        assert read_bootstrap_token() == "bootstrap-secret"

        clear_bootstrap_token()
        assert read_bootstrap_token() is None


def test_operator_session_round_trip(tmp_path: Path) -> None:
    with patch("osk.local_operator._state_root", return_value=tmp_path):
        payload = create_operator_session("operation-1", 60)
        session = read_operator_session()

        assert session is not None
        assert session["operation_id"] == "operation-1"
        assert validate_operator_session(str(payload["token"]), "operation-1") is True
        assert validate_operator_session("wrong-token", "operation-1") is False
        assert validate_operator_session(str(payload["token"]), "operation-2") is False

        clear_operator_session()
        assert read_operator_session() is None


def test_expired_operator_session_is_cleared(tmp_path: Path) -> None:
    expired_now = datetime(2026, 3, 21, 12, 0, tzinfo=timezone.utc)
    expired_at = expired_now - timedelta(minutes=1)
    session_path = tmp_path / "operator-session.json"
    session_path.write_text(
        "{\n"
        '  "operation_id": "operation-1",\n'
        '  "token": "expired-token",\n'
        f'  "created_at": "{(expired_at - timedelta(minutes=5)).isoformat()}",\n'
        f'  "expires_at": "{expired_at.isoformat()}"\n'
        "}\n"
    )

    with patch("osk.local_operator._state_root", return_value=tmp_path):
        assert read_operator_session(now=expired_now) is None
        assert not session_path.exists()
