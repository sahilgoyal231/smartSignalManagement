"""
VSU Main Entry Point — v1.0.0  (FULLY WIRED)
=============================================
Runs on Raspberry Pi Zero 2W inside emergency vehicles.

Subsystems started in order:
  1. BatteryMonitor  — PiJuice HAT I2C, mocked on dev
  2. GPSReader       — u-blox NEO-9M UART, mocked on dev
  3. BeaconBuilder   — JSON + LoRa binary, dead-reckoning fallback
  4. BeaconSigner    — ECDSA-P256, ephemeral key on dev
  5. LoRaTX          — RFM95W SPI, mocked on dev
  6. BLEBeacon       — 19-byte mfr advert, mocked on dev
  7. MQTTClient      — TLS 4G uplink, offline-queue fallback
  8. SirenDetector   — GPIO→FFT→mock detection, 4-state FSM

Main loop (0.5 s siren-on / 5 s standby):
  → build → sign → LoRa TX → MQTT pub → BLE update

Signal handling: SIGINT / SIGTERM → graceful shutdown with stats.
"""
from __future__ import annotations

import signal
import sys
import time
from typing import Optional

from loguru import logger

from vsu.src.config import get_config
from vsu.src.gps_reader import GPSReader, GPSSample
from vsu.src.beacon_builder import BeaconBuilder
from vsu.src.battery_monitor import BatteryMonitor
from vsu.src.beacon_signer import BeaconSigner
from vsu.src.lora_tx import LoRaTX
from vsu.src.ble_beacon import BLEBeacon
from vsu.src.mqtt_client import MQTTClient
from vsu.src.siren_detector import SirenDetector


# ─────────────────────────────────────────────────────────────
# Startup banner
# ─────────────────────────────────────────────────────────────

BANNER = """
╔════════════════════════════════════════════╗
║  🚑 Smart Signal — Vehicle-Side Unit       ║
║  v1.0.0  |  Raspberry Pi Zero 2W          ║
╚════════════════════════════════════════════╝
"""


# ─────────────────────────────────────────────────────────────
# VSU Application
# ─────────────────────────────────────────────────────────────

