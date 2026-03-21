"""PostgreSQL database layer for Osk."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

import asyncpg

from osk.models import EventCategory, EventSeverity, MemberRole

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


class Database:
    def __init__(self) -> None:
        self._pool: asyncpg.Pool | None = None

    def _get_migration_files(self) -> list[Path]:
        if not MIGRATIONS_DIR.exists():
            return []
        return sorted(MIGRATIONS_DIR.glob("*.sql"))

    def _require_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("Database pool has not been initialized.")
        return self._pool

    async def connect(self, database_url: str) -> None:
        self._pool = await asyncpg.create_pool(database_url, min_size=2, max_size=10)
        await self._run_migrations()

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def _run_migrations(self) -> None:
        pool = self._require_pool()
        await pool.execute(
            """CREATE TABLE IF NOT EXISTS schema_migrations (
               filename TEXT PRIMARY KEY,
               applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )"""
        )
        rows = await pool.fetch("SELECT filename FROM schema_migrations")
        applied = {str(row["filename"]) for row in rows}

        for migration_file in self._get_migration_files():
            if migration_file.name in applied:
                logger.info("Skipping previously applied migration: %s", migration_file.name)
                continue

            async with pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(migration_file.read_text())
                    await conn.execute(
                        "INSERT INTO schema_migrations (filename) VALUES ($1)",
                        migration_file.name,
                    )
            logger.info("Applied migration: %s", migration_file.name)

    async def insert_operation(
        self,
        op_id: uuid.UUID,
        name: str,
        token: str,
        coordinator_token: str,
        started_at: datetime,
    ) -> None:
        pool = self._require_pool()
        await pool.execute(
            (
                "INSERT INTO operations (id, name, token, coordinator_token, started_at) "
                "VALUES ($1, $2, $3, $4, $5)"
            ),
            op_id,
            name,
            token,
            coordinator_token,
            started_at,
        )

    async def update_operation_token(self, op_id: uuid.UUID, new_token: str) -> None:
        pool = self._require_pool()
        await pool.execute(
            "UPDATE operations SET token = $1 WHERE id = $2",
            new_token,
            op_id,
        )

    async def get_operation_token(self, op_id: uuid.UUID) -> str | None:
        pool = self._require_pool()
        return await pool.fetchval("SELECT token FROM operations WHERE id = $1", op_id)

    async def get_active_operation(self) -> dict | None:
        pool = self._require_pool()
        row = await pool.fetchrow(
            """SELECT id, name, token, coordinator_token, started_at, stopped_at
               FROM operations
               WHERE stopped_at IS NULL
               ORDER BY started_at DESC
               LIMIT 1"""
        )
        return dict(row) if row else None

    async def mark_operation_stopped(self, op_id: uuid.UUID, stopped_at: datetime) -> None:
        pool = self._require_pool()
        await pool.execute(
            "UPDATE operations SET stopped_at = $1 WHERE id = $2",
            stopped_at,
            op_id,
        )

    async def mark_members_disconnected(self, operation_id: uuid.UUID) -> None:
        pool = self._require_pool()
        await pool.execute(
            """UPDATE members
               SET status = 'disconnected'
               WHERE operation_id = $1 AND status = 'connected'""",
            operation_id,
        )

    async def insert_member(
        self,
        member_id: uuid.UUID,
        operation_id: uuid.UUID,
        name: str,
        role: MemberRole,
    ) -> None:
        pool = self._require_pool()
        await pool.execute(
            "INSERT INTO members (id, operation_id, name, role) VALUES ($1, $2, $3, $4)",
            member_id,
            operation_id,
            name,
            role.value,
        )

    async def update_member_role(self, member_id: uuid.UUID, role: MemberRole) -> None:
        pool = self._require_pool()
        await pool.execute(
            "UPDATE members SET role = $1 WHERE id = $2",
            role.value,
            member_id,
        )

    async def update_member_status(self, member_id: uuid.UUID, status: str) -> None:
        pool = self._require_pool()
        await pool.execute(
            "UPDATE members SET status = $1 WHERE id = $2",
            status,
            member_id,
        )

    async def update_member_gps(
        self, member_id: uuid.UUID, latitude: float, longitude: float
    ) -> None:
        pool = self._require_pool()
        await pool.execute(
            "UPDATE members SET latitude = $1, longitude = $2, last_gps_at = NOW() WHERE id = $3",
            latitude,
            longitude,
            member_id,
        )

    async def get_members(self, operation_id: uuid.UUID) -> list[dict]:
        pool = self._require_pool()
        rows = await pool.fetch(
            "SELECT * FROM members WHERE operation_id = $1 ORDER BY connected_at",
            operation_id,
        )
        return [dict(row) for row in rows]

    async def insert_event(
        self,
        event_id: uuid.UUID,
        operation_id: uuid.UUID,
        severity: EventSeverity,
        category: EventCategory,
        text: str,
        source_member_id: uuid.UUID | None,
        latitude: float | None,
        longitude: float | None,
    ) -> None:
        pool = self._require_pool()
        await pool.execute(
            """INSERT INTO events (id, operation_id, severity, category, text,
               source_member_id, latitude, longitude)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
            event_id,
            operation_id,
            severity.value,
            category.value,
            text,
            source_member_id,
            latitude,
            longitude,
        )

    async def get_events_since(self, operation_id: uuid.UUID, since: str) -> list[dict]:
        pool = self._require_pool()
        rows = await pool.fetch(
            "SELECT * FROM events WHERE operation_id = $1 AND timestamp >= $2 ORDER BY timestamp",
            operation_id,
            since,
        )
        return [dict(row) for row in rows]

    async def insert_alert(
        self,
        alert_id: uuid.UUID,
        event_id: uuid.UUID,
        severity: EventSeverity,
        category: EventCategory,
        text: str,
    ) -> None:
        pool = self._require_pool()
        await pool.execute(
            (
                "INSERT INTO alerts (id, event_id, severity, category, text) "
                "VALUES ($1, $2, $3, $4, $5)"
            ),
            alert_id,
            event_id,
            severity.value,
            category.value,
            text,
        )

    async def insert_pin(
        self, pin_id: uuid.UUID, event_id: uuid.UUID, pinned_by: uuid.UUID
    ) -> None:
        pool = self._require_pool()
        await pool.execute(
            "INSERT INTO pins (id, event_id, pinned_by) VALUES ($1, $2, $3)",
            pin_id,
            event_id,
            pinned_by,
        )

    async def insert_sitrep(
        self,
        sitrep_id: uuid.UUID,
        operation_id: uuid.UUID,
        text: str,
        trend: str,
    ) -> None:
        pool = self._require_pool()
        await pool.execute(
            "INSERT INTO sitreps (id, operation_id, text, trend) VALUES ($1, $2, $3, $4)",
            sitrep_id,
            operation_id,
            text,
            trend,
        )

    async def get_latest_sitrep(self, operation_id: uuid.UUID) -> dict | None:
        pool = self._require_pool()
        row = await pool.fetchrow(
            "SELECT * FROM sitreps WHERE operation_id = $1 ORDER BY timestamp DESC LIMIT 1",
            operation_id,
        )
        return dict(row) if row else None

    async def insert_transcript_segment(
        self,
        stream_id: uuid.UUID,
        member_id: uuid.UUID,
        timestamp: datetime,
        start_time: float,
        end_time: float,
        text: str,
        confidence: float | None,
    ) -> None:
        pool = self._require_pool()
        await pool.execute(
            """INSERT INTO transcript_segments
               (stream_id, member_id, timestamp, start_time, end_time, text, confidence)
               VALUES ($1, $2, $3, $4, $5, $6, $7)""",
            stream_id,
            member_id,
            timestamp,
            start_time,
            end_time,
            text,
            confidence,
        )

    async def insert_observation(
        self,
        member_id: uuid.UUID,
        scene_description: str,
        entities: list,
        threat_score: float,
    ) -> None:
        pool = self._require_pool()
        await pool.execute(
            """INSERT INTO observations (member_id, scene_description, entities, threat_score)
               VALUES ($1, $2, $3::jsonb, $4)""",
            member_id,
            scene_description,
            json.dumps(entities),
            threat_score,
        )

    async def insert_stream(
        self, stream_id: uuid.UUID, member_id: uuid.UUID, stream_type: str
    ) -> None:
        pool = self._require_pool()
        await pool.execute(
            "INSERT INTO streams (id, member_id, stream_type) VALUES ($1, $2, $3)",
            stream_id,
            member_id,
            stream_type,
        )

    async def update_stream_status(self, stream_id: uuid.UUID, status: str) -> None:
        pool = self._require_pool()
        await pool.execute(
            "UPDATE streams SET status = $1 WHERE id = $2",
            status,
            stream_id,
        )
