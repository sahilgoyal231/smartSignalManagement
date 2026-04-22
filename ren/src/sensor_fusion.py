"""
Sensor Fusion Engine (Edge Node)
==================================
Aggregates telemetry from multiple sparse/noisy sources:
  1. LoRa (anonymous, long-range up to 3km, low-latency)
  2. BLE (authenticated ID, short-range <30m, fast)
  3. MQTT/Cloud (authenticated ID, full JSON, global, higher latency)
  4. Audio (local FFT microphone, binary siren presence)
  5. Camera (local computer vision, bounding boxes, visual confirmation)

Because LoRa is anonymous (to fit in 14 bytes), the fusion engine uses
spatial correlation (distance + heading) to associate anonymous LoRa hits
with authenticated MQTT/BLE tracks, creating a unified `FusionTrack`.

Tracks decay in confidence if not updated, and are pruned when stale.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from loguru import logger

from ren.src.beacon_parser import ParsedLoRaBeacon


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance between two coordinates in metres."""
    R = 6371000  # Radius of earth in m
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2)**2 + \
        math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


@dataclass
class FusionTrack:
    """Represents a unified emergency vehicle tracked by the intersection."""
    # Identity
    track_id: str        # e.g., "TRK-001" (anonymous) or "AMB-MH-042" (identified)
    is_identified: bool  # True if mapped to a real vehicle ID via BLE/MQTT
    priority: int        # 1-3 (higher is more urgent)

    # State
    lat: float
    lon: float
    speed_kmh: float
    heading_deg: float
    siren_active: bool

    # Meta
    first_seen: float
    last_seen: float
    confidence: float    # 0.0 to 100.0
    active_sources: Set[str] = field(default_factory=set)

    def age_seconds(self) -> float:
        return time.monotonic() - self.last_seen


