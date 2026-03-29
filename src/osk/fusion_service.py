"""Intelligence fusion service for multimodal observation correlation.

Release 1.3.0 - Trustworthy Intelligence Fusion
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Set, Callable
import uuid

from osk.intelligence_fusion import (
    ObservationGroup,
    RawObservation,
    ConfidenceScore,
    GeoPoint,
    ObservationWindow,
    CorrelationType,
    should_correlate,
    calculate_spatial_correlation,
    calculate_temporal_correlation,
    calculate_category_correlation,
)
from osk.intelligence_contracts import (
    IntelligenceObservation,
)

logger = logging.getLogger(__name__)


class FusionConfig:
    """Configuration for intelligence fusion."""
    
    def __init__(
        self,
        spatial_correlation_threshold: float = 0.7,
        temporal_correlation_threshold: float = 0.7,
        semantic_correlation_threshold: float = 0.8,
        max_correlation_distance_meters: float = 100.0,
        max_correlation_gap_seconds: float = 300.0,
        duplicate_detection_enabled: bool = True,
        duplicate_time_window_seconds: int = 60,
        confidence_calculation_method: str = "weighted_average",
        source_reliability_weight: float = 0.3,
        temporal_weight: float = 0.2,
        spatial_weight: float = 0.2,
        corroboration_weight: float = 0.3,
        max_active_groups: int = 100,
        group_ttl_seconds: int = 3600,  # 1 hour
    ):
        self.spatial_correlation_threshold = spatial_correlation_threshold
        self.temporal_correlation_threshold = temporal_correlation_threshold
        self.semantic_correlation_threshold = semantic_correlation_threshold
        self.max_correlation_distance_meters = max_correlation_distance_meters
        self.max_correlation_gap_seconds = max_correlation_gap_seconds
        self.duplicate_detection_enabled = duplicate_detection_enabled
        self.duplicate_time_window_seconds = duplicate_time_window_seconds
        self.confidence_calculation_method = confidence_calculation_method
        self.source_reliability_weight = source_reliability_weight
        self.temporal_weight = temporal_weight
        self.spatial_weight = spatial_weight
        self.corroboration_weight = corroboration_weight
        self.max_active_groups = max_active_groups
        self.group_ttl_seconds = group_ttl_seconds


class FusionService:
    """Service for multimodal intelligence fusion.
    
    Correlates observations across time, space, and source type to build
    a more accurate picture of field conditions.
    """
    
    def __init__(
        self,
        db,
        config: Optional[FusionConfig] = None,
        on_group_created: Optional[Callable[[ObservationGroup], None]] = None,
        on_group_updated: Optional[Callable[[ObservationGroup], None]] = None,
        on_confidence_scored: Optional[Callable[[uuid.UUID, ConfidenceScore], None]] = None,
    ):
        self.db = db
        self.config = config or FusionConfig()
        self.on_group_created = on_group_created
        self.on_group_updated = on_group_updated
        self.on_confidence_scored = on_confidence_scored
        
        # In-memory cache of active groups
        self._active_groups: Dict[uuid.UUID, ObservationGroup] = {}
        self._recent_observations: deque[RawObservation] = deque(maxlen=100)
        
        self._started = False
        self._cleanup_task: Optional[asyncio.Task] = None
    
    async def start(self) -> None:
        """Start the fusion service."""
        if self._started:
            return
        
        # Load existing active groups from database
        await self._load_active_groups()
        
        # Start cleanup task
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
        
        self._started = True
        logger.info("Fusion service started with %d active groups", len(self._active_groups))
    
    async def stop(self) -> None:
        """Stop the fusion service."""
        if not self._started:
            return
        
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        self._started = False
        logger.info("Fusion service stopped")
    
    async def process_observation(
        self,
        observation: IntelligenceObservation,
    ) -> Optional[ObservationGroup]:
        """Process a new observation through the fusion pipeline.
        
        Args:
            observation: Raw observation to process
            
        Returns:
            ObservationGroup if observation was correlated, None if duplicate
        """
        # Convert to RawObservation
        raw_obs = self._convert_to_raw_observation(observation)
        self._recent_observations.append(raw_obs)
        
        # Check for duplicates
        if self.config.duplicate_detection_enabled:
            if self._is_duplicate(raw_obs):
                logger.debug("Duplicate observation detected: %s", raw_obs.event_id)
                return None
        
        # Try to correlate with existing groups
        correlated_group = await self._correlate_with_groups(raw_obs)
        
        if correlated_group:
            # Add to existing group
            correlated_group.add_observation(raw_obs)
            await self._update_group_in_db(correlated_group)
            
            # Recalculate confidence for all events in group
            await self._recalculate_group_confidence(correlated_group)
            
            if self.on_group_updated:
                self.on_group_updated(correlated_group)
            
            return correlated_group
        else:
            # Create new group
            new_group = self._create_observation_group(raw_obs)
            await self._save_group_to_db(new_group, raw_obs)
            self._active_groups[new_group.id] = new_group
            
            # Calculate initial confidence
            await self._calculate_confidence(raw_obs, new_group)
            
            if self.on_group_created:
                self.on_group_created(new_group)
            
            return new_group
    
    async def get_enriched_event(
        self,
        event_id: uuid.UUID,
    ) -> Optional[Dict]:
        """Get event with confidence scores and attribution.
        
        Args:
            event_id: Event UUID
            
        Returns:
            Enriched event dict or None
        """
        # Query the enriched_events view
        row = await self.db.get_enriched_event(event_id)
        if not row:
            return None
        return dict(row)
    
    async def get_observation_groups(
        self,
        operation_id: uuid.UUID,
        category: Optional[str] = None,
        min_confidence: Optional[float] = None,
        active_only: bool = True,
    ) -> List[ObservationGroup]:
        """Get observation groups for an operation.
        
        Args:
            operation_id: Operation UUID
            category: Filter by category
            min_confidence: Minimum confidence score
            active_only: Only return active groups
            
        Returns:
            List of observation groups
        """
        rows = await self.db.get_observation_groups(
            operation_id=operation_id,
            category=category,
            min_confidence=min_confidence,
            status="active" if active_only else None,
        )
        
        groups = []
        for row in rows:
            group = await self._load_group_from_db(row['id'])
            if group:
                groups.append(group)
        
        return groups
    
    def _convert_to_raw_observation(
        self,
        observation: IntelligenceObservation,
    ) -> RawObservation:
        """Convert IntelligenceObservation to RawObservation."""
        location = None
        if observation.location:
            location = GeoPoint(
                lat=observation.location.latitude,
                lon=observation.location.longitude,
            )
        
        return RawObservation(
            event_id=observation.id,
            member_id=observation.member_id,
            operation_id=observation.operation_id,
            category=observation.category.value if observation.category else "unknown",
            text=observation.text or "",
            severity=observation.severity.value if observation.severity else "info",
            source_type=observation.source_type.value if observation.source_type else "unknown",
            location=location,
            timestamp=observation.timestamp or datetime.now(),
        )
    
    def _is_duplicate(self, obs: RawObservation) -> bool:
        """Check if observation is a duplicate of recent observations."""
        for recent in self._recent_observations:
            if recent.event_id == obs.event_id:
                continue  # Skip self
            
            # Check if same member, same category, close in time
            if (
                recent.member_id == obs.member_id and
                recent.category == obs.category and
                abs((recent.timestamp - obs.timestamp).total_seconds()) <
                self.config.duplicate_time_window_seconds
            ):
                return True
        
        return False
    
    async def _correlate_with_groups(
        self,
        obs: RawObservation,
    ) -> Optional[ObservationGroup]:
        """Try to correlate observation with existing groups."""
        best_match: Optional[ObservationGroup] = None
        best_score = 0.0
        
        for group in self._active_groups.values():
            # Quick category check
            if group.category != obs.category:
                continue
            
            # Check if any observation in group correlates
            for group_obs in group.observations:
                if should_correlate(
                    obs,
                    group_obs,
                    spatial_threshold=self.config.spatial_correlation_threshold,
                    temporal_threshold=self.config.temporal_correlation_threshold,
                    category_threshold=self.config.semantic_correlation_threshold,
                ):
                    # Calculate overall correlation score
                    spatial = calculate_spatial_correlation(obs, group_obs)
                    temporal = calculate_temporal_correlation(obs, group_obs)
                    score = (spatial + temporal) / 2
                    
                    if score > best_score:
                        best_score = score
                        best_match = group
                    break  # Found match in this group
        
        return best_match
    
    def _create_observation_group(self, obs: RawObservation) -> ObservationGroup:
        """Create a new observation group from a single observation."""
        return ObservationGroup(
            id=uuid.uuid4(),
            operation_id=obs.operation_id,
            category=obs.category,
            primary_location=obs.location,
            time_window=ObservationWindow(
                start=obs.timestamp,
                end=obs.timestamp,
            ),
            observations=[obs],
            member_ids={obs.member_id},
            source_types={obs.source_type},
        )
    
    async def _save_group_to_db(
        self,
        group: ObservationGroup,
        primary_obs: RawObservation,
    ) -> None:
        """Save new group to database."""
        await self.db.insert_observation_group(
            group_id=group.id,
            operation_id=group.operation_id,
            category=group.category,
            primary_location_lat=group.primary_location.lat if group.primary_location else None,
            primary_location_lon=group.primary_location.lon if group.primary_location else None,
            location_radius_meters=group.location_radius_meters,
            first_observed_at=group.time_window.start,
            last_observed_at=group.time_window.end,
            source_types=list(group.source_types),
            member_count=len(group.member_ids),
            observation_count=len(group.observations),
            diversity_score=group.get_diversity_score(),
        )
        
        # Link primary observation
        await self.db.insert_observation_group_member(
            group_id=group.id,
            event_id=primary_obs.event_id,
            member_id=primary_obs.member_id,
            correlation_type=CorrelationType.PRIMARY.value,
        )
    
    async def _update_group_in_db(self, group: ObservationGroup) -> None:
        """Update group in database."""
        await self.db.update_observation_group(
            group_id=group.id,
            last_observed_at=group.time_window.end,
            primary_location_lat=group.primary_location.lat if group.primary_location else None,
            primary_location_lon=group.primary_location.lon if group.primary_location else None,
            source_types=list(group.source_types),
            member_count=len(group.member_ids),
            observation_count=len(group.observations),
            diversity_score=group.get_diversity_score(),
        )
        
        # Add new observation to group
        latest_obs = group.observations[-1]
        await self.db.insert_observation_group_member(
            group_id=group.id,
            event_id=latest_obs.event_id,
            member_id=latest_obs.member_id,
            correlation_type=CorrelationType.CORROBORATING.value,
        )
    
    async def _calculate_confidence(
        self,
        obs: RawObservation,
        group: ObservationGroup,
    ) -> ConfidenceScore:
        """Calculate confidence score for an observation."""
        score = ConfidenceScore(
            event_id=obs.event_id,
            operation_id=obs.operation_id,
            group_id=group.id,
        )
        
        # Source reliability (based on source type)
        source_reliability = {
            "manual": 0.9,      # Human reports are generally reliable
            "vision": 0.8,      # Visual evidence
            "audio": 0.7,       # Audio can be ambiguous
            "location": 0.6,    # Location alone is less informative
        }.get(obs.source_type, 0.5)
        
        score.source_reliability = source_reliability
        score.primary_source_type = obs.source_type
        
        # Cross-source corroboration
        if len(group.source_types) > 1:
            score.cross_source_corroboration = min(1.0, (len(group.source_types) - 1) * 0.3)
            score.contributing_sources = list(group.source_types)
        
        # Observation diversity
        score.observation_diversity = group.get_diversity_score()
        
        # Calculate overall
        score.calculate_overall()
        
        # Add explanation
        score.add_confidence_factor(f"Source: {obs.source_type} (reliability: {source_reliability:.1f})")
        if len(group.source_types) > 1:
            score.add_confidence_factor(f"Corroborated by {len(group.source_types)} source types")
        if group.member_count > 1:
            score.add_confidence_factor(f"Reported by {group.member_count} members")
        
        # Save to database
        await self._save_confidence_score(score)
        
        if self.on_confidence_scored:
            self.on_confidence_scored(obs.event_id, score)
        
        return score
    
    async def _recalculate_group_confidence(self, group: ObservationGroup) -> None:
        """Recalculate confidence for all observations in a group."""
        for obs in group.observations:
            await self._calculate_confidence(obs, group)
    
    async def _save_confidence_score(self, score: ConfidenceScore) -> None:
        """Save confidence score to database."""
        await self.db.insert_or_update_confidence_score(
            event_id=score.event_id,
            operation_id=score.operation_id,
            group_id=score.group_id,
            confidence_score=score.score,
            source_reliability=score.source_reliability,
            temporal_consistency=score.temporal_consistency,
            spatial_consistency=score.spatial_consistency,
            cross_source_corroboration=score.cross_source_corroboration,
            observation_diversity=score.observation_diversity,
            primary_source_type=score.primary_source_type,
            contributing_sources=score.contributing_sources,
            contributing_member_count=len(score.contributing_sources),
            confidence_factors=score.confidence_factors,
        )
    
    async def _load_active_groups(self) -> None:
        """Load active groups from database on startup."""
        # This would query the database for active groups
        # and populate self._active_groups
        pass  # Implementation depends on db layer
    
    async def _load_group_from_db(self, group_id: uuid.UUID) -> Optional[ObservationGroup]:
        """Load a group and its observations from database."""
        # Implementation depends on db layer
        pass
    
    async def _periodic_cleanup(self) -> None:
        """Periodically clean up old/expired groups."""
        while self._started:
            try:
                await asyncio.sleep(300)  # Every 5 minutes
                await self._cleanup_old_groups()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in fusion cleanup: %s", e)
    
    async def _cleanup_old_groups(self) -> None:
        """Remove old groups from memory."""
        now = datetime.now()
        expired = []
        
        for group_id, group in self._active_groups.items():
            age_seconds = (now - group.time_window.end).total_seconds()
            if age_seconds > self.config.group_ttl_seconds:
                expired.append(group_id)
        
        for group_id in expired:
            del self._active_groups[group_id]
        
        if expired:
            logger.debug("Cleaned up %d expired observation groups", len(expired))
    
    async def get_fusion_stats(self) -> Dict:
        """Get statistics about the fusion service."""
        return {
            "active_groups": len(self._active_groups),
            "recent_observations": len(self._recent_observations),
            "config": {
                "spatial_threshold": self.config.spatial_correlation_threshold,
                "temporal_threshold": self.config.temporal_correlation_threshold,
                "duplicate_detection": self.config.duplicate_detection_enabled,
            },
        }
