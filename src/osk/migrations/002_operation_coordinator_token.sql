ALTER TABLE operations
ADD COLUMN IF NOT EXISTS coordinator_token TEXT;

UPDATE operations
SET coordinator_token = token
WHERE coordinator_token IS NULL;

ALTER TABLE operations
ALTER COLUMN coordinator_token SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_operations_active
ON operations (stopped_at, started_at DESC);
