"""
VSU Configuration
==================
Loads all environment variables for the Vehicle-Side Unit.
Provides a typed, validated config dataclass used across all VSU modules.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class VSUConfig:
    # ── Identity ───────────────────────────────────────────────
    vehicle_id:     str = field(default_factory=lambda: os.environ["VSU_VEHICLE_ID"])
    vehicle_type:   str = field(default_factory=lambda: os.environ.get("VSU_VEHICLE_TYPE", "AMBULANCE"))
    priority_class: int = field(default_factory=lambda: int(os.environ.get("VSU_PRIORITY_CLASS", "2")))
    city:           str = field(default_factory=lambda: os.environ.get("VSU_CITY", "Mumbai"))

    # ── GPS (u-blox NEO-9M via UART) ───────────────────────────
    gps_serial_port: str  = field(default_factory=lambda: os.environ.get("GPS_SERIAL_PORT", "/dev/serial0"))
    gps_baud_rate:   int  = field(default_factory=lambda: int(os.environ.get("GPS_BAUD_RATE", "9600")))
    gps_timeout_s:   float = 2.0          # seconds to wait for a valid NMEA sentence
    gps_update_hz:   int  = 10            # 10 Hz GPS update rate on NEO-9M
    gps_min_sats:    int  = 4             # minimum satellites for lock
    gps_max_accuracy_m: float = 10.0     # discard GPS fixes worse than this

    # ── LoRa TX (RFM95W via SPI) ───────────────────────────────
    lora_spi_channel:  int   = field(default_factory=lambda: int(os.environ.get("LORA_SPI_CHANNEL", "0")))
    lora_frequency_mhz: float = 433.0    # MHz — matches REN LoRa receiver
    lora_tx_power_dbm: int   = 17        # 17 dBm ≈ 50 mW (legal limit without WPC)
    lora_spreading_factor: int = 9       # SF9: balance of range and data rate
    lora_bandwidth_khz: float = 125.0
    lora_coding_rate:  str   = "4/5"
    lora_beacon_interval_s: float = 0.5  # 2 Hz while active

    # ── 4G MQTT ────────────────────────────────────────────────
    mqtt_host:     str = field(default_factory=lambda: os.environ.get("MQTT_BROKER_HOST", "localhost"))
    mqtt_port:     int = field(default_factory=lambda: int(os.environ.get("MQTT_BROKER_PORT", "8883")))
    mqtt_user:     str = field(default_factory=lambda: os.environ.get("MQTT_BROKER_USER", ""))
    mqtt_password: str = field(default_factory=lambda: os.environ.get("MQTT_BROKER_PASSWORD", ""))
    mqtt_tls:      bool = True            # Always TLS in prod; set False for local dev

    # ── BLE ────────────────────────────────────────────────────
    ble_adv_interval_ms: int = 100        # BLE advertisement interval

    # ── Siren Sensor (GPIO/ADC) ────────────────────────────────
    siren_gpio_pin:      int   = 17       # BCM GPIO 17 (digital trigger from comparator)
    siren_freq_low_hz:   float = 500.0
    siren_freq_high_hz:  float = 2000.0
    siren_hold_s:        float = 0.5     # siren must persist this long before activating

    # ── Security ───────────────────────────────────────────────
    device_cert_path: str = field(default_factory=lambda: os.environ.get("DEVICE_CERT_PATH", "./certs/vsu.crt"))
    device_key_path:  str = field(default_factory=lambda: os.environ.get("DEVICE_KEY_PATH", "./certs/vsu.key"))

    # ── Destinations ───────────────────────────────────────────
    # Optionally pre-configured home hospital / dispatch point
    home_hospital_lat: float = field(default_factory=lambda: float(os.environ.get("HOME_HOSPITAL_LAT", "0.0")))
    home_hospital_lon: float = field(default_factory=lambda: float(os.environ.get("HOME_HOSPITAL_LON", "0.0")))

    # ── Logging ────────────────────────────────────────────────
    log_level: str = field(default_factory=lambda: os.environ.get("LOG_LEVEL", "INFO"))

    def mqtt_topic_beacon(self) -> str:
        return f"smartsignal/{self.city.lower()}/vehicle/{self.vehicle_id}/beacon"

    def mqtt_topic_priority(self) -> str:
        return f"smartsignal/{self.city.lower()}/vehicle/{self.vehicle_id}/priority"


# Singleton
_config: VSUConfig | None = None


def get_config() -> VSUConfig:
    global _config
    if _config is None:
        _config = VSUConfig()
    return _config
