"""
LoRa Beacon Parser (Edge Node)
================================
Decodes the 14-byte compact binary LoRa payload broadcast by
approaching emergency vehicles.

Maintains a brief cache of recent coordinates to prevent processing
duplicate bursts from the same location within a sub-second window.

Payload structure (14 bytes):
  - lat:      int32 (4 bytes)  → x 1e-7 deg
  - lon:      int32 (4 bytes)  → x 1e-7 deg
  - speed:    uint16 (2 bytes) → x 0.1 km/h
  - heading:  uint16 (2 bytes) → x 0.1 deg
  - flags:    uint8 (1 byte)
      bit 7: siren_active
      bit 6: has_destination
      bits 5-3: fix_quality (0-7)
  - priority: uint8 (1 byte)
"""
import struct
import time
from dataclasses import dataclass
from typing import Optional

from loguru import logger


@dataclass
class ParsedLoRaBeacon:
    received_at_ts: float  # monotonic timestamp
    lat: float
    lon: float
    speed_kmh: float
    heading_deg: float
    siren_active: bool
    has_dest: bool
    fix_quality: int
    priority: int
    rssi_dbm: float
    snr_db: float


class LoRaBeaconParser:
    """
    Parses and deduplicates incoming 14-byte LoRa packets.
    """

    def __init__(self, cache_ttl_s: float = 1.0) -> None:
        self._cache_ttl_s = cache_ttl_s
        # Store last received (lat, lon) keyed by timestamp to deduplicate
        self._recent_beacons: list[tuple[float, float, float]] = []

    def parse(self, payload: bytes, rssi: float, snr: float) -> Optional[ParsedLoRaBeacon]:
        """
        Decode the payload. Returns None if invalid or perfectly duplicated
        within the TTL window.
        """
        if len(payload) != 14:
            logger.warning(f"Parser: Dropped packet with invalid length: {len(payload)} bytes")
            return None

        try:
            lat_i, lon_i, spd_i, hdg_i, flags, priority = struct.unpack(">iiHHBB", payload)
            
            lat = lat_i / 1e7
            lon = lon_i / 1e7

            # Deduplication
            if self._is_duplicate(lat, lon):
                logger.debug("Parser: Dropped duplicate packet from exactly same coordinates")
                return None

            beacon = ParsedLoRaBeacon(
                received_at_ts=time.monotonic(),
                lat=lat,
                lon=lon,
                speed_kmh=spd_i / 10.0,
                heading_deg=hdg_i / 10.0,
                siren_active=bool(flags & (1 << 7)),
                has_dest=bool(flags & (1 << 6)),
                fix_quality=(flags >> 3) & 0x7,
                priority=priority,
                rssi_dbm=rssi,
                snr_db=snr,
            )

            self._record_receipt(lat, lon)
            return beacon

        except struct.error as exc:
            logger.error(f"Parser: Failed to decode 14-byte payload — {exc}")
            return None

    def _is_duplicate(self, lat: float, lon: float) -> bool:
        """Returns True if the exact same lat/lon was received within the TTL window."""
        self._prune_cache()
        for ts, cached_lat, cached_lon in self._recent_beacons:
            # We use a strict exact match because even 0.0000001 deg is unique.
            # If the exact identical struct is received, it's a re-transmitted burst
            # or echo rather than a fresh vehicle movement.
            if lat == cached_lat and lon == cached_lon:
                return True
        return False

    def _record_receipt(self, lat: float, lon: float) -> None:
        self._recent_beacons.append((time.monotonic(), lat, lon))
        
    def _prune_cache(self) -> None:
        now = time.monotonic()
        self._recent_beacons = [
            (ts, la, lo) for (ts, la, lo) in self._recent_beacons
            if now - ts <= self._cache_ttl_s
        ]
