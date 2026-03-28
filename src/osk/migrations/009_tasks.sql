-- Migration 009: Task management system for coordinator-directed operations
-- Release: 1.2.0

CREATE TABLE IF NOT EXISTS tasks (
    id UUID PRIMARY KEY,
    operation_id UUID NOT NULL REFERENCES operations(id) ON DELETE CASCADE,
    assigner_id UUID NOT NULL,  -- Coordinator member ID who created task
    assignee_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    
    -- Task definition
    type VARCHAR(32) NOT NULL CHECK (type IN ('CONFIRMATION', 'CHECKPOINT', 'REPORT', 'CUSTOM')),
    title VARCHAR(200) NOT NULL,
    description TEXT,
    
    -- Optional geo-target
    target_lat DOUBLE PRECISION,
    target_lon DOUBLE PRECISION,
    target_radius_meters INTEGER DEFAULT 50,
    
    -- State machine
    state VARCHAR(32) NOT NULL DEFAULT 'PENDING' 
        CHECK (state IN ('PENDING', 'ASSIGNED', 'ACKNOWLEDGED', 'IN_PROGRESS', 'COMPLETED', 'TIMEOUT', 'CANCELLED')),
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    assigned_at TIMESTAMP WITH TIME ZONE,
    acknowledged_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    timeout_at TIMESTAMP WITH TIME ZONE NOT NULL,
    
    -- Outcome
    outcome VARCHAR(32) CHECK (outcome IN ('SUCCESS', 'FAILED', 'UNABLE', 'TIMEOUT', 'CANCELLED')),
    outcome_notes TEXT,
    
    -- Metadata
    priority INTEGER DEFAULT 1 CHECK (priority IN (1, 2, 3)),  -- 1=normal, 2=high, 3=urgent
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 0
);

-- Indexes for common query patterns
CREATE INDEX idx_tasks_operation ON tasks(operation_id);
CREATE INDEX idx_tasks_assignee ON tasks(assignee_id);
CREATE INDEX idx_tasks_state ON tasks(state);
CREATE INDEX idx_tasks_created_at ON tasks(created_at);

-- Composite index for active tasks by assignee (most common member query)
CREATE INDEX idx_tasks_active_by_assignee ON tasks(assignee_id, state, timeout_at) 
    WHERE state IN ('ASSIGNED', 'ACKNOWLEDGED', 'IN_PROGRESS');

-- Index for coordinator dashboard (all tasks by operation)
CREATE INDEX idx_tasks_operation_state ON tasks(operation_id, state, created_at DESC);

-- Index for timeout processing
CREATE INDEX idx_tasks_pending_timeouts ON tasks(state, timeout_at)
    WHERE state IN ('ASSIGNED', 'ACKNOWLEDGED', 'IN_PROGRESS');

-- Add comment for documentation
COMMENT ON TABLE tasks IS 'Coordinator-assigned tasks for field members';
COMMENT ON COLUMN tasks.state IS 'State machine: PENDING → ASSIGNED → ACKNOWLEDGED → IN_PROGRESS → COMPLETED|TIMEOUT|CANCELLED';
COMMENT ON COLUMN tasks.priority IS '1=normal, 2=high, 3=urgent';
