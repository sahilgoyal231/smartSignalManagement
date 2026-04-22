"""
Edge Node MQTT Client
=====================
Handles 4G/LTE connection to the central Cloud MQTT Broker.
Publishes telemetry (active tracks, preemption events) and subscribes 
to cloud commands (e.g. software updates, manual overrides).
"""
import ssl
import json
import time
from typing import Dict, Any, Callable, Optional
import paho.mqtt.client as mqtt
from loguru import logger

from ren.src.config import RENConfig


class EdgeMQTTClient:
    def __init__(self, config: RENConfig):
        self._cfg = config
        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"ren_{self._cfg.node_id}"
        )
        self._setup_tls()
        self._client.username_pw_set(self._cfg.mqtt_user, self._cfg.mqtt_password)
        
        # Callbacks
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        
        # Command handlers mapping: topic_suffix -> handler_function
        self._command_handlers: Dict[str, Callable[[Any], None]] = {}
        
        self.connected = False

    def _setup_tls(self):
        """Configure mTLS if enabled in config."""
        if self._cfg.mqtt_tls:
            logger.info("Configuring MQTT with TLS/mTLS.")
            # Depending on broker setup, we might need a CA cert.
            # Assuming self._cfg.node_cert_path and node_key_path exist.
            try:
                self._client.tls_set(
                    certfile=self._cfg.node_cert_path,
                    keyfile=self._cfg.node_key_path,
                    tls_version=ssl.PROTOCOL_TLSv1_2
                )
            except Exception as e:
                logger.error(f"Failed to configure MQTT TLS: {e}")

    def register_command_handler(self, command: str, handler: Callable[[Any], None]):
        """
        Register a callback for cloud commands.
        Example: register_command_handler("reboot", self._handle_reboot)
        """
        self._command_handlers[command] = handler
        logger.debug(f"Registered MQTT command handler for: {command}")

    def connect(self):
        """Connect to the broker and start the network loop in the background."""
        logger.info(f"Connecting to MQTT Broker {self._cfg.mqtt_host}:{self._cfg.mqtt_port}...")
        try:
            self._client.connect(self._cfg.mqtt_host, self._cfg.mqtt_port, keepalive=60)
            self._client.loop_start()  # Runs in a separate thread
        except Exception as e:
            logger.error(f"MQTT Connection failed: {e}")

    def disconnect(self):
        """Stop the loop and disconnect cleanly."""
        self._client.loop_stop()
        self._client.disconnect()

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            logger.info(f"MQTT Connected successfully to {self._cfg.mqtt_host}.")
            self.connected = True
            
            # Subscribe to commands for this specific node
            cmd_topic = f"city/nodes/{self._cfg.node_id}/commands/#"
            self._client.subscribe(cmd_topic)
            logger.info(f"Subscribed to {cmd_topic}")
            
            # Let cloud know we're online
            self.publish_telemetry({"status": "OFFLINE" if flags else "ONLINE", "uptime_s": 0.0})
        else:
            logger.error(f"MQTT Connection failed. Reason code: {reason_code}")

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        logger.warning(f"MQTT Disconnected. Reason code: {reason_code}")
        self.connected = False

    def _on_message(self, client, userdata, message: mqtt.MQTTMessage):
        """Handle incoming messages (commands from cloud)."""
        topic = message.topic
        payload = message.payload.decode('utf-8')
        logger.info(f"Received MQTT msg on {topic}: {payload}")
        
        # Expected topic format: city/nodes/{node_id}/commands/{command_name}
        parts = topic.split('/')
        if len(parts) >= 5 and parts[3] == "commands":
            command = parts[4]
            if command in self._command_handlers:
                try:
                    data = json.loads(payload)
                    self._command_handlers[command](data)
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON in MQTT command payload: {payload}")
                except Exception as e:
                    logger.error(f"Error executing command handler for {command}: {e}")
            else:
                logger.warning(f"No handler registered for cloud command: {command}")

    def publish_telemetry(self, data: Dict[str, Any]):
        """Publish periodic node health/stats."""
        topic = f"city/nodes/{self._cfg.node_id}/telemetry"
        payload = json.dumps(data)
        if self.connected:
            self._client.publish(topic, payload, qos=1)
        else:
            logger.debug(f"Cannot publish telemetry (offline): {payload}")

    def publish_event(self, event_type: str, data: Dict[str, Any]):
        """Publish high-priority events, e.g., Preemption active."""
        topic = f"city/nodes/{self._cfg.node_id}/events"
        payload = json.dumps({
            "event": event_type,
            "timestamp": time.time(),
            "data": data
        })
        if self.connected:
            self._client.publish(topic, payload, qos=1)
            logger.info(f"Published Event {event_type} to MQTT.")
        else:
            logger.warning(f"Could not publish event {event_type} - MQTT offline.")
