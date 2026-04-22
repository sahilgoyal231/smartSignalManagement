"""
Beacon Payload Builder
========================
Constructs the JSON beacon payload broadcast by the VSU.
Combines GPS fix, vehicle identity, siren state, and battery level
into a structured, versioned dict ready for JSON serialisation,
LoRa transmission, and MQTT publishing.

Payload schema (v1):
{
  "v":            1,                    -- schema version
  "vehicle_id":   "AMB-MH-042",
  "vehicle_type": "AMBULANCE",
  "priority":     2,
  "city":         "Mumbai",
  "ts":           "2026-03-06T14:30:00.123Z",  -- UTC ISO-8601
  "gps": {
    "lat":        19.0654,
    "lon":        72.8647,
    "alt":        12.0,
    "spd":        62.4,               -- km/h
    "hdg":        275.3,              -- degrees
    "acc":        2.5,                -- metres
    "sat":        10,
    "fix":        1
  },
  "siren":        true,
  "bat":          92,                 -- battery %
  "dest": {
    "lat": 19.0456,
    "lon": 72.8272
  } | null,
  "nonce":        "a3f1c2e4...",      -- 16-byte hex (replay prevention)
  "sig":          "..."               -- ECDSA-P256 hex (added by signer module)
}
"""
from __future__ import annotations

import json
import os
import secrets
import time
from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from vsu.src.config import VSUConfig
from vsu.src.gps_reader import GPSSample


# ─────────────────────────────────────────────────────────────
# Dead-reckoning module (fallback when GPS degrades)
# ─────────────────────────────────────────────────────────────

import math

class DeadReckoning:
    """
    Carries forward the last known good GPS position using speed + heading.
    Used when GPS accuracy degrades beyond threshold or fix is lost briefly.
    Errors accumulate quickly — maximum 15 seconds of useful DR.
    """
    MAX_DR_SECONDS = 15.0

    def __init__(self) -> None:
        self._last_good: Optional[GPSSample] = None
        self._last_good_time: Optional[float] = None

    def update(self, sample: GPSSample) -> None:
        """Call every time a valid GPS fix arrives."""
        self._last_good = sample
        self._last_good_time = time.monotonic()

    def extrapolate(self) -> Optional[GPSSample]:
        """
        Returns estimated position based on last good fix + elapsed time.
        Returns None if last fix is too old to be reliable.
        """
        if not self._last_good or not self._last_good_time:
            return None

        elapsed = time.monotonic() - self._last_good_time
        if elapsed > self.MAX_DR_SECONDS:
            logger.warning(f"DR: Last GPS fix {elapsed:.0f}s old — too stale for dead reckoning")
            return None

        s = self._last_good
        # Distance travelled (metres) in elapsed time
        dist_m = (s.speed_kmh / 3.6) * elapsed

        # Convert to lat/lon delta using equirectangular approximation
        delta_lat = (dist_m * math.cos(math.radians(s.heading_deg))) / 111_320
        delta_lon = (dist_m * math.sin(math.radians(s.heading_deg))) / (
            111_320 * math.cos(math.radians(s.lat))
        )

        from dataclasses import replace
        dr_sample = replace(
            s,
            lat=round(s.lat + delta_lat, 7),
            lon=round(s.lon + delta_lon, 7),
            accuracy_m=s.accuracy_m + elapsed * 0.5,   # Accuracy degrades at ~0.5m/s
            timestamp=datetime.now(timezone.utc),
        )
        logger.debug(f"DR: Extrapolated {elapsed:.1f}s → ({dr_sample.lat}, {dr_sample.lon})")
        return dr_sample


# ─────────────────────────────────────────────────────────────
# Beacon Builder
# ─────────────────────────────────────────────────────────────

