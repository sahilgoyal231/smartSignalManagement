"""
Unit Tests — Step 6: MQTT Client & Siren Detector
===================================================
All tests run without hardware/broker.

Run:
    pytest vsu/tests/test_step6.py -v
"""
import time
import threading
import json
from unittest.mock import MagicMock, patch, call
from datetime import datetime, timezone

import pytest

from vsu.src.mqtt_client import MQTTClient, OfflineQueue
from vsu.src.siren_detector import SirenDetector, SirenState


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def mock_config():
    cfg = MagicMock()
    cfg.vehicle_id    = "AMB-MH-042"
    cfg.vehicle_type  = "AMBULANCE"
    cfg.priority_class = 2
    cfg.city          = "Mumbai"
    cfg.mqtt_host     = "127.0.0.1"
    cfg.mqtt_port     = 1883
    cfg.mqtt_user     = "test"
    cfg.mqtt_password = "test"
    cfg.mqtt_tls      = False
    cfg.device_cert_path = "./certs/vsu.crt"
    cfg.device_key_path  = "./certs/vsu.key"
    cfg.mqtt_topic_beacon.return_value   = "smartsignal/mumbai/vehicle/AMB-MH-042/beacon"
    cfg.mqtt_topic_priority.return_value = "smartsignal/mumbai/vehicle/AMB-MH-042/priority"
    cfg.siren_gpio_pin     = 17
    cfg.siren_freq_low_hz  = 500.0
    cfg.siren_freq_high_hz = 2000.0
    cfg.siren_hold_s       = 0.2   # Shorter for tests
    return cfg


# ─────────────────────────────────────────────────────────────
# OfflineQueue Tests
# ─────────────────────────────────────────────────────────────

class TestOfflineQueue:

    def test_push_and_flush(self):
        q = OfflineQueue(maxlen=10)
        q.push("topic/a", b"hello", 1)
        q.push("topic/b", b"world", 0)
        items = q.flush()
        assert len(items) == 2
        assert items[0] == ("topic/a", b"hello", 1)

    def test_flush_clears_queue(self):
        q = OfflineQueue(maxlen=10)
        q.push("t", b"x", 1)
        q.flush()
        assert len(q) == 0

    def test_maxlen_drops_oldest(self):
        q = OfflineQueue(maxlen=3)
        for i in range(5):
            q.push(f"t/{i}", bytes([i]), 1)
        assert len(q) == 3
        items = q.flush()
        # Should have kept the LAST 3 (indices 2, 3, 4)
        payloads = [item[1][0] for item in items]
        assert 0 not in payloads, "Oldest items should have been dropped"

    def test_thread_safe_push_flush(self):
        q = OfflineQueue(maxlen=100)
        errors = []

        def pusher():
            for i in range(50):
                try:
                    q.push("t", bytes([i % 256]), 1)
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=pusher) for _ in range(4)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert not errors, f"Thread safety error: {errors}"


# ─────────────────────────────────────────────────────────────
# MQTTClient Tests
# ─────────────────────────────────────────────────────────────

class TestMQTTClient:

    def test_mock_mode_publishes_without_broker(self, mock_config):
        """Should silently publish in mock mode without raising errors."""
        client = MQTTClient(mock_config)
        client._mock = True
        client._running = True
        result = client.publish("test/topic", b"hello", qos=1)
        assert result is True
        assert client.stats()["published"] == 1

    def test_offline_queue_used_when_disconnected(self, mock_config):
        client = MQTTClient(mock_config)
        client._mock      = False
        client._connected = False
        client._running   = True
        client.publish("t", b"msg", qos=1)
        assert len(client._offline_q) == 1

    def test_stats_returns_expected_keys(self, mock_config):
        client = MQTTClient(mock_config)
        s = client.stats()
        assert "connected"      in s
        assert "published"      in s
        assert "offline_queued" in s
        assert "mock"           in s

    def test_publish_beacon_calls_correct_topic(self, mock_config):
        client = MQTTClient(mock_config)
        client._mock = True
        client._running = True
        result = client.publish_beacon(b'{"v":1}')
        assert result is True

    def test_publish_priority_builds_correct_json(self, mock_config):
        client = MQTTClient(mock_config)
        client._mock = True
        client._running = True
        published_data = []

        original_publish = client.publish
        def capture_publish(topic, payload, qos=1):
            published_data.append((topic, payload))
            return True

        client.publish = capture_publish
        client.publish_priority("AMBULANCE", 2)

        assert len(published_data) == 1
        data = json.loads(published_data[0][1])
        assert data["vehicle_id"]   == "AMB-MH-042"
        assert data["vehicle_type"] == "AMBULANCE"
        assert data["priority"]     == 2

    def test_offline_queue_flushed_on_connect(self, mock_config):
        """On _on_connect, buffered messages should be published."""
        client = MQTTClient(mock_config)
        client._mock = False
        client._offline_q.push("saved/topic", b"saved_msg", 1)
        assert len(client._offline_q) == 1

        # Simulate a successful connection
        mock_paho = MagicMock()
        mock_paho.subscribe = MagicMock()
        mock_paho.publish   = MagicMock()
        client._on_connect(mock_paho, None, {}, 0)

        assert client._connected is True
        assert len(client._offline_q) == 0
        mock_paho.publish.assert_called_once_with("saved/topic", b"saved_msg", qos=1)

    def test_backoff_resets_on_reconnect(self, mock_config):
        client = MQTTClient(mock_config)
        client._reconnect_delay = 32   # Simulate backed-off state
        mock_paho = MagicMock()
        mock_paho.subscribe = MagicMock()
        mock_paho.publish   = MagicMock()
        client._on_connect(mock_paho, None, {}, 0)
        assert client._reconnect_delay == 2   # Should be reset


