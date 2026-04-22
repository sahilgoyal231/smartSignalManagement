"""
LoRa TX Driver — RFM95W via SPI (sx127x)
==========================================
Transmits compact 14-byte beacon packets using the RFM95W LoRa module.
Uses the `pyLoRa` / `spidev` library for SPI communication on Raspberry Pi.

Hardware connections (SPI0, Raspberry Pi Zero 2W):
    RFM95W MOSI  →  GPIO10 (SPI0 MOSI, pin 19)
    RFM95W MISO  →  GPIO9  (SPI0 MISO, pin 21)
    RFM95W SCK   →  GPIO11 (SPI0 CLK,  pin 23)
    RFM95W NSS   →  GPIO8  (SPI0 CE0,  pin 24)
    RFM95W RST   →  GPIO25 (pin 22)
    RFM95W DIO0  →  GPIO24 (pin 18)  ← TX-done interrupt
    RFM95W 3.3V  →  3.3V  (pin 1)
    RFM95W GND   →  GND   (pin 6)

LoRa RF Settings (433 MHz ISM band):
    Frequency:         433.0 MHz
    Spreading Factor:  SF9   (range/reliability balance)
    Bandwidth:         125 kHz
    Coding Rate:       4/5
    TX Power:          17 dBm (≈ 50 mW — within ISM limits)
    Preamble:          8 symbols
    CRC:               Enabled

Airtime for 14-byte payload @ SF9 / 125 kHz = ~92 ms
At 2 Hz beacon rate: duty cycle ≈ 18.4% (within 25% ISM duty limit)
"""
from __future__ import annotations

import struct
import threading
import time
from typing import Optional

from loguru import logger


# ─────────────────────────────────────────────────────────────
# LoRa TX Driver
# ─────────────────────────────────────────────────────────────

