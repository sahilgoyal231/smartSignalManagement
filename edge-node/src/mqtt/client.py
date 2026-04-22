"""
Edge Node — EMQX MQTT Client
"""
import json
import asyncio
from loguru import logger
import paho.mqtt.client as mqtt

class EdgeMqttClient:
    def __init__(self, broker_host: str, broker_port: int, user: str, password: str, node_id: str, city: str):
        self.host = broker_host
        self.port = broker_port
        self.node_id = node_id
        self.city = city
        
        # We append a random short string to prevent connection flapping if multiple clients use same ID in tests
        import random, string
        rand_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
        
        self.client_id = f"{node_id}-{rand_suffix}"
        
        self.client = mqtt.Client(self.client_id, protocol=mqtt.MQTTv311)
        self.client.username_pw_set(user, password)
        
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
        
        self.connected = False
        
        # Incoming commands from cloud (e.g. node.alert)
        self.alert_queue = asyncio.Queue()

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connected = True
            logger.success(f"[{self.node_id}] Connected to EMQX MQTT broker.")
            # Subscribe to cloud alerts destined for this specific node
            topic = f"smartsignal/{self.city}/node/{self.node_id}/alert"
            self.client.subscribe(topic, qos=1)
            logger.info(f"[{self.node_id}] Subscribed to {topic}")
        else:
            logger.error(f"[{self.node_id}] Failed to connect to EMQX. Return code: {rc}")

    def _on_disconnect(self, client, userdata, rc):
        self.connected = False
        if rc != 0:
            logger.warning(f"[{self.node_id}] Unexpected disconnection from EMQX.")

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            # Push to asyncio queue for the main loop to process
            # We use the thread-safe method since paho-mqtt network loop runs in a background thread
            asyncio.run_coroutine_threadsafe(self.alert_queue.put(payload), asyncio.get_running_loop())
        except Exception as e:
            logger.error(f"Error parsing MQTT message: {e}")

    async def connect(self):
        """Connect to broker and start the network loop background thread."""
        try:
            self.client.connect(self.host, self.port, keepalive=60)
            self.client.loop_start() # Starts network thread
            
            # Wait for connection to establish
            for _ in range(20):
                if self.connected:
                    return
                await asyncio.sleep(0.1)
                
            logger.warning(f"[{self.node_id}] MQTT connection timed out. Proceeding offline.")
        except Exception as e:
            logger.error(f"[{self.node_id}] MQTT connection failed: {e}. Proceeding offline.")

    async def disconnect(self):
        self.client.loop_stop()
        self.client.disconnect()

    def publish(self, topic_suffix: str, payload: dict, qos: int = 1):
        """Publish a JSON payload to smartsignal/CITY/node/NODE_ID/SUFFIX"""
        if not self.connected:
            return False
            
        topic = f"smartsignal/{self.city}/node/{self.node_id}/{topic_suffix}"
        try:
            self.client.publish(topic, json.dumps(payload), qos=qos)
            return True
        except Exception as e:
            logger.error(f"Failed to publish to {topic}: {e}")
            return False

    def publish_preempt(self, vehicle_id: str, eta_s: float, approach_phase: int, confidence: float):
        """Emit node.preempt event so the cloud Priority Queue can arbitrate."""
        payload = {
            "event_type": "PREEMPT_TRIGGER",
            "vehicle_id": vehicle_id,
            "target_node_id": self.node_id,
            "city": self.city,
            "eta_s": round(eta_s, 1),
            "approach_phase": approach_phase,
            "confidence": round(confidence, 2),
            "source": "EDGE_NODE"
        }
        self.publish("preempt", payload)

    def publish_heartbeat(self, status: dict):
        """Emit node.heartbeat event so the cloud Health Monitor knows we're alive."""
        self.publish("heartbeat", status, qos=0)
