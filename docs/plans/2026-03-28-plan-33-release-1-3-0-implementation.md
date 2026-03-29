# Release 1.3.0 Implementation Plan

**Date:** 2026-03-28  
**Target Release:** 1.3.0 "Trustworthy Intelligence Fusion"  
**Estimated Duration:** 10 weeks  
**Status:** Planning → Implementation

---

## Executive Summary

Release 1.3.0 improves intelligence quality by fusing multimodal inputs (audio, vision, manual reports, location) into better, more reviewable events. The system will correlate observations across time and space, reduce duplicate reports, and provide confidence scores with source attribution.

This builds on the 1.2.0 task management foundation, providing better intelligence to inform coordinator decisions.

---

## Phase Overview

```
Week 1-2:   [DATA MODELS]      Event correlation, observation grouping, confidence scoring
Week 3-4:   [FUSION ENGINE]    Multimodal correlation algorithms, spatial/temporal reasoning
Week 5-6:   [COORDINATOR UI]   Source attribution, confidence display, explainability
Week 7-8:   [EVALUATION]       Baseline comparison, false-positive measurement
Week 9-10:  [RELEASE]          Documentation, configuration, release prep
```

---

## Workstream 1: Data Models (Weeks 1-2)

### 1.1 Database Schema & Migrations

**Files to Create:**
- `src/osk/migrations/010_observation_correlation.sql`
- `src/osk/migrations/011_confidence_scoring.sql`

**Implementation:**

```sql
-- 010_observation_correlation.sql
-- Track observation groups and correlations

CREATE TABLE IF NOT EXISTS observation_groups (
    id UUID PRIMARY KEY,
    operation_id UUID NOT NULL REFERENCES operations(id) ON DELETE CASCADE,
    
    -- Group characteristics
    category VARCHAR(32) NOT NULL,
    primary_location_lat DOUBLE PRECISION,
    primary_location_lon DOUBLE PRECISION,
    location_radius_meters INTEGER,
    
    -- Temporal bounds
    first_observed_at TIMESTAMP WITH TIME ZONE NOT NULL,
    last_observed_at TIMESTAMP WITH TIME ZONE NOT NULL,
    
    -- Fusion metadata
    source_types TEXT[] NOT NULL,  -- ['audio', 'vision', 'manual', 'location']
    member_count INTEGER NOT NULL DEFAULT 1,
    observation_count INTEGER NOT NULL DEFAULT 1,
    
    -- State
    status VARCHAR(32) DEFAULT 'active' 
        CHECK (status IN ('active', 'resolved', 'consolidated')),
    
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_obs_groups_operation ON observation_groups(operation_id);
CREATE INDEX idx_obs_groups_category ON observation_groups(category);
CREATE INDEX idx_obs_groups_location ON observation_groups 
    USING GIST (point(primary_location_lon, primary_location_lat));
CREATE INDEX idx_obs_groups_time ON observation_groups(first_observed_at, last_observed_at);

-- Link individual observations to groups
CREATE TABLE IF NOT EXISTS observation_group_members (
    group_id UUID NOT NULL REFERENCES observation_groups(id) ON DELETE CASCADE,
    event_id UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    
    -- How this observation relates to the group
    correlation_type VARCHAR(32) NOT NULL 
        CHECK (correlation_type IN ('primary', 'corroborating', 'duplicate', 'related')),
    
    -- Individual confidence contribution
    confidence_contribution DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    
    added_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    PRIMARY KEY (group_id, event_id)
);

CREATE INDEX idx_ogm_group ON observation_group_members(group_id);
CREATE INDEX idx_ogm_event ON observation_group_members(event_id);
```

```sql
-- 011_confidence_scoring.sql
-- Confidence scores and source attribution

CREATE TABLE IF NOT EXISTS event_confidence_scores (
    event_id UUID PRIMARY KEY REFERENCES events(id) ON DELETE CASCADE,
    operation_id UUID NOT NULL REFERENCES operations(id) ON DELETE CASCADE,
    
    -- Overall confidence
    confidence_score DOUBLE PRECISION NOT NULL CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
    confidence_tier VARCHAR(16) NOT NULL 
        CHECK (confidence_tier IN ('low', 'medium', 'high', 'certain')),
    
    -- Component scores
    source_reliability DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    temporal_consistency DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    spatial_consistency DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    cross_source_corroboration DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    
    -- Attribution
    primary_source_type VARCHAR(32),  -- audio, vision, manual, location
    contributing_sources TEXT[] NOT NULL DEFAULT '{}',
    
    -- Explanation
    confidence_factors TEXT[] NOT NULL DEFAULT '{}',
    
    calculated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_confidence_operation ON event_confidence_scores(operation_id);
CREATE INDEX idx_confidence_score ON event_confidence_scores(confidence_score);
CREATE INDEX idx_confidence_tier ON event_confidence_scores(confidence_tier);
```

### 1.2 Core Domain Models

**Files to Create/Modify:**
- `src/osk/intelligence_fusion.py` - New fusion domain models

