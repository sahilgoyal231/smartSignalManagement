"""
Unit Tests — GPS Reader & Beacon Builder
=========================================
Tests run without hardware — uses mock data and patches serial.

Run:
    cd smart-signal-system
    pytest vsu/tests/test_gps_beacon.py -v
"""
import json
import math
import struct
import time
from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from vsu.src.config import VSUConfig
from vsu.src.gps_reader import GPSReader, GPSSample
from vsu.src.beacon_builder import BeaconBuilder, DeadReckoning


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def config():
    cfg = VSUConfig.__new__(VSUConfig)
    cfg.vehicle_id      = "AMB-TEST-001"
    cfg.vehicle_type    = "AMBULANCE"
    cfg.priority_class  = 2
    cfg.city            = "Mumbai"
    cfg.gps_serial_port = "/dev/null"
    cfg.gps_baud_rate   = 9600
    cfg.gps_timeout_s   = 2.0
    cfg.gps_min_sats    = 4
    cfg.gps_max_accuracy_m = 10.0
    cfg.home_hospital_lat  = 19.0456
    cfg.home_hospital_lon  = 72.8272
    cfg.lora_spi_channel   = 0
    cfg.lora_frequency_mhz = 433.0
    cfg.lora_tx_power_dbm  = 17
    cfg.lora_beacon_interval_s = 0.5
    cfg.mqtt_host    = "localhost"
    cfg.mqtt_port    = 8883
    cfg.mqtt_user    = "test"
    cfg.mqtt_password = "test"
    cfg.mqtt_tls     = False
    cfg.siren_gpio_pin     = 17
    cfg.siren_freq_low_hz  = 500.0
    cfg.siren_freq_high_hz = 2000.0
    cfg.siren_hold_s       = 0.5
    cfg.device_cert_path   = "./certs/vsu.crt"
    cfg.device_key_path    = "./certs/vsu.key"
    cfg.log_level          = "DEBUG"
    return cfg


@pytest.fixture
def good_gps():
    return GPSSample(
        lat=19.0654, lon=72.8647, alt_m=12.0,
        speed_kmh=62.4, heading_deg=275.3,
        accuracy_m=2.5, satellites=10, fix_quality=1,
        timestamp=datetime.now(timezone.utc),
    )


# ─────────────────────────────────────────────────────────────
# GPS Reader Tests
# ─────────────────────────────────────────────────────────────

class TestGPSReader:

    def test_heading_smoother_no_wrap(self, config):
        reader = GPSReader(config)
        reader._smoothed_heading = 100.0
        result = reader._smooth_heading(110.0)
        assert 100.0 < result < 110.0, "EMA should be between old and new heading"

    def test_heading_smoother_wrap_359_to_1(self, config):
        """Heading crossing 0°/360° boundary must not snap to 180°."""
        reader = GPSReader(config)
        reader._smoothed_heading = 359.0
        result = reader._smooth_heading(1.0)
        # Result should be near 359–361 range (mod 360), NOT 180
        assert result > 300 or result < 20, \
            f"Wrap-around heading smoother failed: got {result}"

    def test_heading_smoother_initial_value(self, config):
        reader = GPSReader(config)
        assert reader._smoothed_heading is None
        result = reader._smooth_heading(270.0)
        assert result == 270.0, "First reading should set heading directly"

    def test_mock_mode_produces_samples(self, config):
        """Mock loop should generate samples without real hardware."""
        reader = GPSReader(config)
        reader._running = True
        # Run 3 mock iterations then stop
        import threading
        def run_briefly():
            count = 0
            import time as _time
            orig_sleep = _time.sleep
            def fast_sleep(s):
                nonlocal count
                count += 1
                if count >= 3:
                    reader._running = False
                orig_sleep(0.01)
            with patch("time.sleep", fast_sleep):
                reader._mock_loop()
        thread = threading.Thread(target=run_briefly)
        thread.start()
        thread.join(timeout=2)
        assert reader.get_latest_fix() is not None, "Mock mode should produce GPS samples"


# ─────────────────────────────────────────────────────────────
# Beacon Builder Tests
# ─────────────────────────────────────────────────────────────

