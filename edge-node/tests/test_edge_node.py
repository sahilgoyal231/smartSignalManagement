"""
Tests for Edge Node Software Stack
"""
import pytest
import math
import asyncio
from datetime import datetime, timezone

import importlib
# Import using importlib to bypass hyphenated directory names
_fusion_module = importlib.import_module("edge-node.src.fusion.engine")
SensorFusionEngine = _fusion_module.SensorFusionEngine

_eta_module = importlib.import_module("edge-node.src.eta.predictor")
KinematicPredictor = _eta_module.KinematicPredictor

_signal_module = importlib.import_module("edge-node.src.signal.controller")
SignalController = _signal_module.SignalController
ControllerState = _signal_module.ControllerState

def test_sensor_fusion_single_lora():
    """LoRa alone provides high confidence (0.6 * verified value)."""
    engine = SensorFusionEngine(stale_timeout_s=10.0)
    engine.ingest_reading(
        "V1", "LORA", {"lat": 19.1, "lon": 72.1, "confidence": 1.0}
    )
    
    conf = engine.calculate_confidence("V1")
    assert conf == pytest.approx(0.6, abs=0.01)
    
def test_sensor_fusion_multi_sensor():
    """LoRa + Camera confirms presence with higher composite trust."""
    engine = SensorFusionEngine(stale_timeout_s=10.0)
    
    # Ingest simultaneous readings
    engine.ingest_reading("V2", "LORA",   {"lat": 19.1, "lon": 72.1, "confidence": 1.0})
    engine.ingest_reading("V2", "CAMERA", {"confidence": 0.95})
    
    conf = engine.calculate_confidence("V2")
    
    # Expected: (0.6 * 1.0) + (0.3 * 0.95) = 0.6 + 0.285 = 0.885
    assert conf == pytest.approx(0.885)

def test_sensor_fusion_stale_pruning():
    """Old readings decay and are ultimately purged."""
    engine = SensorFusionEngine(stale_timeout_s=2.0)
    
    # Mock ingest a very old reading
    old_time = datetime.now(timezone.utc).timestamp() - 5.0
    engine.observations["V3"] = [
        {"source": "LORA", "timestamp_utc": old_time, "confidence": 1.0}
    ]
    
    conf = engine.calculate_confidence("V3")
    assert conf == 0.0 # Stale reading pruned
    assert "V3" in engine.observations
    assert len(engine.observations["V3"]) == 0

def test_eta_kinematics():
    """Verify haversine distance checks out."""
    # Pune bounds
    node_lat = 18.5204
    node_lon = 73.8567
    pred = KinematicPredictor(node_lat, node_lon)
    
    # Roughly 1 km north (1 deg lat = 111km)
    veh_lat = 18.5204 + (1.0 / 111.0) 
    veh_lon = 73.8567
    
    dist_m = pred.calculate_distance(veh_lat, veh_lon)
    assert 990.0 < dist_m < 1010.0
    
    # Traveling at 60 km/h (16.66 m/s)
    # ETA for 1000m should be exactly 60 seconds
    eta_s = pred.predict_eta(veh_lat, veh_lon, speed_kmh=60.0)
    assert 59.0 < eta_s < 61.0
    
def test_eta_kinematics_stationary_fallback():
    """If a vehicle is stopped at a traffic light, ETA doesn't go to infinity."""
    pred = KinematicPredictor(18.0, 73.0)
    
    # 500m away
    veh_lat = 18.0 + (0.5 / 111.0)
    veh_lon = 73.0
    
    # Speed is literally zero
    eta_s = pred.predict_eta(veh_lat, veh_lon, speed_kmh=0.0)
    
    # It should fallback to 2.77 m/s (10kmh crawl) -> ~180 seconds
    assert 170.0 < eta_s < 190.0

@pytest.mark.asyncio
async def test_signal_controller():
    """Signal controller state transitions securely lock and release."""
    ctrl = SignalController("NODE")
    
    assert ctrl.current_state == ControllerState.NORMAL_OPERATION
    
    # Trigger preempt
    res = await ctrl.preempt("V1", priority=1, approach_phase=2)
    assert res is True
    assert ctrl.current_state == ControllerState.HOLD_GREEN
    assert ctrl.active_preemption_id == "V1"
    
    # Re-trigger from same vehicle shouldn't break state
    res = await ctrl.preempt("V1", priority=1, approach_phase=2)
    assert res is True
    assert ctrl.current_state == ControllerState.HOLD_GREEN
    
    # Release 
    res = await ctrl.release()
    assert res is True
    assert ctrl.current_state == ControllerState.NORMAL_OPERATION
    assert ctrl.active_preemption_id is None
