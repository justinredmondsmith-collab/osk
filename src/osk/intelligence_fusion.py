"""Intelligence fusion domain models and correlation algorithms.

Release 1.3.0 - Trustworthy Intelligence Fusion
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import List, Dict, Optional, Set
import uuid
import math


@dataclass
class GeoPoint:
    """Geographic point with latitude and longitude."""
    lat: float
    lon: float
    
    def distance_to(self, other: GeoPoint) -> float:
        """Calculate distance in meters to another point."""
        # Simple Euclidean approximation (sufficient for local operations)
        lat_diff = (self.lat - other.lat) * 111000
        lon_diff = (self.lon - other.lon) * 111000 * math.cos(math.radians(self.lat))
        return math.sqrt(lat_diff**2 + lon_diff**2)


@dataclass
class RawObservation:
    """Raw observation from any source before fusion processing."""
    event_id: uuid.UUID
    member_id: uuid.UUID
    operation_id: uuid.UUID
    category: str
    text: str
    severity: str
    source_type: str  # 'audio', 'vision', 'location', 'manual'
    location: Optional[GeoPoint] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ConfidenceFactor:
    """Individual factor contributing to confidence score."""
    factor_type: str  # 'corroboration', 'source_quality', 'temporal_freshness', etc.
    weight: float  # 0-1, importance of this factor
    contribution: float  # 0-1, actual contribution after evaluation
    explanation: str


@dataclass
class ConfidenceScore:
    """Confidence score with breakdown of contributing factors."""
    overall: float  # 0-1 overall confidence
    factors: List[ConfidenceFactor]
    tier: str  # 'low', 'medium', 'high', 'certain'
    
    def __post_init__(self):
        if self.tier is None:
            self.tier = self._calculate_tier()
    
    def _calculate_tier(self) -> str:
        if self.overall >= 0.9:
            return "certain"
        elif self.overall >= 0.7:
            return "high"
        elif self.overall >= 0.4:
            return "medium"
        else:
            return "low"


@dataclass
class SourceAttribution:
    """Attribution information for contributing sources."""
    member_id: uuid.UUID
    source_type: str
    timestamp: datetime
    confidence_contribution: float


class CorrelationType(Enum):
    """Type of correlation between observations."""
    DUPLICATE = auto()  # Same event from same source
    CORROBORATING = auto()  # Same event from different sources
    RELATED = auto()  # Different but related events
    UNRELATED = auto()  # No correlation


@dataclass
class ObservationWindow:
    """Temporal window for correlation."""
    start: datetime
    end: datetime
    
    def duration_seconds(self) -> float:
        return (self.end - self.start).total_seconds()
    
    def contains(self, timestamp: datetime) -> bool:
        return self.start <= timestamp <= self.end


@dataclass
class ObservationGroup:
    """Group of correlated observations."""
    id: uuid.UUID
    operation_id: uuid.UUID
    primary_category: str
    observations: List[RawObservation] = field(default_factory=list)
    confidence: Optional[ConfidenceScore] = None
    spatial_bounds: Optional[Dict] = None
    temporal_span: Optional[ObservationWindow] = None
    source_attributions: List[SourceAttribution] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def add_observation(self, obs: RawObservation) -> None:
        """Add an observation to this group."""
        self.observations.append(obs)
        self.updated_at = datetime.now()
        self._update_bounds()
    
    def _update_bounds(self) -> None:
        """Update spatial and temporal bounds from observations."""
        if not self.observations:
            return
        
        # Update temporal span
        timestamps = [obs.timestamp for obs in self.observations]
        self.temporal_span = ObservationWindow(
            start=min(timestamps),
            end=max(timestamps)
        )
        
        # Update spatial bounds
        locations = [obs.location for obs in self.observations if obs.location]
        if locations:
            lats = [loc.lat for loc in locations]
            lons = [loc.lon for loc in locations]
            self.spatial_bounds = {
                "min_lat": min(lats),
                "max_lat": max(lats),
                "min_lon": min(lons),
                "max_lon": max(lons),
                "center": GeoPoint(
                    lat=(min(lats) + max(lats)) / 2,
                    lon=(min(lons) + max(lons)) / 2
                )
            }
    
    def get_contributing_sources(self) -> Set[str]:
        """Get set of contributing source types."""
        return set(obs.source_type for obs in self.observations)
    
    def get_unique_members(self) -> Set[uuid.UUID]:
        """Get set of unique member IDs."""
        return set(obs.member_id for obs in self.observations)


# Correlation functions

def should_correlate(obs1: RawObservation, obs2: RawObservation) -> bool:
    """Determine if two observations should be correlated.
    
    Checks for duplicates (same member) or corroboration (same event).
    """
    # Same member + same category + close time = duplicate
    if obs1.member_id == obs2.member_id:
        return obs1.category == obs2.category and _close_in_time(obs1, obs2)
    
    # Different members = check for corroboration
    return (
        obs1.category == obs2.category and
        _close_in_time(obs1, obs2) and
        _close_in_space(obs1, obs2)
    )


def _close_in_time(obs1: RawObservation, obs2: RawObservation, threshold_seconds: float = 300.0) -> bool:
    """Check if observations are close in time."""
    gap = abs((obs1.timestamp - obs2.timestamp).total_seconds())
    return gap < threshold_seconds


def _close_in_space(obs1: RawObservation, obs2: RawObservation, threshold_meters: float = 100.0) -> bool:
    """Check if observations are close in space."""
    if not obs1.location or not obs2.location:
        return True  # If no location, assume close
    return obs1.location.distance_to(obs2.location) < threshold_meters


def calculate_spatial_correlation(
    obs1: RawObservation,
    obs2: RawObservation,
    max_distance_meters: float = 100.0
) -> float:
    """Calculate spatial correlation score (0-1).
    
    1.0 = same location
    0.0 = at or beyond max distance
    """
    if not obs1.location or not obs2.location:
        return 0.5  # Neutral if no location data
    
    distance = obs1.location.distance_to(obs2.location)
    
    if distance >= max_distance_meters:
        return 0.0
    return 1.0 - (distance / max_distance_meters)


def calculate_temporal_correlation(
    obs1: RawObservation,
    obs2: RawObservation,
    max_gap_seconds: float = 300.0
) -> float:
    """Calculate temporal correlation score (0-1).
    
    1.0 = same time
    0.0 = at or beyond max gap
    """
    gap = abs((obs1.timestamp - obs2.timestamp).total_seconds())
    
    if gap >= max_gap_seconds:
        return 0.0
    return 1.0 - (gap / max_gap_seconds)


def calculate_category_correlation(obs1: RawObservation, obs2: RawObservation) -> float:
    """Calculate category correlation score (0-1).
    
    1.0 = exact match
    0.0 = completely different
    """
    if obs1.category == obs2.category:
        return 1.0
    
    # Related categories could have partial scores
    related_categories = {
        "police_action": ["blocked_route", "hazard"],
        "medical": ["hazard"],
        "fire": ["hazard", "blocked_route"],
    }
    
    related = related_categories.get(obs1.category, [])
    if obs2.category in related:
        return 0.5
    
    return 0.0


def determine_correlation_type(
    obs1: RawObservation,
    obs2: RawObservation
) -> CorrelationType:
    """Determine the type of correlation between two observations."""
    # Same member = potential duplicate
    if obs1.member_id == obs2.member_id:
        if obs1.category == obs2.category and _close_in_time(obs1, obs2):
            return CorrelationType.DUPLICATE
        return CorrelationType.UNRELATED
    
    # Different members = check for corroboration
    spatial = calculate_spatial_correlation(obs1, obs2)
    temporal = calculate_temporal_correlation(obs1, obs2)
    category = calculate_category_correlation(obs1, obs2)
    
    # High correlation across all dimensions = corroborating
    if spatial > 0.5 and temporal > 0.5 and category == 1.0:
        return CorrelationType.CORROBORATING
    
    # Moderate correlation = related
    if spatial > 0.0 and temporal > 0.0 and category > 0.0:
        return CorrelationType.RELATED
    
    return CorrelationType.UNRELATED


def calculate_overall_confidence(group: ObservationGroup) -> ConfidenceScore:
    """Calculate confidence score for an observation group."""
    factors = []
    base_confidence = 0.5
    
    # Factor 1: Corroboration (multiple sources)
    num_sources = len(group.observations)
    source_bonus = min(0.3, (num_sources - 1) * 0.15) if num_sources > 1 else 0.0
    factors.append(ConfidenceFactor(
        factor_type="corroboration",
        weight=0.3,
        contribution=source_bonus,
        explanation=f"{num_sources} contributing observation(s)"
    ))
    
    # Factor 2: Source diversity (different source types)
    source_types = group.get_contributing_sources()
    type_bonus = min(0.2, (len(source_types) - 1) * 0.1) if len(source_types) > 1 else 0.0
    factors.append(ConfidenceFactor(
        factor_type="source_diversity",
        weight=0.2,
        contribution=type_bonus,
        explanation=f"{len(source_types)} source type(s): {', '.join(source_types)}"
    ))
    
    # Factor 3: Member diversity (different members)
    members = group.get_unique_members()
    member_bonus = min(0.2, (len(members) - 1) * 0.1) if len(members) > 1 else 0.0
    factors.append(ConfidenceFactor(
        factor_type="member_diversity",
        weight=0.2,
        contribution=member_bonus,
        explanation=f"{len(members)} unique member(s)"
    ))
    
    # Factor 4: Temporal freshness
    if group.temporal_span:
        age_seconds = (datetime.now() - group.temporal_span.end).total_seconds()
        # Decay over 1 hour
        freshness = max(0.0, 1.0 - (age_seconds / 3600))
        freshness_contrib = freshness * 0.15
    else:
        freshness_contrib = 0.1
    
    factors.append(ConfidenceFactor(
        factor_type="temporal_freshness",
        weight=0.15,
        contribution=freshness_contrib,
        explanation="Recent observations" if freshness_contrib > 0.1 else "Older observations"
    ))
    
    # Factor 5: Source quality (sensor vs manual)
    has_sensor = any(st in source_types for st in ['audio', 'vision'])
    quality_contrib = 0.1 if has_sensor else 0.0
    factors.append(ConfidenceFactor(
        factor_type="source_quality",
        weight=0.15,
        contribution=quality_contrib,
        explanation="Sensor data present" if has_sensor else "Manual reports only"
    ))
    
    # Calculate overall confidence
    overall = min(1.0, base_confidence + sum(f.contribution for f in factors))
    
    return ConfidenceScore(
        overall=overall,
        factors=factors,
        tier=None  # Will be calculated in __post_init__
    )
