"""Tests for database layer — uses mocked asyncpg pool."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from osk.db import Database
from osk.intelligence_contracts import IntelligenceObservation, ObservationKind
from osk.models import (
    CoordinatorGap,
    CoordinatorTaskStatus,
    EventCategory,
    EventSeverity,
    FindingNote,
    FindingStatus,
    MemberRole,
    SynthesisFinding,
)


@pytest.fixture
def db() -> Database:
    return Database()


@pytest.fixture
def mock_pool() -> MagicMock:
    pool = MagicMock()
    conn = MagicMock()
    conn.execute = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
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
    assert len(migrations) >= 8
    assert migrations[0].name == "001_initial.sql"
    assert migrations[1].name == "002_operation_coordinator_token.sql"
    assert migrations[2].name == "003_members_reconnect_and_audit.sql"
    assert migrations[3].name == "004_member_heartbeat.sql"
    assert migrations[4].name == "005_intelligence_observations.sql"
    assert migrations[5].name == "006_synthesis_findings.sql"
    assert migrations[6].name == "007_finding_review_and_ingest_receipts.sql"
    assert migrations[7].name == "008_coordinator_state.sql"


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
    mock_pool.fetchrow = AsyncMock(return_value={"id": finding.id})

    result = await db.upsert_synthesis_finding(uuid.uuid4(), finding)

    mock_pool.fetchrow.assert_called_once()
    assert "INSERT INTO synthesis_findings" in mock_pool.fetchrow.call_args.args[0]
    assert result == {"id": finding.id}


async def test_get_recent_synthesis_findings(db: Database, mock_pool: MagicMock) -> None:
    db._pool = mock_pool
    mock_pool.fetch = AsyncMock(return_value=[{"title": "Police Action"}])

    result = await db.get_recent_synthesis_findings(uuid.uuid4(), 10)

    assert result == [{"title": "Police Action"}]


async def test_get_synthesis_findings(db: Database, mock_pool: MagicMock) -> None:
    db._pool = mock_pool
    mock_pool.fetch = AsyncMock(return_value=[{"title": "Police Action"}])
    since = datetime(2026, 3, 21, 18, 0, tzinfo=timezone.utc)

    result = await db.get_synthesis_findings(
        uuid.uuid4(),
        limit=10,
        since=since,
        status=FindingStatus.OPEN,
        severity=EventSeverity.WARNING,
        category=EventCategory.POLICE_ACTION,
    )

    assert result == [{"title": "Police Action"}]
    query = mock_pool.fetch.await_args.args[0]
    assert "status =" in query
    assert "severity =" in query
    assert "category =" in query


async def test_get_synthesis_finding_detail(db: Database, mock_pool: MagicMock) -> None:
    db._pool = mock_pool
    finding_id = uuid.uuid4()
    observation_id = uuid.uuid4()
    mock_pool.fetchrow = AsyncMock(
        return_value={
            "id": finding_id,
            "operation_id": uuid.uuid4(),
            "latest_event_id": None,
            "details": {"observation_ids": [str(observation_id)]},
        }
    )
    mock_pool.fetch = AsyncMock(
        side_effect=[
            [{"id": observation_id, "summary": "Police moving east."}],
            [{"id": uuid.uuid4(), "text": "Watching east entrance"}],
        ]
    )

    detail = await db.get_synthesis_finding_detail(uuid.uuid4(), finding_id)

    assert detail is not None
    assert detail["observations"][0]["summary"] == "Police moving east."
    assert detail["notes"][0]["text"] == "Watching east entrance"


async def test_get_synthesis_finding_correlations(db: Database, mock_pool: MagicMock) -> None:
    db._pool = mock_pool
    finding_id = uuid.uuid4()
    source_member_id = uuid.uuid4()
    mock_pool.fetchrow = AsyncMock(
        return_value={
            "id": finding_id,
            "operation_id": uuid.uuid4(),
            "category": EventCategory.POLICE_ACTION.value,
            "latest_event_id": None,
            "first_seen_at": datetime(2026, 3, 21, 18, 0, tzinfo=timezone.utc),
            "last_seen_at": datetime(2026, 3, 21, 18, 5, tzinfo=timezone.utc),
            "details": {"member_ids": [str(source_member_id)]},
        }
    )
    mock_pool.fetch = AsyncMock(
        side_effect=[
            [
                {
                    "id": uuid.uuid4(),
                    "category": EventCategory.POLICE_ACTION.value,
                    "latest_event_id": None,
                    "details": {"member_ids": [str(source_member_id)]},
                }
            ],
            [
                {
                    "id": uuid.uuid4(),
                    "category": EventCategory.POLICE_ACTION.value,
                    "severity": EventSeverity.WARNING.value,
                    "text": "Police pushing east",
                    "source_member_id": source_member_id,
                }
            ],
        ]
    )

    result = await db.get_synthesis_finding_correlations(uuid.uuid4(), finding_id, limit=3)

    assert result is not None
    assert result["related_findings"][0]["correlation_reasons"] == [
        "shared_category",
        "shared_member_context",
    ]
    assert result["related_events"][0]["correlation_reasons"] == [
        "shared_category",
        "shared_member_context",
    ]


async def test_update_synthesis_finding_status(db: Database, mock_pool: MagicMock) -> None:
    db._pool = mock_pool
    updated_row = {"id": uuid.uuid4(), "status": "acknowledged"}
    mock_pool.fetchrow = AsyncMock(return_value=updated_row)

    result = await db.update_synthesis_finding_status(
        uuid.uuid4(),
        uuid.uuid4(),
        FindingStatus.ACKNOWLEDGED,
        changed_at=datetime.now(timezone.utc),
    )

    assert result == updated_row


async def test_get_review_feed_mixes_items(db: Database) -> None:
    operation_id = uuid.uuid4()
    db.get_synthesis_findings = AsyncMock(
        return_value=[
            {
                "id": uuid.uuid4(),
                "title": "Police Action",
                "summary": "Police advancing north.",
                "severity": "warning",
                "category": "police_action",
                "status": "open",
                "corroborated": True,
                "notes_count": 1,
                "last_seen_at": datetime(2026, 3, 21, 18, 4, tzinfo=timezone.utc),
                "updated_at": datetime(2026, 3, 21, 18, 5, tzinfo=timezone.utc),
            }
        ]
    )
    db.get_events = AsyncMock(
        return_value=[
            {
                "id": uuid.uuid4(),
                "timestamp": datetime(2026, 3, 21, 18, 3, tzinfo=timezone.utc),
                "category": "police_action",
                "severity": "warning",
                "text": "Police advancing",
                "source_member_id": uuid.uuid4(),
            }
        ]
    )
    db.get_recent_sitreps = AsyncMock(
        return_value=[
            {
                "id": uuid.uuid4(),
                "timestamp": datetime(2026, 3, 21, 18, 2, tzinfo=timezone.utc),
                "text": "Situation remains tense.",
                "trend": "escalating",
            }
        ]
    )

    result = await db.get_review_feed(operation_id, limit=10)

    assert [item["type"] for item in result] == ["finding", "event", "sitrep"]
    assert result[0]["title"] == "Police Action"
    assert result[2]["trend"] == "escalating"


async def test_upsert_open_coordinator_gap_inserts_when_missing(
    db: Database,
    mock_pool: MagicMock,
) -> None:
    db._pool = mock_pool
    mock_pool.fetchrow = AsyncMock(
        side_effect=[
            None,
            {"id": uuid.uuid4(), "kind": "route_viability_confirmation", "status": "open"},
        ]
    )
    gap = CoordinatorGap(
        operation_id=uuid.uuid4(),
        kind="route_viability_confirmation",
        title="Confirm safest exit",
        summary="Need a route check.",
        severity=EventSeverity.WARNING,
    )

    result = await db.upsert_open_coordinator_gap(gap.operation_id, gap)

    assert result["status"] == "open"
    assert "INSERT INTO coordinator_gaps" in mock_pool.fetchrow.await_args_list[1].args[0]


async def test_update_coordinator_task_status_returns_updated_row(
    db: Database,
    mock_pool: MagicMock,
) -> None:
    db._pool = mock_pool
    updated_row = {"id": uuid.uuid4(), "status": "completed"}
    mock_pool.fetchrow = AsyncMock(return_value=updated_row)

    result = await db.update_coordinator_task_status(
        uuid.uuid4(),
        uuid.uuid4(),
        status=CoordinatorTaskStatus.COMPLETED,
        changed_at=datetime.now(timezone.utc),
        details={"report_assessment": "clear"},
    )

    assert result == updated_row
    assert "UPDATE coordinator_tasks" in mock_pool.fetchrow.await_args.args[0]


async def test_get_coordinator_state_returns_active_records(
    db: Database,
    mock_pool: MagicMock,
) -> None:
    db._pool = mock_pool
    gap_id = uuid.uuid4()
    task_id = uuid.uuid4()
    recommendation_id = uuid.uuid4()
    mock_pool.fetch = AsyncMock(
        side_effect=[
            [
                {
                    "id": gap_id,
                    "title": "Confirm safest exit",
                    "status": "open",
                    "updated_at": datetime.now(timezone.utc),
                }
            ],
            [
                {
                    "id": task_id,
                    "gap_id": gap_id,
                    "status": "open",
                    "assigned_member_name": "Sensor-1",
                    "updated_at": datetime.now(timezone.utc),
                }
            ],
            [
                {
                    "id": recommendation_id,
                    "route_key": "north_exit",
                    "status": "emitted",
                    "updated_at": datetime.now(timezone.utc),
                }
            ],
        ]
    )

    result = await db.get_coordinator_state(uuid.uuid4(), limit=5)

    assert result["active_gap"]["id"] == gap_id
    assert result["active_task"]["id"] == task_id
    assert result["active_recommendation"]["id"] == recommendation_id


async def test_escalate_synthesis_finding(db: Database, mock_pool: MagicMock) -> None:
    db._pool = mock_pool
    updated_row = {"id": uuid.uuid4(), "severity": "critical"}
    mock_pool.fetchrow = AsyncMock(return_value=updated_row)

    result = await db.escalate_synthesis_finding(
        uuid.uuid4(),
        uuid.uuid4(),
        changed_at=datetime.now(timezone.utc),
    )

    assert result == updated_row


async def test_insert_synthesis_finding_note(db: Database, mock_pool: MagicMock) -> None:
    db._pool = mock_pool
    note = FindingNote(
        operation_id=uuid.uuid4(),
        finding_id=uuid.uuid4(),
        text="Hold this for dashboard review.",
    )

    await db.insert_synthesis_finding_note(note)

    assert mock_pool.execute.await_count == 2
    assert "INSERT INTO synthesis_finding_notes" in mock_pool.execute.await_args_list[0].args[0]
    assert "UPDATE synthesis_findings" in mock_pool.execute.await_args_list[1].args[0]


async def test_claim_ingest_receipt_detects_duplicate(db: Database, mock_pool: MagicMock) -> None:
    db._pool = mock_pool
    seen_at = datetime(2026, 3, 21, 18, 0, tzinfo=timezone.utc)
    mock_pool.fetchrow = AsyncMock(return_value={"last_seen_at": seen_at})

    duplicate = await db.claim_ingest_receipt(
        uuid.uuid4(),
        kind="audio",
        member_id=uuid.uuid4(),
        ingest_key="chunk-1",
        item_id=uuid.uuid4(),
        seen_at=seen_at,
        window_seconds=60,
    )

    assert duplicate is True


async def test_insert_manual_report_once_inserts_event_and_receipt(
    db: Database,
    mock_pool: MagicMock,
) -> None:
    db._pool = mock_pool
    conn = mock_pool.acquire.return_value.__aenter__.return_value
    conn.fetchrow = AsyncMock(return_value=None)
    event_id = uuid.uuid4()
    timestamp = datetime(2026, 3, 22, 1, 0, tzinfo=timezone.utc)

    result = await db.insert_manual_report_once(
        operation_id=uuid.uuid4(),
        member_id=uuid.uuid4(),
        report_id="report-1",
        event_id=event_id,
        text="Need medics at the west gate",
        timestamp=timestamp,
    )

    assert result == {
        "duplicate": False,
        "event_id": event_id,
        "text": "Need medics at the west gate",
        "timestamp": timestamp,
    }
    assert conn.execute.await_count == 2
    assert "INSERT INTO events" in conn.execute.await_args_list[0].args[0]
    assert "INSERT INTO ingest_receipts" in conn.execute.await_args_list[1].args[0]


async def test_insert_manual_report_once_returns_duplicate_existing_event(
    db: Database,
    mock_pool: MagicMock,
) -> None:
    db._pool = mock_pool
    conn = mock_pool.acquire.return_value.__aenter__.return_value
    existing_event_id = uuid.uuid4()
    seen_at = datetime(2026, 3, 22, 1, 5, tzinfo=timezone.utc)
    conn.fetchrow = AsyncMock(
        side_effect=[
            {"item_id": existing_event_id, "last_seen_at": seen_at},
            {"id": existing_event_id, "text": "Need medics at the west gate", "timestamp": seen_at},
        ]
    )

    result = await db.insert_manual_report_once(
        operation_id=uuid.uuid4(),
        member_id=uuid.uuid4(),
        report_id="report-1",
        event_id=uuid.uuid4(),
        text="Need medics at the west gate",
        timestamp=seen_at,
    )

    assert result == {
        "duplicate": True,
        "event_id": existing_event_id,
        "text": "Need medics at the west gate",
        "timestamp": seen_at,
    }
    assert conn.execute.await_count == 1
    assert "UPDATE ingest_receipts" in conn.execute.await_args.args[0]


async def test_prune_ingest_receipts(db: Database, mock_pool: MagicMock) -> None:
    db._pool = mock_pool

    await db.prune_ingest_receipts(
        uuid.uuid4(),
        older_than=datetime.now(timezone.utc),
    )

    mock_pool.execute.assert_called_once()
    assert "DELETE FROM ingest_receipts" in mock_pool.execute.call_args.args[0]


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


async def test_get_audit_events_filters_actions(db: Database, mock_pool: MagicMock) -> None:
    db._pool = mock_pool
    operation_id = uuid.uuid4()
    mock_pool.fetch = AsyncMock(return_value=[{"action": "wipe_follow_up_verified"}])

    result = await db.get_audit_events(
        operation_id,
        25,
        actions=["wipe_follow_up_verified", "wipe_follow_up_reopened"],
    )

    assert result == [{"action": "wipe_follow_up_verified"}]
    mock_pool.fetch.assert_awaited_once()
    sql = mock_pool.fetch.await_args.args[0]
    assert "AND action = ANY($2::text[])" in sql
    assert mock_pool.fetch.await_args.args[1:] == (
        operation_id,
        ["wipe_follow_up_verified", "wipe_follow_up_reopened"],
        25,
    )


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
