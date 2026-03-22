CREATE TABLE IF NOT EXISTS intelligence_observations (
    id UUID PRIMARY KEY,
    operation_id UUID NOT NULL REFERENCES operations(id),
    source_member_id UUID NOT NULL REFERENCES members(id),
    kind TEXT NOT NULL,
    summary TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_intelligence_observations_operation_created
    ON intelligence_observations(operation_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_intelligence_observations_member
    ON intelligence_observations(source_member_id, created_at DESC);
