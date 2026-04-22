"""
Edge Node — Sensor Fusion Engine
"""
from typing import Dict, Any, List
from datetime import datetime, timezone
from loguru import logger

class SensorFusionEngine:
    def __init__(self, stale_timeout_s: float = 15.0):
        self.stale_timeout_s = stale_timeout_s
        self.observations: Dict[str, List[Dict[str, Any]]] = {}

    def ingest_reading(self, vehicle_id: str, source: str, data: Dict[str, Any]):
        """Ingest a sensor reading (LoRa, Camera, Audio, BLE) for a given vehicle."""
        if vehicle_id not in self.observations:
            self.observations[vehicle_id] = []
        
        data['source'] = source
        data['timestamp_utc'] = datetime.now(timezone.utc).timestamp()
        self.observations[vehicle_id].append(data)

    def calculate_confidence(self, vehicle_id: str) -> float:
        """
        Calculate a fused confidence score [0.0, 1.0] taking into account varying
        sensor reliabilities and recency.
        
        Weights:
        - LoRa Crypto-Signed Beacon = 0.6 (Highly trusted, but GPS can drift)
        - Visual (YOLOv8 Ambulance/Fire/Police) = 0.3 (Confirms physical presence)
        - Audio (Siren FFT Signature) = 0.2 (Confirms active emergency state)
        - BLE (Secondary short-range MAC) = 0.1
        
        Score is clamped to 1.0. Recent readings carry more weight.
        """
        weights = {
            "LORA": 0.6,
            "CAMERA": 0.3,
            "AUDIO": 0.2,
            "BLE": 0.1
        }
        
        now = datetime.now(timezone.utc).timestamp()
        readings = self.observations.get(vehicle_id, [])
        
        # Prune stale readings first
        fresh_readings = [
            r for r in readings 
            if (now - r['timestamp_utc']) <= self.stale_timeout_s
        ]
        self.observations[vehicle_id] = fresh_readings
        
        if not fresh_readings:
            return 0.0

        confidence = 0.0
        sources_seen = set()

        # Iterate freshest to oldest
        for r in reversed(fresh_readings):
            src = r['source']
            if src not in sources_seen:
                base_weight = weights.get(src, 0.0)
                
                # Decay weight by age (linear decay over stale timeout)
                age = now - r['timestamp_utc']
                decay_factor = max(0.0, 1.0 - (age / self.stale_timeout_s))
                
                # Apply source-specific confidence modifiers if provided
                src_conf = r.get("confidence", 1.0)
                
                confidence += (base_weight * src_conf * decay_factor)
                sources_seen.add(src)

        return min(1.0, confidence)

    def get_fused_state(self, vehicle_id: str) -> Dict[str, Any]:
        """Returns the best known state for the vehicle by fusing measurements."""
        readings = self.observations.get(vehicle_id, [])
        if not readings:
            return {}
            
        # Simplistic fusion: just take the most recent GPS location from LoRa
        lora_readings = [r for r in readings if r['source'] == 'LORA']
        
        if not lora_readings:
            # We detected it visually/acoustically but have no LoRa telemetry yet
            return {"confidence": self.calculate_confidence(vehicle_id)}
            
        latest_lora = lora_readings[-1]
        
        return {
            "vehicle_id": vehicle_id,
            "location_lat": latest_lora.get("lat"),
            "location_lon": latest_lora.get("lon"),
            "speed_kmh": latest_lora.get("speed_kmh", 0.0),
            "heading_deg": latest_lora.get("heading_deg", 0.0),
            "confidence": self.calculate_confidence(vehicle_id),
            "last_seen_s_ago": datetime.now(timezone.utc).timestamp() - latest_lora['timestamp_utc']
        }