class LoRaTX:
    """
    RFM95W LoRa transmitter driver.

    On non-Pi hardware (dev/test), falls back to mock mode — logs
    what would be transmitted without touching SPI.

    Usage:
        lora = LoRaTX(config)
        lora.start()
        lora.transmit(beacon_bytes)   # non-blocking (queued)
        lora.stop()
    """

    # GPIO pin numbers (BCM)
    PIN_RST  = 25
    PIN_DIO0 = 24
    PIN_CS   = 8

    def __init__(self, config) -> None:
        self._cfg       = config
        self._mock      = False
        self._running   = False
        self._lora      = None
        self._lock      = threading.Lock()
        self._tx_queue: list[bytes] = []
        self._tx_thread: Optional[threading.Thread] = None
        self._tx_count  = 0
        self._tx_errors = 0

    # ─────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────

    def start(self) -> None:
        """Initialise SPI + LoRa module, start TX worker thread."""
        self._lora = self._init_hardware()
        self._running = True
        self._tx_thread = threading.Thread(
            target=self._tx_worker, daemon=True, name="lora-tx"
        )
        self._tx_thread.start()
        mode = "MOCK" if self._mock else "HARDWARE"
        logger.info(
            f"LoRaTX: Started [{mode}] "
            f"freq={self._cfg.lora_frequency_mhz}MHz "
            f"SF={self._cfg.lora_spreading_factor} "
            f"pwr={self._cfg.lora_tx_power_dbm}dBm"
        )

    def stop(self) -> None:
        """Drain TX queue and shut down."""
        self._running = False
        if self._tx_thread:
            self._tx_thread.join(timeout=3)
        logger.info(
            f"LoRaTX: Stopped. TX count={self._tx_count}, errors={self._tx_errors}"
        )

    # ─────────────────────────────────────────────
    # Public: enqueue a packet for transmission
    # ─────────────────────────────────────────────

    def transmit(self, data: bytes) -> None:
        """
        Enqueue bytes for LoRa transmission (non-blocking).
        The TX worker thread sends them sequentially.
        Drops oldest packet if queue exceeds 5 items (backpressure).
        """
        with self._lock:
            self._tx_queue.append(data)
            if len(self._tx_queue) > 5:
                dropped = self._tx_queue.pop(0)
                logger.warning(f"LoRaTX: Queue full — dropped oldest packet ({len(dropped)}B)")

    @property
    def tx_count(self) -> int:
        return self._tx_count

    # ─────────────────────────────────────────────
    # Private: TX worker
    # ─────────────────────────────────────────────

    def _tx_worker(self) -> None:
        """Background thread — dequeues and transmits packets one by one."""
        while self._running:
            packet = None
            with self._lock:
                if self._tx_queue:
                    packet = self._tx_queue.pop(0)

            if packet:
                self._send_packet(packet)
            else:
                time.sleep(0.01)  # 10ms idle poll

    def _send_packet(self, data: bytes) -> None:
        """Transmit a single packet. Blocks until TX is complete."""
        if self._mock:
            self._mock_transmit(data)
            return

        try:
            self._lora.set_payload_length(len(data))
            self._lora.write_payload(list(data))   # pyLoRa expects list of ints
            self._lora.set_mode_tx()

            # Wait for TX-done (DIO0 goes HIGH), timeout 500ms
            timeout = time.monotonic() + 0.5
            while time.monotonic() < timeout:
                if self._lora.get_irq_flags().get("tx_done"):
                    break
                time.sleep(0.005)

            self._lora.clear_irq_flags(TxDone=1)
            self._lora.set_mode_stdby()
            self._tx_count += 1
            logger.debug(f"LoRaTX: Sent {len(data)}B  total={self._tx_count}")

        except Exception as exc:
            self._tx_errors += 1
            logger.error(f"LoRaTX: TX error — {exc}")

    def _mock_transmit(self, data: bytes) -> None:
        """Simulate LoRa TX without hardware — logs hex and airtime estimate."""
        # Airtime calculation: T_sym = 2^SF / BW
        sf  = self._cfg.lora_spreading_factor
        bw  = self._cfg.lora_bandwidth_khz * 1000
        t_sym_ms = (2 ** sf / bw) * 1000
        n_payload = len(data)
        # Simplified Semtech airtime formula (payload only)
        t_airtime_ms = t_sym_ms * (8 + max(
            ((8 * n_payload - 4 * sf + 28) / (4 * sf)) * 5, 0
        ))
        self._tx_count += 1
        logger.debug(
            f"LoRaTX [MOCK]: TX #{self._tx_count} "
            f"payload={data.hex()} "
            f"({len(data)}B) "
            f"airtime≈{t_airtime_ms:.0f}ms"
        )
        time.sleep(t_airtime_ms / 1000)   # Simulate real airtime

    # ─────────────────────────────────────────────
    # Private: hardware init
    # ─────────────────────────────────────────────

    def _init_hardware(self):
        """
        Initialise the RFM95W via pyLoRa/spidev.
        Falls back to mock mode if not running on Raspberry Pi.
        """
        try:
            from pyLoRa import LoRa, MODE, BW, CODING_RATE  # type: ignore

            lora = LoRa(verbose=False)
            lora.set_mode(MODE.SLEEP)
            lora.set_pa_config(pa_select=1, max_power=21,
                               output_power=self._cfg.lora_tx_power_dbm - 2)
            lora.set_freq(self._cfg.lora_frequency_mhz)
            lora.set_spreading_factor(self._cfg.lora_spreading_factor)
            lora.set_bw(BW.BW125)
            lora.set_coding_rate(CODING_RATE.CR4_5)
            lora.set_rx_crc(True)
            lora.set_preamble(8)
            lora.set_mode(MODE.STDBY)
            logger.success("LoRaTX: RFM95W hardware initialised")
            return lora

        except (ImportError, RuntimeError, OSError) as exc:
            logger.warning(f"LoRaTX: Hardware not available ({exc}) — MOCK mode")
            self._mock = True
            return None

    # ─────────────────────────────────────────────
    # Stats
    # ─────────────────────────────────────────────

    def stats(self) -> dict:
        return {
            "tx_count":   self._tx_count,
            "tx_errors":  self._tx_errors,
            "queue_len":  len(self._tx_queue),
            "mock_mode":  self._mock,
        }
