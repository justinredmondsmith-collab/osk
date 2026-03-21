ALTER TABLE members
ADD COLUMN IF NOT EXISTS reconnect_token TEXT;

UPDATE members
SET reconnect_token = gen_random_uuid()::text
WHERE reconnect_token IS NULL;

ALTER TABLE members
ALTER COLUMN reconnect_token SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_members_reconnect_token
ON members(reconnect_token);

CREATE TABLE IF NOT EXISTS audit_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    operation_id UUID NOT NULL REFERENCES operations(id),
    actor_member_id UUID REFERENCES members(id),
    actor_type TEXT NOT NULL,
    action TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_events_operation_timestamp
ON audit_events(operation_id, timestamp DESC);
