CREATE TABLE IF NOT EXISTS coordinator_gaps (
    id UUID PRIMARY KEY,
    operation_id UUID NOT NULL REFERENCES operations(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    severity TEXT NOT NULL,
    requested_route_key TEXT NULL,
    source_finding_id UUID NULL REFERENCES synthesis_findings(id) ON DELETE SET NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ NULL,
    cancelled_at TIMESTAMPTZ NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_coordinator_gaps_open_kind
    ON coordinator_gaps(operation_id, kind)
    WHERE status = 'open';

CREATE INDEX IF NOT EXISTS idx_coordinator_gaps_operation_status_updated
    ON coordinator_gaps(operation_id, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS coordinator_tasks (
    id UUID PRIMARY KEY,
    operation_id UUID NOT NULL REFERENCES operations(id) ON DELETE CASCADE,
    gap_id UUID NOT NULL REFERENCES coordinator_gaps(id) ON DELETE CASCADE,
    assigned_member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'open',
    prompt TEXT NOT NULL,
    assignment_reason TEXT NOT NULL,
    requested_route_key TEXT NULL,
    requested_location_label TEXT NULL,
    requested_viewpoint TEXT NULL,
    completion_event_id UUID NULL REFERENCES events(id) ON DELETE SET NULL,
    superseded_by_task_id UUID NULL REFERENCES coordinator_tasks(id) ON DELETE SET NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ NULL,
    cancelled_at TIMESTAMPTZ NULL
);

CREATE INDEX IF NOT EXISTS idx_coordinator_tasks_operation_member_status_updated
    ON coordinator_tasks(operation_id, assigned_member_id, status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_coordinator_tasks_operation_gap_status_updated
    ON coordinator_tasks(operation_id, gap_id, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS coordinator_recommendations (
    id UUID PRIMARY KEY,
    operation_id UUID NOT NULL REFERENCES operations(id) ON DELETE CASCADE,
    gap_id UUID NULL REFERENCES coordinator_gaps(id) ON DELETE SET NULL,
    route_key TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    rationale TEXT NOT NULL,
    supporting_task_id UUID NULL REFERENCES coordinator_tasks(id) ON DELETE SET NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    emitted_at TIMESTAMPTZ NULL,
    invalidated_at TIMESTAMPTZ NULL,
    invalidated_reason TEXT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_coordinator_recommendations_active
    ON coordinator_recommendations(operation_id)
    WHERE status = 'emitted';

CREATE INDEX IF NOT EXISTS idx_coordinator_recommendations_operation_status_updated
    ON coordinator_recommendations(operation_id, status, updated_at DESC);
