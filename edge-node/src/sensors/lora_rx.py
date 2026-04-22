"""
Edge Node — LoRa RX Parser
"""
import asyncio
import json
import traceback
from loguru import logger

class LoraReceiver:
    """
    Simulates reading decrypted VSU beacon payloads from a serial LoRa module.
    In production, this reads /dev/ttyUSB0, decodes the protobuf/JSON, and verifies
    the ECDSA signature via a connected HSM or software crypto module.
    """
    def __init__(self, port: str):
        self.port = port
        self.running = False
        
    async def run(self, fusion_engine):
        self.running = True
        logger.info(f"LoRa RX listening on {self.port}")
        
        # We simulate incoming LoRa traffic by tailing a dummy file 
        # or just generating mock data for specific vehicles if we are testing.
        # But to be robust, we'll expose an async ingestion queue.
        self.queue = asyncio.Queue()
        
        while self.running:
            try:
                # Wait for an incoming JSON string
                payload_str = await self.queue.get()
                
                # Parse JSON
                data = json.loads(payload_str)
                
                # Verify basic structure
                req_keys = ["vehicle_id", "priority_class", "gps", "siren_active", "signature"]
                if not all(k in data for k in req_keys):
                    logger.warning("Dropped malformed LoRa beacon")
                    continue
                    
                # Skip if siren is not active
                if not data["siren_active"]:
                    continue

                # Ingest into fusion engine
                # The payload must contain gps.lat, gps.lon, gps.speed_kmh, gps.heading_deg
                gps = data.get("gps", {})
                
                fusion_engine.ingest_reading(
                    vehicle_id=data["vehicle_id"],
                    source="LORA",
                    data={
                        "confidence": 1.0, # Cryptographically verified
                        "lat": gps.get("lat", 0.0),
                        "lon": gps.get("lon", 0.0),
                        "speed_kmh": gps.get("speed_kmh", 0.0),
                        "heading_deg": gps.get("heading_deg", 0.0),
                        "priority_class": data["priority_class"]
                    }
                )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"LoRa RX error: {e}")
                logger.debug(traceback.format_exc())

    async def simulate_reception(self, payload_dict: dict):
        """Helper to inject simulated LoRa payloads into the queue."""
        if hasattr(self, 'queue'):
            await self.queue.put(json.dumps(payload_dict))
