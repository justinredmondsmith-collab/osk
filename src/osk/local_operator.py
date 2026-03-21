"""Local operator bootstrap and session helpers."""

from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

BOOTSTRAP_TOKEN_FILENAME = "coordinator-token.txt"
OPERATOR_SESSION_FILENAME = "operator-session.json"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _state_root() -> Path:
    return Path.home() / ".local" / "state" / "osk"


def bootstrap_token_path() -> Path:
    return _state_root() / BOOTSTRAP_TOKEN_FILENAME


def operator_session_path() -> Path:
    return _state_root() / OPERATOR_SESSION_FILENAME


def write_bootstrap_token(token: str) -> Path:
    path = bootstrap_token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token + "\n")
    os.chmod(path, 0o600)
    return path


def read_bootstrap_token() -> str | None:
    path = bootstrap_token_path()
    if not path.exists():
        return None
    token = path.read_text().strip()
    return token or None


def clear_bootstrap_token() -> None:
    bootstrap_token_path().unlink(missing_ok=True)


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

    payload = json.loads(path.read_text())
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
