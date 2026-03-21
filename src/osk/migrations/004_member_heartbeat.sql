ALTER TABLE members
ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ;

UPDATE members
SET last_seen_at = COALESCE(last_gps_at, connected_at, NOW())
WHERE last_seen_at IS NULL;

ALTER TABLE members
ALTER COLUMN last_seen_at SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_members_last_seen
ON members (operation_id, last_seen_at DESC);
