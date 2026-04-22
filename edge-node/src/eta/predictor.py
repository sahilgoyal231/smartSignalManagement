"""
Edge Node — ETA Predictor Core Logic
"""
import math

class KinematicPredictor:
    def __init__(self, node_lat: float, node_lon: float):
        self.node_lat = node_lat
        self.node_lon = node_lon
        
    def _haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate the great-circle distance between two points on the Earth surface in meters."""
        R = 6371000.0  # Earth radius in meters
        
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)
        
        a = math.sin(delta_phi / 2.0)**2 + \
            math.cos(phi1) * math.cos(phi2) * \
            math.sin(delta_lambda / 2.0)**2
            
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

    def predict_eta(self, veh_lat: float, veh_lon: float, speed_kmh: float) -> float:
        """
        Calculate straightforward kinematic ETA in seconds.
        If speed is extremely low, assumes a fallback speed to avoid infinite ETA.
        """
        dist_m = self._haversine_distance(self.node_lat, self.node_lon, veh_lat, veh_lon)
        
        # Convert speed to m/s
        speed_ms = speed_kmh * (1000.0 / 3600.0)
        
        # If stationary or crawling, assume rolling at 10 km/h (2.77 m/s) minimum 
        # to ensure the system doesn't drop the preemption request immediately.
        effective_speed_ms = max(speed_ms, 2.77)
        
        eta_s = dist_m / effective_speed_ms
        return eta_s

    def calculate_distance(self, veh_lat: float, veh_lon: float) -> float:
        """Return distance in meters."""
        return self._haversine_distance(self.node_lat, self.node_lon, veh_lat, veh_lon)
