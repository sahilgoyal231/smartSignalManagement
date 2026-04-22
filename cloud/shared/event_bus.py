import json
from typing import Dict, Any, List
from loguru import logger
from redis.asyncio import Redis

from cloud.shared.config import get_settings

settings = get_settings()

def get_redis_client() -> Redis:
    # Use from_url to parse rediss:// schemes easily
    return Redis.from_url(settings.redis_url, decode_responses=False)

class EventProducer:
    """Async Event Producer for publishing internal events via Redis Pub/Sub."""
    
    def __init__(self):
        self.redis: Redis = None
        self._started = False

    async def start(self):
        """Start the producer."""
        if not self._started:
            if not self.redis:
                self.redis = get_redis_client()
            self._started = True
            logger.info(f"Event Producer connected to Redis at {settings.redis_url.split('@')[-1] if '@' in settings.redis_url else settings.redis_url}")

    async def stop(self):
        """Stop the producer."""
        if self._started:
            await self.redis.aclose()
            self._started = False
            logger.info("Event Producer stopped.")

    async def send_event(self, topic: str, payload: Dict[str, Any], key: str = None):
        """Send a JSON event to a Redis Pub/Sub channel."""
        if not self._started:
            raise RuntimeError("Event producer must be started before sending events.")
            
        try:
            value = json.dumps(payload).encode('utf-8')
            await self.redis.publish(topic, value)
            logger.debug(f"Redis Pub/Sub -> {topic}: {payload}")
        except Exception as e:
            logger.error(f"Failed to send event to {topic}: {e}")
            raise


class EventConsumer:
    """Async Event Consumer for subscribing to internal events via Redis Pub/Sub."""
    
    def __init__(self, topics: List[str], group_id: str = None):
        self.topics = topics
        # group_id is ignored for basic Pub/Sub, kept for interface compatibility
        self.group_id = group_id 
        
        self.redis: Redis = None
        self.pubsub = None
        self._started = False

    async def start(self):
        """Start the consumer."""
        if not self._started:
            if not self.redis:
                self.redis = get_redis_client()
            self.pubsub = self.redis.pubsub()
            for topic in self.topics:
                await self.pubsub.subscribe(topic)
                
            self._started = True
            logger.info(f"Event Consumer listening on topics: {self.topics}")

    async def stop(self):
        """Stop the consumer."""
        if self._started:
            await self.pubsub.unsubscribe()
            await self.pubsub.close()
            await self.redis.aclose()
            self._started = False
            logger.info(f"Event Consumer stopped.")

    async def __aiter__(self):
        """Yields messages as they arrive."""
        if not self._started:
            await self.start()
            
        async for msg in self.pubsub.listen():
            if msg['type'] == 'message':
                try:
                    topic = msg['channel'].decode('utf-8')
                    value = json.loads(msg['data'].decode('utf-8'))
                    yield topic, value
                except Exception as e:
                    logger.error(f"Failed to decode message: {e}")
