"""Tests for database layer — uses mocked asyncpg pool."""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from osk.db import Database
from osk.intelligence_contracts import IntelligenceObservation, ObservationKind
from osk.models import EventCategory, EventSeverity, MemberRole, SynthesisFinding


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
    assert len(migrations) >= 6
    assert migrations[0].name == "001_initial.sql"
    assert migrations[1].name == "002_operation_coordinator_token.sql"
    assert migrations[2].name == "003_members_reconnect_and_audit.sql"
    assert migrations[3].name == "004_member_heartbeat.sql"
    assert migrations[4].name == "005_intelligence_observations.sql"
    assert migrations[5].name == "006_synthesis_findings.sql"


async def test_insert_operation(db: Database, mock_pool: MagicMock) -> None:
    db._pool = mock_pool
    await db.insert_operation(
        uuid.uuid4(),
        "Test Op",
        "token123",
        "coordinator123",
        datetime.fromisoformat("2026-03-21T00:00:00+00:00"),
    )
    mock_pool.execute.assert_called_once()
    assert "INSERT INTO operations" in mock_pool.execute.call_args[0][0]


async def test_get_active_operation(db: Database, mock_pool: MagicMock) -> None:
    db._pool = mock_pool
    row = {"id": uuid.uuid4(), "name": "Active", "token": "join", "coordinator_token": "admin"}
    mock_pool.fetchrow = AsyncMock(return_value=row)
    result = await db.get_active_operation()
    assert result == row


async def test_mark_operation_stopped(db: Database, mock_pool: MagicMock) -> None:
    db._pool = mock_pool
    await db.mark_operation_stopped(
        uuid.uuid4(),
        datetime.fromisoformat("2026-03-21T01:00:00+00:00"),
    )
    mock_pool.execute.assert_called_once()
    assert "UPDATE operations SET stopped_at" in mock_pool.execute.call_args.args[0]


async def test_mark_members_disconnected(db: Database, mock_pool: MagicMock) -> None:
    db._pool = mock_pool
    await db.mark_members_disconnected(uuid.uuid4())
    mock_pool.execute.assert_called_once()
    assert "UPDATE members" in mock_pool.execute.call_args.args[0]


async def test_mark_member_connected(db: Database, mock_pool: MagicMock) -> None:
    db._pool = mock_pool
    await db.mark_member_connected(
        uuid.uuid4(),
        datetime.fromisoformat("2026-03-21T02:00:00+00:00"),
    )
    mock_pool.execute.assert_called_once()
    assert "status = 'connected'" in mock_pool.execute.call_args.args[0]


async def test_insert_member(db: Database, mock_pool: MagicMock) -> None:
    db._pool = mock_pool
    connected_at = datetime.fromisoformat("2026-03-21T00:00:00+00:00")
    await db.insert_member(
        uuid.uuid4(),
        uuid.uuid4(),
        "Jay",
        MemberRole.OBSERVER,
        "resume-token",
        connected_at,
        connected_at,
    )
    mock_pool.execute.assert_called_once()


async def test_update_member_heartbeat(db: Database, mock_pool: MagicMock) -> None:
    db._pool = mock_pool
    await db.update_member_heartbeat(
        uuid.uuid4(),
        datetime.fromisoformat("2026-03-21T00:05:00+00:00"),
    )
    mock_pool.execute.assert_called_once()
    assert "UPDATE members SET last_seen_at" in mock_pool.execute.call_args.args[0]


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


async def test_insert_intelligence_observation(db: Database, mock_pool: MagicMock) -> None:
    db._pool = mock_pool
    observation = IntelligenceObservation(
        kind=ObservationKind.TRANSCRIPT,
        source_member_id=uuid.uuid4(),
        summary="Police moving east.",
        confidence=0.92,
        details={"adapter": "fake-transcriber"},
    )

    await db.insert_intelligence_observation(uuid.uuid4(), observation)

    mock_pool.execute.assert_called_once()
    assert "INSERT INTO intelligence_observations" in mock_pool.execute.call_args.args[0]


async def test_get_recent_intelligence_observations(db: Database, mock_pool: MagicMock) -> None:
    db._pool = mock_pool
    mock_pool.fetch = AsyncMock(return_value=[{"summary": "Police moving east."}])

    result = await db.get_recent_intelligence_observations(uuid.uuid4(), 10)

    assert result == [{"summary": "Police moving east."}]


async def test_upsert_synthesis_finding(db: Database, mock_pool: MagicMock) -> None:
    db._pool = mock_pool
    finding = SynthesisFinding(
        signature="police_action:movement-north",
        category=EventCategory.POLICE_ACTION,
        severity=EventSeverity.WARNING,
        title="Police Action",
        summary="Police advancing north. Corroborated by 2 sources across 2 signals.",
    )

    await db.upsert_synthesis_finding(uuid.uuid4(), finding)

    mock_pool.execute.assert_called_once()
    assert "INSERT INTO synthesis_findings" in mock_pool.execute.call_args.args[0]


async def test_get_recent_synthesis_findings(db: Database, mock_pool: MagicMock) -> None:
    db._pool = mock_pool
    mock_pool.fetch = AsyncMock(return_value=[{"title": "Police Action"}])

    result = await db.get_recent_synthesis_findings(uuid.uuid4(), 10)

    assert result == [{"title": "Police Action"}]


async def test_get_events_since(db: Database, mock_pool: MagicMock) -> None:
    db._pool = mock_pool
    result = await db.get_events_since(uuid.uuid4(), "2026-01-01T00:00:00Z")
    assert result == []


async def test_insert_audit_event(db: Database, mock_pool: MagicMock) -> None:
    db._pool = mock_pool
    await db.insert_audit_event(
        uuid.uuid4(),
        "system",
        "started",
        details={"ok": True},
    )
    mock_pool.execute.assert_called_once()
    assert "INSERT INTO audit_events" in mock_pool.execute.call_args.args[0]


async def test_get_audit_events(db: Database, mock_pool: MagicMock) -> None:
    db._pool = mock_pool
    mock_pool.fetch = AsyncMock(return_value=[{"action": "started"}])
    result = await db.get_audit_events(uuid.uuid4(), 25)
    assert result == [{"action": "started"}]


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
