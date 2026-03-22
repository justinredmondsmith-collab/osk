"""Local operator bootstrap and session helpers."""

from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

OPERATOR_BOOTSTRAP_FILENAME = "operator-bootstrap.json"
OPERATOR_SESSION_FILENAME = "operator-session.json"
DASHBOARD_BOOTSTRAP_FILENAME = "dashboard-bootstrap.json"
DASHBOARD_SESSION_FILENAME = "dashboard-session.json"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _state_root() -> Path:
    return Path.home() / ".local" / "state" / "osk"


def _write_payload(path: Path, payload: dict[str, object]) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.chmod(path, 0o600)
    return payload


def _read_ttl_payload(
    path: Path,
    *,
    clear_func,
    now: datetime | None = None,
) -> dict[str, object] | None:
    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        clear_func()
        return None

    current_time = now or _utcnow()
    expires_at_raw = payload.get("expires_at")
    if not isinstance(expires_at_raw, str):
        clear_func()
        return None

    try:
        expires_at = datetime.fromisoformat(expires_at_raw)
    except ValueError:
        clear_func()
        return None
    if expires_at <= current_time:
        clear_func()
        return None
    return payload


def _create_token_payload(
    operation_id: str,
    *,
    ttl_minutes: int,
    token_field: str,
) -> dict[str, object]:
    created_at = _utcnow()
    expires_at = created_at + timedelta(minutes=max(ttl_minutes, 1))
    return {
        "operation_id": operation_id,
        token_field: secrets.token_urlsafe(32),
        "created_at": created_at.isoformat(),
        "expires_at": expires_at.isoformat(),
    }


def _consume_token_payload(
    operation_id: str,
    token: str,
    *,
    token_field: str,
    read_func,
    clear_func,
) -> bool:
    payload = read_func()
    if payload is None:
        return False
    if payload.get("operation_id") != operation_id:
        return False
    expected_token = payload.get(token_field)
    if not isinstance(expected_token, str):
        clear_func()
        return False
    if not secrets.compare_digest(expected_token, token):
        return False
    clear_func()
    return True


def _validate_session_token(
    token: str,
    operation_id: str,
    *,
    read_func,
) -> bool:
    payload = read_func()
    if payload is None:
        return False
    if payload.get("operation_id") != operation_id:
        return False
    session_token = payload.get("token")
    if not isinstance(session_token, str):
        return False
    return secrets.compare_digest(session_token, token)


def bootstrap_session_path() -> Path:
    return _state_root() / OPERATOR_BOOTSTRAP_FILENAME


def operator_session_path() -> Path:
    return _state_root() / OPERATOR_SESSION_FILENAME


def dashboard_bootstrap_path() -> Path:
    return _state_root() / DASHBOARD_BOOTSTRAP_FILENAME


def dashboard_session_path() -> Path:
    return _state_root() / DASHBOARD_SESSION_FILENAME


def create_bootstrap_session(operation_id: str, ttl_minutes: int) -> dict[str, object]:
    return _write_payload(
        bootstrap_session_path(),
        _create_token_payload(
            operation_id,
            ttl_minutes=ttl_minutes,
            token_field="bootstrap_token",
        ),
    )


def clear_bootstrap_session() -> None:
    bootstrap_session_path().unlink(missing_ok=True)


def read_bootstrap_session(*, now: datetime | None = None) -> dict[str, object] | None:
    return _read_ttl_payload(
        bootstrap_session_path(),
        clear_func=clear_bootstrap_session,
        now=now,
    )


def consume_bootstrap_session(operation_id: str, bootstrap_token: str) -> bool:
    return _consume_token_payload(
        operation_id,
        bootstrap_token,
        token_field="bootstrap_token",
        read_func=read_bootstrap_session,
        clear_func=clear_bootstrap_session,
    )


def create_operator_session(operation_id: str, ttl_minutes: int) -> dict[str, object]:
    return _write_payload(
        operator_session_path(),
        _create_token_payload(
            operation_id,
            ttl_minutes=ttl_minutes,
            token_field="token",
        ),
    )


def clear_operator_session() -> None:
    operator_session_path().unlink(missing_ok=True)


def read_operator_session(*, now: datetime | None = None) -> dict[str, object] | None:
    return _read_ttl_payload(
        operator_session_path(),
        clear_func=clear_operator_session,
        now=now,
    )


def validate_operator_session(token: str, operation_id: str) -> bool:
    return _validate_session_token(
        token,
        operation_id,
        read_func=read_operator_session,
    )


def create_dashboard_bootstrap(operation_id: str, ttl_minutes: int) -> dict[str, object]:
    return _write_payload(
        dashboard_bootstrap_path(),
        _create_token_payload(
            operation_id,
            ttl_minutes=ttl_minutes,
            token_field="dashboard_code",
        ),
    )


def clear_dashboard_bootstrap() -> None:
    dashboard_bootstrap_path().unlink(missing_ok=True)


def read_dashboard_bootstrap(*, now: datetime | None = None) -> dict[str, object] | None:
    return _read_ttl_payload(
        dashboard_bootstrap_path(),
        clear_func=clear_dashboard_bootstrap,
        now=now,
    )


def consume_dashboard_bootstrap_code(operation_id: str, dashboard_code: str) -> bool:
    return _consume_token_payload(
        operation_id,
        dashboard_code,
        token_field="dashboard_code",
        read_func=read_dashboard_bootstrap,
        clear_func=clear_dashboard_bootstrap,
    )


def create_dashboard_session(operation_id: str, ttl_minutes: int) -> dict[str, object]:
    return _write_payload(
        dashboard_session_path(),
        _create_token_payload(
            operation_id,
            ttl_minutes=ttl_minutes,
            token_field="token",
        ),
    )


def clear_dashboard_session() -> None:
    dashboard_session_path().unlink(missing_ok=True)


def read_dashboard_session(*, now: datetime | None = None) -> dict[str, object] | None:
    return _read_ttl_payload(
        dashboard_session_path(),
        clear_func=clear_dashboard_session,
        now=now,
    )


def validate_dashboard_session(token: str, operation_id: str) -> bool:
    return _validate_session_token(
        token,
        operation_id,
        read_func=read_dashboard_session,
    )
