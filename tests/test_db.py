"""Tests for database layer — uses mocked asyncpg pool."""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from osk.db import Database
from osk.models import EventCategory, EventSeverity, MemberRole


@pytest.fixture
def db() -> Database:
    return Database()


@pytest.fixture
def mock_pool() -> MagicMock:
    pool = MagicMock()
    conn = MagicMock()
    conn.execute = AsyncMock()
    tx = MagicMock()
    tx.__aenter__ = AsyncMock(return_value=None)
    tx.__aexit__ = AsyncMock(return_value=None)
    conn.transaction.return_value = tx
    acquire_ctx = MagicMock()
    acquire_ctx.__aenter__ = AsyncMock(return_value=conn)
    acquire_ctx.__aexit__ = AsyncMock(return_value=None)
    pool.acquire.return_value = acquire_ctx
    pool.execute = AsyncMock()
    pool.fetch = AsyncMock(return_value=[])
    pool.fetchrow = AsyncMock(return_value=None)
    pool.fetchval = AsyncMock(return_value=None)
    pool.close = AsyncMock()
    return pool


async def test_migration_files_exist(db: Database) -> None:
    migrations = db._get_migration_files()
    assert len(migrations) > 0
    assert migrations[0].name == "001_initial.sql"


async def test_insert_operation(db: Database, mock_pool: MagicMock) -> None:
    db._pool = mock_pool
    await db.insert_operation(uuid.uuid4(), "Test Op", "token123")
    mock_pool.execute.assert_called_once()
    assert "INSERT INTO operations" in mock_pool.execute.call_args[0][0]


async def test_insert_member(db: Database, mock_pool: MagicMock) -> None:
    db._pool = mock_pool
    await db.insert_member(uuid.uuid4(), uuid.uuid4(), "Jay", MemberRole.OBSERVER)
    mock_pool.execute.assert_called_once()


async def test_update_member_gps(db: Database, mock_pool: MagicMock) -> None:
    db._pool = mock_pool
    await db.update_member_gps(uuid.uuid4(), 39.75, -104.99)
    mock_pool.execute.assert_called_once()
    assert "UPDATE members" in mock_pool.execute.call_args[0][0]


async def test_insert_event(db: Database, mock_pool: MagicMock) -> None:
    db._pool = mock_pool
    await db.insert_event(
        uuid.uuid4(),
        uuid.uuid4(),
        EventSeverity.WARNING,
        EventCategory.POLICE_ACTION,
        "Police staging",
        None,
        39.75,
        -104.99,
    )
    mock_pool.execute.assert_called_once()


async def test_get_events_since(db: Database, mock_pool: MagicMock) -> None:
    db._pool = mock_pool
    result = await db.get_events_since(uuid.uuid4(), "2026-01-01T00:00:00Z")
    assert result == []


async def test_run_migrations_applies_only_pending(
    db: Database,
    mock_pool: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration_one = tmp_path / "001_first.sql"
    migration_two = tmp_path / "002_second.sql"
    migration_one.write_text("CREATE TABLE first_table(id INT);")
    migration_two.write_text("CREATE TABLE second_table(id INT);")

    monkeypatch.setattr("osk.db.MIGRATIONS_DIR", tmp_path)
    mock_pool.fetch.return_value = [{"filename": "001_first.sql"}]
    db._pool = mock_pool

    await db._run_migrations()

    assert mock_pool.execute.await_count == 1
    assert "schema_migrations" in mock_pool.execute.await_args.args[0]
    assert mock_pool.acquire.return_value.__aenter__.return_value.execute.await_count == 2
    execute_calls = mock_pool.acquire.return_value.__aenter__.return_value.execute.await_args_list
    assert "CREATE TABLE second_table" in execute_calls[0].args[0]
    assert execute_calls[1].args == (
        "INSERT INTO schema_migrations (filename) VALUES ($1)",
        "002_second.sql",
    )
