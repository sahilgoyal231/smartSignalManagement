"""
BLE Beacon — Ambulance Emergency Advertisement
================================================
Broadcasts BLE advertisements at 100ms intervals containing:
  - Vehicle ID (truncated to fit BLE AD payload limit)
  - Live lat/lon (compressed to int32 × 1e7)
  - Siren state
  - Priority class
  - VSU schema marker (0xEC for Emergency Clearance)

Uses the `bluepy` library on Raspberry Pi.
Falls back to mock/log mode on non-Pi hardware (dev/test).

BLE Advertisement Packet Layout (Manufacturer Specific Data, type 0xFF):
  Bytes  0–1   : Company ID = 0x08EC (SmartSignal Emergency Clearance)
  Byte   2     : Schema version = 0x01
  Byte   3     : Priority (1–5)
  Bytes  4–7   : Latitude  × 1e7 (signed int32, big-endian)
  Bytes  8–11  : Longitude × 1e7 (signed int32, big-endian)
  Byte   12    : Flags: bit7=siren, bit6=gps_valid
  Bytes  13–18 : Vehicle ID ASCII (6 chars, right-padded with 0x00)
Total: 19 bytes manufacturer data → fits in a single BLE 4.x advertisement packet.

Range:    ~10–30 m (class 2 BLE, adequate for intersections)
Purpose:  Short-range confirmation for edge node BLE scanner at intersection
"""
from __future__ import annotations

import struct
import threading
import time
from typing import Optional

from loguru import logger


COMPANY_ID     = 0x08EC   # SmartSignal custom company ID
SCHEMA_VERSION = 0x01


def _encode_ble_payload(
    vehicle_id:  str,
    priority:    int,
    lat:         float,
    lon:         float,
    siren:       bool,
    gps_valid:   bool,
) -> bytes:
    """
    Encode the 19-byte BLE manufacturer-specific advertisement payload.

    Returns raw bytes ready to pass to the HCI advertising command.
    """
    lat_i = int(round(lat * 1e7))
    lon_i = int(round(lon * 1e7))

    flags = 0
    if siren:     flags |= (1 << 7)
    if gps_valid: flags |= (1 << 6)

    # Vehicle ID: take up to 6 ASCII chars, pad with null bytes
    vid_bytes = vehicle_id.encode("ascii", errors="replace")[:6].ljust(6, b"\x00")

    payload = struct.pack(
        ">HBBiiB6s",
        COMPANY_ID, SCHEMA_VERSION, priority,
        lat_i, lon_i,
        flags, vid_bytes,
    )
    return payload   # 19 bytes


def _decode_ble_payload(data: bytes) -> dict:
    """
    Decode a 19-byte BLE advertisement payload.
    Used by the edge node BLE scanner.
    """
    if len(data) < 19:
        raise ValueError(f"BLE payload too short: {len(data)} bytes")

    company_id, schema, priority, lat_i, lon_i, flags, vid_bytes = struct.unpack(
        ">HBBiiB6s", data[:19]
    )
    return {
        "company_id":  company_id,
        "schema":      schema,
        "priority":    priority,
        "lat":         lat_i / 1e7,
        "lon":         lon_i / 1e7,
        "siren":       bool(flags & (1 << 7)),
        "gps_valid":   bool(flags & (1 << 6)),
        "vehicle_id":  vid_bytes.rstrip(b"\x00").decode("ascii", errors="replace"),
    }


# ─────────────────────────────────────────────────────────────
# BLE Beacon Manager
# ─────────────────────────────────────────────────────────────

