CREATE TABLE IF NOT EXISTS synthesis_findings (
    id UUID PRIMARY KEY,
    operation_id UUID NOT NULL REFERENCES operations(id),
    signature TEXT NOT NULL,
    category TEXT NOT NULL,
    severity TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    corroborated BOOLEAN NOT NULL DEFAULT FALSE,
    source_count INTEGER NOT NULL DEFAULT 1,
    signal_count INTEGER NOT NULL DEFAULT 1,
    observation_count INTEGER NOT NULL DEFAULT 1,
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    latest_observation_id UUID NULL REFERENCES intelligence_observations(id),
    latest_event_id UUID NULL REFERENCES events(id),
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (operation_id, signature)
);

CREATE INDEX IF NOT EXISTS idx_synthesis_findings_operation_recent
    ON synthesis_findings(operation_id, last_seen_at DESC, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_synthesis_findings_operation_status
    ON synthesis_findings(operation_id, status, severity);
