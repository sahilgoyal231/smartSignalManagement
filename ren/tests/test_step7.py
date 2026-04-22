"""
Unit Tests — Step 7: Edge Node loosely LoRa Receival + Parsing
==============================================================
Tests the ren/src modules without hardware.
"""
import struct
import time
from unittest.mock import MagicMock

import pytest

from ren.src.lora_rx import LoRaRX
from ren.src.beacon_parser import LoRaBeaconParser, ParsedLoRaBeacon


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def mock_config():
    cfg = MagicMock()
    cfg.node_id = "NODE-001"
    cfg.lat = 19.0650
    cfg.lon = 72.8640
    cfg.lora_frequency_mhz = 433.0
    return cfg

@pytest.fixture
def parser():
    return LoRaBeaconParser(cache_ttl_s=0.5)

@pytest.fixture
def valid_14b_payload():
    # Construct a valid payload: (lat, lon, spd, hdg, flags, priority)
    lat_i = int(round(19.0654 * 1e7))
    lon_i = int(round(72.8647 * 1e7))
    spd_i = int(round(62.4 * 10))
    hdg_i = int(round(275.3 * 10))
    # Flags: siren=True(bit7), dest=False(bit6), fix=4 (bits 5-3)
    flags = (1 << 7) | (0 << 6) | (4 << 3)
    priority = 2
    return struct.pack(">iiHHBB", lat_i, lon_i, spd_i, hdg_i, flags, priority)


# ─────────────────────────────────────────────────────────────
# LoRa RX Driver Tests
# ─────────────────────────────────────────────────────────────

class TestLoRaRX:

    def test_mock_mode_initialised_without_hardware(self, mock_config):
        # pyLora won't be installed in our test env usually
        rx = LoRaRX(mock_config, lambda p, r, s: None)
        assert rx._mock is True

    def test_mock_mode_simulates_packets(self, mock_config):
        received = []
        def handler(payload, rssi, snr):
            received.append((payload, rssi, snr))
            rx.stop() # Stop immediately after first packet
            
        rx = LoRaRX(mock_config, handler)
        # Hack the sleep to run faster inline without background threading
        rx._mock = True
        
        # Call loop directly in test (with mock sleep to avoid 2s delay)
        import time
        from unittest.mock import patch
        
        rx._running = True
        with patch('time.sleep', return_value=None):
            # Hack: break the while loop after 1 iteration
            def mock_sleep_interrupt(*args):
                rx._running = False
            time.sleep = mock_sleep_interrupt
            rx._mock_loop()
            
        assert len(received) == 1
        payload, rssi, snr = received[0]
        assert len(payload) == 14
        assert isinstance(rssi, float)
        assert snr == 8.5
        assert rx.stats()["rx_count"] == 1


# ─────────────────────────────────────────────────────────────
# Beacon Parser Tests
# ─────────────────────────────────────────────────────────────

class TestBeaconParser:

    def test_valid_packet_parsed_correctly(self, parser, valid_14b_payload):
        beacon = parser.parse(valid_14b_payload, rssi=-42.0, snr=9.5)
        
        assert beacon is not None
        assert isinstance(beacon, ParsedLoRaBeacon)
        assert beacon.lat == pytest.approx(19.0654, abs=1e-5)
        assert beacon.lon == pytest.approx(72.8647, abs=1e-5)
        assert beacon.speed_kmh == 62.4
        assert beacon.heading_deg == 275.3
        assert beacon.siren_active is True
        assert beacon.has_dest is False
        assert beacon.fix_quality == 4
        assert beacon.priority == 2
        assert beacon.rssi_dbm == -42.0

    def test_short_packet_rejected(self, parser):
        assert parser.parse(b"\x00" * 13, -50.0, 5.0) is None
        
    def test_long_packet_rejected(self, parser):
        assert parser.parse(b"\x00" * 15, -50.0, 5.0) is None

    def test_exact_duplicate_rejected_within_ttl(self, parser, valid_14b_payload):
        # First parse succeeds
        b1 = parser.parse(valid_14b_payload, rssi=-40.0, snr=9.0)
        assert b1 is not None
        
        # Immediate second parse of EXACT same packet fails (duplicate)
        b2 = parser.parse(valid_14b_payload, rssi=-40.0, snr=9.0)
        assert b2 is None

    def test_duplicate_accepted_after_ttl_expires(self, parser, valid_14b_payload):
        b1 = parser.parse(valid_14b_payload, rssi=-40.0, snr=9.0)
        assert b1 is not None
        
        # Forcibly age the cache
        parser._recent_beacons[0] = (parser._recent_beacons[0][0] - 2.0, b1.lat, b1.lon)
        
        # Now it should be accepted again
        b2 = parser.parse(valid_14b_payload, rssi=-40.0, snr=9.0)
        assert b2 is not None

    def test_different_coordinates_accepted(self, parser, valid_14b_payload):
        b1 = parser.parse(valid_14b_payload, rssi=-40.0, snr=9.0)
        assert b1 is not None
        
        # Tweak lon by +1 unit in binary representation
        payload_mut = bytearray(valid_14b_payload)
        payload_mut[7] ^= 0x01
        
        b2 = parser.parse(bytes(payload_mut), rssi=-40.0, snr=9.0)
        assert b2 is not None