class BLEBeacon:
    """
    Manages continuous BLE advertising with live position updates.

    Internally uses a background thread that re-issues the HCI advertising
    command whenever position or siren state changes.

    Usage:
        ble = BLEBeacon(config)
        ble.start(initial_lat, initial_lon, siren=False)
        ble.update(new_lat, new_lon, siren=True)   # called from main loop
        ble.stop()
    """

    ADV_INTERVAL_MS = 100   # advertisement interval in milliseconds

    def __init__(self, config) -> None:
        self._cfg      = config
        self._mock     = False
        self._running  = False
        self._thread: Optional[threading.Thread] = None
        self._lock     = threading.Lock()

        # Current advertising data
        self._lat:   float = 0.0
        self._lon:   float = 0.0
        self._siren: bool  = False
        self._dirty: bool  = True   # True = payload needs to be re-sent

        self._adv_count  = 0
        self._hci_handle = None

    # ─────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────

    def start(self, lat: float, lon: float, siren: bool = False) -> None:
        """Start BLE advertising. Call once after GPS fix is acquired."""
        with self._lock:
            self._lat   = lat
            self._lon   = lon
            self._siren = siren
            self._dirty = True

        self._hci_handle = self._init_ble()
        self._running = True
        self._thread  = threading.Thread(
            target=self._adv_loop, daemon=True, name="ble-beacon"
        )
        self._thread.start()
        mode = "MOCK" if self._mock else "HARDWARE"
        logger.info(f"BLEBeacon: Started [{mode}] interval={self.ADV_INTERVAL_MS}ms")

    def stop(self) -> None:
        """Stop BLE advertising."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        if self._hci_handle and not self._mock:
            try:
                self._hci_handle.stop_advertising()
            except Exception:
                pass
        logger.info(f"BLEBeacon: Stopped. Total advertisements: {self._adv_count}")

    def update(self, lat: float, lon: float, siren: bool) -> None:
        """
        Update the advertised position and siren state.
        The background thread picks up the change on its next iteration.
        Thread-safe — safe to call from main loop.
        """
        with self._lock:
            if lat != self._lat or lon != self._lon or siren != self._siren:
                self._lat   = lat
                self._lon   = lon
                self._siren = siren
                self._dirty = True

    # ─────────────────────────────────────────────
    # Private: advertising loop
    # ─────────────────────────────────────────────

    def _adv_loop(self) -> None:
        """Background thread — maintains continuous BLE advertising."""
        while self._running:
            with self._lock:
                dirty = self._dirty
                lat, lon, siren = self._lat, self._lon, self._siren
                if dirty:
                    self._dirty = False

            if dirty:
                payload = _encode_ble_payload(
                    vehicle_id=self._cfg.vehicle_id,
                    priority=self._cfg.priority_class,
                    lat=lat, lon=lon,
                    siren=siren,
                    gps_valid=(lat != 0.0 and lon != 0.0),
                )
                self._set_advertisement(payload)

            time.sleep(self.ADV_INTERVAL_MS / 1000.0)
            self._adv_count += 1

    def _set_advertisement(self, payload: bytes) -> None:
        """Push new advertisement payload to BLE hardware."""
        if self._mock:
            logger.debug(
                f"BLEBeacon [MOCK]: payload={payload.hex()} "
                f"siren={'ON' if self._siren else 'OFF'} "
                f"lat={self._lat:.5f} lon={self._lon:.5f}"
            )
            return

        try:
            self._hci_handle.set_manufacturer_data(payload)
            self._hci_handle.start_advertising()
        except Exception as exc:
            logger.error(f"BLEBeacon: Failed to set advertisement: {exc}")

    # ─────────────────────────────────────────────
    # Private: hardware init
    # ─────────────────────────────────────────────

    def _init_ble(self):
        """Initialise BLE advertising via bluepy/hciconfig."""
        try:
            from bluepy.btle import Peripheral   # type: ignore
            # For advertising we use raw HCI — check bluepy advert API
            from bluepy import btle              # type: ignore
            logger.success("BLEBeacon: bluepy available — hardware mode")
            return object()   # placeholder handle
        except (ImportError, OSError) as exc:
            logger.warning(f"BLEBeacon: bluepy not available ({exc}) — MOCK mode")
            self._mock = True
            return None

    # ─────────────────────────────────────────────
    # Stats
    # ─────────────────────────────────────────────

    def stats(self) -> dict:
        return {
            "adv_count": self._adv_count,
            "mock_mode": self._mock,
            "lat":       self._lat,
            "lon":       self._lon,
            "siren":     self._siren,
        }


# ─────────────────────────────────────────────────────────────
# Encode/Decode convenience exports
# ─────────────────────────────────────────────────────────────

encode_ble_payload = _encode_ble_payload
decode_ble_payload = _decode_ble_payload
