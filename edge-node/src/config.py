"""
Edge Node — Config Defaults
"""
import os

NODE_ID = os.environ.get("NODE_ID", "NODE-PUN-001")
CITY = os.environ.get("CITY", "Pune, India")

# Mapbox coordinates for this node (Used for Kinematics)
# Default is approx Pune
NODE_LAT = float(os.environ.get("NODE_LAT", "18.5204"))  
NODE_LON = float(os.environ.get("NODE_LON", "73.8567"))

MQTT_BROKER_HOST = os.environ.get("MQTT_BROKER_HOST", "localhost")
MQTT_BROKER_PORT = int(os.environ.get("MQTT_BROKER_PORT", "1883"))
MQTT_USER = os.environ.get("MQTT_USER", "edge_node_user")
MQTT_PASS = os.environ.get("MQTT_PASS", "smartsignal_edge")

PREEMPT_THRESHOLD_S = int(os.environ.get("PREEMPT_THRESHOLD_S", "45"))
ALERT_THRESHOLD_S = int(os.environ.get("ALERT_THRESHOLD_S", "90"))
MAX_GREEN_HOLD_S = int(os.environ.get("MAX_GREEN_HOLD_S", "60"))

# LoRa serial port emulation
LORA_PORT = os.environ.get("LORA_PORT", "/dev/ttyUSB0")