class BeaconBuilder:
    """
    Constructs and serialises beacon payloads for transmission.

    Usage:
        builder = BeaconBuilder(config)
        payload = builder.build(gps_fix, siren_active=True, battery_pct=92)
        json_bytes = builder.to_json_bytes(payload)
        lora_bytes = builder.to_lora_bytes(payload)  # compact binary for LoRa
    """

    SCHEMA_VERSION = 1

    def __init__(self, config: VSUConfig) -> None:
        self._cfg = config
        self._dr = DeadReckoning()
        self._last_payload: Optional[dict] = None

    # ─────────────────────────────────────────────
    # Build payload dict
    # ─────────────────────────────────────────────

    def build(
        self,
        gps: Optional[GPSSample],
        siren_active: bool,
        battery_pct: int,
        destination_lat: Optional[float] = None,
        destination_lon: Optional[float] = None,
    ) -> Optional[dict]:
        """
        Builds the full beacon payload dict.

        Returns None if no GPS position is available at all
        (neither fresh fix nor dead-reckoned estimate).
        """
        # Get position: fresh GPS → dead reckoning → fail
        position: Optional[GPSSample] = None
        position_source = "gps"

        if gps and gps.accuracy_m <= self._cfg.gps_max_accuracy_m:
            position = gps
            self._dr.update(gps)       # Feed valid fix to DR engine
        else:
            position = self._dr.extrapolate()
            position_source = "dead_reckoning"
            if position:
                logger.warning(
                    f"Beacon: Using dead-reckoned position (accuracy ~{position.accuracy_m:.1f}m)"
                )

        if not position:
            logger.error("Beacon: No GPS position available — beacon suppressed")
            return None

        # Build destination block
        dest = None
        if destination_lat and destination_lon:
            dest = {"lat": destination_lat, "lon": destination_lon}
        elif self._cfg.home_hospital_lat and self._cfg.home_hospital_lon:
            dest = {
                "lat": self._cfg.home_hospital_lat,
                "lon": self._cfg.home_hospital_lon,
            }

        # Build nonce (16 random bytes as hex — prevents replay attacks)
        nonce = secrets.token_hex(16)

        payload = {
            "v":            self.SCHEMA_VERSION,
            "vehicle_id":   self._cfg.vehicle_id,
            "vehicle_type": self._cfg.vehicle_type,
            "priority":     self._cfg.priority_class,
            "city":         self._cfg.city,
            "ts":           datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "gps": {
                "lat": position.lat,
                "lon": position.lon,
                "alt": position.alt_m,
                "spd": position.speed_kmh,
                "hdg": position.heading_deg,
                "acc": position.accuracy_m,
                "sat": position.satellites,
                "fix": position.fix_quality,
                "src": position_source,
            },
            "siren":  siren_active,
            "bat":    max(0, min(100, battery_pct)),
            "dest":   dest,
            "nonce":  nonce,
            "sig":    None,            # Filled in by the signer module (Step 5)
        }

        self._last_payload = payload
        return payload

    # ─────────────────────────────────────────────
    # Serialisation
    # ─────────────────────────────────────────────

    def to_json_bytes(self, payload: dict, compact: bool = False) -> bytes:
        """Serialise payload to UTF-8 JSON bytes for MQTT publishing."""
        separators = (",", ":") if compact else (", ", ": ")
        return json.dumps(payload, separators=separators).encode("utf-8")

    def to_lora_bytes(self, payload: dict) -> bytes:
        """
        Ultra-compact binary encoding for LoRa (to minimise airtime).
        Packs: lat(4B), lon(4B), speed(2B), heading(2B), flags(1B), priority(1B) = 14 bytes

        Flags byte layout:
          bit 7: siren_active
          bit 6: has_destination
          bits 5-3: fix_quality (0-7)
          bits 2-0: reserved

        Vehicle ID is communicated separately via the authenticated MQTT channel.
        LoRa is low-bandwidth — this compact format fits in a single LoRa packet.
        """
        import struct

        gps    = payload["gps"]
        flags  = 0
        if payload["siren"]:
            flags |= (1 << 7)
        if payload["dest"]:
            flags |= (1 << 6)
        flags |= (gps["fix"] & 0x7) << 3

        # lat/lon: encode as signed int32 (multiply by 1e7 for 0.1 µm precision)
        lat_i = int(round(gps["lat"] * 1e7))
        lon_i = int(round(gps["lon"] * 1e7))
        spd_i = int(round(gps["spd"] * 10))        # 0.1 km/h precision
        hdg_i = int(round(gps["hdg"] * 10)) % 3600  # 0.1° precision, 0–3599

        try:
            packed = struct.pack(
                ">iiHHBB",
                lat_i, lon_i, spd_i, hdg_i,
                flags, payload["priority"]
            )
            return packed
        except struct.error as exc:
            logger.error(f"LoRa pack error: {exc}. Falling back to JSON.")
            return self.to_json_bytes(payload, compact=True)

    @staticmethod
    def from_lora_bytes(data: bytes) -> dict:
        """
        Decode a compact LoRa binary beacon (mirror of to_lora_bytes).
        Used by the edge node LoRa receiver.
        """
        import struct

        if len(data) < 14:
            raise ValueError(f"LoRa packet too short: {len(data)} bytes")

        lat_i, lon_i, spd_i, hdg_i, flags, priority = struct.unpack(">iiHHBB", data[:14])

        return {
            "lat":          lat_i / 1e7,
            "lon":          lon_i / 1e7,
            "speed_kmh":    spd_i / 10.0,
            "heading_deg":  hdg_i / 10.0,
            "siren_active": bool(flags & (1 << 7)),
            "has_dest":     bool(flags & (1 << 6)),
            "fix_quality":  (flags >> 3) & 0x7,
            "priority":     priority,
        }

    def get_last_payload(self) -> Optional[dict]:
        return self._last_payload
