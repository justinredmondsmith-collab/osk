# Plan 1: Core Hub Infrastructure + Connection Layer

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the foundational infrastructure — project scaffolding, data models, database, storage (ephemeral + LUKS), CLI, Docker stack, WebSocket server with token auth, member management, and QR code join flow.

**Architecture:** New Python project with FastAPI + asyncpg + WebSockets. PostgreSQL on tmpfs for ephemeral storage, LUKS encrypted volume for pinned evidence. CLI wrapper (`osk`) orchestrates Docker stack and host-side operations. Members authenticate via operation token embedded in QR code.

**Tech Stack:** Python 3.11, FastAPI, uvicorn, asyncpg, websockets, pydantic, cryptography, qrcode, tomli/tomli-w, pytest, pytest-asyncio

**Spec:** `docs/specs/2026-03-21-osk-design.md`

---

## File Map

| File | Responsibility |
|---|---|
| `pyproject.toml` | Package config, dependencies, entry points |
| `src/osk/__init__.py` | Package init, version |
| `src/osk/__main__.py` | CLI entry point (`python -m osk`) |
| `src/osk/cli.py` | Argument parsing, command dispatch |
| `src/osk/config.py` | Load/save config from `~/.config/osk/config.toml` |
| `src/osk/models.py` | Pydantic models: Operation, Member, Stream, Event, Alert, Pin, SitRep |
| `src/osk/db.py` | asyncpg connection pool, migration runner, CRUD |
| `src/osk/migrations/001_initial.sql` | Core schema: operations, members, streams, events, alerts, pins |
| `src/osk/storage.py` | tmpfs mount/unmount, LUKS create/open/close/wipe, keyring ops |
| `src/osk/hub.py` | Orchestrator: start/stop Docker stack, DB, server |
| `src/osk/operation.py` | Operation lifecycle: create, token generation, rotation |
| `src/osk/connection_manager.py` | WebSocket connections, auth, roles, heartbeat, broadcast |
| `src/osk/server.py` | FastAPI app, REST endpoints, WebSocket handler |
| `src/osk/qr.py` | QR code generation (terminal ASCII + PNG) |
| `src/osk/tls.py` | Self-signed TLS certificate generation |
| `compose.yml` | Docker stack: PostgreSQL + Ollama |
| `Dockerfile` | Container build for osk hub |
| `tests/conftest.py` | Shared fixtures, mocks |
| `tests/test_models.py` | Model validation tests |
| `tests/test_config.py` | Config loading tests |
| `tests/test_db.py` | Database CRUD tests |
| `tests/test_storage.py` | Storage layer tests |
| `tests/test_operation.py` | Operation lifecycle tests |
| `tests/test_connection_manager.py` | WebSocket auth + role tests |
| `tests/test_server.py` | REST endpoint + integration tests |
| `tests/test_qr.py` | QR generation tests |
| `tests/test_tls.py` | TLS cert generation tests |
| `tests/test_cli.py` | CLI command tests |

---

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/osk/__init__.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "osk"
version = "0.1.0"
description = "Civilian situational awareness platform"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "websockets>=12.0",
    "asyncpg>=0.29",
    "httpx>=0.27",
    "pydantic>=2.0",
    "python-dotenv>=1.0.0",
    "jinja2>=3.1.0",
    "cryptography>=42.0",
    "qrcode[pil]>=7.4",
    "tomli>=2.0;python_version<'3.11'",
    "tomli-w>=1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "httpx>=0.27",
    "ruff>=0.4",
]

[project.scripts]
osk = "osk.cli:main"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
target-version = "py311"
line-length = 100

[tool.setuptools.packages.find]
where = ["src"]
```

- [ ] **Step 2: Create package init**

```python
# src/osk/__init__.py
"""Osk — Civilian situational awareness platform."""

__version__ = "0.1.0"
```

- [ ] **Step 3: Create __main__.py**

```python
# src/osk/__main__.py
"""Allow running as `python -m osk`."""
from osk.cli import main

main()
```

- [ ] **Step 4: Install in dev mode and verify**

Run: `cd /var/home/bazzite/osk && pip install -e ".[dev]"`
Expected: installs successfully, `osk` command available (will fail until cli.py exists — that's fine)

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/osk/__init__.py src/osk/__main__.py
git commit -m "feat: project scaffolding with pyproject.toml"
```

---

### Task 2: Pydantic Models

**Files:**
- Create: `src/osk/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write failing tests for core models**

```python
# tests/test_models.py
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from osk.models import (
    Alert,
    Event,
    EventCategory,
    EventSeverity,
    Member,
    MemberRole,
    MemberStatus,
    Operation,
    Pin,
    SitRep,
    Stream,
    StreamStatus,
    StreamType,
)


def test_operation_defaults():
    op = Operation(name="Test Op")
    assert op.name == "Test Op"
    assert op.token is not None
    assert len(op.token) > 0
    assert op.started_at is not None


def test_member_creation():
    m = Member(name="Jay", role=MemberRole.OBSERVER)
    assert m.id is not None
    assert m.role == MemberRole.OBSERVER
    assert m.status == MemberStatus.CONNECTED


def test_member_role_values():
    assert MemberRole.OBSERVER.value == "observer"
    assert MemberRole.SENSOR.value == "sensor"
    assert MemberRole.COORDINATOR.value == "coordinator"


def test_stream_creation():
    s = Stream(
        member_id=uuid.uuid4(),
        stream_type=StreamType.AUDIO,
    )
    assert s.status == StreamStatus.ACTIVE


def test_event_creation():
    e = Event(
        severity=EventSeverity.WARNING,
        category=EventCategory.POLICE_ACTION,
        text="Police forming line on 5th St",
        source_member_id=uuid.uuid4(),
    )
    assert e.id is not None
    assert e.timestamp is not None


def test_event_severity_ordering():
    assert EventSeverity.INFO.level < EventSeverity.ADVISORY.level
    assert EventSeverity.ADVISORY.level < EventSeverity.WARNING.level
    assert EventSeverity.WARNING.level < EventSeverity.CRITICAL.level


def test_alert_from_event():
    event_id = uuid.uuid4()
    a = Alert(
        event_id=event_id,
        severity=EventSeverity.WARNING,
        category=EventCategory.ESCALATION,
        text="Escalation detected near you",
    )
    assert a.event_id == event_id


def test_pin_creation():
    p = Pin(event_id=uuid.uuid4(), pinned_by=uuid.uuid4())
    assert p.pinned_at is not None


def test_sitrep_creation():
    sr = SitRep(
        text="Crowd stable, two exits clear",
        trend="stable",
    )
    assert sr.timestamp is not None
    assert sr.trend == "stable"


def test_operation_serialization():
    op = Operation(name="Test")
    d = op.model_dump()
    assert d["name"] == "Test"
    assert "token" in d


def test_event_serialization():
    e = Event(
        severity=EventSeverity.CRITICAL,
        category=EventCategory.MEDICAL,
        text="Medical emergency",
        source_member_id=uuid.uuid4(),
    )
    d = e.model_dump(mode="json")
    assert d["severity"] == "critical"
    assert d["category"] == "medical"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_models.py -v`
Expected: ImportError — `osk.models` not found

- [ ] **Step 3: Implement models**

```python
# src/osk/models.py
"""Core Pydantic models for Osk."""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> uuid.UUID:
    return uuid.uuid4()


def _new_token() -> str:
    return secrets.token_urlsafe(32)


class MemberRole(str, Enum):
    OBSERVER = "observer"
    SENSOR = "sensor"
    COORDINATOR = "coordinator"