class VSUApp:
    """
    Main VSU application.
    Manages all threads and the main beacon loop.
    """

    ACTIVE_INTERVAL_S  = 0.5   # 2 Hz when siren is on
    STANDBY_INTERVAL_S = 5.0   # 0.2 Hz in standby (saves power and spectrum)

    def __init__(self) -> None:
        self._cfg = get_config()
        self._running  = False

        # Subsystems (all initialised in start())
        self._gps:          Optional[GPSReader]      = None
        self._battery:      Optional[BatteryMonitor] = None
        self._builder:      Optional[BeaconBuilder]  = None
        self._signer:       Optional[BeaconSigner]   = None
        self._lora_tx:      Optional[LoRaTX]         = None
        self._ble_beacon:   Optional[BLEBeacon]      = None
        self._mqtt_client:  Optional[MQTTClient]     = None
        self._siren_det:    Optional[SirenDetector]  = None

        # State
        self._siren_active  = False
        self._beacon_count  = 0

        self._setup_logging()
        self._setup_signals()

    # ─────────────────────────────────────────────
    # Public
    # ─────────────────────────────────────────────

    def start(self) -> None:
        print(BANNER)
        logger.info(f"VSU starting → vehicle={self._cfg.vehicle_id} type={self._cfg.vehicle_type}")
        self._running = True

        # ── Step 1: Battery monitor ──────────────────
        logger.info("Starting battery monitor...")
        self._battery = BatteryMonitor()
        self._battery.start()

        # ── Step 2: GPS reader ───────────────────────
        logger.info("Starting GPS reader...")
        self._gps = GPSReader(self._cfg)
        self._gps.start()

        # ── Step 3: Beacon builder ───────────────────
        self._builder = BeaconBuilder(self._cfg)

        # ── Step 4: Wait for GPS fix ─────────────────
        logger.info("Waiting for GPS fix (timeout 60s)...")
        if self._gps.wait_for_fix(timeout_s=60.0):
            fix = self._gps.get_latest_fix()
            logger.success(
                f"GPS fix acquired → "
                f"({fix.lat}, {fix.lon}) "
                f"sats={fix.satellites} acc={fix.accuracy_m}m"
            )
        else:
            logger.warning("No GPS fix within 60s — continuing in dead-reckoning mode")

        # ── Step 5a: Beacon signer (ECDSA-P256) ─────
        logger.info("Initialising beacon signer...")
        self._signer = BeaconSigner(
            self._cfg.device_key_path,
            self._cfg.device_cert_path,
        )

        # ── Step 5b: LoRa TX ─────────────────────────
        logger.info("Initialising LoRa TX...")
        self._lora_tx = LoRaTX(self._cfg)
        self._lora_tx.start()

        # ── Step 5c: BLE beacon ───────────────────────
        logger.info("Initialising BLE beacon...")
        self._ble_beacon = BLEBeacon(self._cfg)
        first_fix = self._gps.get_latest_fix()
        init_lat  = first_fix.lat if first_fix else 0.0
        init_lon  = first_fix.lon if first_fix else 0.0
        self._ble_beacon.start(init_lat, init_lon, siren=False)

        # ── Step 6a: MQTT client ──────────────────────
        logger.info("Initialising MQTT client...")
        self._mqtt_client = MQTTClient(
            self._cfg,
            on_config_update=self._handle_config_update,
        )
        self._mqtt_client.start()

        # ── Step 6b: Siren detector ───────────────────
        logger.info("Initialising siren detector...")
        self._siren_det = SirenDetector(self._cfg)
        self._siren_det.start()

        # ── Main beacon loop ─────────────────────────
        logger.success(
            f"VSU fully initialised — entering main beacon loop\n"
            f"  Signer:  {self._signer.get_cert_hash()[:16]}...\n"
            f"  LoRa:    {self._lora_tx.stats()}\n"
            f"  MQTT:    {self._mqtt_client.stats()}\n"
            f"  Siren:   {self._siren_det.stats()}"
        )
        self._main_loop()

    def stop(self) -> None:
        logger.info("VSU: Shutting down...")
        self._running = False

        # Stop in reverse startup order
        for name, subsystem in [
            ("SirenDetector",  self._siren_det),
            ("MQTTClient",     self._mqtt_client),
            ("BLEBeacon",      self._ble_beacon),
            ("LoRaTX",         self._lora_tx),
            ("GPSReader",      self._gps),
            ("BatteryMonitor", self._battery),
        ]:
            if subsystem:
                try:
                    subsystem.stop()
                except Exception as exc:
                    logger.warning(f"VSU: {name} stop error — {exc}")

        logger.success(
            f"VSU stopped cleanly.\n"
            f"  Total beacons:  {self._beacon_count}\n"
            f"  MQTT published: {self._mqtt_client.stats()['published'] if self._mqtt_client else 0}\n"
            f"  LoRa TX count:  {self._lora_tx.tx_count if self._lora_tx else 0}"
        )

    # ─────────────────────────────────────────────
    # Main beacon loop
    # ─────────────────────────────────────────────

    def _main_loop(self) -> None:
        while self._running:
            loop_start = time.monotonic()

            # 1. Gather live data
            gps_fix     = self._gps.get_latest_fix() if self._gps else None
            battery_pct = self._battery.get_percent() if self._battery else 100
            siren_on    = self._get_siren_state()

            # 2. Build beacon
            payload = self._builder.build(
                gps=gps_fix,
                siren_active=siren_on,
                battery_pct=battery_pct,
                destination_lat=self._cfg.home_hospital_lat or None,
                destination_lon=self._cfg.home_hospital_lon or None,
            )

            if payload:
                # 3. Sign (Step 5 — no-op for now)
                payload = self._sign_payload(payload)

                # 4. Transmit (Steps 5 & 6 — log for now)
                self._transmit(payload, siren_on)
                self._beacon_count += 1

                if self._beacon_count % 20 == 0:
                    logger.info(
                        f"VSU: beacon #{self._beacon_count} | "
                        f"GPS=({payload['gps']['lat']:.5f},{payload['gps']['lon']:.5f}) | "
                        f"spd={payload['gps']['spd']:.1f}km/h | "
                        f"siren={'ON' if siren_on else 'OFF'} | "
                        f"bat={battery_pct}%"
                    )
            else:
                logger.warning("VSU: No position available — beacon skipped this cycle")

            # 5. Sleep to maintain target interval
            elapsed  = time.monotonic() - loop_start
            interval = self.ACTIVE_INTERVAL_S if siren_on else self.STANDBY_INTERVAL_S
            sleep_s  = max(0.0, interval - elapsed)
            time.sleep(sleep_s)

    # ─────────────────────────────────────────────
    # Siren state
    # ─────────────────────────────────────────────

    def _get_siren_state(self) -> bool:
        """
        Returns True if siren is active.
        Uses SirenDetector result (Step 6) or falls back to manual flag.
        """
        if self._siren_det:
            return self._siren_det.is_siren_active()
        # Step 6 not wired yet — default to OFF in standby
        return self._siren_active

    def set_siren(self, active: bool) -> None:
        """Manual siren override (used by operator app or test harness)."""
        self._siren_active = active
        logger.info(f"VSU: Siren manually {'activated' if active else 'deactivated'}")

    # ─────────────────────────────────────────────
    # Sign
    # ─────────────────────────────────────────────

    def _sign_payload(self, payload: dict) -> dict:
        """Signs beacon with ECDSA-P256 (real key or ephemeral dev key)."""
        if self._signer:
            return self._signer.sign(payload)
        payload["sig"] = "UNSIGNED_DEV_MODE"
        return payload

    # ─────────────────────────────────────────────
    # Config update handler (from MQTT)
    # ─────────────────────────────────────────────

    def _handle_config_update(self, config: dict) -> None:
        """
        Handles over-the-air config updates from cloud.
        Currently supports: beacon_interval, preempt_threshold, log_level.
        """
        logger.info(f"VSU: Applying remote config: {list(config.keys())}")
        if "beacon_interval_active" in config:
            self.ACTIVE_INTERVAL_S = float(config["beacon_interval_active"])
        if "log_level" in config:
            logger.info(f"VSU: Log level → {config['log_level']}")

    # ─────────────────────────────────────────────
    # Transmit — all channels
    # ─────────────────────────────────────────────

    def _transmit(self, payload: dict, siren_on: bool) -> None:
        """Broadcasts signed beacon via LoRa + MQTT + BLE simultaneously."""
        # 1. LoRa broadcast (edge node receives within ~200ms)
        if self._lora_tx:
            lora_bytes = self._builder.to_lora_bytes(payload)
            self._lora_tx.transmit(lora_bytes)

        # 2. MQTT over 4G (cloud receives real-time telemetry)
        if self._mqtt_client:
            json_bytes = self._builder.to_json_bytes(payload, compact=True)
            self._mqtt_client.publish_beacon(json_bytes)
            # Send priority message on siren activation
            if siren_on and self._beacon_count == 1:
                self._mqtt_client.publish_priority(
                    self._cfg.vehicle_type, self._cfg.priority_class
                )

        # 3. BLE advertisement update (≤30m short-range)
        if self._ble_beacon:
            self._ble_beacon.update(
                payload["gps"]["lat"], payload["gps"]["lon"], siren_on
            )

    # ─────────────────────────────────────────────
    # Setup helpers
    # ─────────────────────────────────────────────

    def _setup_logging(self) -> None:
        logger.remove()  # Remove default handler
        logger.add(
            sys.stderr,
            level=self._cfg.log_level,
            format="<green>{time:HH:mm:ss.SSS}</green> | <level>{level:<8}</level> | {message}",
            colorize=True,
        )
        try:
            logger.add(
                "/var/log/smart-signal/vsu.log",
                rotation="50 MB",
                retention="7 days",
                level="DEBUG",
                catch=True,
            )
        except PermissionError:
            logger.warning("Could not write to /var/log/smart-signal/vsu.log (permission denied) - console logging only.")

    def _setup_signals(self) -> None:
        """Catch SIGINT (Ctrl+C) and SIGTERM (systemd stop) for clean shutdown."""
        def _handler(sig, frame):
            logger.info(f"VSU: Received signal {sig} — shutting down...")
            self.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT,  _handler)
        signal.signal(signal.SIGTERM, _handler)


# ─────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────

def main() -> None:
    app = VSUApp()
    app.start()


if __name__ == "__main__":
    main()
