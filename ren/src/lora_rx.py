"""
LoRa Receiver Driver (Edge Node)
==================================
Receives 14-byte 433MHz broadcasts from ambulances using an RFM95W module
connected via SPI. Includes a mock/simulator mode for development.

Runs a dedicated background thread to poll the SPI radio interface.
Passes received packets to a callback function asynchronously.
"""
from __future__ import annotations

import queue
import threading
import time
from typing import Callable, Optional

from loguru import logger

from ren.src.config import RENConfig


class LoRaRX:
    """
    Background driver for receiving LoRa Packets via RFM95W.
    """

    def __init__(
        self,
        config: RENConfig,
        on_packet_received: Callable[[bytes, int, float], None]
    ) -> None:
        """
        :param on_packet_received: Callback function (payload_bytes, rssi_dbm, snr_db)
        """
        self._cfg = config
        self._on_packet = on_packet_received
        self._running = False
        self._thread: Optional[threading.Thread] = None

        self._rx_count = 0
        self._mock = False

        self._init_hardware()

    def _init_hardware(self) -> None:
        """Initialise SPI and pyLoRa. Fall back to mock mode if absent."""
        try:
            from pyLora import pyLora   # type: ignore
            import spidev              # type: ignore

            self._lora = pyLora()
            # Standard setup
            self._lora.set_frequency(self._cfg.lora_frequency_mhz)
            self._lora.set_spreading_factor(self._cfg.lora_spreading_factor)
            
            # Request continuous receive mode
            self._lora.receive()
            self._mock = False

            logger.info(
                f"LoRaRX: Hardware init OK. "
                f"freq={self._cfg.lora_frequency_mhz}MHz "
                f"SF={self._cfg.lora_spreading_factor}"
            )
        except (ImportError, RuntimeError, FileNotFoundError) as exc:
            logger.warning(
                f"LoRaRX: Hardware not available ({exc}) — enabling MOCK receiver"
            )
            self._mock = True

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._rx_loop, daemon=True, name="lora-rx"
        )
        self._thread.start()
        mode = "[MOCK]" if self._mock else "[HW]"
        logger.info(f"LoRaRX: Started {mode}")

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        logger.info(f"LoRaRX: Stopped. Total packets received: {self._rx_count}")

    def _rx_loop(self) -> None:
        if self._mock:
            self._mock_loop()
            return

        # Real hardware polling loop
        logger.debug("LoRaRX: Entering hardware polling loop...")
        while self._running:
            try:
                if self._lora.packet_available():
                    payload = self._lora.receive_packet()
                    rssi = self._lora.packet_rssi()
                    snr  = self._lora.packet_snr()

                    if payload and len(payload) == 14:
                        self._rx_count += 1
                        logger.debug(f"LoRaRX: valid 14B packet (RSSI={rssi}dBm, SNR={snr}dB)")
                        self._on_packet(bytes(payload), rssi, snr)
                    else:
                        logger.warning(
                            f"LoRaRX: Dropped malformed packet (len={len(payload) if payload else 0})"
                        )
                else:
                    time.sleep(0.01)  # 10ms poll
            except Exception as exc:
                logger.error(f"LoRaRX: Hardware reading error — {exc}")
                time.sleep(1.0)

    def _mock_loop(self) -> None:
        """
        Simulates receiving a LoRa pulse from an ambulance every 2 seconds.
        The packet is 14 bytes encoded identically to VSU.
        """
        import struct

        logger.debug("LoRaRX: Entering simulated polling loop...")
        
        # Start coordinate ~1 km west of intersection
        lat = self._cfg.lat
        lon = self._cfg.lon - 0.0090
        
        while self._running:
            time.sleep(2.0)
            
            # Move east towards intersection
            lon += 0.0002

            # Mock data packed via struct:
            # lat_i, lon_i, spd_i, hdg_i, flags, priority
            # Flags: bit 7 (siren), bit 6 (dest), bits 5-3 (fix=7)
            lat_i = int(round(lat * 1e7))
            lon_i = int(round(lon * 1e7))
            spd_i = int(round(65.4 * 10))  # 65.4 km/h
            hdg_i = int(round(90.0 * 10))  # 90 degrees (East)
            
            siren_active = True
            flags = (int(siren_active) << 7) | (0 << 6) | (7 << 3)
            priority = 2

            try:
                mock_payload = struct.pack(
                    ">iiHHBB", lat_i, lon_i, spd_i, hdg_i, flags, priority
                )
                rssi = -65.0 + (lon - self._cfg.lon) * 1000  # Fake RSSI curve
                snr = 8.5
                
                self._rx_count += 1
                self._on_packet(mock_payload, rssi, snr)
            except Exception as e:
                logger.error(f"LoRaRX mock error: {e}")

    def stats(self) -> dict:
        return {
            "rx_count": self._rx_count,
            "mock_mode": self._mock,
        }