class MemberStatus(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    KICKED = "kicked"


class StreamType(str, Enum):
    AUDIO = "audio"
    VIDEO = "video"


class StreamStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    ENDED = "ended"


class EventSeverity(str, Enum):
    INFO = "info"
    ADVISORY = "advisory"
    WARNING = "warning"
    CRITICAL = "critical"

    @property
    def level(self) -> int:
        return {"info": 0, "advisory": 1, "warning": 2, "critical": 3}[self.value]


class EventCategory(str, Enum):
    CROWD_MOVEMENT = "crowd_movement"
    POLICE_ACTION = "police_action"
    BLOCKED_ROUTE = "blocked_route"
    ESCALATION = "escalation"
    MEDICAL = "medical"
    WEATHER = "weather"
    COMMUNITY = "community"
    MANUAL_REPORT = "manual_report"


class Operation(BaseModel):
    id: uuid.UUID = Field(default_factory=_new_id)
    name: str
    token: str = Field(default_factory=_new_token)
    started_at: datetime = Field(default_factory=_utcnow)
    stopped_at: datetime | None = None


class Member(BaseModel):
    id: uuid.UUID = Field(default_factory=_new_id)
    name: str
    role: MemberRole = MemberRole.OBSERVER
    status: MemberStatus = MemberStatus.CONNECTED
    latitude: float | None = None
    longitude: float | None = None
    last_gps_at: datetime | None = None
    connected_at: datetime = Field(default_factory=_utcnow)


class Stream(BaseModel):
    id: uuid.UUID = Field(default_factory=_new_id)
    member_id: uuid.UUID
    stream_type: StreamType
    status: StreamStatus = StreamStatus.ACTIVE
    started_at: datetime = Field(default_factory=_utcnow)
    ended_at: datetime | None = None


class Event(BaseModel):
    id: uuid.UUID = Field(default_factory=_new_id)
    severity: EventSeverity
    category: EventCategory
    text: str
    source_member_id: uuid.UUID | None = None
    latitude: float | None = None
    longitude: float | None = None
    timestamp: datetime = Field(default_factory=_utcnow)


class Alert(BaseModel):
    id: uuid.UUID = Field(default_factory=_new_id)
    event_id: uuid.UUID
    severity: EventSeverity
    category: EventCategory
    text: str
    timestamp: datetime = Field(default_factory=_utcnow)


class Pin(BaseModel):
    id: uuid.UUID = Field(default_factory=_new_id)
    event_id: uuid.UUID
    pinned_by: uuid.UUID
    pinned_at: datetime = Field(default_factory=_utcnow)


class SitRep(BaseModel):
    id: uuid.UUID = Field(default_factory=_new_id)
    text: str
    trend: str  # "escalating", "stable", "de-escalating"
    timestamp: datetime = Field(default_factory=_utcnow)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_models.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/osk/models.py tests/test_models.py
git commit -m "feat: core Pydantic models for Operation, Member, Event, Alert, Pin, SitRep"
```

---

### Task 3: Configuration

**Files:**
- Create: `src/osk/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_config.py
from __future__ import annotations

from pathlib import Path

from osk.config import OskConfig, load_config, save_config


def test_default_config():
    cfg = OskConfig()
    assert cfg.max_sensors == 10
    assert cfg.whisper_model == "small"
    assert cfg.sitrep_interval_minutes == 10
    assert cfg.alert_cooldown_seconds == 60
    assert cfg.frame_change_threshold == 0.15
    assert cfg.observer_clip_rate_limit == 3
    assert cfg.luks_volume_size_gb == 1
    assert cfg.hotspot_band == "5GHz"


def test_load_missing_config(tmp_path: Path):
    cfg = load_config(tmp_path / "nonexistent.toml")
    assert cfg == OskConfig()


def test_save_and_load_config(tmp_path: Path):
    cfg = OskConfig(max_sensors=5, whisper_model="tiny")
    path = tmp_path / "config.toml"
    save_config(cfg, path)
    loaded = load_config(path)
    assert loaded.max_sensors == 5
    assert loaded.whisper_model == "tiny"


def test_config_partial_file(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text('max_sensors = 3\n')
    cfg = load_config(path)
    assert cfg.max_sensors == 3
    assert cfg.whisper_model == "small"  # default preserved
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -v`
Expected: ImportError

- [ ] **Step 3: Implement config**

```python
# src/osk/config.py
"""Configuration management for Osk."""
from __future__ import annotations

from pathlib import Path

import tomli_w

from pydantic import BaseModel

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


DEFAULT_CONFIG_PATH = Path.home() / ".config" / "osk" / "config.toml"


class OskConfig(BaseModel):
    max_sensors: int = 10
    whisper_model: str = "small"
    vision_model: str = "llama3.2-vision:11b-instruct-q4_K_M"
    summarizer_model: str = "mistral"
    sitrep_interval_minutes: int = 10
    alert_cooldown_seconds: int = 60
    gps_interval_moving_seconds: int = 10
    gps_interval_stationary_seconds: int = 60
    frame_change_threshold: float = 0.15
    frame_baseline_interval_seconds: int = 30
    frame_sampling_fps: float = 2.0
    observer_clip_rate_limit: int = 3
    luks_volume_size_gb: int = 1
    tls_cert_path: str = str(Path.home() / ".config" / "osk" / "cert.pem")
    tls_key_path: str = str(Path.home() / ".config" / "osk" / "key.pem")
    hotspot_ssid: str = ""
    hotspot_band: str = "5GHz"
    map_tile_cache_path: str = str(Path.home() / ".config" / "osk" / "tiles")
    hub_port: int = 8443
    ollama_base_url: str = "http://localhost:11434"


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> OskConfig:
    if not path.exists():
        return OskConfig()
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return OskConfig(**data)


def save_config(config: OskConfig, path: Path = DEFAULT_CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        tomli_w.dump(config.model_dump(), f)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_config.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/osk/config.py tests/test_config.py
git commit -m "feat: configuration management with TOML persistence"
```

---

### Task 4: Database Layer + Migrations

**Files:**
- Create: `src/osk/db.py`
- Create: `src/osk/migrations/001_initial.sql`
- Create: `tests/test_db.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Write migration SQL**

```sql
-- src/osk/migrations/001_initial.sql

CREATE TABLE IF NOT EXISTS operations (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    token TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    stopped_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS members (
    id UUID PRIMARY KEY,
    operation_id UUID NOT NULL REFERENCES operations(id),
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'observer',
    status TEXT NOT NULL DEFAULT 'connected',
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    last_gps_at TIMESTAMPTZ,
    connected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_members_operation ON members(operation_id);

CREATE TABLE IF NOT EXISTS streams (
    id UUID PRIMARY KEY,
    member_id UUID NOT NULL REFERENCES members(id),
    stream_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_streams_member ON streams(member_id);

CREATE TABLE IF NOT EXISTS transcript_segments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stream_id UUID NOT NULL REFERENCES streams(id),
    member_id UUID NOT NULL REFERENCES members(id),
    timestamp TIMESTAMPTZ NOT NULL,
    start_time DOUBLE PRECISION NOT NULL,
    end_time DOUBLE PRECISION NOT NULL,
    text TEXT NOT NULL,
    confidence DOUBLE PRECISION
);

CREATE INDEX IF NOT EXISTS idx_transcripts_stream ON transcript_segments(stream_id);

CREATE TABLE IF NOT EXISTS observations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    member_id UUID NOT NULL REFERENCES members(id),
    scene_description TEXT NOT NULL,
    entities JSONB DEFAULT '[]',
    threat_score DOUBLE PRECISION DEFAULT 0.0,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS events (
    id UUID PRIMARY KEY,
    operation_id UUID NOT NULL REFERENCES operations(id),
    severity TEXT NOT NULL,
    category TEXT NOT NULL,
    text TEXT NOT NULL,
    source_member_id UUID REFERENCES members(id),
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_events_operation ON events(operation_id);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);

CREATE TABLE IF NOT EXISTS alerts (
    id UUID PRIMARY KEY,
    event_id UUID NOT NULL REFERENCES events(id),
    severity TEXT NOT NULL,
    category TEXT NOT NULL,
    text TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pins (
    id UUID PRIMARY KEY,
    event_id UUID NOT NULL REFERENCES events(id),
    pinned_by UUID NOT NULL REFERENCES members(id),
    pinned_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sitreps (
    id UUID PRIMARY KEY,
    operation_id UUID NOT NULL REFERENCES operations(id),
    text TEXT NOT NULL,
    trend TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sitreps_operation ON sitreps(operation_id);
```

- [ ] **Step 2: Write conftest with mock database**

```python
# tests/conftest.py
"""Shared test fixtures for Osk."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from osk.models import (
    Event,
    EventCategory,
    EventSeverity,
    Member,
    MemberRole,
    Operation,
)


@pytest.fixture
def operation() -> Operation:
    return Operation(name="Test Operation")


@pytest.fixture
def coordinator(operation: Operation) -> Member:
    return Member(name="Coordinator", role=MemberRole.COORDINATOR)


@pytest.fixture
def sensor_member() -> Member:
    return Member(name="Sensor-1", role=MemberRole.SENSOR)


@pytest.fixture
def observer_member() -> Member:
    return Member(name="Observer-1", role=MemberRole.OBSERVER)


@pytest.fixture
def sample_event() -> Event:
    return Event(
        severity=EventSeverity.WARNING,
        category=EventCategory.POLICE_ACTION,
        text="Police staging at 5th and Main",
        source_member_id=uuid.uuid4(),
        latitude=39.75,
        longitude=-104.99,
    )


@pytest.fixture
def mock_db() -> MagicMock:
    db = MagicMock()
    db.connect = AsyncMock()
    db.close = AsyncMock()
    db.insert_operation = AsyncMock()
    db.insert_member = AsyncMock()
    db.update_member_role = AsyncMock()
    db.update_member_status = AsyncMock()
    db.update_member_gps = AsyncMock()
    db.insert_event = AsyncMock()
    db.insert_alert = AsyncMock()
    db.insert_pin = AsyncMock()
    db.insert_sitrep = AsyncMock()
    db.get_events_since = AsyncMock(return_value=[])
    db.get_latest_sitrep = AsyncMock(return_value=None)
    db.get_members = AsyncMock(return_value=[])
    return db
```

- [ ] **Step 3: Write failing database tests**

```python
# tests/test_db.py
"""Tests for database layer — uses mocked asyncpg pool."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from osk.db import Database
from osk.models import EventCategory, EventSeverity, MemberRole


@pytest.fixture
def db():
    return Database()


@pytest.fixture
def mock_pool():
    pool = MagicMock()
    pool.execute = AsyncMock()
    pool.fetch = AsyncMock(return_value=[])
    pool.fetchrow = AsyncMock(return_value=None)
    pool.fetchval = AsyncMock(return_value=None)
    pool.close = AsyncMock()
    return pool


async def test_migration_files_exist(db: Database):
    migrations = db._get_migration_files()
    assert len(migrations) > 0
    assert migrations[0].name == "001_initial.sql"


async def test_insert_operation(db: Database, mock_pool: MagicMock):
    db._pool = mock_pool
    op_id = uuid.uuid4()
    await db.insert_operation(op_id, "Test Op", "token123")
    mock_pool.execute.assert_called_once()
    call_args = mock_pool.execute.call_args
    assert "INSERT INTO operations" in call_args[0][0]


async def test_insert_member(db: Database, mock_pool: MagicMock):
    db._pool = mock_pool
    await db.insert_member(
        uuid.uuid4(), uuid.uuid4(), "Jay", MemberRole.OBSERVER
    )
    mock_pool.execute.assert_called_once()


async def test_update_member_gps(db: Database, mock_pool: MagicMock):
    db._pool = mock_pool
    await db.update_member_gps(uuid.uuid4(), 39.75, -104.99)
    mock_pool.execute.assert_called_once()
    assert "UPDATE members" in mock_pool.execute.call_args[0][0]


async def test_insert_event(db: Database, mock_pool: MagicMock):
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


async def test_get_events_since(db: Database, mock_pool: MagicMock):
    db._pool = mock_pool
    mock_pool.fetch.return_value = []
    result = await db.get_events_since(uuid.uuid4(), "2026-01-01T00:00:00Z")
    assert result == []
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/test_db.py -v`
Expected: ImportError

- [ ] **Step 5: Implement Database class**

```python
# src/osk/db.py
"""PostgreSQL database layer for Osk."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
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

    async def connect(self, database_url: str) -> None:
        self._pool = await asyncpg.create_pool(database_url, min_size=2, max_size=10)
        await self._run_migrations()

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def _run_migrations(self) -> None:
        for migration_file in self._get_migration_files():
            sql = migration_file.read_text()
            await self._pool.execute(sql)
            logger.info("Applied migration: %s", migration_file.name)

    # --- Operations ---

    async def insert_operation(
        self, op_id: uuid.UUID, name: str, token: str
    ) -> None:
        await self._pool.execute(
            "INSERT INTO operations (id, name, token) VALUES ($1, $2, $3)",
            op_id,
            name,
            token,
        )

    async def update_operation_token(
        self, op_id: uuid.UUID, new_token: str
    ) -> None:
        await self._pool.execute(
            "UPDATE operations SET token = $1 WHERE id = $2",
            new_token,
            op_id,
        )

    async def get_operation_token(self, op_id: uuid.UUID) -> str | None:
        return await self._pool.fetchval(
            "SELECT token FROM operations WHERE id = $1", op_id
        )

    # --- Members ---

    async def insert_member(
        self,
        member_id: uuid.UUID,
        operation_id: uuid.UUID,
        name: str,
        role: MemberRole,
    ) -> None:
        await self._pool.execute(
            "INSERT INTO members (id, operation_id, name, role) VALUES ($1, $2, $3, $4)",
            member_id,
            operation_id,
            name,
            role.value,
        )

    async def update_member_role(
        self, member_id: uuid.UUID, role: MemberRole
    ) -> None:
        await self._pool.execute(
            "UPDATE members SET role = $1 WHERE id = $2",
            role.value,
            member_id,
        )

    async def update_member_status(
        self, member_id: uuid.UUID, status: str
    ) -> None:
        await self._pool.execute(
            "UPDATE members SET status = $1 WHERE id = $2",
            status,
            member_id,
        )

    async def update_member_gps(
        self,
        member_id: uuid.UUID,
        latitude: float,
        longitude: float,
    ) -> None:
        await self._pool.execute(
            "UPDATE members SET latitude = $1, longitude = $2, last_gps_at = NOW() WHERE id = $3",
            latitude,
            longitude,
            member_id,
        )

    async def get_members(self, operation_id: uuid.UUID) -> list[dict]:
        rows = await self._pool.fetch(
            "SELECT * FROM members WHERE operation_id = $1 ORDER BY connected_at",
            operation_id,
        )
        return [dict(r) for r in rows]

    # --- Events ---

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
        await self._pool.execute(
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

    async def get_events_since(
        self, operation_id: uuid.UUID, since: str
    ) -> list[dict]:
        rows = await self._pool.fetch(
            "SELECT * FROM events WHERE operation_id = $1 AND timestamp >= $2 ORDER BY timestamp",
            operation_id,
            since,
        )
        return [dict(r) for r in rows]

    # --- Alerts ---

    async def insert_alert(
        self,
        alert_id: uuid.UUID,
        event_id: uuid.UUID,
        severity: EventSeverity,
        category: EventCategory,
        text: str,
    ) -> None:
        await self._pool.execute(
            "INSERT INTO alerts (id, event_id, severity, category, text) VALUES ($1, $2, $3, $4, $5)",
            alert_id,
            event_id,
            severity.value,
            category.value,
            text,
        )

    # --- Pins ---

    async def insert_pin(
        self,
        pin_id: uuid.UUID,
        event_id: uuid.UUID,
        pinned_by: uuid.UUID,
    ) -> None:
        await self._pool.execute(
            "INSERT INTO pins (id, event_id, pinned_by) VALUES ($1, $2, $3)",
            pin_id,
            event_id,
            pinned_by,
        )

    # --- SitReps ---

    async def insert_sitrep(
        self,
        sitrep_id: uuid.UUID,
        operation_id: uuid.UUID,
        text: str,
        trend: str,
    ) -> None:
        await self._pool.execute(
            "INSERT INTO sitreps (id, operation_id, text, trend) VALUES ($1, $2, $3, $4)",
            sitrep_id,
            operation_id,
            text,
            trend,
        )

    async def get_latest_sitrep(self, operation_id: uuid.UUID) -> dict | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM sitreps WHERE operation_id = $1 ORDER BY timestamp DESC LIMIT 1",
            operation_id,
        )
        return dict(row) if row else None

    # --- Transcript Segments ---

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
        await self._pool.execute(
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

    # --- Observations ---

    async def insert_observation(
        self,
        member_id: uuid.UUID,
        scene_description: str,
        entities: list,
        threat_score: float,
    ) -> None:
        import json

        await self._pool.execute(
            """INSERT INTO observations (member_id, scene_description, entities, threat_score)
               VALUES ($1, $2, $3::jsonb, $4)""",
            member_id,
            scene_description,
            json.dumps(entities),
            threat_score,
        )

    # --- Streams ---

    async def insert_stream(
        self,
        stream_id: uuid.UUID,
        member_id: uuid.UUID,
        stream_type: str,
    ) -> None:
        await self._pool.execute(
            "INSERT INTO streams (id, member_id, stream_type) VALUES ($1, $2, $3)",
            stream_id,
            member_id,
            stream_type,
        )

    async def update_stream_status(
        self, stream_id: uuid.UUID, status: str
    ) -> None:
        await self._pool.execute(
            "UPDATE streams SET status = $1 WHERE id = $2",
            status,
            stream_id,
        )
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_db.py -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add src/osk/db.py src/osk/migrations/001_initial.sql tests/conftest.py tests/test_db.py
git commit -m "feat: database layer with asyncpg, migration runner, and CRUD operations"
```

---

### Task 5: Storage Layer (tmpfs + LUKS)

**Files:**
- Create: `src/osk/storage.py`
- Create: `tests/test_storage.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_storage.py
"""Tests for ephemeral storage and LUKS management — all subprocess calls mocked."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from osk.storage import StorageManager


@pytest.fixture
def storage(tmp_path: Path) -> StorageManager:
    return StorageManager(
        tmpfs_path=tmp_path / "tmpfs",
        luks_image_path=tmp_path / "osk.luks",
        luks_mount_path=tmp_path / "evidence",
        luks_size_gb=1,
    )


def test_storage_init(storage: StorageManager):
    assert storage.tmpfs_path is not None
    assert storage.luks_image_path is not None


@patch("osk.storage.subprocess")
def test_create_luks_volume(mock_subprocess: MagicMock, storage: StorageManager):
    mock_subprocess.run.return_value = MagicMock(returncode=0)
    storage.create_luks_volume("test-passphrase")
    # Should call: truncate, cryptsetup luksFormat, cryptsetup open, mkfs, cryptsetup close
    assert mock_subprocess.run.call_count >= 3


@patch("osk.storage.subprocess")
def test_mount_tmpfs(mock_subprocess: MagicMock, storage: StorageManager):
    mock_subprocess.run.return_value = MagicMock(returncode=0)
    storage.mount_tmpfs()
    cmd = mock_subprocess.run.call_args[0][0]
    assert "mount" in cmd
    assert "tmpfs" in cmd


@patch("osk.storage.subprocess")
def test_unmount_tmpfs(mock_subprocess: MagicMock, storage: StorageManager):
    mock_subprocess.run.return_value = MagicMock(returncode=0)
    storage.unmount_tmpfs()
    cmd = mock_subprocess.run.call_args[0][0]
    assert "umount" in cmd


@patch("osk.storage.subprocess")
def test_open_luks(mock_subprocess: MagicMock, storage: StorageManager):
    mock_subprocess.run.return_value = MagicMock(returncode=0)
    storage.open_luks("test-passphrase")
    # Should call cryptsetup open and mount
    assert mock_subprocess.run.call_count >= 2


@patch("osk.storage.subprocess")
def test_close_luks(mock_subprocess: MagicMock, storage: StorageManager):
    mock_subprocess.run.return_value = MagicMock(returncode=0)
    storage.close_luks()
    cmd = mock_subprocess.run.call_args[0][0]
    assert "cryptsetup" in cmd


@patch("osk.storage.subprocess")
def test_emergency_wipe(mock_subprocess: MagicMock, storage: StorageManager):
    mock_subprocess.run.return_value = MagicMock(returncode=0)
    storage.emergency_wipe()
    # Should revoke keyring, close LUKS, unmount tmpfs
    assert mock_subprocess.run.call_count >= 2


@patch("osk.storage.subprocess")
def test_store_passphrase_in_keyring(mock_subprocess: MagicMock, storage: StorageManager):
    mock_subprocess.run.return_value = MagicMock(returncode=0, stdout="12345\n")
    storage.store_passphrase_in_keyring("test-passphrase")
    assert storage._keyring_id == "12345"


@patch("osk.storage.subprocess")
def test_revoke_keyring(mock_subprocess: MagicMock, storage: StorageManager):
    mock_subprocess.run.return_value = MagicMock(returncode=0)
    storage._keyring_id = "12345"
    storage.revoke_keyring()
    cmd = mock_subprocess.run.call_args[0][0]
    assert "keyctl" in cmd
    assert "revoke" in cmd[1] if len(cmd) > 1 else True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_storage.py -v`
Expected: ImportError

- [ ] **Step 3: Implement StorageManager**

```python
# src/osk/storage.py
"""Ephemeral storage (tmpfs) and LUKS encrypted volume management."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

LUKS_MAPPER_NAME = "osk-evidence"


class StorageManager:
    def __init__(
        self,
        tmpfs_path: Path,
        luks_image_path: Path,
        luks_mount_path: Path,
        luks_size_gb: int = 1,
    ) -> None:
        self.tmpfs_path = tmpfs_path
        self.luks_image_path = luks_image_path
        self.luks_mount_path = luks_mount_path
        self.luks_size_gb = luks_size_gb
        self._keyring_id: str | None = None

    # --- tmpfs ---

    def mount_tmpfs(self) -> None:
        self.tmpfs_path.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["sudo", "mount", "-t", "tmpfs", "-o", "size=512M", "tmpfs", str(self.tmpfs_path)],
            check=True,
        )
        logger.info("Mounted tmpfs at %s", self.tmpfs_path)

    def unmount_tmpfs(self) -> None:
        subprocess.run(
            ["sudo", "umount", str(self.tmpfs_path)],
            check=True,
        )
        logger.info("Unmounted tmpfs at %s", self.tmpfs_path)

    # --- LUKS ---

    def create_luks_volume(self, passphrase: str) -> None:
        if self.luks_image_path.exists():
            logger.info("LUKS volume already exists at %s", self.luks_image_path)
            return
        self.luks_image_path.parent.mkdir(parents=True, exist_ok=True)
        size_bytes = self.luks_size_gb * 1024 * 1024 * 1024
        subprocess.run(
            ["truncate", "-s", str(size_bytes), str(self.luks_image_path)],
            check=True,
        )
        subprocess.run(
            ["sudo", "cryptsetup", "luksFormat", "--batch-mode",
             str(self.luks_image_path)],
            input=passphrase.encode(),
            check=True,
        )
        subprocess.run(
            ["sudo", "cryptsetup", "open", str(self.luks_image_path),
             LUKS_MAPPER_NAME, "--type", "luks"],
            input=passphrase.encode(),
            check=True,
        )
        subprocess.run(
            ["sudo", "mkfs.ext4", f"/dev/mapper/{LUKS_MAPPER_NAME}"],
            check=True,
        )
        subprocess.run(
            ["sudo", "cryptsetup", "close", LUKS_MAPPER_NAME],
            check=True,
        )
        logger.info("Created LUKS volume at %s (%d GB)", self.luks_image_path, self.luks_size_gb)

    def open_luks(self, passphrase: str) -> None:
        subprocess.run(
            ["sudo", "cryptsetup", "open", str(self.luks_image_path),
             LUKS_MAPPER_NAME, "--type", "luks"],
            input=passphrase.encode(),
            check=True,
        )
        self.luks_mount_path.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["sudo", "mount", f"/dev/mapper/{LUKS_MAPPER_NAME}",
             str(self.luks_mount_path)],
            check=True,
        )
        self.store_passphrase_in_keyring(passphrase)
        logger.info("Opened LUKS volume, mounted at %s", self.luks_mount_path)

    def close_luks(self) -> None:
        subprocess.run(
            ["sudo", "umount", str(self.luks_mount_path)],
            check=False,
        )
        subprocess.run(
            ["sudo", "cryptsetup", "close", LUKS_MAPPER_NAME],
            check=False,
        )
        logger.info("Closed LUKS volume")

    # --- Keyring ---

    def store_passphrase_in_keyring(self, passphrase: str) -> None:
        result = subprocess.run(
            ["keyctl", "add", "user", "osk-passphrase", passphrase, "@s"],
            capture_output=True,
            text=True,
            check=True,
        )
        self._keyring_id = result.stdout.strip()
        logger.info("Stored passphrase in kernel keyring (id=%s)", self._keyring_id)

    def revoke_keyring(self) -> None:
        if self._keyring_id:
            subprocess.run(
                ["keyctl", "revoke", self._keyring_id],
                check=False,
            )
            self._keyring_id = None
            logger.info("Revoked kernel keyring entry")

    # --- Emergency Wipe ---

    def emergency_wipe(self) -> None:
        logger.warning("EMERGENCY WIPE initiated")
        self.revoke_keyring()
        self.close_luks()
        try:
            self.unmount_tmpfs()
        except subprocess.CalledProcessError:
            logger.warning("tmpfs unmount failed during wipe — may already be unmounted")
        logger.warning("EMERGENCY WIPE complete")
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_storage.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/osk/storage.py tests/test_storage.py
git commit -m "feat: storage layer with tmpfs, LUKS encrypted volume, kernel keyring, emergency wipe"
```

---

### Task 6: TLS Certificate Generation

**Files:**
- Create: `src/osk/tls.py`
- Create: `tests/test_tls.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_tls.py
from __future__ import annotations

from pathlib import Path

from osk.tls import generate_self_signed_cert


def test_generate_cert(tmp_path: Path):
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    generate_self_signed_cert(cert_path, key_path)
    assert cert_path.exists()
    assert key_path.exists()
    assert cert_path.stat().st_size > 0
    assert key_path.stat().st_size > 0


def test_cert_contains_pem_markers(tmp_path: Path):
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    generate_self_signed_cert(cert_path, key_path)
    assert "BEGIN CERTIFICATE" in cert_path.read_text()
    assert "BEGIN" in key_path.read_text()


def test_no_overwrite_existing(tmp_path: Path):
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    generate_self_signed_cert(cert_path, key_path)
    mtime = cert_path.stat().st_mtime
    generate_self_signed_cert(cert_path, key_path)
    assert cert_path.stat().st_mtime == mtime  # not overwritten
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tls.py -v`
Expected: ImportError

- [ ] **Step 3: Implement TLS cert generation**

```python
# src/osk/tls.py
"""Self-signed TLS certificate generation for Osk hub."""
from __future__ import annotations

import datetime
import logging
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

logger = logging.getLogger(__name__)


def generate_self_signed_cert(cert_path: Path, key_path: Path) -> None:
    if cert_path.exists() and key_path.exists():
        logger.info("TLS certificate already exists at %s", cert_path)
        return

    cert_path.parent.mkdir(parents=True, exist_ok=True)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "osk-hub"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Osk"),
    ])

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
        .not_valid_after(
            datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365)
        )
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
            ]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    logger.info("Generated self-signed TLS certificate at %s", cert_path)


import ipaddress  # noqa: E402 — used in SAN extension above
```

Note: move the `import ipaddress` to the top of the file during implementation.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_tls.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/osk/tls.py tests/test_tls.py
git commit -m "feat: self-signed TLS certificate generation"
```

---

### Task 7: QR Code Generation

**Files:**
- Create: `src/osk/qr.py`
- Create: `tests/test_qr.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_qr.py
from __future__ import annotations

from pathlib import Path

from osk.qr import generate_qr_ascii, generate_qr_png, build_join_url


def test_build_join_url():
    url = build_join_url("192.168.1.1", 8443, "abc123token")
    assert url == "https://192.168.1.1:8443/join?token=abc123token"


def test_generate_qr_ascii():
    text = generate_qr_ascii("https://example.com")
    assert len(text) > 0
    assert "\n" in text  # multiple lines


def test_generate_qr_png(tmp_path: Path):
    out = tmp_path / "qr.png"
    generate_qr_png("https://example.com", out)
    assert out.exists()
    assert out.stat().st_size > 0
    # Check PNG magic bytes
    assert out.read_bytes()[:4] == b"\x89PNG"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_qr.py -v`
Expected: ImportError

- [ ] **Step 3: Implement QR generation**

```python
# src/osk/qr.py
"""QR code generation for Osk operation join URL."""
from __future__ import annotations

import io
from pathlib import Path

import qrcode
from qrcode.image.pure import PyPNGImage


def build_join_url(host: str, port: int, token: str) -> str:
    return f"https://{host}:{port}/join?token={token}"


def generate_qr_ascii(data: str) -> str:
    qr = qrcode.QRCode(border=1)
    qr.add_data(data)
    qr.make(fit=True)
    buf = io.StringIO()
    qr.print_ascii(out=buf)
    return buf.getvalue()


def generate_qr_png(data: str, output_path: Path) -> None:
    qr = qrcode.QRCode(border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(image_factory=PyPNGImage)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path))
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_qr.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/osk/qr.py tests/test_qr.py
git commit -m "feat: QR code generation for operation join URL"
```

---

### Task 8: Operation Lifecycle

**Files:**
- Create: `src/osk/operation.py`
- Create: `tests/test_operation.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_operation.py
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from osk.models import MemberRole, MemberStatus, Operation
from osk.operation import OperationManager


@pytest.fixture
def op_manager(mock_db: MagicMock) -> OperationManager:
    return OperationManager(db=mock_db)


async def test_create_operation(op_manager: OperationManager):
    op = await op_manager.create("Test Op")
    assert op.name == "Test Op"
    assert op.token is not None
    op_manager.db.insert_operation.assert_called_once()


async def test_add_member(op_manager: OperationManager):
    op = await op_manager.create("Test Op")
    member = await op_manager.add_member(op.id, "Jay")
    assert member.name == "Jay"
    assert member.role == MemberRole.OBSERVER
    assert member.id in op_manager.members


async def test_promote_member(op_manager: OperationManager):
    op = await op_manager.create("Test Op")
    member = await op_manager.add_member(op.id, "Jay")
    await op_manager.promote_member(member.id)
    assert op_manager.members[member.id].role == MemberRole.SENSOR
    op_manager.db.update_member_role.assert_called_once()


async def test_demote_member(op_manager: OperationManager):
    op = await op_manager.create("Test Op")
    member = await op_manager.add_member(op.id, "Jay")
    await op_manager.promote_member(member.id)
    await op_manager.demote_member(member.id)
    assert op_manager.members[member.id].role == MemberRole.OBSERVER


async def test_kick_member(op_manager: OperationManager):
    op = await op_manager.create("Test Op")
    member = await op_manager.add_member(op.id, "Jay")
    await op_manager.kick_member(member.id)
    assert op_manager.members[member.id].status == MemberStatus.KICKED


async def test_rotate_token(op_manager: OperationManager):
    op = await op_manager.create("Test Op")
    old_token = op.token
    new_token = await op_manager.rotate_token(op.id)
    assert new_token != old_token
    assert op_manager.operation.token == new_token


async def test_validate_token(op_manager: OperationManager):
    op = await op_manager.create("Test Op")
    assert op_manager.validate_token(op.token) is True
    assert op_manager.validate_token("wrong-token") is False


async def test_get_sensor_count(op_manager: OperationManager):
    op = await op_manager.create("Test Op")
    await op_manager.add_member(op.id, "Jay")
    m2 = await op_manager.add_member(op.id, "Mika")
    await op_manager.promote_member(m2.id)
    assert op_manager.get_sensor_count() == 1


async def test_update_member_gps(op_manager: OperationManager):
    op = await op_manager.create("Test Op")
    member = await op_manager.add_member(op.id, "Jay")
    await op_manager.update_member_gps(member.id, 39.75, -104.99)
    assert op_manager.members[member.id].latitude == 39.75
    assert op_manager.members[member.id].longitude == -104.99
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_operation.py -v`
Expected: ImportError

- [ ] **Step 3: Implement OperationManager**

```python
# src/osk/operation.py
"""Operation lifecycle management."""
from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timezone

from osk.models import Member, MemberRole, MemberStatus, Operation

logger = logging.getLogger(__name__)


class OperationManager:
    def __init__(self, db) -> None:
        self.db = db
        self.operation: Operation | None = None
        self.members: dict[uuid.UUID, Member] = {}

    async def create(self, name: str) -> Operation:
        self.operation = Operation(name=name)
        self.members.clear()
        await self.db.insert_operation(
            self.operation.id, self.operation.name, self.operation.token
        )
        logger.info("Created operation: %s (id=%s)", name, self.operation.id)
        return self.operation

    def validate_token(self, token: str) -> bool:
        return self.operation is not None and secrets.compare_digest(
            self.operation.token, token
        )

    async def rotate_token(self, op_id: uuid.UUID) -> str:
        new_token = secrets.token_urlsafe(32)
        self.operation.token = new_token
        await self.db.update_operation_token(op_id, new_token)
        logger.info("Rotated operation token for %s", op_id)
        return new_token

    async def add_member(
        self, operation_id: uuid.UUID, name: str
    ) -> Member:
        member = Member(name=name, role=MemberRole.OBSERVER)
        self.members[member.id] = member
        await self.db.insert_member(
            member.id, operation_id, name, member.role
        )
        logger.info("Member joined: %s (id=%s)", name, member.id)
        return member

    async def promote_member(self, member_id: uuid.UUID) -> None:
        member = self.members[member_id]
        member.role = MemberRole.SENSOR
        await self.db.update_member_role(member_id, MemberRole.SENSOR)
        logger.info("Promoted %s to sensor", member.name)

    async def demote_member(self, member_id: uuid.UUID) -> None:
        member = self.members[member_id]
        member.role = MemberRole.OBSERVER
        await self.db.update_member_role(member_id, MemberRole.OBSERVER)
        logger.info("Demoted %s to observer", member.name)

    async def kick_member(self, member_id: uuid.UUID) -> None:
        member = self.members[member_id]
        member.status = MemberStatus.KICKED
        await self.db.update_member_status(member_id, MemberStatus.KICKED.value)
        logger.info("Kicked member: %s", member.name)

    async def update_member_gps(
        self, member_id: uuid.UUID, lat: float, lon: float
    ) -> None:
        member = self.members[member_id]
        member.latitude = lat
        member.longitude = lon
        member.last_gps_at = datetime.now(timezone.utc)
        await self.db.update_member_gps(member_id, lat, lon)

    def get_sensor_count(self) -> int:
        return sum(
            1
            for m in self.members.values()
            if m.role == MemberRole.SENSOR and m.status == MemberStatus.CONNECTED
        )

    def get_member_list(self) -> list[dict]:
        return [m.model_dump(mode="json") for m in self.members.values()]
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_operation.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/osk/operation.py tests/test_operation.py
git commit -m "feat: operation lifecycle — create, members, roles, token rotation, kick"
```

---

### Task 9: Connection Manager (WebSocket Auth + Roles)

**Files:**
- Create: `src/osk/connection_manager.py`
- Create: `tests/test_connection_manager.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_connection_manager.py
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from osk.connection_manager import ConnectionManager
from osk.models import EventSeverity, MemberRole


@pytest.fixture
def mock_ws() -> MagicMock:
    ws = MagicMock()
    ws.send_json = AsyncMock()
    ws.send_bytes = AsyncMock()
    ws.close = AsyncMock()
    return ws


@pytest.fixture
def conn_mgr() -> ConnectionManager:
    return ConnectionManager()


def test_register_connection(conn_mgr: ConnectionManager, mock_ws: MagicMock):
    member_id = uuid.uuid4()
    conn_mgr.register(member_id, mock_ws, MemberRole.OBSERVER)
    assert member_id in conn_mgr.connections


def test_unregister_connection(conn_mgr: ConnectionManager, mock_ws: MagicMock):
    member_id = uuid.uuid4()
    conn_mgr.register(member_id, mock_ws, MemberRole.OBSERVER)
    conn_mgr.unregister(member_id)
    assert member_id not in conn_mgr.connections


async def test_send_to_member(conn_mgr: ConnectionManager, mock_ws: MagicMock):
    member_id = uuid.uuid4()
    conn_mgr.register(member_id, mock_ws, MemberRole.OBSERVER)
    await conn_mgr.send_to(member_id, {"type": "test"})
    mock_ws.send_json.assert_called_once_with({"type": "test"})


async def test_broadcast_all(conn_mgr: ConnectionManager):
    ws1 = MagicMock(send_json=AsyncMock())
    ws2 = MagicMock(send_json=AsyncMock())
    conn_mgr.register(uuid.uuid4(), ws1, MemberRole.OBSERVER)
    conn_mgr.register(uuid.uuid4(), ws2, MemberRole.SENSOR)
    await conn_mgr.broadcast({"type": "status", "members": 2})
    ws1.send_json.assert_called_once()
    ws2.send_json.assert_called_once()


async def test_broadcast_by_role(conn_mgr: ConnectionManager):
    ws_obs = MagicMock(send_json=AsyncMock())
    ws_sen = MagicMock(send_json=AsyncMock())
    ws_coord = MagicMock(send_json=AsyncMock())
    conn_mgr.register(uuid.uuid4(), ws_obs, MemberRole.OBSERVER)
    conn_mgr.register(uuid.uuid4(), ws_sen, MemberRole.SENSOR)
    conn_mgr.register(uuid.uuid4(), ws_coord, MemberRole.COORDINATOR)
    await conn_mgr.broadcast_to_role(
        MemberRole.COORDINATOR, {"type": "event", "text": "test"}
    )
    ws_obs.send_json.assert_not_called()
    ws_sen.send_json.assert_not_called()
    ws_coord.send_json.assert_called_once()


async def test_broadcast_alert_filters_by_severity(conn_mgr: ConnectionManager):
    ws_obs = MagicMock(send_json=AsyncMock())
    ws_sen = MagicMock(send_json=AsyncMock())
    conn_mgr.register(uuid.uuid4(), ws_obs, MemberRole.OBSERVER)
    conn_mgr.register(uuid.uuid4(), ws_sen, MemberRole.SENSOR)
    # Advisory should go to sensors but not observers
    await conn_mgr.broadcast_alert(
        {"type": "alert", "severity": "advisory", "text": "test"}
    )
    ws_sen.send_json.assert_called_once()
    ws_obs.send_json.assert_not_called()


async def test_broadcast_alert_critical_reaches_all(conn_mgr: ConnectionManager):
    ws_obs = MagicMock(send_json=AsyncMock())
    ws_sen = MagicMock(send_json=AsyncMock())
    conn_mgr.register(uuid.uuid4(), ws_obs, MemberRole.OBSERVER)
    conn_mgr.register(uuid.uuid4(), ws_sen, MemberRole.SENSOR)
    await conn_mgr.broadcast_alert(
        {"type": "alert", "severity": "critical", "text": "danger"}
    )
    ws_obs.send_json.assert_called_once()
    ws_sen.send_json.assert_called_once()


def test_update_role(conn_mgr: ConnectionManager, mock_ws: MagicMock):
    member_id = uuid.uuid4()
    conn_mgr.register(member_id, mock_ws, MemberRole.OBSERVER)
    conn_mgr.update_role(member_id, MemberRole.SENSOR)
    assert conn_mgr.roles[member_id] == MemberRole.SENSOR


async def test_disconnect_member(conn_mgr: ConnectionManager, mock_ws: MagicMock):
    member_id = uuid.uuid4()
    conn_mgr.register(member_id, mock_ws, MemberRole.OBSERVER)
    await conn_mgr.disconnect(member_id)
    mock_ws.close.assert_called_once()
    assert member_id not in conn_mgr.connections


def test_connected_count(conn_mgr: ConnectionManager):
    conn_mgr.register(uuid.uuid4(), MagicMock(), MemberRole.OBSERVER)
    conn_mgr.register(uuid.uuid4(), MagicMock(), MemberRole.SENSOR)
    assert conn_mgr.connected_count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_connection_manager.py -v`
Expected: ImportError

- [ ] **Step 3: Implement ConnectionManager**

```python
# src/osk/connection_manager.py
"""WebSocket connection management with role-based broadcasting."""
from __future__ import annotations

import logging
import uuid

from osk.models import EventSeverity, MemberRole

logger = logging.getLogger(__name__)

# Minimum severity level for each role to receive alerts
ALERT_THRESHOLDS: dict[MemberRole, int] = {
    MemberRole.COORDINATOR: EventSeverity.INFO.level,
    MemberRole.SENSOR: EventSeverity.ADVISORY.level,
    MemberRole.OBSERVER: EventSeverity.CRITICAL.level,
}


class ConnectionManager:
    def __init__(self) -> None:
        self.connections: dict[uuid.UUID, object] = {}
        self.roles: dict[uuid.UUID, MemberRole] = {}

    def register(
        self, member_id: uuid.UUID, websocket, role: MemberRole
    ) -> None:
        self.connections[member_id] = websocket
        self.roles[member_id] = role
        logger.info("Registered connection: %s (role=%s)", member_id, role.value)

    def unregister(self, member_id: uuid.UUID) -> None:
        self.connections.pop(member_id, None)
        self.roles.pop(member_id, None)

    def update_role(self, member_id: uuid.UUID, role: MemberRole) -> None:
        self.roles[member_id] = role

    @property
    def connected_count(self) -> int:
        return len(self.connections)

    async def send_to(self, member_id: uuid.UUID, message: dict) -> None:
        ws = self.connections.get(member_id)
        if ws:
            try:
                await ws.send_json(message)
            except Exception:
                logger.warning("Failed to send to %s", member_id)
                self.unregister(member_id)

    async def broadcast(self, message: dict) -> None:
        dead = []
        for member_id, ws in self.connections.items():
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(member_id)
        for mid in dead:
            self.unregister(mid)

    async def broadcast_to_role(
        self, role: MemberRole, message: dict
    ) -> None:
        dead = []
        for member_id, ws in self.connections.items():
            if self.roles.get(member_id) == role:
                try:
                    await ws.send_json(message)
                except Exception:
                    dead.append(member_id)
        for mid in dead:
            self.unregister(mid)

    async def broadcast_alert(self, alert_message: dict) -> None:
        severity_str = alert_message.get("severity", "info")
        severity_level = EventSeverity(severity_str).level
        dead = []
        for member_id, ws in self.connections.items():
            role = self.roles.get(member_id, MemberRole.OBSERVER)
            threshold = ALERT_THRESHOLDS.get(role, EventSeverity.CRITICAL.level)
            if severity_level >= threshold:
                try:
                    await ws.send_json(alert_message)
                except Exception:
                    dead.append(member_id)
        for mid in dead:
            self.unregister(mid)

    async def disconnect(self, member_id: uuid.UUID) -> None:
        ws = self.connections.get(member_id)
        if ws:
            try:
                await ws.close()
            except Exception:
                pass
            self.unregister(member_id)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_connection_manager.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/osk/connection_manager.py tests/test_connection_manager.py
git commit -m "feat: WebSocket connection manager with role-based alert filtering"
```

---

### Task 10: FastAPI Server + REST Endpoints + WebSocket Handler

**Files:**
- Create: `src/osk/server.py`
- Create: `tests/test_server.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_server.py
"""Tests for FastAPI server — uses httpx test client."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from osk.server import create_app
from osk.models import MemberRole, Operation


@pytest.fixture
def operation() -> Operation:
    return Operation(name="Test Op")


@pytest.fixture
def mock_op_manager(operation: Operation) -> MagicMock:
    mgr = MagicMock()
    mgr.operation = operation
    mgr.validate_token = MagicMock(return_value=True)
    mgr.add_member = AsyncMock(return_value=MagicMock(
        id=uuid.uuid4(),
        name="Jay",
        role=MemberRole.OBSERVER,
        model_dump=MagicMock(return_value={"id": str(uuid.uuid4()), "name": "Jay"}),
    ))
    mgr.promote_member = AsyncMock()
    mgr.demote_member = AsyncMock()
    mgr.kick_member = AsyncMock()
    mgr.rotate_token = AsyncMock(return_value="new-token")
    mgr.get_member_list = MagicMock(return_value=[])
    mgr.get_sensor_count = MagicMock(return_value=0)
    mgr.members = {}
    return mgr


@pytest.fixture
def mock_conn_mgr() -> MagicMock:
    mgr = MagicMock()
    mgr.broadcast = AsyncMock()
    mgr.broadcast_alert = AsyncMock()
    mgr.disconnect = AsyncMock()
    mgr.connected_count = 0
    return mgr


@pytest.fixture
def app(mock_op_manager: MagicMock, mock_conn_mgr: MagicMock, mock_db: MagicMock):
    return create_app(
        op_manager=mock_op_manager,
        conn_manager=mock_conn_mgr,
        db=mock_db,
    )


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)


def test_join_page_valid_token(client: TestClient, mock_op_manager: MagicMock):
    mock_op_manager.validate_token.return_value = True
    resp = client.get("/join?token=valid-token")
    assert resp.status_code == 200


def test_join_page_invalid_token(client: TestClient, mock_op_manager: MagicMock):
    mock_op_manager.validate_token.return_value = False
    resp = client.get("/join?token=bad-token")
    assert resp.status_code == 403


def test_operation_status(client: TestClient, mock_op_manager: MagicMock):
    resp = client.get("/api/operation/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Test Op"


def test_list_members(client: TestClient):
    resp = client.get("/api/members")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_promote_member(client: TestClient, mock_op_manager: MagicMock):
    member_id = uuid.uuid4()
    mock_op_manager.members = {member_id: MagicMock(role=MemberRole.OBSERVER)}
    resp = client.post(f"/api/members/{member_id}/promote")
    assert resp.status_code == 200
    mock_op_manager.promote_member.assert_called_once()


def test_demote_member(client: TestClient, mock_op_manager: MagicMock):
    member_id = uuid.uuid4()
    mock_op_manager.members = {member_id: MagicMock(role=MemberRole.SENSOR)}
    resp = client.post(f"/api/members/{member_id}/demote")
    assert resp.status_code == 200


def test_kick_member(client: TestClient, mock_op_manager: MagicMock, mock_conn_mgr: MagicMock):
    member_id = uuid.uuid4()
    mock_op_manager.members = {member_id: MagicMock()}
    resp = client.post(f"/api/members/{member_id}/kick")
    assert resp.status_code == 200
    mock_op_manager.kick_member.assert_called_once()
    mock_conn_mgr.disconnect.assert_called_once()


def test_rotate_token(client: TestClient, mock_op_manager: MagicMock):
    resp = client.post("/api/rotate-token")
    assert resp.status_code == 200
    assert resp.json()["token"] == "new-token"


def test_pin_event(client: TestClient, mock_db: MagicMock):
    event_id = uuid.uuid4()
    resp = client.post(
        f"/api/pin/{event_id}",
        json={"member_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 200


def test_report(client: TestClient, mock_db: MagicMock):
    resp = client.post(
        "/api/report",
        json={"member_id": str(uuid.uuid4()), "text": "Suspicious activity"},
    )
    assert resp.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_server.py -v`
Expected: ImportError

- [ ] **Step 3: Implement server**

```python
# src/osk/server.py
"""FastAPI application with REST endpoints and WebSocket handler."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from osk.connection_manager import ConnectionManager
from osk.models import (
    Event,
    EventCategory,
    EventSeverity,
    MemberRole,
    Pin,
)
from osk.operation import OperationManager

logger = logging.getLogger(__name__)


class ReportRequest(BaseModel):
    member_id: str
    text: str


class PinRequest(BaseModel):
    member_id: str


def create_app(
    op_manager: OperationManager,
    conn_manager: ConnectionManager,
    db,
) -> FastAPI:
    app = FastAPI(title="Osk Hub", docs_url=None, redoc_url=None)

    # --- Join page ---

    @app.get("/join")
    async def join_page(token: str = Query(...)):
        if not op_manager.validate_token(token):
            return JSONResponse({"error": "Invalid token"}, status_code=403)
        return HTMLResponse(
            f"<html><body><h1>Osk</h1><p>Join: {op_manager.operation.name}</p>"
            f"<script>sessionStorage.setItem('osk_token','{token}');</script>"
            f"</body></html>"
        )

    # --- Operation ---

    @app.get("/api/operation/status")
    async def operation_status():
        op = op_manager.operation
        return {
            "name": op.name,
            "id": str(op.id),
            "started_at": op.started_at.isoformat(),
            "members": len(op_manager.members),
            "sensors": op_manager.get_sensor_count(),
            "connected": conn_manager.connected_count,
        }

    # --- Members ---

    @app.get("/api/members")
    async def list_members():
        return op_manager.get_member_list()

    @app.post("/api/members/{member_id}/promote")
    async def promote_member(member_id: uuid.UUID):
        if member_id not in op_manager.members:
            return JSONResponse({"error": "Member not found"}, status_code=404)
        await op_manager.promote_member(member_id)
        conn_manager.update_role(member_id, MemberRole.SENSOR)
        await conn_manager.send_to(
            member_id, {"type": "role_change", "role": "sensor"}
        )
        return {"status": "promoted"}

    @app.post("/api/members/{member_id}/demote")
    async def demote_member(member_id: uuid.UUID):
        if member_id not in op_manager.members:
            return JSONResponse({"error": "Member not found"}, status_code=404)
        await op_manager.demote_member(member_id)
        conn_manager.update_role(member_id, MemberRole.OBSERVER)
        await conn_manager.send_to(
            member_id, {"type": "role_change", "role": "observer"}
        )
        return {"status": "demoted"}

    @app.post("/api/members/{member_id}/kick")
    async def kick_member(member_id: uuid.UUID):
        if member_id not in op_manager.members:
            return JSONResponse({"error": "Member not found"}, status_code=404)
        await op_manager.kick_member(member_id)
        await conn_manager.disconnect(member_id)
        return {"status": "kicked"}

    # --- Token rotation ---

    @app.post("/api/rotate-token")
    async def rotate_token():
        new_token = await op_manager.rotate_token(op_manager.operation.id)
        return {"token": new_token}

    # --- Pins ---

    @app.post("/api/pin/{event_id}")
    async def pin_event(event_id: uuid.UUID, req: PinRequest):
        pin = Pin(event_id=event_id, pinned_by=uuid.UUID(req.member_id))
        await db.insert_pin(pin.id, pin.event_id, pin.pinned_by)
        return {"status": "pinned", "pin_id": str(pin.id)}

    # --- Reports ---

    @app.post("/api/report")
    async def submit_report(req: ReportRequest):
        event = Event(
            severity=EventSeverity.INFO,
            category=EventCategory.MANUAL_REPORT,
            text=req.text,
            source_member_id=uuid.UUID(req.member_id),
        )
        await db.insert_event(
            event.id,
            op_manager.operation.id,
            event.severity,
            event.category,
            event.text,
            event.source_member_id,
            None,
            None,
        )
        return {"status": "reported", "event_id": str(event.id)}

    # --- Emergency wipe ---

    @app.post("/api/wipe")
    async def trigger_wipe():
        await conn_manager.broadcast({"type": "wipe"})
        return {"status": "wipe_initiated"}

    # --- Events (coordinator) ---

    @app.get("/api/events")
    async def get_events(since: str = "1970-01-01T00:00:00Z"):
        events = await db.get_events_since(op_manager.operation.id, since)
        return events

    # --- SitRep (coordinator) ---

    @app.get("/api/sitrep/latest")
    async def get_latest_sitrep():
        sitrep = await db.get_latest_sitrep(op_manager.operation.id)
        return sitrep or {"text": "No situation reports yet", "trend": "stable"}

    # --- WebSocket ---

    @app.websocket("/ws")
    async def websocket_handler(ws: WebSocket):
        await ws.accept()
        member_id = None
        try:
            # First message must be auth
            raw = await ws.receive_json()
            if raw.get("type") != "auth":
                await ws.close(code=4001, reason="First message must be auth")
                return

            token = raw.get("token", "")
            name = raw.get("name", "Anonymous")

            if not op_manager.validate_token(token):
                await ws.close(code=4003, reason="Invalid token")
                return

            member = await op_manager.add_member(op_manager.operation.id, name)
            member_id = member.id
            conn_manager.register(member_id, ws, member.role)

            await ws.send_json({
                "type": "auth_ok",
                "member_id": str(member_id),
                "role": member.role.value,
            })

            # Message loop
            while True:
                msg = await ws.receive()
                if msg.get("type") == "websocket.disconnect":
                    break

                if "text" in msg:
                    data = json.loads(msg["text"])
                    msg_type = data.get("type")

                    if msg_type == "gps":
                        await op_manager.update_member_gps(
                            member_id, data["lat"], data["lon"]
                        )
                    elif msg_type == "report":
                        event = Event(
                            severity=EventSeverity.INFO,
                            category=EventCategory.MANUAL_REPORT,
                            text=data["text"],
                            source_member_id=member_id,
                        )
                        await db.insert_event(
                            event.id,
                            op_manager.operation.id,
                            event.severity,
                            event.category,
                            event.text,
                            event.source_member_id,
                            None,
                            None,
                        )
                    elif msg_type == "pong":
                        pass  # heartbeat response
                    elif msg_type == "audio_meta":
                        pass  # handled by intelligence pipeline (Plan 2)
                    elif msg_type == "frame_meta":
                        pass  # handled by intelligence pipeline (Plan 2)
                    elif msg_type == "clip_meta":
                        pass  # handled by intelligence pipeline (Plan 2)

                elif "bytes" in msg:
                    pass  # binary audio/frame data — handled by Plan 2

        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.error("WebSocket error for %s: %s", member_id, e)
        finally:
            if member_id:
                conn_manager.unregister(member_id)
                await op_manager.update_member_gps(member_id, 0, 0)  # clear
                logger.info("Member disconnected: %s", member_id)

    return app
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_server.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/osk/server.py tests/test_server.py
git commit -m "feat: FastAPI server with REST endpoints, WebSocket auth, member management"
```

---

### Task 11: CLI + Hub Orchestrator

**Files:**
- Create: `src/osk/cli.py`
- Create: `src/osk/hub.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_cli.py
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from osk.cli import parse_args


def test_parse_start():
    args = parse_args(["start", "My Operation"])
    assert args.command == "start"
    assert args.name == "My Operation"


def test_parse_stop():
    args = parse_args(["stop"])
    assert args.command == "stop"


def test_parse_install():
    args = parse_args(["install"])
    assert args.command == "install"


def test_parse_config():
    args = parse_args(["config", "--set", "max_sensors=5"])
    assert args.command == "config"
    assert args.set == "max_sensors=5"


def test_parse_evidence_unlock():
    args = parse_args(["evidence", "unlock"])
    assert args.command == "evidence"
    assert args.evidence_command == "unlock"


def test_parse_evidence_export():
    args = parse_args(["evidence", "export"])
    assert args.evidence_command == "export"


def test_parse_evidence_destroy():
    args = parse_args(["evidence", "destroy"])
    assert args.evidence_command == "destroy"


def test_parse_rotate_token():
    args = parse_args(["rotate-token"])
    assert args.command == "rotate-token"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli.py -v`
Expected: ImportError

- [ ] **Step 3: Implement CLI**

```python
# src/osk/cli.py
"""CLI entry point for Osk."""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="osk",
        description="Osk — Civilian situational awareness platform",
    )
    sub = parser.add_subparsers(dest="command")

    # osk install
    sub.add_parser("install", help="Install Osk (pull containers, download models)")

    # osk start <name>
    start_p = sub.add_parser("start", help="Start an operation")
    start_p.add_argument("name", help="Operation name")

    # osk stop
    sub.add_parser("stop", help="Stop the current operation")

    # osk config
    config_p = sub.add_parser("config", help="View or set configuration")
    config_p.add_argument("--set", help="Set a config value (key=value)")

    # osk rotate-token
    sub.add_parser("rotate-token", help="Rotate the operation token")

    # osk evidence <subcommand>
    ev_p = sub.add_parser("evidence", help="Manage pinned evidence")
    ev_sub = ev_p.add_subparsers(dest="evidence_command")
    ev_sub.add_parser("unlock", help="Unlock and view pinned evidence")
    ev_sub.add_parser("export", help="Export pinned evidence as zip")
    ev_sub.add_parser("destroy", help="Permanently destroy evidence volume")

    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.command is None:
        parse_args(["--help"])
        return

    if args.command == "start":
        from osk.hub import run_hub
        asyncio.run(run_hub(args.name))
    elif args.command == "stop":
        print("Stop not yet implemented (send SIGINT to running hub)")
    elif args.command == "install":
        from osk.hub import install
        install()
    elif args.command == "config":
        from osk.config import load_config, save_config, OskConfig
        cfg = load_config()
        if args.set:
            key, _, value = args.set.partition("=")
            data = cfg.model_dump()
            # coerce type from existing field
            field_type = type(data.get(key, value))
            data[key] = field_type(value)
            cfg = OskConfig(**data)
            save_config(cfg)
            print(f"Set {key} = {value}")
        else:
            for k, v in cfg.model_dump().items():
                print(f"  {k} = {v}")
    elif args.command == "rotate-token":
        print("Token rotation requires a running hub (use dashboard or API)")
    elif args.command == "evidence":
        if args.evidence_command == "unlock":
            print("Evidence unlock not yet implemented")
        elif args.evidence_command == "export":
            print("Evidence export not yet implemented")
        elif args.evidence_command == "destroy":
            print("Evidence destroy not yet implemented")
```

- [ ] **Step 4: Implement hub orchestrator (stub)**

```python
# src/osk/hub.py
"""Hub orchestrator — starts and stops all Osk subsystems."""
from __future__ import annotations

import getpass
import logging
import signal
import subprocess
import sys
from pathlib import Path

import uvicorn

from osk.config import load_config
from osk.connection_manager import ConnectionManager
from osk.db import Database
from osk.operation import OperationManager
from osk.qr import build_join_url, generate_qr_ascii, generate_qr_png
from osk.server import create_app
from osk.storage import StorageManager
from osk.tls import generate_self_signed_cert

logger = logging.getLogger(__name__)


def install() -> None:
    """One-time install: pull containers, download models, generate TLS cert, create LUKS volume."""
    config = load_config()
    cert_path = Path(config.tls_cert_path)
    key_path = Path(config.tls_key_path)

    print("=== Osk Install ===")

    # TLS cert
    print("Generating TLS certificate...")
    generate_self_signed_cert(cert_path, key_path)
    print(f"  Certificate: {cert_path}")

    # LUKS volume
    passphrase = getpass.getpass("Set evidence encryption passphrase: ")
    passphrase_confirm = getpass.getpass("Confirm passphrase: ")
    if passphrase != passphrase_confirm:
        print("Passphrases do not match. Aborting.")
        sys.exit(1)

    storage = StorageManager(
        tmpfs_path=Path("/tmp/osk-tmpfs"),
        luks_image_path=Path.home() / ".config" / "osk" / "evidence.luks",
        luks_mount_path=Path("/tmp/osk-evidence"),
        luks_size_gb=config.luks_volume_size_gb,
    )
    print("Creating encrypted evidence volume...")
    storage.create_luks_volume(passphrase)

    # Docker images
    print("Pulling container images...")
    subprocess.run(["docker", "compose", "pull"], check=False, cwd=Path(__file__).parent.parent.parent)

    print("\n=== Install complete ===")
    print("Run: osk start \"Operation Name\"")


async def run_hub(name: str) -> None:
    """Start the hub and run until interrupted."""
    config = load_config()

    # Storage
    storage = StorageManager(
        tmpfs_path=Path("/tmp/osk-tmpfs"),
        luks_image_path=Path.home() / ".config" / "osk" / "evidence.luks",
        luks_mount_path=Path("/tmp/osk-evidence"),
        luks_size_gb=config.luks_volume_size_gb,
    )

    passphrase = getpass.getpass("Operation passphrase: ")

    print("Mounting ephemeral storage...")
    storage.mount_tmpfs()

    print("Opening encrypted evidence volume...")
    storage.open_luks(passphrase)

    # Database
    db = Database()
    db_url = f"postgresql://osk:osk@localhost:5432/osk"
    print("Connecting to database...")
    await db.connect(db_url)

    # Operation
    op_manager = OperationManager(db=db)
    operation = await op_manager.create(name)

    # Connection manager
    conn_manager = ConnectionManager()

    # QR code
    join_url = build_join_url("0.0.0.0", config.hub_port, operation.token)
    print("\n" + generate_qr_ascii(join_url))
    print(f"\nOperation: {name}")
    print(f"Join URL: {join_url}")
    print(f"Members scan the QR code above to join.\n")

    qr_path = Path.home() / ".config" / "osk" / "join-qr.png"
    generate_qr_png(join_url, qr_path)

    # FastAPI app
    app = create_app(
        op_manager=op_manager,
        conn_manager=conn_manager,
        db=db,
    )

    # Signal handling
    def shutdown_handler(sig, frame):
        logger.info("Shutdown signal received")

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    # Run server
    cert_path = config.tls_cert_path
    key_path = config.tls_key_path
    uvicorn_config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=config.hub_port,
        ssl_certfile=cert_path,
        ssl_keyfile=key_path,
        log_level="info",
    )
    server = uvicorn.Server(uvicorn_config)

    try:
        await server.serve()
    finally:
        print("\nShutting down...")
        await conn_manager.broadcast({"type": "op_ended"})
        await db.close()
        storage.revoke_keyring()
        storage.close_luks()
        storage.unmount_tmpfs()
        print("Operation ended.")
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_cli.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add src/osk/cli.py src/osk/hub.py tests/test_cli.py
git commit -m "feat: CLI with start/stop/install/config/evidence commands and hub orchestrator"
```

---

### Task 12: Docker Stack

**Files:**
- Create: `compose.yml`
- Create: `Dockerfile`

- [ ] **Step 1: Create compose.yml**

```yaml
# compose.yml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: osk
      POSTGRES_PASSWORD: osk
      POSTGRES_DB: osk
    # NOTE: In production, PostgreSQL data dir will be on tmpfs.
    # For development, use a named volume.
    volumes:
      - osk-postgres:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U osk"]
      interval: 5s
      timeout: 3s
      retries: 5

  ollama:
    image: ollama/ollama:latest
    volumes:
      - osk-ollama:/root/.ollama
    ports:
      - "11434:11434"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    healthcheck:
      test: ["CMD-SHELL", "ollama list || true"]
      interval: 10s
      timeout: 5s
      retries: 3

  ollama-init:
    image: ollama/ollama:latest
    depends_on:
      ollama:
        condition: service_healthy
    entrypoint: ["/bin/sh", "-c"]
    command:
      - |
        ollama pull mistral
        ollama pull llama3.2-vision:11b-instruct-q4_K_M
        ollama pull nomic-embed-text
    environment:
      OLLAMA_HOST: http://ollama:11434

volumes:
  osk-postgres:
  osk-ollama:
```

- [ ] **Step 2: Create Dockerfile**

```dockerfile
# Dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir .

EXPOSE 8443

CMD ["python", "-m", "osk", "start", "default"]
```

- [ ] **Step 3: Commit**

```bash
git add compose.yml Dockerfile
git commit -m "feat: Docker compose stack with PostgreSQL, Ollama, and Osk hub"
```

---

### Task 13: Run Full Test Suite + Push

- [ ] **Step 1: Run all tests**

Run: `pytest tests/ -v --tb=short`
Expected: all PASS

- [ ] **Step 2: Run ruff**

Run: `ruff check src/ tests/ --fix && ruff format src/ tests/`
Expected: clean

- [ ] **Step 3: Commit any lint fixes**

```bash
git add -A
git commit -m "style: lint and format fixes"
```

- [ ] **Step 4: Push to GitHub**

```bash
git push origin main
```