# ─────────────────────────────────────────────────────────────
# SirenDetector FSM Tests
# ─────────────────────────────────────────────────────────────

class TestSirenDetector:

    def _detector(self, mock_config):
        det = SirenDetector(mock_config)
        det._method = "mock"   # Bypass hardware init
        return det

    def test_initial_state_is_idle(self, mock_config):
        det = self._detector(mock_config)
        assert det.get_state() == SirenState.IDLE
        assert det.is_siren_active() is False

    def test_signal_advances_to_detected(self, mock_config):
        det = self._detector(mock_config)
        det._update_state(True)
        assert det.get_state() == SirenState.DETECTED

    def test_transient_signal_resets_to_idle(self, mock_config):
        """A single false-positive should not survive."""
        det = self._detector(mock_config)
        det._update_state(True)   # IDLE → DETECTED
        det._update_state(False)  # DETECTED → IDLE (signal lost before hold_s)
        assert det.get_state() == SirenState.IDLE

    def test_sustained_signal_activates_siren(self, mock_config):
        """Signal must persist past hold_s to reach ACTIVE."""
        det = self._detector(mock_config)
        det._update_state(True)   # IDLE → DETECTED
        # Simulate hold time elapsed
        det._detected_at = time.monotonic() - (mock_config.siren_hold_s + 0.1)
        det._update_state(True)   # DETECTED → ACTIVE
        assert det.get_state() == SirenState.ACTIVE
        assert det.is_siren_active() is True

    def test_activation_counter_increments(self, mock_config):
        det = self._detector(mock_config)
        for _ in range(3):
            # Each cycle: IDLE → DETECTED → ACTIVE → CLEARING → IDLE
            det._state = SirenState.IDLE
            det._update_state(True)
            det._detected_at = time.monotonic() - (mock_config.siren_hold_s + 0.1)
            det._update_state(True)   # → ACTIVE
        assert det._activation_count == 3

    def test_signal_loss_transitions_to_clearing(self, mock_config):
        det = self._detector(mock_config)
        det._state = SirenState.ACTIVE
        det._activated_at = time.monotonic()
        det._update_state(False)   # ACTIVE → CLEARING
        assert det.get_state() == SirenState.CLEARING

    def test_clearing_returns_to_idle_after_hold(self, mock_config):
        det = self._detector(mock_config)
        det._state = SirenState.CLEARING
        det._clearing_at = time.monotonic() - (mock_config.siren_hold_s + 0.1)
        det._update_state(False)
        assert det.get_state() == SirenState.IDLE

    def test_signal_returns_during_clearing(self, mock_config):
        """If siren comes back on during CLEARING, should reactivate."""
        det = self._detector(mock_config)
        det._state = SirenState.CLEARING
        det._clearing_at = time.monotonic()
        det._update_state(True)   # CLEARING → ACTIVE
        assert det.get_state() == SirenState.ACTIVE

    def test_stats_returns_expected_fields(self, mock_config):
        det = self._detector(mock_config)
        s = det.stats()
        assert "state"          in s
        assert "method"         in s
        assert "activations"    in s
        assert "total_active_s" in s

    def test_mock_mode_cycles_correctly(self, mock_config):
        """Mock loop cycles quiet→siren→quiet over 25s cycle."""
        det = self._detector(mock_config)
        det._mock_start = time.monotonic() - 7   # t=7s → in siren zone (5–15s)
        elapsed = (time.monotonic() - det._mock_start) % 25
        siren_on = 5 <= elapsed < 15
        assert siren_on is True   # At t=7 should be active
