-- Migration 010: Observation correlation and grouping
-- Release: 1.3.0

-- Track observation groups for multimodal fusion
CREATE TABLE IF NOT EXISTS observation_groups (
    id UUID PRIMARY KEY,
    operation_id UUID NOT NULL REFERENCES operations(id) ON DELETE CASCADE,
    
    -- Group characteristics
    category VARCHAR(32) NOT NULL,
    primary_location_lat DOUBLE PRECISION,
    primary_location_lon DOUBLE PRECISION,
    location_radius_meters INTEGER DEFAULT 50,
    
    -- Temporal bounds
    first_observed_at TIMESTAMP WITH TIME ZONE NOT NULL,
    last_observed_at TIMESTAMP WITH TIME ZONE NOT NULL,
    
    -- Fusion metadata
    source_types TEXT[] NOT NULL DEFAULT '{}',  -- ['audio', 'vision', 'manual', 'location']
    member_count INTEGER NOT NULL DEFAULT 1,
    observation_count INTEGER NOT NULL DEFAULT 1,
    
    -- Correlation quality
    diversity_score DOUBLE PRECISION DEFAULT 0.0,
    correlation_strength DOUBLE PRECISION DEFAULT 0.0,
    
    -- State
    status VARCHAR(32) DEFAULT 'active' 
        CHECK (status IN ('active', 'resolved', 'consolidated')),
    
    -- Consolidation tracking
    consolidated_into UUID REFERENCES observation_groups(id),
    
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_obs_groups_operation ON observation_groups(operation_id);
CREATE INDEX idx_obs_groups_category ON observation_groups(category);
CREATE INDEX idx_obs_groups_status ON observation_groups(status);
CREATE INDEX idx_obs_groups_time ON observation_groups(first_observed_at, last_observed_at);
CREATE INDEX idx_obs_groups_diversity ON observation_groups(diversity_score);

-- GiST index for spatial queries if PostGIS available, otherwise B-tree on lat/lon
CREATE INDEX idx_obs_groups_location ON observation_groups(primary_location_lat, primary_location_lon);

-- Link individual observations to groups
CREATE TABLE IF NOT EXISTS observation_group_members (
    group_id UUID NOT NULL REFERENCES observation_groups(id) ON DELETE CASCADE,
    event_id UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    
    -- How this observation relates to the group
    correlation_type VARCHAR(32) NOT NULL 
        CHECK (correlation_type IN ('primary', 'corroborating', 'duplicate', 'related')),
    
    -- Individual contribution scores
    spatial_correlation DOUBLE PRECISION DEFAULT 0.0,
    temporal_correlation DOUBLE PRECISION DEFAULT 0.0,
    semantic_correlation DOUBLE PRECISION DEFAULT 0.0,
    overall_correlation DOUBLE PRECISION DEFAULT 0.0,
    
    added_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    PRIMARY KEY (group_id, event_id)
);

CREATE INDEX idx_ogm_group ON observation_group_members(group_id);
CREATE INDEX idx_ogm_event ON observation_group_members(event_id);
CREATE INDEX idx_ogm_member ON observation_group_members(member_id);
CREATE INDEX idx_ogm_correlation ON observation_group_members(correlation_type);

-- Trigger to update observation_groups counts
CREATE OR REPLACE FUNCTION update_observation_group_stats()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE observation_groups
        SET observation_count = observation_count + 1,
            member_count = (
                SELECT COUNT(DISTINCT member_id) 
                FROM observation_group_members 
                WHERE group_id = NEW.group_id
            ),
            updated_at = NOW()
        WHERE id = NEW.group_id;
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE observation_groups
        SET observation_count = observation_count - 1,
            member_count = (
                SELECT COUNT(DISTINCT member_id) 
                FROM observation_group_members 
                WHERE group_id = OLD.group_id
            ),
            updated_at = NOW()
        WHERE id = OLD.group_id;
        RETURN OLD;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER observation_group_stats_trigger
    AFTER INSERT OR DELETE ON observation_group_members
    FOR EACH ROW
    EXECUTE FUNCTION update_observation_group_stats();

COMMENT ON TABLE observation_groups IS 'Groups of correlated observations for multimodal fusion';
COMMENT ON TABLE observation_group_members IS 'Links events to their observation groups with correlation metadata';
