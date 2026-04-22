"""
Unit Tests — Step 8: Edge Node Sensor Fusion Engine
=====================================================
Tests the multi-modal fusion of LoRa, BLE, MQTT, and Audio inputs.
Verifies anonymous track spawning, spatial promotion, and confidence decay.
"""
import time
from unittest.mock import patch

import pytest

from ren.src.beacon_parser import ParsedLoRaBeacon
from ren.src.sensor_fusion import FusionTrack, SensorFusionEngine, haversine_distance


@pytest.fixture
def engine():
    return SensorFusionEngine()

@pytest.fixture
def lora_beacon():
    return ParsedLoRaBeacon(
        received_at_ts=time.monotonic(),
        lat=19.0654,
        lon=72.8647,
        speed_kmh=62.4,
        heading_deg=275.3,
        siren_active=True,
        has_dest=False,
        fix_quality=4,
        priority=2,
        rssi_dbm=-65.0,
        snr_db=9.5
    )


class TestSensorFusionEngine:

    def test_haversine_distance(self):
        # 1 degree of latitude is ~111km
        lat1, lon1 = 19.0000, 72.8000
        lat2, lon2 = 19.0010, 72.8000
        dist = haversine_distance(lat1, lon1, lat2, lon2)
        assert 110.0 < dist < 112.0

        # Exact same point
        assert haversine_distance(lat1, lon1, lat1, lon1) == 0.0

    def test_lora_spawns_anonymous_track(self, engine, lora_beacon):
        engine.process_lora(lora_beacon)
        tracks = engine.get_tracks()
        
        assert len(tracks) == 1
        t = tracks[0]
        assert t.track_id.startswith("TRK-")
        assert not t.is_identified
        assert t.lat == 19.0654
        assert "lora" in t.active_sources
        assert t.confidence == 40.0

    def test_subsequent_lora_updates_existing_track(self, engine, lora_beacon):
        engine.process_lora(lora_beacon)
        
        # Move vehicle slightly (10 metres)
        lora_beacon.lat += 0.0001
        engine.process_lora(lora_beacon)
        
        tracks = engine.get_tracks()
        assert len(tracks) == 1
        assert tracks[0].lat == 19.0655
        assert tracks[0].confidence == 55.0  # 40 + 15

    def test_far_lora_spawns_second_track(self, engine, lora_beacon):
        engine.process_lora(lora_beacon)
        
        # Second vehicle 2km away
        lora_beacon.lat += 0.02
        engine.process_lora(lora_beacon)
        
        assert len(engine.get_tracks()) == 2

    def test_ble_promotes_anonymous_track(self, engine, lora_beacon):
        # 1. Anonymous LoRa arrives
        engine.process_lora(lora_beacon)
        assert list(engine._tracks.keys())[0].startswith("TRK-")
        
        # 2. BLE from SAME location arrives with ID
        engine.process_ble("AMB-MH-042", 2, 19.0654, 72.8647, True)
        
        # 3. Track should be promoted
        tracks = engine.get_tracks()
        assert len(tracks) == 1
        assert "AMB-MH-042" in engine._tracks
        t = tracks[0]
        assert t.track_id == "AMB-MH-042"
        assert t.is_identified is True
        assert "ble" in t.active_sources
        assert "lora" in t.active_sources  # Keeps history
        assert t.confidence == 70.0  # 40 + 30

    def test_mqtt_promotes_anonymous_track(self, engine, lora_beacon):
        engine.process_lora(lora_beacon)
        payload = {
            "siren": True,
            "priority": 3,
            "gps": {"lat": 19.0654, "lon": 72.8647, "spd": 60.0}
        }
        engine.process_mqtt("FIRE-11", payload)
        
        assert "FIRE-11" in engine._tracks
        t = engine._tracks["FIRE-11"]
        assert t.is_identified
        assert t.priority == 3
        assert "mqtt" in t.active_sources

    def test_mqtt_without_lora_spawns_identified_track(self, engine):
        payload = {"siren": False, "priority": 1, "gps": {"lat": 10.0, "lon": 20.0}}
        engine.process_mqtt("POLICE-99", payload)
        
        tracks = engine.get_tracks()
        assert len(tracks) == 1
        assert tracks[0].track_id == "POLICE-99"
        assert tracks[0].is_identified is True

    def test_local_audio_boosts_active_siren_tracks(self, engine, lora_beacon):
        # Track 1 has siren ON
        engine.process_lora(lora_beacon)
        
        # Track 2 has siren OFF
        l2 = ParsedLoRaBeacon(**lora_beacon.__dict__)
        l2.lat += 0.01
        l2.siren_active = False
        engine.process_lora(l2)
        
        assert engine.get_tracks()[0].confidence == 40.0
        assert engine.get_tracks()[1].confidence == 40.0
        
        # Audio detects siren
        engine.process_local_audio(True)
        
        # Only Track 1 should get boosted
        tracks = list(engine._tracks.values())
        t1 = [t for t in tracks if t.siren_active][0]
        t2 = [t for t in tracks if not t.siren_active][0]
        
        assert t1.confidence == 45.0
        assert "audio" in t1.active_sources
        assert t2.confidence == 40.0
        assert "audio" not in t2.active_sources

    def test_tick_decays_confidence(self, engine):
        t = FusionTrack(
            track_id="TEST", is_identified=True, priority=1,
            lat=0.0, lon=0.0, speed_kmh=0.0, heading_deg=0.0,
            siren_active=False,
            first_seen=0.0, last_seen=time.monotonic() - 3.0,  # 3s old
            confidence=50.0
        )
        engine._tracks["TEST"] = t
        
        engine.tick()
        assert t.confidence == 49.5  # Decayed by 0.5 because age > 2s

    def test_tick_prunes_stale_track(self, engine):
        t = FusionTrack(
            track_id="TEST", is_identified=True, priority=1,
            lat=0.0, lon=0.0, speed_kmh=0.0, heading_deg=0.0,
            siren_active=False,
            first_seen=0.0, last_seen=time.monotonic() - 31.0,  # 31s old
            confidence=0.0
        )
        engine._tracks["TEST"] = t
        
        engine.tick()
        assert len(engine.get_tracks()) == 0

    def test_tick_removes_stale_sources(self, engine):
        t = FusionTrack(
            track_id="TEST", is_identified=True, priority=1,
            lat=0.0, lon=0.0, speed_kmh=0.0, heading_deg=0.0,
            siren_active=False,
            first_seen=0.0, last_seen=time.monotonic() - 6.0,  # 6s old > source decay (5s)
            confidence=80.0,
            active_sources={"lora", "mqtt"}
        )
        engine._tracks["TEST"] = t
        
        engine.tick()
        assert len(t.active_sources) == 0
