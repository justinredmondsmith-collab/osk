"""Local operator bootstrap and session helpers."""

from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

OPERATOR_BOOTSTRAP_FILENAME = "operator-bootstrap.json"
OPERATOR_SESSION_FILENAME = "operator-session.json"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _state_root() -> Path:
    return Path.home() / ".local" / "state" / "osk"


def bootstrap_session_path() -> Path:
    return _state_root() / OPERATOR_BOOTSTRAP_FILENAME


def operator_session_path() -> Path:
    return _state_root() / OPERATOR_SESSION_FILENAME


def create_bootstrap_session(operation_id: str, ttl_minutes: int) -> dict[str, object]:
    created_at = _utcnow()
    expires_at = created_at + timedelta(minutes=max(ttl_minutes, 1))
    payload = {
        "operation_id": operation_id,
        "bootstrap_token": secrets.token_urlsafe(32),
        "created_at": created_at.isoformat(),
        "expires_at": expires_at.isoformat(),
    }
    path = bootstrap_session_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.chmod(path, 0o600)
    return payload


def clear_bootstrap_session() -> None:
    bootstrap_session_path().unlink(missing_ok=True)


def read_bootstrap_session(*, now: datetime | None = None) -> dict[str, object] | None:
    path = bootstrap_session_path()
    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        clear_bootstrap_session()
        return None
    current_time = now or _utcnow()
    expires_at_raw = payload.get("expires_at")
    if not isinstance(expires_at_raw, str):
        clear_bootstrap_session()
        return None

    expires_at = datetime.fromisoformat(expires_at_raw)
    if expires_at <= current_time:
        clear_bootstrap_session()
        return None
    return payload


def consume_bootstrap_session(operation_id: str, bootstrap_token: str) -> bool:
    payload = read_bootstrap_session()
    if payload is None:
        return False
    if payload.get("operation_id") != operation_id:
        return False
    expected_token = payload.get("bootstrap_token")
    if not isinstance(expected_token, str):
        clear_bootstrap_session()
        return False
    if not secrets.compare_digest(expected_token, bootstrap_token):
        return False
    clear_bootstrap_session()
    return True


def create_operator_session(operation_id: str, ttl_minutes: int) -> dict[str, object]:
    created_at = _utcnow()
    expires_at = created_at + timedelta(minutes=max(ttl_minutes, 1))
    payload = {
        "operation_id": operation_id,
        "token": secrets.token_urlsafe(32),
        "created_at": created_at.isoformat(),
        "expires_at": expires_at.isoformat(),
    }
    path = operator_session_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.chmod(path, 0o600)
    return payload


def clear_operator_session() -> None:
    operator_session_path().unlink(missing_ok=True)


def read_operator_session(*, now: datetime | None = None) -> dict[str, object] | None:
    path = operator_session_path()
    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        clear_operator_session()
        return None
    current_time = now or _utcnow()
    expires_at_raw = payload.get("expires_at")
    if not isinstance(expires_at_raw, str):
        clear_operator_session()
        return None

    expires_at = datetime.fromisoformat(expires_at_raw)
    if expires_at <= current_time:
        clear_operator_session()
        return None
    return payload


def validate_operator_session(token: str, operation_id: str) -> bool:
    payload = read_operator_session()
    if payload is None:
        return False
    if payload.get("operation_id") != operation_id:
        return False
    session_token = payload.get("token")
    if not isinstance(session_token, str):
        return False
    return secrets.compare_digest(session_token, token)
