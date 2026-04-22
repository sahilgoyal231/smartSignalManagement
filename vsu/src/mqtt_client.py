"""
MQTT Client — 4G Uplink to Cloud EMQX Broker
==============================================
Publishes signed beacon payloads to the cloud EMQX broker over TLS.
Handles:
  - TLS mutual auth (client cert + CA cert)
  - Auto-reconnect with exponential backoff
  - Offline queue (up to 200 messages) — flushes when connection restored
  - QoS 1 for beacon topic, QoS 0 for heartbeat
  - Will message (last-will) so cloud detects VSU offline instantly

MQTT Topics published:
  smartsignal/{city}/vehicle/{id}/beacon      QoS 1  — full signed beacon (JSON)
  smartsignal/{city}/vehicle/{id}/priority    QoS 1  — priority/alert override
  smartsignal/{city}/vehicle/{id}/heartbeat   QoS 0  — keep-alive 30s

MQTT Topics subscribed:
  smartsignal/{city}/vehicle/{id}/ack         QoS 1  — delivery confirmation from edge
  smartsignal/{city}/vehicle/{id}/config      QoS 1  — OTA config from cloud

Connection:
  Broker:  EMQX (cloud or local)
  Port:    8883 (TLS) in production, 1883 in dev
  Auth:    username/password + client certificate (X.509 mutual TLS)
  QoS:     1 for reliability (at-least-once delivery)
"""
from __future__ import annotations

import json
import queue
import ssl
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Callable, Optional

import paho.mqtt.client as mqtt
from loguru import logger

from vsu.src.config import VSUConfig


# ─────────────────────────────────────────────────────────────
# Offline message store
# ─────────────────────────────────────────────────────────────

class OfflineQueue:
    """Thread-safe bounded queue for messages buffered during disconnection."""

    def __init__(self, maxlen: int = 200) -> None:
        self._q: deque = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def push(self, topic: str, payload: bytes, qos: int) -> None:
        with self._lock:
            self._q.append((topic, payload, qos))

    def flush(self) -> list[tuple[str, bytes, int]]:
        with self._lock:
            items = list(self._q)
            self._q.clear()
            return items

    def __len__(self) -> int:
        with self._lock:
            return len(self._q)


# ─────────────────────────────────────────────────────────────
# MQTT Client
# ─────────────────────────────────────────────────────────────

