"""
GPS Reader Module — u-blox NEO-9M via UART
============================================
Reads NMEA 0183 sentences from the NEO-9M GPS module over a serial port.
Parses GGA (fix data) and RMC (speed, heading) sentences.
Applies quality filters: min satellites, max accuracy, heading smoothing.

Hardware:
    NEO-9M TX  →  Pi Zero 2W GPIO14 (RX, pin 8)
    NEO-9M RX  →  Pi Zero 2W GPIO15 (TX, pin 10)
    NEO-9M VCC →  3.3V (pin 1)
    NEO-9M GND →  GND  (pin 6)
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import pynmea2
import serial
from loguru import logger

from vsu.src.config import VSUConfig


# ─────────────────────────────────────────────────────────────
# Data class: one GPS sample
# ─────────────────────────────────────────────────────────────

@dataclass
class GPSSample:
    lat:          float
    lon:          float
    alt_m:        float
    speed_kmh:    float
    heading_deg:  float
    accuracy_m:   float       # Horizontal dilution of precision converted to metres
    satellites:   int
    fix_quality:  int         # 0=no fix, 1=GPS, 2=DGPS, 4=RTK
    timestamp:    datetime


# ─────────────────────────────────────────────────────────────
# GPS Reader
# ─────────────────────────────────────────────────────────────

class GPSReader:
    """
    Background-thread GPS reader for u-blox NEO-9M.
    Continuously reads NMEA from serial port. Latest fix is always available
    via get_latest_fix() without blocking the main thread.

    Usage:
        reader = GPSReader(config)
        reader.start()
        sample = reader.get_latest_fix()  # non-blocking
        reader.stop()
    """

    # Conversion: HDOP * 2.5 ≈ metres CEP estimate
    HDOP_TO_METRES = 2.5

    def __init__(self, config: VSUConfig) -> None:
        self._cfg = config
        self._lock = threading.Lock()
        self._latest: Optional[GPSSample] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._has_fix = threading.Event()

        # Kalman-like heading smoother (exponential moving average)
        self._smoothed_heading: Optional[float] = None
        self._heading_alpha = 0.2   # lower = smoother (more lag)

    # ─────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────

    def start(self) -> None:
        """Start the background reader thread."""
        logger.info(
            f"GPS: Opening serial port {self._cfg.gps_serial_port} "
            f"@ {self._cfg.gps_baud_rate} baud"
        )
        self._running = True
        self._thread = threading.Thread(target=self._reader_loop, daemon=True, name="gps-reader")
        self._thread.start()

    def stop(self) -> None:
        """Stop the background reader thread gracefully."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        logger.info("GPS: Reader stopped.")

    def get_latest_fix(self) -> Optional[GPSSample]:
        """Return the most recent valid GPS fix (or None if no fix yet)."""
        with self._lock:
            return self._latest

    def wait_for_fix(self, timeout_s: float = 60.0) -> bool:
        """Block until a valid GPS fix is available (up to timeout_s seconds)."""
        acquired = self._has_fix.wait(timeout=timeout_s)
        if not acquired:
            logger.warning("GPS: Timed out waiting for first fix.")
        return acquired

    def has_fix(self) -> bool:
        return self._has_fix.is_set()

    # ─────────────────────────────────────────────
    # Private: background serial reader loop
    # ─────────────────────────────────────────────

    def _reader_loop(self) -> None:
        """Continuously read and parse NMEA sentences from serial port."""
        try:
            ser = serial.Serial(
                port=self._cfg.gps_serial_port,
                baudrate=self._cfg.gps_baud_rate,
                timeout=self._cfg.gps_timeout_s,
            )
        except serial.SerialException as exc:
            logger.error(f"GPS: Cannot open serial port — {exc}. Running in MOCK mode.")
            self._mock_loop()
            return

        logger.info("GPS: Serial port open, waiting for NMEA sentences...")

        gga: Optional[pynmea2.GGA] = None
        rmc: Optional[pynmea2.RMC] = None

        while self._running:
            try:
                raw_line = ser.readline().decode("ascii", errors="replace").strip()
                if not raw_line.startswith("$"):
                    continue

                msg = pynmea2.parse(raw_line)

                if isinstance(msg, pynmea2.types.talker.GGA):
                    gga = msg
                elif isinstance(msg, pynmea2.types.talker.RMC):
                    rmc = msg

                # Build a full sample when we have both GGA + RMC
                if gga and rmc:
                    sample = self._build_sample(gga, rmc)
                    if sample:
                        with self._lock:
                            self._latest = sample
                        self._has_fix.set()

            except pynmea2.ParseError:
                pass   # Corrupt NMEA line — skip silently
            except serial.SerialException as exc:
                logger.error(f"GPS: Serial error — {exc}")
                time.sleep(1)
            except Exception as exc:
                logger.warning(f"GPS: Unexpected error — {exc}")

        ser.close()

    def _build_sample(
        self,
        gga: pynmea2.GGA,
        rmc: pynmea2.RMC,
    ) -> Optional[GPSSample]:
        """Parse and validate a GGA + RMC pair into a GPSSample."""
        try:
            fix_quality = int(gga.gps_qual or 0)
            num_sats    = int(gga.num_sats or 0)
            hdop        = float(gga.horizontal_dil or 99.9)
            accuracy_m  = hdop * self.HDOP_TO_METRES

            # Quality gates
            if fix_quality == 0:
                return None   # No fix
            if num_sats < self._cfg.gps_min_sats:
                return None   # Not enough satellites
            if accuracy_m > self._cfg.gps_max_accuracy_m:
                logger.debug(f"GPS: Fix rejected — accuracy {accuracy_m:.1f}m > {self._cfg.gps_max_accuracy_m}m")
                return None

            lat = float(gga.latitude)
            lon = float(gga.longitude)
            alt_m = float(gga.altitude or 0.0)

            # Speed: RMC gives knots → convert to km/h
            speed_knots = float(rmc.spd_over_grnd or 0.0)
            speed_kmh   = speed_knots * 1.852

            # Heading from RMC (true course over ground)
            raw_heading = float(rmc.true_course or 0.0)
            heading_deg = self._smooth_heading(raw_heading)

            # Timestamp: combine GPS date + time → UTC datetime
            gps_ts = datetime.combine(
                rmc.datestamp,
                rmc.timestamp,
                tzinfo=timezone.utc
            )

            return GPSSample(
                lat=round(lat, 7),
                lon=round(lon, 7),
                alt_m=round(alt_m, 1),
                speed_kmh=round(speed_kmh, 2),
                heading_deg=round(heading_deg, 1),
                accuracy_m=round(accuracy_m, 2),
                satellites=num_sats,
                fix_quality=fix_quality,
                timestamp=gps_ts,
            )

        except Exception as exc:
            logger.warning(f"GPS: Sample build failed — {exc}")
            return None

    def _smooth_heading(self, raw_deg: float) -> float:
        """
        Exponential moving average for heading.
        Handles circular wrap-around (e.g. 359° → 1°).
        """
        if self._smoothed_heading is None:
            self._smoothed_heading = raw_deg
            return raw_deg

        # Wrap-around correction
        diff = raw_deg - self._smoothed_heading
        if diff > 180:
            diff -= 360
        elif diff < -180:
            diff += 360

        self._smoothed_heading = (self._smoothed_heading + self._heading_alpha * diff) % 360
        return self._smoothed_heading

    # ─────────────────────────────────────────────
    # Mock mode (no hardware — for dev/testing)
    # ─────────────────────────────────────────────

    def _mock_loop(self) -> None:
        """
        Feeds simulated GPS data when running on a dev machine without hardware.
        Simulates an ambulance driving west through Mumbai at 60 km/h.
        """
        import math
        logger.warning("GPS: ⚠️  Running in MOCK mode (no hardware)")

        lat, lon = 19.0654, 72.8647   # Starts at BKC Mumbai
        heading  = 275.0               # Heading west
        speed    = 60.0                # km/h

        while self._running:
            # Move position based on speed + heading
            dist_deg = (speed / 3.6) * 0.5 / 111_320   # 0.5s step in degrees
            lat += dist_deg * math.sin(math.radians(heading)) * -1
            lon += dist_deg * math.cos(math.radians(heading))

            sample = GPSSample(
                lat=round(lat, 7),
                lon=round(lon, 7),
                alt_m=12.0,
                speed_kmh=speed + (hash(str(lat)) % 5 - 2),   # slight jitter
                heading_deg=heading,
                accuracy_m=2.5,
                satellites=10,
                fix_quality=1,
                timestamp=datetime.now(timezone.utc),
            )
            with self._lock:
                self._latest = sample
            self._has_fix.set()
            time.sleep(0.5)