**Implementation:**

```python
# src/osk/intelligence_fusion.py

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, List, Dict, Set
import uuid
import math


class CorrelationType(Enum):
    """How an observation relates to a group."""
    PRIMARY = "primary"           # First/most significant observation
    CORROBORATING = "corroborating"  # Supports primary
    DUPLICATE = "duplicate"       # Same observation, different source
    RELATED = "related"           # Connected but distinct


class ConfidenceTier(Enum):
    """Confidence score tiers for display."""
    LOW = "low"           # 0.0 - 0.4
    MEDIUM = "medium"     # 0.4 - 0.7
    HIGH = "high"         # 0.7 - 0.9
    CERTAIN = "certain"   # 0.9 - 1.0


@dataclass
class GeoPoint:
    """Geographic point with utility methods."""
    lat: float
    lon: float
    
    def distance_to(self, other: GeoPoint) -> float:
        """Calculate distance in meters using haversine formula."""
        R = 6371000  # Earth's radius in meters
        
        lat1, lon1 = math.radians(self.lat), math.radians(self.lon)
        lat2, lon2 = math.radians(other.lat), math.radians(other.lon)
        
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = (math.sin(dlat / 2) ** 2 + 
             math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        return R * c
    
    def is_within_radius(self, center: GeoPoint, radius_meters: float) -> bool:
        """Check if this point is within radius of center."""
        return self.distance_to(center) <= radius_meters


@dataclass
class ObservationWindow:
    """Time window for temporal analysis."""
    start: datetime
    end: datetime
    
    def duration_seconds(self) -> float:
        return (self.end - self.start).total_seconds()
    
    def contains(self, timestamp: datetime) -> bool:
        return self.start <= timestamp <= self.end
    
    def overlaps(self, other: ObservationWindow) -> bool:
        return (self.start <= other.end and other.start <= self.end)
    
    def gap_to(self, other: ObservationWindow) -> float:
        """Return gap in seconds between this window and another."""
        if self.overlaps(other):
            return 0.0
        if self.end < other.start:
            return (other.start - self.end).total_seconds()
        return (self.start - other.end).total_seconds()


@dataclass
class RawObservation:
    """Single raw observation before fusion."""
    event_id: uuid.UUID
    member_id: uuid.UUID
    operation_id: uuid.UUID
    
    # Content
    category: str
    text: str
    severity: str
    
    # Source
    source_type: str  # audio, vision, manual, location
    
    # Context
    location: Optional[GeoPoint] = None
    timestamp: datetime = field(default_factory=datetime.now)
    
    # Metadata
    audio_transcript: Optional[str] = None
    vision_description: Optional[str] = None


@dataclass
class ObservationGroup:
    """Group of correlated observations."""
    id: uuid.UUID
    operation_id: uuid.UUID
    
    # Characteristics
    category: str
    primary_location: Optional[GeoPoint] = None
    location_radius_meters: int = 50
    
    # Temporal bounds
    time_window: ObservationWindow = field(default_factory=lambda: ObservationWindow(
        start=datetime.now(),
        end=datetime.now()
    ))
    
    # Members
    observations: List[RawObservation] = field(default_factory=list)
    member_ids: Set[uuid.UUID] = field(default_factory=set)
    
    # Source diversity
    source_types: Set[str] = field(default_factory=set)
    
    # State
    status: str = "active"  # active, resolved, consolidated
    
    def add_observation(self, obs: RawObservation) -> None:
        """Add observation to group, updating bounds."""
        self.observations.append(obs)
        self.member_ids.add(obs.member_id)
        self.source_types.add(obs.source_type)
        
        # Update temporal bounds
        if obs.timestamp < self.time_window.start:
            self.time_window.start = obs.timestamp
        if obs.timestamp > self.time_window.end:
            self.time_window.end = obs.timestamp
        
        # Update location (centroid of all points)
        if obs.location:
            self._update_location(obs.location)
    
    def _update_location(self, new_point: GeoPoint) -> None:
        """Update primary location as centroid."""
        if not self.primary_location:
            self.primary_location = new_point
            return
        
        # Simple centroid calculation
        n = len(self.observations)
        if n > 1:
            self.primary_location = GeoPoint(
                lat=(self.primary_location.lat * (n - 1) + new_point.lat) / n,
                lon=(self.primary_location.lon * (n - 1) + new_point.lon) / n
            )
    
    def get_diversity_score(self) -> float:
        """Score 0-1 based on source type diversity."""
        if len(self.source_types) <= 1:
            return 0.0
        # More source types = higher diversity
        return min(1.0, (len(self.source_types) - 1) / 3.0)
    
    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "category": self.category,
            "location": {
                "lat": self.primary_location.lat if self.primary_location else None,
                "lon": self.primary_location.lon if self.primary_location else None,
                "radius_meters": self.location_radius_meters,
            } if self.primary_location else None,
            "time_window": {
                "start": self.time_window.start.isoformat(),
                "end": self.time_window.end.isoformat(),
            },
            "observation_count": len(self.observations),
            "member_count": len(self.member_ids),
            "source_types": list(self.source_types),
            "status": self.status,
            "diversity_score": self.get_diversity_score(),
        }


@dataclass
class ConfidenceScore:
    """Confidence scoring for fused events."""
    event_id: uuid.UUID
    operation_id: uuid.UUID
    
    # Overall score
    score: float = 0.5  # 0.0 - 1.0
    
    # Component scores
    source_reliability: float = 0.5
    temporal_consistency: float = 0.5
    spatial_consistency: float = 0.5
    cross_source_corroboration: float = 0.0
    
    # Attribution
    primary_source_type: Optional[str] = None
    contributing_sources: List[str] = field(default_factory=list)
    
    # Explanation
    confidence_factors: List[str] = field(default_factory=list)
    
    calculated_at: datetime = field(default_factory=datetime.now)
    
    @property
    def tier(self) -> ConfidenceTier:
        if self.score >= 0.9:
            return ConfidenceTier.CERTAIN
        if self.score >= 0.7:
            return ConfidenceTier.HIGH
        if self.score >= 0.4:
            return ConfidenceTier.MEDIUM
        return ConfidenceTier.LOW
    
    def calculate_overall(self) -> float:
        """Calculate overall confidence from components."""
        # Weighted average with cross-source bonus
        base_score = (
            self.source_reliability * 0.3 +
            self.temporal_consistency * 0.2 +
            self.spatial_consistency * 0.2 +
            self.cross_source_corroboration * 0.3
        )
        
        # Boost for multiple corroborating sources
        if len(self.contributing_sources) > 1:
            base_score = min(1.0, base_score * 1.1)
        
        self.score = base_score
        return base_score
    
    def add_confidence_factor(self, factor: str) -> None:
        """Add explanatory factor."""
        self.confidence_factors.append(factor)
    
    def to_dict(self) -> dict:
        return {
            "event_id": str(self.event_id),
            "score": round(self.score, 2),
            "tier": self.tier.value,
            "components": {
                "source_reliability": round(self.source_reliability, 2),
                "temporal_consistency": round(self.temporal_consistency, 2),
                "spatial_consistency": round(self.spatial_consistency, 2),
                "cross_source_corroboration": round(self.cross_source_corroboration, 2),
            },
            "attribution": {
                "primary_source": self.primary_source_type,
                "contributing_sources": self.contributing_sources,
            },
            "explanation": self.confidence_factors,
            "calculated_at": self.calculated_at.isoformat(),
        }


# Spatial and temporal analysis functions

def calculate_spatial_correlation(
    obs1: RawObservation,
    obs2: RawObservation,
    max_distance_meters: float = 100.0
) -> float:
    """Calculate spatial correlation score between two observations."""
    if not obs1.location or not obs2.location:
        return 0.5  # Neutral if no location data
    
    distance = obs1.location.distance_to(obs2.location)
    if distance <= max_distance_meters:
        # Linear falloff from 1.0 at 0m to 0.0 at max_distance
        return 1.0 - (distance / max_distance_meters)
    return 0.0


def calculate_temporal_correlation(
    obs1: RawObservation,
    obs2: RawObservation,
    max_gap_seconds: float = 300.0  # 5 minutes
) -> float:
    """Calculate temporal correlation score between two observations."""
    gap = abs((obs1.timestamp - obs2.timestamp).total_seconds())
    if gap <= max_gap_seconds:
        return 1.0 - (gap / max_gap_seconds)
    return 0.0


def calculate_category_correlation(
    obs1: RawObservation,
    obs2: RawObservation,
) -> float:
    """Calculate category/semantic correlation."""
    if obs1.category == obs2.category:
        return 1.0
    
    # Related categories could have partial correlation
    related_pairs = [
        ({"police_action", "blocked_route"}, 0.7),
        ({"medical", "casualty"}, 0.8),
        ({"fire", "smoke"}, 0.9),
    ]
    
    for pair, score in related_pairs:
        if obs1.category in pair and obs2.category in pair:
            return score
    
    return 0.0


def should_correlate(
    obs1: RawObservation,
    obs2: RawObservation,
    spatial_threshold: float = 0.7,
    temporal_threshold: float = 0.7,
    category_threshold: float = 0.8,
) -> bool:
    """Determine if two observations should be correlated."""
    spatial = calculate_spatial_correlation(obs1, obs2)
    temporal = calculate_temporal_correlation(obs1, obs2)
    category = calculate_category_correlation(obs1, obs2)
    
    # Require strong match in at least 2 dimensions
    matches = sum([
        spatial >= spatial_threshold,
        temporal >= temporal_threshold,
        category >= category_threshold,
    ])
    
    return matches >= 2


class FusionError(Exception):
    """Raised when intelligence fusion fails."""
    pass


class CorrelationError(Exception):
    """Raised when observation correlation fails."""
    pass