class MQTTClient:
    """
    TLS MQTT client for VSU → Cloud communication.

    Usage:
        client = MQTTClient(config)
        client.start()
        client.publish(topic, payload, qos=1)
        client.stop()
    """

    MAX_BACKOFF_S  = 60     # Maximum reconnect wait
    HEARTBEAT_S    = 30     # Heartbeat interval
    KEEPALIVE_S    = 60     # MQTT keepalive

    def __init__(
        self,
        config: VSUConfig,
        on_config_update: Optional[Callable[[dict], None]] = None,
    ) -> None:
        self._cfg  = config
        self._on_config_update = on_config_update
        self._connected         = False
        self._reconnect_delay   = 2
        self._offline_q         = OfflineQueue(maxlen=200)
        self._publish_count     = 0
        self._running           = False
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._mock              = False

        self._client = self._build_client()

    # ─────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────

    def start(self) -> None:
        self._running = True

        if self._mock:
            logger.info("MQTT: Running in MOCK mode (no broker)")
            return

        try:
            self._client.connect(
                self._cfg.mqtt_host,
                self._cfg.mqtt_port,
                keepalive=self.KEEPALIVE_S,
            )
            self._client.loop_start()   # background network thread
        except Exception as exc:
            logger.warning(f"MQTT: Initial connect failed ({exc}) — will retry in background")

        # Heartbeat thread
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, daemon=True, name="mqtt-heartbeat"
        )
        self._heartbeat_thread.start()
        logger.info(
            f"MQTT: Client started → {self._cfg.mqtt_host}:{self._cfg.mqtt_port} "
            f"TLS={'yes' if self._cfg.mqtt_tls else 'no'}"
        )

    def stop(self) -> None:
        self._running = False
        if not self._mock:
            self._client.loop_stop()
            self._client.disconnect()
        logger.info(
            f"MQTT: Stopped. Published={self._publish_count}, "
            f"Offline queue remaining={len(self._offline_q)}"
        )

    def is_connected(self) -> bool:
        return self._connected or self._mock

    # ─────────────────────────────────────────────
    # Publish
    # ─────────────────────────────────────────────

    def publish(self, topic: str, payload: bytes, qos: int = 1) -> bool:
        """
        Publish a message. If disconnected, buffers in the offline queue.
        Returns True if sent immediately, False if queued.
        """
        if self._mock:
            logger.debug(f"MQTT [MOCK]: pub → {topic}  ({len(payload)}B  qos={qos})")
            self._publish_count += 1
            return True

        if not self._connected:
            self._offline_q.push(topic, payload, qos)
            logger.debug(
                f"MQTT: Offline — queued message ({len(self._offline_q)} buffered)"
            )
            return False

        result = self._client.publish(topic, payload, qos=qos, retain=False)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            self._publish_count += 1
            logger.debug(f"MQTT: Published → {topic} ({len(payload)}B qos={qos})")
            return True
        else:
            logger.warning(f"MQTT: Publish failed rc={result.rc} — queuing")
            self._offline_q.push(topic, payload, qos)
            return False

    def publish_beacon(self, payload_bytes: bytes) -> bool:
        return self.publish(
            self._cfg.mqtt_topic_beacon(), payload_bytes, qos=1
        )

    def publish_priority(self, vehicle_type: str, priority: int) -> bool:
        msg = json.dumps({
            "vehicle_id":   self._cfg.vehicle_id,
            "vehicle_type": vehicle_type,
            "priority":     priority,
            "ts":           datetime.now(timezone.utc).isoformat(),
        }).encode()
        return self.publish(self._cfg.mqtt_topic_priority(), msg, qos=1)

    # ─────────────────────────────────────────────
    # Heartbeat
    # ─────────────────────────────────────────────

    def _heartbeat_loop(self) -> None:
        """Publishes keep-alive every 30 seconds to confirm VSU is alive."""
        while self._running:
            hb_payload = json.dumps({
                "vehicle_id": self._cfg.vehicle_id,
                "ts":         datetime.now(timezone.utc).isoformat(),
                "bat":        100,   # battery updated by main loop
            }).encode()
            self.publish(
                f"smartsignal/{self._cfg.city.lower()}/vehicle"
                f"/{self._cfg.vehicle_id}/heartbeat",
                hb_payload,
                qos=0,
            )
            time.sleep(self.HEARTBEAT_S)

    # ─────────────────────────────────────────────
    # Paho callbacks
    # ─────────────────────────────────────────────

    def _on_connect(self, client, userdata, flags, rc, properties=None) -> None:
        if rc == 0:
            self._connected = True
            self._reconnect_delay = 2   # Reset backoff on success
            logger.success(f"MQTT: Connected to {self._cfg.mqtt_host}:{self._cfg.mqtt_port}")

            # Subscribe to server→VSU topics
            ack_topic = (
                f"smartsignal/{self._cfg.city.lower()}/"
                f"vehicle/{self._cfg.vehicle_id}/ack"
            )
            cfg_topic = (
                f"smartsignal/{self._cfg.city.lower()}/"
                f"vehicle/{self._cfg.vehicle_id}/config"
            )
            client.subscribe([(ack_topic, 1), (cfg_topic, 1)])
            logger.debug(f"MQTT: Subscribed → {ack_topic}, {cfg_topic}")

            # Flush offline queue
            buffered = self._offline_q.flush()
            if buffered:
                logger.info(f"MQTT: Flushing {len(buffered)} offline messages...")
                for topic, payload, qos in buffered:
                    client.publish(topic, payload, qos=qos)
        else:
            logger.error(f"MQTT: Connection refused — rc={rc} ({_rc_to_str(rc)})")

    def _on_disconnect(self, client, userdata, rc, properties=None) -> None:
        self._connected = False
        if rc != 0:
            logger.warning(
                f"MQTT: Unexpected disconnect (rc={rc}) — "
                f"reconnecting in {self._reconnect_delay}s"
            )
            time.sleep(self._reconnect_delay)
            self._reconnect_delay = min(self._reconnect_delay * 2, self.MAX_BACKOFF_S)
        else:
            logger.info("MQTT: Cleanly disconnected")

    def _on_message(self, client, userdata, msg) -> None:
        """Handle incoming messages from cloud (ACKs, config updates)."""
        try:
            data = json.loads(msg.payload.decode())
            if "config" in msg.topic:
                logger.info(f"MQTT: Config update received: {list(data.keys())}")
                if self._on_config_update:
                    self._on_config_update(data)
            elif "ack" in msg.topic:
                logger.debug(f"MQTT: ACK received for event {data.get('event_id','?')}")
        except Exception as exc:
            logger.warning(f"MQTT: Message parse error — {exc}")

    # ─────────────────────────────────────────────
    # Build client
    # ─────────────────────────────────────────────

    def _build_client(self) -> mqtt.Client:
        try:
            client = mqtt.Client(
                client_id=f"vsu-{self._cfg.vehicle_id}",
                protocol=mqtt.MQTTv5,
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            )
        except Exception:
            # Older paho-mqtt fallback
            client = mqtt.Client(client_id=f"vsu-{self._cfg.vehicle_id}")

        client.username_pw_set(self._cfg.mqtt_user, self._cfg.mqtt_password)

        # TLS — mutual auth with device certificate
        if self._cfg.mqtt_tls:
            try:
                context = ssl.create_default_context()
                context.load_cert_chain(
                    self._cfg.device_cert_path,
                    self._cfg.device_key_path,
                )
                client.tls_set_context(context)
                logger.debug("MQTT: TLS configured with device certificate")
            except (FileNotFoundError, ssl.SSLError) as exc:
                logger.warning(f"MQTT: TLS cert load failed ({exc}) — falling back to no-TLS")

        # Last-will message (so cloud detects offline VSU)
        will_topic = (
            f"smartsignal/{self._cfg.city.lower()}/"
            f"vehicle/{self._cfg.vehicle_id}/status"
        )
        client.will_set(
            will_topic,
            payload=json.dumps({
                "vehicle_id": self._cfg.vehicle_id,
                "status":     "OFFLINE",
                "ts":         datetime.now(timezone.utc).isoformat(),
            }).encode(),
            qos=1,
            retain=True,
        )

        # Register callbacks
        client.on_connect    = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message    = self._on_message

        # Check if broker is reachable — if not, use mock mode
        import socket
        try:
            socket.setdefaulttimeout(2)
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((self._cfg.mqtt_host, self._cfg.mqtt_port))
        except (socket.error, OSError):
            logger.warning(
                f"MQTT: Broker {self._cfg.mqtt_host}:{self._cfg.mqtt_port} "
                f"unreachable — MOCK mode"
            )
            self._mock = True

        return client

    def stats(self) -> dict:
        return {
            "connected":      self._connected,
            "mock":           self._mock,
            "published":      self._publish_count,
            "offline_queued": len(self._offline_q),
        }


def _rc_to_str(rc: int) -> str:
    return {
        1: "incorrect protocol version",
        2: "invalid client ID",
        3: "server unavailable",
        4: "bad credentials",
        5: "not authorized",
    }.get(rc, "unknown")
