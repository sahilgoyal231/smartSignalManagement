import asyncio
import json
from typing import AsyncGenerator, Callable, Any, Dict
from loguru import logger
import ssl
import aiomqtt  # Replaces asyncio-mqtt in newer versions
from cloud.shared.config import get_settings

settings = get_settings()

class CloudMQTTClient:
    """
    Async MQTT client for the cloud backend to communicate with EMQX.
    Handles auto-reconnects and message yielding.
    """
    def __init__(self, client_id_suffix: str):
        self.client_id = f"{settings.mqtt_client_id_prefix}-{client_id_suffix}"
        self.broker = settings.mqtt_broker_host
        self.port = settings.mqtt_broker_port
        self.user = settings.mqtt_broker_user
        self.password = settings.mqtt_broker_password
        self.client = None
        self._connected = False

    async def connect(self):
        """Connect to the broker."""
        try:
            if not self.client:
                kwargs = {
                    "hostname": self.broker,
                    "port": self.port,
                    "username": self.user,
                    "password": self.password,
                    "identifier": self.client_id,
                    "clean_session": False
                }
                if self.port == 8883:
                    kwargs["tls_context"] = ssl.create_default_context()

                self.client = aiomqtt.Client(**kwargs)
            
            self._connected = True
            logger.info(f"Connected to MQTT broker configuration at {self.broker}:{self.port}")
        except Exception as e:
            logger.error(f"MQTT Configuration failed: {e}")
            raise

    async def disconnect(self):
        """Disconnect from the broker."""
        if self._connected:
            self._connected = False
            logger.info("Disconnected from MQTT broker")

    async def publish(self, topic: str, payload: Dict[str, Any], qos: int = 1):
        """Publish a JSON payload to a topic."""
        try:
            msg = json.dumps(payload)
            await self.client.publish(topic, payload=msg.encode(), qos=qos)
            logger.debug(f"Published to {topic}: {payload}")
        except Exception as e:
            logger.error(f"Failed to publish to {topic}: {e}")

    async def subscribe_and_listen(self, topic: str) -> AsyncGenerator[tuple[str, Dict[str, Any]], None]:
        """
        Subscribe to a topic and yield incoming messages.
        Returns a tuple of (topic, parsed_json_payload).
        Will auto-reconnect if the connection drops.
        """
        reconnect_interval = 3
        while True:
            try:
                # Use context manager style for aiomqtt
                async with self.client:
                    self._connected = True
                    logger.info(f"Subscribed to MQTT topic: {topic}")
                    await self.client.subscribe(topic, qos=1)
                    
                    async for message in self.client.messages:
                        try:
                            payload_str = message.payload.decode()
                            data = json.loads(payload_str)
                            yield message.topic.value, data
                        except json.JSONDecodeError:
                            logger.warning(f"Invalid JSON received on {message.topic}: {message.payload}")
                        except Exception as e:
                            logger.error(f"Error processing message on {message.topic}: {e}")
                            
            except aiomqtt.MqttError as error:
                self._connected = False
                logger.error(f"MQTT connection lost: {error}. Reconnecting in {reconnect_interval}s...")
                await asyncio.sleep(reconnect_interval)
                reconnect_interval = min(reconnect_interval * 2, 60) # Exponential backoff
            except Exception as e:
                self._connected = False
                logger.error(f"Unexpected MQTT error: {e}. Reconnecting in {reconnect_interval}s...")
                await asyncio.sleep(reconnect_interval)