class TestBeaconBuilder:

    def test_build_with_good_gps(self, config, good_gps):
        builder = BeaconBuilder(config)
        payload = builder.build(gps=good_gps, siren_active=True, battery_pct=85)
        assert payload is not None
        assert payload["vehicle_id"]   == "AMB-TEST-001"
        assert payload["vehicle_type"] == "AMBULANCE"
        assert payload["siren"]        is True
        assert payload["bat"]          == 85
        assert payload["gps"]["lat"]   == pytest.approx(19.0654, abs=1e-4)
        assert payload["gps"]["lon"]   == pytest.approx(72.8647, abs=1e-4)
        assert payload["gps"]["src"]   == "gps"
        assert len(payload["nonce"])   == 32   # 16 bytes hex = 32 chars

    def test_build_adds_home_hospital_as_dest(self, config, good_gps):
        builder = BeaconBuilder(config)
        payload = builder.build(gps=good_gps, siren_active=True, battery_pct=90)
        assert payload["dest"] is not None
        assert payload["dest"]["lat"] == pytest.approx(19.0456, abs=1e-4)

    def test_build_falls_back_to_dead_reckoning(self, config, good_gps):
        builder = BeaconBuilder(config)
        # First, feed a good fix to prime DR engine
        builder.build(gps=good_gps, siren_active=True, battery_pct=90)

        # Now pass bad GPS (accuracy too poor)
        bad_gps = replace(good_gps, accuracy_m=50.0)   # exceeds max_accuracy_m=10
        payload = builder.build(gps=bad_gps, siren_active=True, battery_pct=90)

        assert payload is not None, "Should fall back to dead reckoning"
        assert payload["gps"]["src"] == "dead_reckoning"

    def test_build_returns_none_with_no_position(self, config):
        builder = BeaconBuilder(config)
        # No GPS fix, no DR seed → should return None
        bad_gps = replace(
            GPSSample(0, 0, 0, 0, 0, 50.0, 0, 0, datetime.now(timezone.utc)),
            accuracy_m=50.0
        )
        payload = builder.build(gps=bad_gps, siren_active=False, battery_pct=100)
        assert payload is None

    def test_nonce_is_unique_per_beacon(self, config, good_gps):
        builder = BeaconBuilder(config)
        p1 = builder.build(gps=good_gps, siren_active=True, battery_pct=90)
        p2 = builder.build(gps=good_gps, siren_active=True, battery_pct=90)
        assert p1["nonce"] != p2["nonce"], "Each beacon must have a unique nonce"

    def test_battery_clamped(self, config, good_gps):
        builder = BeaconBuilder(config)
        p = builder.build(gps=good_gps, siren_active=False, battery_pct=150)
        assert p["bat"] == 100, "Battery > 100 should be clamped to 100"
        p2 = builder.build(gps=good_gps, siren_active=False, battery_pct=-10)
        assert p2["bat"] == 0, "Battery < 0 should be clamped to 0"

    def test_to_json_bytes_valid(self, config, good_gps):
        builder = BeaconBuilder(config)
        payload = builder.build(gps=good_gps, siren_active=True, battery_pct=80)
        raw = builder.to_json_bytes(payload)
        parsed = json.loads(raw)
        assert parsed["vehicle_id"] == "AMB-TEST-001"

    def test_lora_roundtrip(self, config, good_gps):
        """LoRa binary encode then decode should recover position within tolerance."""
        builder = BeaconBuilder(config)
        payload = builder.build(gps=good_gps, siren_active=True, battery_pct=80)
        lora_bytes = builder.to_lora_bytes(payload)
        assert len(lora_bytes) == 14

        decoded = BeaconBuilder.from_lora_bytes(lora_bytes)
        assert decoded["lat"]         == pytest.approx(good_gps.lat, abs=1e-5)
        assert decoded["lon"]         == pytest.approx(good_gps.lon, abs=1e-5)
        assert decoded["speed_kmh"]   == pytest.approx(good_gps.speed_kmh, abs=0.1)
        assert decoded["siren_active"] is True
        assert decoded["priority"]     == 2

    def test_lora_bytes_exactly_14(self, config, good_gps):
        builder = BeaconBuilder(config)
        payload = builder.build(gps=good_gps, siren_active=False, battery_pct=60)
        assert len(builder.to_lora_bytes(payload)) == 14


# ─────────────────────────────────────────────────────────────
# Dead Reckoning Tests
# ─────────────────────────────────────────────────────────────

class TestDeadReckoning:

    def test_extrapolate_moves_position(self, good_gps):
        dr = DeadReckoning()
        dr.update(good_gps)

        # Patch monotonic time to simulate 5 seconds elapsed
        with patch("time.monotonic", return_value=dr._last_good_time + 5):
            estimate = dr.extrapolate()

        assert estimate is not None
        # At 62.4 km/h heading 275° (west), lat should change slightly, lon move west
        assert estimate.lon < good_gps.lon, "Heading west should decrease longitude"

    def test_extrapolate_returns_none_when_stale(self, good_gps):
        dr = DeadReckoning()
        dr.update(good_gps)
        # 20 seconds later — beyond MAX_DR_SECONDS (15)
        with patch("time.monotonic", return_value=dr._last_good_time + 20):
            result = dr.extrapolate()
        assert result is None, "Should reject stale dead-reckoning"

    def test_extrapolate_returns_none_with_no_seed(self):
        dr = DeadReckoning()
        assert dr.extrapolate() is None

    def test_accuracy_degrades_over_time(self, good_gps):
        dr = DeadReckoning()
        dr.update(good_gps)
        with patch("time.monotonic", return_value=dr._last_good_time + 10):
            est = dr.extrapolate()
        assert est.accuracy_m > good_gps.accuracy_m, \
            "Dead-reckoned accuracy should be worse than original"

    def test_mqtt_topic_format(self, config):
        assert config.mqtt_topic_beacon() == "smartsignal/mumbai/vehicle/AMB-TEST-001/beacon"
        assert config.mqtt_topic_priority() == "smartsignal/mumbai/vehicle/AMB-TEST-001/priority"
