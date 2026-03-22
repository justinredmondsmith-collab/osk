"""PostgreSQL database layer for Osk."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import asyncpg

from osk.intelligence_contracts import IntelligenceObservation
from osk.models import (
    EventCategory,
    EventSeverity,
    FindingNote,
    FindingStatus,
    MemberRole,
    SynthesisFinding,
)

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
        reconnect_token: str,
        connected_at: datetime,
        last_seen_at: datetime,
    ) -> None:
        pool = self._require_pool()
        await pool.execute(
            (
                "INSERT INTO members "
                "(id, operation_id, name, role, reconnect_token, connected_at, last_seen_at) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7)"
            ),
            member_id,
            operation_id,
            name,
            role.value,
            reconnect_token,
            connected_at,
            last_seen_at,
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

    async def mark_member_connected(self, member_id: uuid.UUID, connected_at: datetime) -> None:
        pool = self._require_pool()
        await pool.execute(
            (
                "UPDATE members "
                "SET status = 'connected', connected_at = $1, last_seen_at = $1 "
                "WHERE id = $2"
            ),
            connected_at,
            member_id,
        )

    async def update_member_heartbeat(self, member_id: uuid.UUID, last_seen_at: datetime) -> None:
        pool = self._require_pool()
        await pool.execute(
            "UPDATE members SET last_seen_at = $1 WHERE id = $2",
            last_seen_at,
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

    async def insert_audit_event(
        self,
        operation_id: uuid.UUID,
        actor_type: str,
        action: str,
        *,
        actor_member_id: uuid.UUID | None = None,
        details: dict | None = None,
    ) -> None:
        pool = self._require_pool()
        await pool.execute(
            """INSERT INTO audit_events (operation_id, actor_member_id, actor_type, action, details)
               VALUES ($1, $2, $3, $4, $5::jsonb)""",
            operation_id,
            actor_member_id,
            actor_type,
            action,
            json.dumps(details or {}),
        )

    async def get_audit_events(self, operation_id: uuid.UUID, limit: int = 50) -> list[dict]:
        pool = self._require_pool()
        rows = await pool.fetch(
            """SELECT * FROM audit_events
               WHERE operation_id = $1
               ORDER BY timestamp DESC
               LIMIT $2""",
            operation_id,
            limit,
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

    async def get_events(
        self,
        operation_id: uuid.UUID,
        *,
        since: datetime | None = None,
        limit: int = 25,
        severity: EventSeverity | None = None,
        category: EventCategory | None = None,
    ) -> list[dict]:
        pool = self._require_pool()
        conditions = ["operation_id = $1"]
        args: list[object] = [operation_id]

        if since is not None:
            args.append(since)
            conditions.append(f"timestamp >= ${len(args)}")
        if severity is not None:
            args.append(severity.value)
            conditions.append(f"severity = ${len(args)}")
        if category is not None:
            args.append(category.value)
            conditions.append(f"category = ${len(args)}")

        args.append(max(1, limit))
        query = f"""
            SELECT * FROM events
            WHERE {" AND ".join(conditions)}
            ORDER BY timestamp DESC
            LIMIT ${len(args)}
        """
        rows = await pool.fetch(query, *args)
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

    async def get_recent_sitreps(
        self,
        operation_id: uuid.UUID,
        *,
        since: datetime | None = None,
        limit: int = 10,
    ) -> list[dict]:
        pool = self._require_pool()
        args: list[object] = [operation_id]
        conditions = ["operation_id = $1"]
        if since is not None:
            args.append(since)
            conditions.append(f"timestamp >= ${len(args)}")
        args.append(max(1, limit))
        query = f"""
            SELECT * FROM sitreps
            WHERE {" AND ".join(conditions)}
            ORDER BY timestamp DESC
            LIMIT ${len(args)}
        """
        rows = await pool.fetch(query, *args)
        return [dict(row) for row in rows]

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

    async def insert_intelligence_observation(
        self,
        operation_id: uuid.UUID,
        observation: IntelligenceObservation,
    ) -> None:
        pool = self._require_pool()
        await pool.execute(
            """INSERT INTO intelligence_observations
               (id, operation_id, source_member_id, kind, summary, confidence, details, created_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8)""",
            observation.id,
            operation_id,
            observation.source_member_id,
            observation.kind.value,
            observation.summary,
            observation.confidence,
            json.dumps(observation.details),
            observation.created_at,
        )

    async def get_recent_intelligence_observations(
        self,
        operation_id: uuid.UUID,
        limit: int = 25,
    ) -> list[dict]:
        pool = self._require_pool()
        rows = await pool.fetch(
            """SELECT * FROM intelligence_observations
               WHERE operation_id = $1
               ORDER BY created_at DESC
               LIMIT $2""",
            operation_id,
            limit,
        )
        return [dict(row) for row in rows]

    async def upsert_synthesis_finding(
        self,
        operation_id: uuid.UUID,
        finding: SynthesisFinding,
    ) -> dict:
        pool = self._require_pool()
        row = await pool.fetchrow(
            """INSERT INTO synthesis_findings
               (id, operation_id, signature, category, severity, title, summary, status,
                corroborated, source_count, signal_count, observation_count, first_seen_at,
                last_seen_at, status_updated_at, acknowledged_at, resolved_at, notes_count,
                latest_observation_id, latest_event_id, details)
               VALUES (
                 $1, $2, $3, $4, $5, $6, $7, $8, $9,
                 $10, $11, $12, $13, $14, $15, $16, $17, $18, $19::jsonb
               )
               ON CONFLICT (operation_id, signature) DO UPDATE SET
                 severity = EXCLUDED.severity,
                 title = EXCLUDED.title,
                 summary = EXCLUDED.summary,
                 status = CASE
                   WHEN synthesis_findings.status = 'resolved'
                     AND EXCLUDED.last_seen_at > synthesis_findings.last_seen_at
                   THEN 'open'
                   ELSE synthesis_findings.status
                 END,
                 corroborated = EXCLUDED.corroborated,
                 source_count = EXCLUDED.source_count,
                 signal_count = EXCLUDED.signal_count,
                 observation_count = EXCLUDED.observation_count,
                 last_seen_at = EXCLUDED.last_seen_at,
                 status_updated_at = CASE
                   WHEN synthesis_findings.status = 'resolved'
                     AND EXCLUDED.last_seen_at > synthesis_findings.last_seen_at
                   THEN NOW()
                   ELSE synthesis_findings.status_updated_at
                 END,
                 acknowledged_at = CASE
                   WHEN synthesis_findings.status = 'resolved'
                     AND EXCLUDED.last_seen_at > synthesis_findings.last_seen_at
                   THEN NULL
                   ELSE synthesis_findings.acknowledged_at
                 END,
                 resolved_at = CASE
                   WHEN synthesis_findings.status = 'resolved'
                     AND EXCLUDED.last_seen_at > synthesis_findings.last_seen_at
                   THEN NULL
                   ELSE synthesis_findings.resolved_at
                 END,
                 latest_observation_id = EXCLUDED.latest_observation_id,
                 latest_event_id = EXCLUDED.latest_event_id,
                 details = EXCLUDED.details,
                 updated_at = NOW()
               RETURNING *""",
            finding.id,
            operation_id,
            finding.signature,
            finding.category.value,
            finding.severity.value,
            finding.title,
            finding.summary,
            finding.status.value,
            finding.corroborated,
            finding.source_count,
            finding.signal_count,
            finding.observation_count,
            finding.first_seen_at,
            finding.last_seen_at,
            finding.status_updated_at,
            finding.acknowledged_at,
            finding.resolved_at,
            finding.notes_count,
            finding.latest_observation_id,
            finding.latest_event_id,
            json.dumps(finding.details),
        )
        return dict(row)

    async def get_recent_synthesis_findings(
        self,
        operation_id: uuid.UUID,
        limit: int = 25,
    ) -> list[dict]:
        pool = self._require_pool()
        rows = await pool.fetch(
            """SELECT * FROM synthesis_findings
               WHERE operation_id = $1
               ORDER BY last_seen_at DESC, updated_at DESC
               LIMIT $2""",
            operation_id,
            limit,
        )
        return [dict(row) for row in rows]

    async def get_synthesis_findings(
        self,
        operation_id: uuid.UUID,
        *,
        limit: int = 25,
        since: datetime | None = None,
        status: FindingStatus | None = None,
        severity: EventSeverity | None = None,
        category: EventCategory | None = None,
    ) -> list[dict]:
        pool = self._require_pool()
        conditions = ["operation_id = $1"]
        args: list[object] = [operation_id]

        if since is not None:
            args.append(since)
            conditions.append(f"updated_at >= ${len(args)}")
        if status is not None:
            args.append(status.value)
            conditions.append(f"status = ${len(args)}")
        if severity is not None:
            args.append(severity.value)
            conditions.append(f"severity = ${len(args)}")
        if category is not None:
            args.append(category.value)
            conditions.append(f"category = ${len(args)}")

        args.append(max(1, limit))
        query = f"""
            SELECT * FROM synthesis_findings
            WHERE {" AND ".join(conditions)}
            ORDER BY updated_at DESC, last_seen_at DESC
            LIMIT ${len(args)}
        """
        rows = await pool.fetch(query, *args)
        return [dict(row) for row in rows]

    async def get_synthesis_finding(
        self,
        operation_id: uuid.UUID,
        finding_id: uuid.UUID,
    ) -> dict | None:
        pool = self._require_pool()
        row = await pool.fetchrow(
            """SELECT * FROM synthesis_findings
               WHERE operation_id = $1 AND id = $2""",
            operation_id,
            finding_id,
        )
        return dict(row) if row else None

    async def get_synthesis_finding_notes(
        self,
        finding_id: uuid.UUID,
        limit: int = 20,
    ) -> list[dict]:
        pool = self._require_pool()
        rows = await pool.fetch(
            """SELECT * FROM synthesis_finding_notes
               WHERE finding_id = $1
               ORDER BY created_at DESC
               LIMIT $2""",
            finding_id,
            limit,
        )
        return [dict(row) for row in rows]

    async def get_intelligence_observations_by_ids(
        self,
        observation_ids: list[uuid.UUID],
    ) -> list[dict]:
        if not observation_ids:
            return []
        pool = self._require_pool()
        rows = await pool.fetch(
            """SELECT * FROM intelligence_observations
               WHERE id = ANY($1::uuid[])
               ORDER BY created_at DESC""",
            observation_ids,
        )
        return [dict(row) for row in rows]

    async def get_events_by_ids(self, event_ids: list[uuid.UUID]) -> list[dict]:
        if not event_ids:
            return []
        pool = self._require_pool()
        rows = await pool.fetch(
            """SELECT * FROM events
               WHERE id = ANY($1::uuid[])
               ORDER BY timestamp DESC""",
            event_ids,
        )
        return [dict(row) for row in rows]

    async def get_synthesis_finding_detail(
        self,
        operation_id: uuid.UUID,
        finding_id: uuid.UUID,
        *,
        note_limit: int = 20,
    ) -> dict | None:
        finding = await self.get_synthesis_finding(operation_id, finding_id)
        if finding is None:
            return None

        details = finding.get("details") or {}
        observation_ids = [
            uuid.UUID(str(observation_id))
            for observation_id in details.get("observation_ids", [])
            if observation_id
        ]
        event_ids: list[uuid.UUID] = []
        latest_event_id = finding.get("latest_event_id")
        if latest_event_id:
            event_ids.append(uuid.UUID(str(latest_event_id)))

        observations = await self.get_intelligence_observations_by_ids(observation_ids)
        events = await self.get_events_by_ids(event_ids)
        notes = await self.get_synthesis_finding_notes(finding_id, limit=note_limit)
        return {
            "finding": finding,
            "observations": observations,
            "events": events,
            "notes": notes,
        }

    async def get_synthesis_finding_correlations(
        self,
        operation_id: uuid.UUID,
        finding_id: uuid.UUID,
        *,
        limit: int = 10,
        window_minutes: int = 30,
    ) -> dict | None:
        finding = await self.get_synthesis_finding(operation_id, finding_id)
        if finding is None:
            return None

        window = timedelta(minutes=max(int(window_minutes), 1))
        from_ts = finding["first_seen_at"] - window
        to_ts = finding["last_seen_at"] + window
        finding_details = finding.get("details") or {}
        member_ids = {str(member_id) for member_id in finding_details.get("member_ids", [])}

        pool = self._require_pool()
        candidate_finding_rows = await pool.fetch(
            """SELECT * FROM synthesis_findings
               WHERE operation_id = $1
                 AND id <> $2
                 AND last_seen_at BETWEEN $3 AND $4
               ORDER BY last_seen_at DESC
               LIMIT $5""",
            operation_id,
            finding_id,
            from_ts,
            to_ts,
            max(1, limit * 3),
        )
        candidate_event_rows = await pool.fetch(
            """SELECT * FROM events
               WHERE operation_id = $1
                 AND timestamp BETWEEN $2 AND $3
               ORDER BY timestamp DESC
               LIMIT $4""",
            operation_id,
            from_ts,
            to_ts,
            max(1, limit * 3),
        )

        related_findings: list[dict] = []
        for row in candidate_finding_rows:
            candidate = dict(row)
            candidate_details = candidate.get("details") or {}
            candidate_member_ids = {
                str(member_id) for member_id in candidate_details.get("member_ids", [])
            }
            reasons: list[str] = []
            if candidate.get("category") == finding.get("category"):
                reasons.append("shared_category")
            if member_ids and candidate_member_ids.intersection(member_ids):
                reasons.append("shared_member_context")
            if candidate.get("latest_event_id") and (
                candidate.get("latest_event_id") == finding.get("latest_event_id")
            ):
                reasons.append("shared_event")
            if not reasons:
                continue
            candidate["correlation_reasons"] = reasons
            related_findings.append(candidate)
            if len(related_findings) >= max(1, limit):
                break

        related_events: list[dict] = []
        for row in candidate_event_rows:
            candidate = dict(row)
            reasons = []
            if candidate.get("category") == finding.get("category"):
                reasons.append("shared_category")
            source_member_id = candidate.get("source_member_id")
            if source_member_id and str(source_member_id) in member_ids:
                reasons.append("shared_member_context")
            if candidate.get("id") == finding.get("latest_event_id"):
                reasons.append("linked_event")
            if not reasons:
                continue
            candidate["correlation_reasons"] = reasons
            related_events.append(candidate)
            if len(related_events) >= max(1, limit):
                break

        return {
            "finding": finding,
            "related_findings": related_findings,
            "related_events": related_events,
            "window_minutes": max(int(window_minutes), 1),
        }

    async def update_synthesis_finding_status(
        self,
        operation_id: uuid.UUID,
        finding_id: uuid.UUID,
        status: FindingStatus,
        *,
        changed_at: datetime,
    ) -> dict | None:
        pool = self._require_pool()
        row = await pool.fetchrow(
            """UPDATE synthesis_findings
               SET status = $3,
                   status_updated_at = $4,
                   acknowledged_at = CASE
                     WHEN $3 = 'acknowledged' THEN COALESCE(acknowledged_at, $4)
                     WHEN $3 = 'open' THEN NULL
                     ELSE acknowledged_at
                   END,
                   resolved_at = CASE
                     WHEN $3 = 'resolved' THEN $4
                     WHEN $3 = 'open' THEN NULL
                     ELSE resolved_at
                   END,
                   updated_at = NOW()
               WHERE operation_id = $1 AND id = $2
               RETURNING *""",
            operation_id,
            finding_id,
            status.value,
            changed_at,
        )
        return dict(row) if row else None

    async def get_review_feed(
        self,
        operation_id: uuid.UUID,
        *,
        since: datetime | None = None,
        limit: int = 50,
        finding_status: FindingStatus | None = None,
        severity: EventSeverity | None = None,
        category: EventCategory | None = None,
        include_types: set[str] | None = None,
    ) -> list[dict]:
        include = include_types or {"finding", "event", "sitrep"}
        per_type_limit = max(int(limit), 1) * 2
        items: list[dict] = []

        if "finding" in include:
            findings = await self.get_synthesis_findings(
                operation_id,
                since=since,
                limit=per_type_limit,
                status=finding_status,
                severity=severity,
                category=category,
            )
            items.extend(
                {
                    "type": "finding",
                    "id": row["id"],
                    "timestamp": row["updated_at"],
                    "finding_id": row["id"],
                    "title": row["title"],
                    "summary": row["summary"],
                    "severity": row["severity"],
                    "category": row["category"],
                    "status": row["status"],
                    "corroborated": row["corroborated"],
                    "notes_count": row["notes_count"],
                    "last_seen_at": row["last_seen_at"],
                }
                for row in findings
            )

        if "event" in include:
            events = await self.get_events(
                operation_id,
                since=since,
                limit=per_type_limit,
                severity=severity,
                category=category,
            )
            items.extend(
                {
                    "type": "event",
                    "id": row["id"],
                    "timestamp": row["timestamp"],
                    "event_id": row["id"],
                    "title": row["category"].replace("_", " ").title(),
                    "summary": row["text"],
                    "severity": row["severity"],
                    "category": row["category"],
                    "source_member_id": row["source_member_id"],
                }
                for row in events
            )

        if "sitrep" in include and severity is None and category is None and finding_status is None:
            sitreps = await self.get_recent_sitreps(
                operation_id,
                since=since,
                limit=per_type_limit,
            )
            items.extend(
                {
                    "type": "sitrep",
                    "id": row["id"],
                    "timestamp": row["timestamp"],
                    "sitrep_id": row["id"],
                    "title": "Situation Report",
                    "summary": row["text"],
                    "trend": row["trend"],
                }
                for row in sitreps
            )

        items.sort(key=lambda item: item["timestamp"], reverse=True)
        return items[: max(int(limit), 1)]

    async def escalate_synthesis_finding(
        self,
        operation_id: uuid.UUID,
        finding_id: uuid.UUID,
        *,
        changed_at: datetime,
    ) -> dict | None:
        pool = self._require_pool()
        row = await pool.fetchrow(
            """UPDATE synthesis_findings
               SET severity = CASE severity
                   WHEN 'info' THEN 'advisory'
                   WHEN 'advisory' THEN 'warning'
                   WHEN 'warning' THEN 'critical'
                   ELSE severity
                 END,
                   updated_at = NOW(),
                   status_updated_at = CASE
                     WHEN status = 'resolved' THEN $3
                     ELSE status_updated_at
                   END,
                   status = CASE
                     WHEN status = 'resolved' THEN 'open'
                     ELSE status
                   END,
                   resolved_at = CASE
                     WHEN status = 'resolved' THEN NULL
                     ELSE resolved_at
                   END
               WHERE operation_id = $1 AND id = $2
               RETURNING *""",
            operation_id,
            finding_id,
            changed_at,
        )
        return dict(row) if row else None

    async def insert_synthesis_finding_note(
        self,
        note: FindingNote,
    ) -> None:
        pool = self._require_pool()
        await pool.execute(
            """INSERT INTO synthesis_finding_notes
               (id, operation_id, finding_id, author_type, text, created_at)
               VALUES ($1, $2, $3, $4, $5, $6)""",
            note.id,
            note.operation_id,
            note.finding_id,
            note.author_type,
            note.text,
            note.created_at,
        )
        await pool.execute(
            """UPDATE synthesis_findings
               SET notes_count = notes_count + 1,
                   updated_at = NOW()
               WHERE operation_id = $1 AND id = $2""",
            note.operation_id,
            note.finding_id,
        )

    async def claim_ingest_receipt(
        self,
        operation_id: uuid.UUID,
        *,
        kind: str,
        member_id: uuid.UUID,
        ingest_key: str,
        item_id: uuid.UUID,
        seen_at: datetime,
        window_seconds: int,
    ) -> bool:
        pool = self._require_pool()
        existing = await pool.fetchrow(
            """SELECT last_seen_at
               FROM ingest_receipts
               WHERE operation_id = $1 AND kind = $2 AND member_id = $3 AND ingest_key = $4""",
            operation_id,
            kind,
            member_id,
            ingest_key,
        )
        duplicate = False
        if existing is None:
            await pool.execute(
                """INSERT INTO ingest_receipts
                   (operation_id, kind, member_id, ingest_key, item_id, first_seen_at, last_seen_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $6)""",
                operation_id,
                kind,
                member_id,
                ingest_key,
                item_id,
                seen_at,
            )
            return False

        last_seen_at = existing["last_seen_at"]
        duplicate = (seen_at - last_seen_at) <= timedelta(seconds=max(window_seconds, 1))
        await pool.execute(
            """UPDATE ingest_receipts
               SET item_id = $5,
                   last_seen_at = $6,
                   duplicate_count = duplicate_count + $7
               WHERE operation_id = $1 AND kind = $2 AND member_id = $3 AND ingest_key = $4""",
            operation_id,
            kind,
            member_id,
            ingest_key,
            item_id,
            seen_at,
            1 if duplicate else 0,
        )
        return duplicate

    async def prune_ingest_receipts(
        self,
        operation_id: uuid.UUID,
        *,
        older_than: datetime,
    ) -> None:
        pool = self._require_pool()
        await pool.execute(
            """DELETE FROM ingest_receipts
               WHERE operation_id = $1 AND last_seen_at < $2""",
            operation_id,
            older_than,
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
