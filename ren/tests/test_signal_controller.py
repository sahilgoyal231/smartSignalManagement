"""
Tests for Signal Controller Interface
"""
import pytest
from unittest.mock import MagicMock, patch

from ren.src.config import RENConfig
from ren.src.signal_controller import (
    get_signal_controller, MockSignalController, 
    RelaySignalController, SerialSignalController
)

@pytest.fixture
def config():
    cfg = RENConfig()
    cfg.controller_type = "MOCK"
    return cfg

def test_get_signal_controller_mock(config):
    config.controller_type = "MOCK"
    controller = get_signal_controller(config)
    assert isinstance(controller, MockSignalController)

def test_get_signal_controller_relay(config):
    config.controller_type = "RELAY"
    with patch("ren.src.signal_controller.logger"):
        controller = get_signal_controller(config)
        assert isinstance(controller, RelaySignalController)

def test_get_signal_controller_serial(config):
    config.controller_type = "SERIAL"
    with patch("ren.src.signal_controller.logger"):
        controller = get_signal_controller(config)
        assert isinstance(controller, SerialSignalController)

def test_mock_controller_preemption(config):
    controller = MockSignalController(config)
    assert controller._active_phase is None

    result = controller.set_preemption("PHASE_NORTH_SOUTH")
    assert result is True
    assert controller._active_phase == "PHASE_NORTH_SOUTH"

    result = controller.clear_preemption()
    assert result is True
    assert controller._active_phase is None

def test_decision_engine_triggers_controller():
    # An integration style test for decision engine and mock controller
    from ren.src.decision_engine import DecisionEngine
    from ren.src.sensor_fusion import FusionTrack
    
    cfg = MagicMock()
    cfg.lat = 0.0
    cfg.lon = 0.0
    
    mock_controller = MagicMock()
    engine = DecisionEngine(cfg, mock_controller)
    
    # Send a track that should trigger preemption
    t = FusionTrack(
        track_id="T01", is_identified=True, priority=1,
        lat=0.005, lon=0.0, speed_kmh=60.0, heading_deg=180.0,
        siren_active=True, first_seen=0.0, last_seen=0.0, confidence=80.0
    )
    
    decision = engine.evaluate([t])
    assert decision.should_preempt is True
    
    # Should have called set_preemption on the controller
    mock_controller.set_preemption.assert_called_once_with("PHASE_NORTH_SOUTH")
    
    # Now simulate the vehicle clearing the intersection
    # Move it past the intersection
    t2 = FusionTrack(
        track_id="T01", is_identified=True, priority=1,
        lat=-0.005, lon=0.0, speed_kmh=60.0, heading_deg=180.0,
        siren_active=True, first_seen=0.0, last_seen=0.0, confidence=80.0
    )
    decision = engine.evaluate([t2])
    assert decision.should_preempt is False
    
    # Should have called clear_preemption
    mock_controller.clear_preemption.assert_called_once()
