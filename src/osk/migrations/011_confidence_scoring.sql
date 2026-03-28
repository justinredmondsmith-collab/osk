-- Migration 011: Confidence scoring and source attribution
-- Release: 1.3.0

CREATE TABLE IF NOT EXISTS event_confidence_scores (
    event_id UUID PRIMARY KEY REFERENCES events(id) ON DELETE CASCADE,
    operation_id UUID NOT NULL REFERENCES operations(id) ON DELETE CASCADE,
    group_id UUID REFERENCES observation_groups(id) ON DELETE SET NULL,
    
    -- Overall confidence (0.0 - 1.0)
    confidence_score DOUBLE PRECISION NOT NULL 
        CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
    confidence_tier VARCHAR(16) NOT NULL 
        CHECK (confidence_tier IN ('low', 'medium', 'high', 'certain')),
    
    -- Component scores
    source_reliability DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    temporal_consistency DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    spatial_consistency DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    cross_source_corroboration DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    observation_diversity DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    
    -- Attribution
    primary_source_type VARCHAR(32),  -- audio, vision, manual, location
    contributing_sources TEXT[] NOT NULL DEFAULT '{}',
    contributing_member_count INTEGER NOT NULL DEFAULT 1,
    
    -- Explanation (human-readable factors)
    confidence_factors TEXT[] NOT NULL DEFAULT '{}',
    
    -- Metadata
    calculation_method VARCHAR(32) DEFAULT 'weighted_average',
    calculated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    recalculation_reason VARCHAR(64),  -- Why score was recalculated
    
    -- Review tracking
    reviewed_by UUID,
    reviewed_at TIMESTAMP WITH TIME ZONE,
    review_notes TEXT,
    override_score DOUBLE PRECISION,  -- Manual override
    
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_confidence_operation ON event_confidence_scores(operation_id);
CREATE INDEX idx_confidence_score ON event_confidence_scores(confidence_score);
CREATE INDEX idx_confidence_tier ON event_confidence_scores(confidence_tier);
CREATE INDEX idx_confidence_group ON event_confidence_scores(group_id);
CREATE INDEX idx_confidence_calculated ON event_confidence_scores(calculated_at);

-- View for coordinator dashboard showing enriched events
CREATE OR REPLACE VIEW enriched_events AS
SELECT 
    e.id,
    e.operation_id,
    e.severity,
    e.category,
    e.text,
    e.source_member_id,
    e.timestamp as event_timestamp,
    e.created_at,
    
    -- Confidence scores
    COALESCE(ecs.confidence_score, 0.5) as confidence_score,
    COALESCE(ecs.confidence_tier, 'medium') as confidence_tier,
    ecs.primary_source_type,
    ecs.contributing_sources,
    ecs.contributing_member_count,
    ecs.confidence_factors,
    
    -- Group information
    og.id as group_id,
    og.observation_count as group_observation_count,
    og.member_count as group_member_count,
    og.diversity_score as group_diversity_score,
    og.primary_location_lat,
    og.primary_location_lon,
    og.first_observed_at as group_first_observed,
    og.last_observed_at as group_last_observed,
    
    -- Attribution summary
    CASE 
        WHEN ecs.contributing_member_count > 1 THEN 'corroborated'
        WHEN og.observation_count > 1 THEN 'grouped'
        ELSE 'single_source'
    END as attribution_type
    
FROM events e
LEFT JOIN event_confidence_scores ecs ON e.id = ecs.event_id
LEFT JOIN observation_groups og ON ecs.group_id = og.id;

-- Function to calculate confidence tier from score
CREATE OR REPLACE FUNCTION calculate_confidence_tier(score DOUBLE PRECISION)
RETURNS VARCHAR(16) AS $$
BEGIN
    IF score >= 0.9 THEN
        RETURN 'certain';
    ELSIF score >= 0.7 THEN
        RETURN 'high';
    ELSIF score >= 0.4 THEN
        RETURN 'medium';
    ELSE
        RETURN 'low';
    END IF;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Trigger to auto-update confidence tier
CREATE OR REPLACE FUNCTION update_confidence_tier()
RETURNS TRIGGER AS $$
BEGIN
    NEW.confidence_tier := calculate_confidence_tier(NEW.confidence_score);
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER confidence_tier_trigger
    BEFORE INSERT OR UPDATE ON event_confidence_scores
    FOR EACH ROW
    EXECUTE FUNCTION update_confidence_tier();

-- Table for fusion configuration (per operation)
CREATE TABLE IF NOT EXISTS fusion_config (
    operation_id UUID PRIMARY KEY REFERENCES operations(id) ON DELETE CASCADE,
    
    -- Correlation thresholds
    spatial_correlation_threshold DOUBLE PRECISION DEFAULT 0.7,
    temporal_correlation_threshold DOUBLE PRECISION DEFAULT 0.7,
    semantic_correlation_threshold DOUBLE PRECISION DEFAULT 0.8,
    
    -- Distance/time windows
    max_correlation_distance_meters INTEGER DEFAULT 100,
    max_correlation_gap_seconds INTEGER DEFAULT 300,  -- 5 minutes
    
    -- Confidence calculation weights
    source_reliability_weight DOUBLE PRECISION DEFAULT 0.3,
    temporal_weight DOUBLE PRECISION DEFAULT 0.2,
    spatial_weight DOUBLE PRECISION DEFAULT 0.2,
    corroboration_weight DOUBLE PRECISION DEFAULT 0.3,
    
    -- Duplicate detection
    duplicate_detection_enabled BOOLEAN DEFAULT true,
    duplicate_time_window_seconds INTEGER DEFAULT 60,
    
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Trigger to update fusion_config updated_at
CREATE TRIGGER fusion_config_updated_at
    BEFORE UPDATE ON fusion_config
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

COMMENT ON TABLE event_confidence_scores IS 'Confidence scores and source attribution for events';
COMMENT ON VIEW enriched_events IS 'Events enriched with confidence scores and group information';
COMMENT ON TABLE fusion_config IS 'Per-operation configuration for intelligence fusion';
