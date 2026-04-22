"""
Unit Tests — Step 9: Edge Node Preemption Decision Engine
===========================================================
Tests ETA calculation, distance thresholds, approach heading logic,
siren states, and multi-vehicle priority resolution.
"""
from unittest.mock import MagicMock
import pytest

from ren.src.decision_engine import DecisionEngine, PreemptionDecision, SignalState
from ren.src.sensor_fusion import FusionTrack


@pytest.fixture
def config():
    cfg = MagicMock()
    # Intersection is at (0.0, 0.0) for easy math
    cfg.lat = 0.0
    cfg.lon = 0.0
    return cfg

@pytest.fixture
def engine(config):
    controller = MagicMock()
    return DecisionEngine(config, signal_controller=controller)

def _make_track(track_id="T01", lat=0.0, lon=0.0, heading=0.0, speed=60.0, siren=True, prio=1, conf=80.0):
    return FusionTrack(
        track_id=track_id, is_identified=True, priority=prio,
        lat=lat, lon=lon, speed_kmh=speed, heading_deg=heading,
        siren_active=siren, first_seen=0.0, last_seen=0.0, confidence=conf
    )

class TestDecisionEngine:

    def test_no_tracks_returns_normal_state(self, engine):
        decision = engine.evaluate([])
        assert decision.should_preempt is False
        assert engine._current_state == SignalState.NORMAL

    def test_low_confidence_track_ignored(self, engine):
        t = _make_track(conf=49.0) # Below threshold 50.0
        decision = engine.evaluate([t])
        assert decision.should_preempt is False

    def test_vehicle_moving_away_ignored(self, engine):
        # Intersection is (0,0). Vehicle is North at (0.01, 0)
        # Heading is 0 (North) -> moving further North (away)
        t = _make_track(lat=0.01, lon=0.0, heading=0.0)
        decision = engine.evaluate([t])
        assert decision.should_preempt is False

    def test_vehicle_approaching_triggers_preemption(self, engine):
        # Vehicle is North at (0.005, 0) -> ~550m away
        # Heading is 180 (South) -> approaching intersection
        # Speed 60 km/h -> 16.6 m/s -> ETA ~33s
        t = _make_track(lat=0.005, lon=0.0, heading=180.0, speed=60.0)
        decision = engine.evaluate([t])
        
        assert decision.should_preempt is True
        assert decision.active_vehicle_id == "T01"

    def test_siren_off_prevents_preemption(self, engine):
        t = _make_track(lat=0.005, lon=0.0, heading=180.0, siren=False)
        decision = engine.evaluate([t])
        assert decision.should_preempt is False
        assert "Siren is OFF" in decision.reason

    def test_vehicle_too_far_is_monitored_but_no_preempt(self, engine):
        # Vehicle is ~1.1km North
        t = _make_track(lat=0.01, lon=0.0, heading=180.0, speed=60.0)
        decision = engine.evaluate([t])
        assert decision.should_preempt is False
        assert engine._current_state == SignalState.NORMAL

    def test_multi_vehicle_priority_resolution(self, engine):
        # T1: Ambulance (Prio 2), 20s away (South)
        t1 = _make_track("AMB-1", lat=0.003, lon=0.0, heading=180.0, speed=60.0, prio=2)
        # T2: Firetruck (Prio 3), 30s away (East)
        t2 = _make_track("FIRE-1", lat=0.0, lon=0.004, heading=270.0, speed=60.0, prio=3)
        
        decision = engine.evaluate([t1, t2])
        
        # Priority 3 wins over Priority 2
        assert decision.should_preempt is True
        assert decision.active_vehicle_id == "FIRE-1"
        assert decision.priority == 3

    def test_multi_vehicle_eta_resolution_same_priority(self, engine):
        # T1: Prio 2, 20s away
        t1 = _make_track("PA-1", lat=0.003, lon=0.0, heading=180.0, speed=60.0, prio=2)
        # T2: Prio 2, 10s away
        t2 = _make_track("PA-2", lat=0.0015, lon=0.0, heading=180.0, speed=60.0, prio=2)
        
        decision = engine.evaluate([t1, t2])
        
        # Closest ETA wins if priority is equal
        assert decision.should_preempt is True
        assert decision.active_vehicle_id == "PA-2"

    def test_target_phase_mapping(self, engine):
        t_north = _make_track(lat=-0.003, lon=0.0, heading=0.0)    # Driving North
        t_south = _make_track(lat=0.003,  lon=0.0, heading=180.0)  # Driving South
        t_east  = _make_track(lat=0.0, lon=-0.003, heading=90.0)   # Driving East
        t_west  = _make_track(lat=0.0, lon=0.003,  heading=270.0)  # Driving West
        
        assert engine.evaluate([t_north]).target_phase == "PHASE_NORTH_SOUTH"
        assert engine.evaluate([t_south]).target_phase == "PHASE_NORTH_SOUTH"
        assert engine.evaluate([t_east]).target_phase  == "PHASE_EAST_WEST"
        assert engine.evaluate([t_west]).target_phase  == "PHASE_EAST_WEST"
