"""
Edge Node (REN) Configuration
===============================
Loads configuration for the Roadside Edge Node from environment variables.
"""
import os
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class RENConfig:
    # ── Node Identity ─────────────────────────────
    node_id: str = field(default_factory=lambda: os.environ.get("REN_NODE_ID", "NODE-001"))
    city:    str = field(default_factory=lambda: os.environ.get("REN_CITY", "Mumbai"))
    
    # ── Location (Intersection Center) ────────────
    lat: float = field(default_factory=lambda: float(os.environ.get("REN_LAT", "19.0650")))
    lon: float = field(default_factory=lambda: float(os.environ.get("REN_LON", "72.8640")))

    # ── LoRa Hardware Settings (RFM95W) ───────────
    lora_frequency_mhz:    float = field(default_factory=lambda: float(os.environ.get("LORA_FREQ_MHZ", "433.0")))
    lora_spreading_factor: int   = field(default_factory=lambda: int(os.environ.get("LORA_SF", "9")))
    lora_bandwidth_khz:    float = field(default_factory=lambda: float(os.environ.get("LORA_BW_KHZ", "125.0")))
    lora_coding_rate:      str   = field(default_factory=lambda: os.environ.get("LORA_CR", "4/5"))

    # ── Security & MQTT ───────────────────────────
    mqtt_host:     str  = field(default_factory=lambda: os.environ.get("MQTT_BROKER_HOST", "localhost"))
    mqtt_port:     int  = field(default_factory=lambda: int(os.environ.get("MQTT_BROKER_PORT", "1883")))
    mqtt_user:     str  = field(default_factory=lambda: os.environ.get("MQTT_BROKER_USER", "ren_user"))
    mqtt_password: str  = field(default_factory=lambda: os.environ.get("MQTT_BROKER_PASSWORD", "ren_pass"))
    mqtt_tls:      bool = field(default_factory=lambda: os.environ.get("MQTT_TLS", "0") == "1")

    # X.509 Mutual Auth
    node_cert_path: str = field(default_factory=lambda: os.environ.get("REN_CERT_PATH", "ren/certs/ren.crt"))
    node_key_path:  str = field(default_factory=lambda: os.environ.get("REN_KEY_PATH", "ren/certs/ren.key"))

    # ── Signal Controller ─────────────────────────
    controller_type: str   = field(default_factory=lambda: os.environ.get("CONTROLLER_TYPE", "MOCK"))
    controller_serial_port: str = field(default_factory=lambda: os.environ.get("CONTROLLER_SERIAL_PORT", "/dev/ttyUSB0"))
    controller_serial_baud: int = field(default_factory=lambda: int(os.environ.get("CONTROLLER_SERIAL_BAUD", "9600")))
    relay_pin_ns: int      = field(default_factory=lambda: int(os.environ.get("RELAY_PIN_NS", "17")))
    relay_pin_ew: int      = field(default_factory=lambda: int(os.environ.get("RELAY_PIN_EW", "27")))

    log_level: str = field(default_factory=lambda: os.environ.get("LOG_LEVEL", "INFO"))


# Singleton instance
_config: Optional[RENConfig] = None

def get_config() -> RENConfig:
    global _config
    if _config is None:
        _config = RENConfig()
    return _config