class SensorFusionEngine:
    """
    Maintains active vehicle tracks by fusing multi-modal inputs.
    Runs periodically (e.g., 10Hz tick) to decay and prune stale tracks.
    """

    MAX_TRACK_AGE_S = 30.0           # Prune track if unseen for 30s
    SPATIAL_MATCH_RADIUS_M = 150.0   # Max distance to associate anonymous LoRa with track
    
    def __init__(self) -> None:
        self._tracks: Dict[str, FusionTrack] = {}
        self._track_counter = 0

        # Global sensor states
        self._local_audio_siren = False
        self._local_audio_last_seen = 0.0

    # ─────────────────────────────────────────────
    # Telemetry Ingress APIs
    # ─────────────────────────────────────────────

    def process_lora(self, beacon: ParsedLoRaBeacon) -> None:
        """
        LoRa is ultra-low-latency but anonymous (14 bytes).
        Try to match spatially with an existing track, else spawn new anonymous track.
        """
        now = time.monotonic()
        best_track: Optional[FusionTrack] = None
        best_dist = self.SPATIAL_MATCH_RADIUS_M

        for track in self._tracks.values():
            dist = haversine_distance(beacon.lat, beacon.lon, track.lat, track.lon)
            # Also could verify heading matches, but distance is primary
            if dist < best_dist:
                best_dist = dist
                best_track = track

        if best_track:
            # Update existing track
            best_track.lat = beacon.lat
            best_track.lon = beacon.lon
            best_track.speed_kmh = beacon.speed_kmh
            best_track.heading_deg = beacon.heading_deg
            # Siren state from LoRa is trusted
            best_track.siren_active = beacon.siren_active
            best_track.last_seen = now
            best_track.active_sources.add("lora")
            # Increase confidence
            best_track.confidence = min(100.0, best_track.confidence + 15.0)
            logger.debug(f"Fusion: LoRa mapped to {best_track.track_id} (dist={best_dist:.1f}m)")
        else:
            # Spawn new anonymous track
            self._track_counter += 1
            new_id = f"TRK-{self._track_counter:03d}"
            t = FusionTrack(
                track_id=new_id,
                is_identified=False,
                priority=beacon.priority,
                lat=beacon.lat,
                lon=beacon.lon,
                speed_kmh=beacon.speed_kmh,
                heading_deg=beacon.heading_deg,
                siren_active=beacon.siren_active,
                first_seen=now,
                last_seen=now,
                confidence=40.0,   # Start at 40 until more packets arrive
                active_sources={"lora"}
            )
            self._tracks[new_id] = t
            logger.info(f"Fusion: Spawned new anonymous track {new_id} from LoRa")

    def process_ble(self, vehicle_id: str, priority: int, lat: float, lon: float, siren: bool) -> None:
        """
        BLE has ID and is extremely short-range (<30m).
        Provides very high confidence confirmation.
        """
        now = time.monotonic()
        
        # 1. Does this ID already exist?
        if vehicle_id in self._tracks:
            t = self._tracks[vehicle_id]
        else:
            # 2. Try to promote an anonymous track spatially
            t = self._promote_anonymous_track(vehicle_id, lat, lon)
            if not t:
                # 3. Create fresh authenticated track
                t = FusionTrack(
                    track_id=vehicle_id,
                    is_identified=True,
                    priority=priority,
                    lat=lat, lon=lon, speed_kmh=0.0, heading_deg=0.0,
                    siren_active=siren,
                    first_seen=now, last_seen=now,
                    confidence=80.0, active_sources=set()
                )
                self._tracks[vehicle_id] = t
                logger.info(f"Fusion: Spawned new identified track {vehicle_id} from BLE")

        t.lat = lat
        t.lon = lon
        t.siren_active = siren
        t.priority = max(t.priority, priority)
        t.last_seen = now
        t.active_sources.add("ble")
        t.confidence = min(100.0, t.confidence + 30.0)

    def process_mqtt(self, vehicle_id: str, payload: dict) -> None:
        """
        MQTT comes from the cloud (ECDSA verified).
        Authoritative ground truth, but might be 1-2s lagged.
        """
        now = time.monotonic()
        gps = payload.get("gps", {})
        lat = gps.get("lat", 0.0)
        lon = gps.get("lon", 0.0)
        siren = payload.get("siren", False)
        prio = payload.get("priority", 1)

        if vehicle_id in self._tracks:
            t = self._tracks[vehicle_id]
        else:
            t = self._promote_anonymous_track(vehicle_id, lat, lon)
            if not t:
                t = FusionTrack(
                    track_id=vehicle_id, is_identified=True, priority=prio,
                    lat=lat, lon=lon, speed_kmh=gps.get("spd", 0.0), 
                    heading_deg=gps.get("hdg", 0.0), siren_active=siren,
                    first_seen=now, last_seen=now, confidence=70.0,
                    active_sources=set()
                )
                self._tracks[vehicle_id] = t
                logger.info(f"Fusion: Spawned new identified track {vehicle_id} from MQTT")
        
        # Update, but only if MQTT is fresher than LoRa (often LoRa is faster)
        # We assume MQTT latency is ~1s. If we got LoRa 0.1s ago, we don't clobber
        # the tight lat/lon, but we DO update the ID and confidence.
        time_since_last = now - t.last_seen
        if time_since_last > 1.0 or "lora" not in t.active_sources:
            t.lat = lat
            t.lon = lon
            t.speed_kmh = gps.get("spd", t.speed_kmh)
            t.heading_deg = gps.get("hdg", t.heading_deg)
        
        t.siren_active = t.siren_active or siren  # Logical OR for safety
        t.priority = max(t.priority, prio)
        t.last_seen = now
        t.active_sources.add("mqtt")
        t.confidence = min(100.0, t.confidence + 20.0)

    def process_local_audio(self, siren_detected: bool) -> None:
        """
        Local edge node microphone detects siren sweep.
        """
        self._local_audio_siren = siren_detected
        if siren_detected:
            self._local_audio_last_seen = time.monotonic()
            # Boost confidence of all tracks that claim to have siren active
            for t in self._tracks.values():
                if t.siren_active:
                    t.confidence = min(100.0, t.confidence + 5.0)
                    t.active_sources.add("audio")

    # ─────────────────────────────────────────────
    # Maintenance / Query
    # ─────────────────────────────────────────────

    def _promote_anonymous_track(self, vehicle_id: str, lat: float, lon: float) -> Optional[FusionTrack]:
        """Find the closest anonymous track and upgrade it to identified."""
        best_track: Optional[FusionTrack] = None
        best_dist = self.SPATIAL_MATCH_RADIUS_M
        best_key = None

        for key, track in list(self._tracks.items()):
            if not track.is_identified:
                dist = haversine_distance(lat, lon, track.lat, track.lon)
                if dist < best_dist:
                    best_dist = dist
                    best_track = track
                    best_key = key

        if best_track and best_key:
            # Upgrade it
            best_track.track_id = vehicle_id
            best_track.is_identified = True
            logger.info(f"Fusion: Promoted anonymous {best_key} → {vehicle_id} (dist={best_dist:.1f}m)")
            # Re-key in dictionary
            self._tracks[vehicle_id] = best_track
            del self._tracks[best_key]
            return best_track
            
        return None

    def tick(self) -> None:
        """
        Called periodically (e.g., 10Hz). Decays confidence and prunes stale tracks.
        """
        now = time.monotonic()
        dead_keys = []

        for key, t in self._tracks.items():
            age = now - t.last_seen
            
            # Confidence decay
            if age > 2.0:
                t.confidence -= 5.0 * 0.1  # Decay by 5 per sec if running at 10Hz (approx)
            
            # Source decay
            if age > 5.0:
                t.active_sources.discard("lora")
                t.active_sources.discard("ble")
                t.active_sources.discard("mqtt")

            # Pruning
            if age > self.MAX_TRACK_AGE_S or t.confidence <= 0:
                dead_keys.append(key)

        for key in dead_keys:
            logger.info(f"Fusion: Pruned stale/low-confidence track {key}")
            del self._tracks[key]

    def get_tracks(self) -> List[FusionTrack]:
        """Returns all currently active tracks."""
        return list(self._tracks.values())
