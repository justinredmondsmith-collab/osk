ALTER TABLE synthesis_findings
    ADD COLUMN IF NOT EXISTS status_updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS acknowledged_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS notes_count INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS synthesis_finding_notes (
    id UUID PRIMARY KEY,
    operation_id UUID NOT NULL REFERENCES operations(id),
    finding_id UUID NOT NULL REFERENCES synthesis_findings(id) ON DELETE CASCADE,
    author_type TEXT NOT NULL DEFAULT 'coordinator',
    text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_synthesis_finding_notes_finding_created
    ON synthesis_finding_notes(finding_id, created_at DESC);

CREATE TABLE IF NOT EXISTS ingest_receipts (
    operation_id UUID NOT NULL REFERENCES operations(id),
    kind TEXT NOT NULL,
    member_id UUID NOT NULL REFERENCES members(id),
    ingest_key TEXT NOT NULL,
    item_id UUID NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    duplicate_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (operation_id, kind, member_id, ingest_key)
);

CREATE INDEX IF NOT EXISTS idx_ingest_receipts_operation_last_seen
    ON ingest_receipts(operation_id, last_seen_at DESC);
