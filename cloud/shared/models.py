"""
Shared Pydantic models used across all cloud services.
Defines canonical data shapes for vehicles, edge nodes, events, and payloads.
"""
from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────

class VehicleType(str, Enum):
    AMBULANCE = "AMBULANCE"
    FIRE = "FIRE"
    POLICE = "POLICE"
    DISASTER = "DISASTER"


class PriorityClass(int, Enum):
    MASS_CASUALTY = 1
    AMBULANCE = 2
    FIRE = 3
    POLICE = 4
    DISASTER_RESPONSE = 5


class ControllerType(str, Enum):
    PLC_NTCIP = "PLC_NTCIP"
    RELAY = "RELAY"
    SCOOT = "SCOOT"
    ECONOLITE = "ECONOLITE"


class PreemptOutcome(str, Enum):
    CLEARED = "CLEARED"
    ABORTED = "ABORTED"
    TIMEOUT = "TIMEOUT"
    MANUAL = "MANUAL"


class FaultSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SignalPhaseState(str, Enum):
    GREEN = "GREEN"
    AMBER = "AMBER"
    RED = "RED"
    ALL_RED = "ALL_RED"
    FLASHING_AMBER = "FLASHING_AMBER"


# ─────────────────────────────────────────────
# GPS / Location
# ─────────────────────────────────────────────

class GPSData(BaseModel):
    lat: float = Field(..., ge=-90, le=90, description="Latitude in decimal degrees")
    lon: float = Field(..., ge=-180, le=180, description="Longitude in decimal degrees")
    alt_m: float = Field(0.0, description="Altitude in meters")
    speed_kmh: float = Field(0.0, ge=0, description="Speed in km/h")
    heading_deg: float = Field(0.0, ge=0, lt=360, description="Heading 0–359 degrees")
    accuracy_m: float = Field(5.0, ge=0, description="GPS accuracy estimate in meters")


# ─────────────────────────────────────────────
# Vehicle Beacon (broadcast from VSU)
# ─────────────────────────────────────────────

class VehicleBeacon(BaseModel):
    """
    Payload broadcast by Vehicle-Side Unit (VSU).
    Signed with ECDSA-P256 private key before transmission.
    """
    vehicle_id: str = Field(..., json_schema_extra={"example": "AMB-MH-042"})
    vehicle_type: VehicleType
    priority_class: PriorityClass
    timestamp_utc: datetime
    gps: GPSData
    siren_active: bool
    battery_pct: int = Field(..., ge=0, le=100)
    destination: Optional[GPSData] = None
    nonce: str = Field(..., description="16-byte random hex for replay prevention")
    signature: str = Field(..., description="ECDSA-P256 hex signature of payload")


# ─────────────────────────────────────────────
# Vehicle Registry
# ─────────────────────────────────────────────

class VehicleRegisterRequest(BaseModel):
    vehicle_id: str = Field(..., min_length=3, max_length=20)
    vehicle_type: VehicleType
    priority_class: PriorityClass = PriorityClass.AMBULANCE
    license_plate: str = Field(..., max_length=15)
    agency_name: str = Field(..., max_length=100)
    city: str = Field(..., max_length=50)
    cert_pem: str = Field(..., description="X.509 public certificate in PEM format")


class VehicleResponse(BaseModel):
    vehicle_id: str
    vehicle_type: VehicleType
    priority_class: PriorityClass
    license_plate: str
    agency_name: str
    city: str
    is_active: bool
    registered_at: datetime
    last_seen: Optional[datetime] = None
    vsu_cert_hash: Optional[str] = None
    vsu_cert_pem: Optional[str] = None


# ─────────────────────────────────────────────
# Edge Node
# ─────────────────────────────────────────────

class EdgeNodeResponse(BaseModel):
    node_id: str
    location_lat: float
    location_lon: float
    intersection_name: str
    city: str
    is_online: bool
    last_heartbeat: Optional[datetime] = None
    firmware_version: Optional[str] = None
    controller_type: Optional[ControllerType] = None


class NodeHeartbeat(BaseModel):
    node_id: str
    timestamp_utc: datetime
    cpu_pct: float
    mem_pct: float
    temp_c: float
    cam_ok: bool
    lora_ok: bool
    lte_signal_dbm: int
    controller_ok: bool
    uptime_s: int
    firmware_version: str


# ─────────────────────────────────────────────
# Preemption Event
# ─────────────────────────────────────────────

class PreemptionEventCreate(BaseModel):
    vehicle_id: str
    node_id: str
    triggered_at: datetime
    eta_at_trigger_s: float
    approach_phase: int
    sensor_confidence: float = Field(..., ge=0, le=1)
    trigger_method: str  # e.g. "LORA+CAMERA+AUDIO"


class PreemptionEventResponse(BaseModel):
    event_id: UUID
    vehicle_id: str
    node_id: str
    triggered_at: datetime
    cleared_at: Optional[datetime] = None
    eta_at_trigger_s: float
    actual_arrival_s: Optional[float] = None
    approach_phase: int
    sensor_confidence: float
    trigger_method: str
    outcome: PreemptOutcome


# ─────────────────────────────────────────────
# MQTT Messages
# ─────────────────────────────────────────────

class PreemptActiveMessage(BaseModel):
    """Published by edge node when preemption is triggered."""
    vehicle_id: str
    node_id: str
    eta_s: float
    approach_phase: int
    confidence: float
    timestamp_utc: datetime


class PreemptAlertMessage(BaseModel):
    """Published by cloud to pre-alert upstream edge nodes."""
    vehicle_id: str
    vehicle_type: VehicleType
    priority_class: PriorityClass
    origin_node_id: str
    target_node_id: str
    estimated_eta_s: float
    gps: GPSData
    timestamp_utc: datetime


class SystemFaultMessage(BaseModel):
    """Published by edge node on hardware/software fault."""
    node_id: str
    fault_type: str
    severity: FaultSeverity
    detail: str
    timestamp_utc: datetime
