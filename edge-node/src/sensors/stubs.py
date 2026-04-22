"""
Edge Node — Sensor Stubs
(Camera/YOLOv8 + Audio/FFT simulations)
"""
import random
import asyncio

class YoloCameraStub:
    """Simulates a camera running YOLOv8 detecting emergency vehicles."""
    
    def __init__(self, node_id: str, trigger_prob: float = 0.05):
        self.node_id = node_id
        self._trigger_prob = trigger_prob
        self.active_detections = []
        
    async def run(self, fusion_engine):
        """Background loop pushing visual detection events to the fusion engine."""
        while True:
            await asyncio.sleep(2.0)
            
            # Simulate a 5% chance of visually tracking a nearby ambulance
            if random.random() < self._trigger_prob:
                conf = round(random.uniform(0.60, 0.95), 2)
                veh_id = f"VISUAL-GHOST-{random.randint(100,999)}"
                fusion_engine.ingest_reading(
                    vehicle_id=veh_id, 
                    source="CAMERA", 
                    data={"confidence": conf, "bounding_box": [10, 20, 100, 200]}
                )


class AudioFftStub:
    """Simulates a microphone running FFT to detect siren acoustic signatures."""
    
    def __init__(self, node_id: str, trigger_prob: float = 0.10):
        self.node_id = node_id
        self._trigger_prob = trigger_prob
        
    async def run(self, fusion_engine):
        """Background loop pushing audio detection events to the fusion engine."""
        while True:
            await asyncio.sleep(1.0)
            
            # Simulate a 10% chance of hearing a Hi-Lo or Yelp siren
            if random.random() < self._trigger_prob:
                conf = round(random.uniform(0.50, 0.85), 2)
                veh_id = f"AUDIO-GHOST-{random.randint(100,999)}"
                fusion_engine.ingest_reading(
                    vehicle_id=veh_id, 
                    source="AUDIO", 
                    data={"confidence": conf, "freq_hz": 1200}
                )
