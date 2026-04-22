"""
Preemption Decision Engine (Edge Node)
========================================
Analyses active FusionTracks to determine if the traffic signal should be
preempted (forced to green) to allow an emergency vehicle to pass.

Logic:
1. Filters out vehicles that are moving away from the intersection.
2. Calculates ETA (Estimated Time of Arrival) based on distance and speed.
3. Groups tracking into 4 discrete states:
   - APPROACHING (far away, just monitoring)
   - PREEMPT_CANDIDATE (getting close, evaluating)
   - PREEMPT_ACTIVE (siren on, within ETA threshold → trigger green light)
   - CLEARED (passed the intersection)

Handles priority resolution (e.g., Fire Truck (Priority 3) beats Ambulance (Priority 2)).
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, List, Optional

from loguru import logger

from ren.src.config import RENConfig
from ren.src.sensor_fusion import FusionTrack, haversine_distance
from ren.src.signal_controller import BaseSignalController
from ren.src.mqtt_client import EdgeMQTTClient


class SignalState(Enum):
    NORMAL = auto()
    PREEMPTION_REQUESTED = auto()
    PREEMPTION_ACTIVE = auto()
    RECOVERY = auto()


@dataclass
class PreemptionDecision:
    """The output of the decision engine."""
    should_preempt: bool
    target_phase: str          # e.g., "NORTHBOUND_STRAIGHT"
    active_vehicle_id: str     # The ID of the vehicle causing the preemption
    priority: int
    eta_seconds: float
    distance_m: float
    reason: str


class DecisionEngine:
    """
    Evaluates tracks and decides when to take over the traffic light.
    """

    # Configurable thresholds
    PREEMPT_ETA_MIN_S = 8.0     # Time needed to safely clear pedestrians/cross-traffic
    PREEMPT_ETA_MAX_S = 35.0    # Don't preempt too early (causes traffic jams)
    MAX_AFFECT_RADIUS_M = 800.0 # Ignore vehicles further than this
    MIN_CONFIDENCE = 50.0       # Ignore noisy/ghost tracks

    def __init__(self, config: RENConfig, signal_controller: BaseSignalController, mqtt_client: Optional[EdgeMQTTClient] = None) -> None:
        self._cfg = config
        self._signal_controller = signal_controller
        self._mqtt_client = mqtt_client
        self._current_state = SignalState.NORMAL
        self._active_preemption: Optional[PreemptionDecision] = None
        self._cleared_vehicles: set[str] = set()

    def evaluate(self, tracks: List[FusionTrack]) -> PreemptionDecision:
        """
        Evaluate all active tracks and return the current required signal state.
        Called periodically (e.g., every 500ms).
        """
        candidates: List[PreemptionDecision] = []

        for track in tracks:
            decision = self._evaluate_single_track(track)
            if decision:
                candidates.append(decision)

        if not candidates:
            # Nobody needs preemption
            if self._current_state != SignalState.NORMAL:
                logger.info("🚦 ALL VEHICLES CLEARED. Reverting to normal operation.")
                self._signal_controller.clear_preemption()
                if self._mqtt_client:
                    self._mqtt_client.publish_event("PREEMPT_CLEARED", {"reason": "All vehicles cleared"})
            self._current_state = SignalState.NORMAL
            self._active_preemption = None
            return PreemptionDecision(
                should_preempt=False, target_phase="NORMAL",
                active_vehicle_id="", priority=0,
                eta_seconds=0.0, distance_m=0.0, reason="No active candidates"
            )

        # ── Priority Resolution ─────────────────────────────────────
        # If multiple vehicles are approaching, pick the most critical one.
        # Sort by:
        #  1. Priority (Higher first, e.g., Fire > Police)
        #  2. ETA (Lowest first, who is arriving soonest)
        candidates.sort(key=lambda c: (-c.priority, c.eta_seconds))
        winner = candidates[0]

        if winner.should_preempt:
            if self._current_state == SignalState.NORMAL:
                logger.warning(
                    f"🚦 PREEMPTION TRIGGERED by {winner.active_vehicle_id} "
                    f"({winner.target_phase}, ETA={winner.eta_seconds:.1f}s)"
                )
            # Apply preemption through controller
            if self._active_preemption is None or self._active_preemption.target_phase != winner.target_phase:
                self._signal_controller.set_preemption(winner.target_phase)
                if self._mqtt_client:
                    self._mqtt_client.publish_event("PREEMPT_ACTIVE", {
                        "vehicle_id": winner.active_vehicle_id,
                        "phase": winner.target_phase,
                        "eta_s": winner.eta_seconds,
                        "priority": winner.priority
                    })
            self._current_state = SignalState.PREEMPTION_ACTIVE
        else:
            if self._current_state != SignalState.NORMAL:
                logger.info("🚦 PREEMPTION CLEARED. Reverting to normal operation.")
                self._signal_controller.clear_preemption()
                if self._mqtt_client:
                    self._mqtt_client.publish_event("PREEMPT_CLEARED", {"reason": "Preemption logic deactivated"})
            self._current_state = SignalState.NORMAL

        self._active_preemption = winner
        return winner

    def _evaluate_single_track(self, track: FusionTrack) -> Optional[PreemptionDecision]:
        """Evaluates a single vehicle. Returns None if vehicle is ignored."""
        
        # 1. Ignore low confidence or stale tracks
        if track.confidence < self.MIN_CONFIDENCE:
            return None
        
        # 2. Ignore if already cleared
        if track.track_id in self._cleared_vehicles:
            return None

        # 3. Calculate distance to intersection
        dist_m = haversine_distance(track.lat, track.lon, self._cfg.lat, self._cfg.lon)
        if dist_m > self.MAX_AFFECT_RADIUS_M:
            return None

        # 4. Determine if vehicle is approaching or moving away
        # Calculate bearing from vehicle to intersection
        phi1 = math.radians(track.lat)
        phi2 = math.radians(self._cfg.lat)
        dlambda = math.radians(self._cfg.lon - track.lon)
        y = math.sin(dlambda) * math.cos(phi2)
        x = math.cos(phi1) * math.sin(phi2) - \
            math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)
        bearing_to_intersection = (math.degrees(math.atan2(y, x)) + 360) % 360

        # If heading differ from bearing-to-intersection by > 60 degrees, it's not heading towards us
        heading_diff = abs((track.heading_deg - bearing_to_intersection + 180) % 360 - 180)
        
        is_approaching = heading_diff <= 60.0

        # Are they cleared? (Usually identified by being very close, then moving away)
        if dist_m < 50.0 and not is_approaching:
            logger.info(f"🚦 Vehicle {track.track_id} has CLEARED the intersection.")
            self._cleared_vehicles.add(track.track_id)
            return None

        if not is_approaching:
            return None

        # 5. Calculate ETA
        # Avoid division by zero. If moving very slowly, cap ETA to max.
        speed_ms = track.speed_kmh / 3.6
        eta_s = (dist_m / speed_ms) if speed_ms > 1.0 else 999.0

        # 6. Determine Target Phase (N/S/E/W) based on vehicle heading
        # For a standard 4-way, if heading is North (0), they are coming from the South.
        # So we need to turn the Northbound/Southbound phase green.
        target_phase = self._heading_to_phase(track.heading_deg)

        # 7. Make Preemption Decision
        should_preempt = False
        reason = "Monitoring approaching vehicle"

        if not track.siren_active:
            reason = "Siren is OFF (No preemption required)"
        elif eta_s > self.PREEMPT_ETA_MAX_S:
            reason = f"Vehicle too far away (ETA > {self.PREEMPT_ETA_MAX_S}s)"
        elif eta_s < self.PREEMPT_ETA_MIN_S:
            should_preempt = True
            reason = f"CRITICAL: ETA < {self.PREEMPT_ETA_MIN_S}s"
        else:
            should_preempt = True
            reason = f"Preempting (Active in sweet spot {self.PREEMPT_ETA_MIN_S}-{self.PREEMPT_ETA_MAX_S}s)"

        return PreemptionDecision(
            should_preempt=should_preempt,
            target_phase=target_phase,
            active_vehicle_id=track.track_id,
            priority=track.priority,
            eta_seconds=eta_s,
            distance_m=dist_m,
            reason=reason
        )

    def _heading_to_phase(self, heading: float) -> str:
        """Maps an incoming vehicle heading to a traffic light phase."""
        if 45 <= heading < 135:
            return "PHASE_EAST_WEST"     # Vehicle heading East
        elif 135 <= heading < 225:
            return "PHASE_NORTH_SOUTH"   # Vehicle heading South
        elif 225 <= heading < 315:
            return "PHASE_EAST_WEST"     # Vehicle heading West
        else:
            return "PHASE_NORTH_SOUTH"   # Vehicle heading North
