"""Tests for database layer — uses mocked asyncpg pool."""

from __future__ import annotations

import uuid
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
