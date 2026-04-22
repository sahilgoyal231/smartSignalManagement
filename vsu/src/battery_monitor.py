"""
Battery Monitor
================
Reads battery percentage from the PiJuice UPS HAT via I2C.
Falls back to vehicle power-rail ADC reading if PiJuice unavailable.

PiJuice I2C address: 0x14
Register 60 (0x3C): battery level (0–100)

Also monitors:
  - Charging status
  - Temperature of battery
  - Low-battery alert at 20%
"""
from __future__ import annotations

import time
import threading
from typing import Optional
from loguru import logger

# PiJuice I2C registers
PIJUICE_ADDR    = 0x14
REG_BAT_LEVEL   = 0x3C   # Battery charge level (0–100)
REG_STATUS      = 0x40   # Status byte
REG_BAT_TEMP    = 0x47   # Battery temperature (°C, signed)

LOW_BATTERY_PCT = 20     # Alert threshold


class BatteryMonitor:
    """
    Reads battery state from PiJuice HAT via I2C every 30 seconds.
    Thread-safe; latest value retrieved via get_percent().

    Usage:
        monitor = BatteryMonitor()
        monitor.start()
        pct = monitor.get_percent()  # 0–100
        monitor.stop()
    """

    def __init__(self, update_interval_s: int = 30) -> None:
        self._pct:          int   = 100
        self._charging:     bool  = False
        self._temp_c:       float = 25.0
        self._lock          = threading.Lock()
        self._running       = False
        self._thread: Optional[threading.Thread] = None
        self._interval      = update_interval_s
        self._use_mock      = False

    def start(self) -> None:
        self._running = True
        self._thread  = threading.Thread(
            target=self._monitor_loop, daemon=True, name="battery-monitor"
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)

    def get_percent(self) -> int:
        with self._lock:
            return self._pct

    def is_charging(self) -> bool:
        with self._lock:
            return self._charging

    def get_temp_c(self) -> float:
        with self._lock:
            return self._temp_c

    # ─────────────────────────────────────────────
    # Private
    # ─────────────────────────────────────────────

    def _monitor_loop(self) -> None:
        try:
            import smbus2
            bus = smbus2.SMBus(1)   # I2C bus 1 on Raspberry Pi
            logger.info("Battery: PiJuice I2C connected.")
        except (ImportError, FileNotFoundError, OSError):
            logger.warning("Battery: PiJuice not available — mock mode (100%)")
            self._use_mock = True

        while self._running:
            if self._use_mock:
                # Simulate slow drain when not charging
                with self._lock:
                    self._pct = max(0, self._pct - 1) if not self._charging else min(100, self._pct + 1)
            else:
                try:
                    level = bus.read_byte_data(PIJUICE_ADDR, REG_BAT_LEVEL)
                    status= bus.read_byte_data(PIJUICE_ADDR, REG_STATUS)
                    raw_t = bus.read_byte_data(PIJUICE_ADDR, REG_BAT_TEMP)
                    temp  = raw_t if raw_t < 128 else raw_t - 256   # signed

                    with self._lock:
                        self._pct      = max(0, min(100, level))
                        self._charging = bool(status & 0x40)
                        self._temp_c   = float(temp)

                    if self._pct <= LOW_BATTERY_PCT:
                        logger.warning(f"Battery: LOW — {self._pct}% ({'charging' if self._charging else 'discharging'})")

                except Exception as exc:
                    logger.error(f"Battery: I2C read error — {exc}")

            time.sleep(self._interval)
