CREATE EXTENSION IF NOT EXISTS pgcrypto;

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
