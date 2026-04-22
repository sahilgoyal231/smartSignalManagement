"""
SQLAlchemy ORM Models — PostgreSQL
====================================
Defines all 6 database tables with relationships, indexes, and constraints.
Tables: vehicles, edge_nodes, signal_phases, preemption_events, system_faults, users
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer,
    Numeric, SmallInteger, String, Text, Float, UniqueConstraint, Index,
    func, Enum as SAEnum
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """All models share this base — provides metadata and type annotations."""
    pass


# ─────────────────────────────────────────────────────────────
# Table 1: vehicles
# ─────────────────────────────────────────────────────────────

class Vehicle(Base):
    """
    Registered emergency vehicles with their VSU hardware credentials.
    Each vehicle has a unique X.509 certificate for beacon authentication.
    """
    __tablename__ = "vehicles"

    vehicle_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    vehicle_type: Mapped[str] = mapped_column(
        SAEnum("AMBULANCE", "FIRE", "POLICE", "DISASTER", name="vehicle_type_enum"),
        nullable=False
    )
    priority_class: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=2)
    license_plate: Mapped[str] = mapped_column(String(15), unique=True, nullable=False)
    agency_name: Mapped[str] = mapped_column(String(100), nullable=False)
    city: Mapped[str] = mapped_column(String(50), nullable=False)
    vsu_cert_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="SHA-256 fingerprint of X.509 device cert")
    vsu_cert_pem: Mapped[str] = mapped_column(Text, nullable=False, comment="Full PEM certificate for signature verification")
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    preemption_events: Mapped[List["PreemptionEvent"]] = relationship(
        "PreemptionEvent", back_populates="vehicle", lazy="dynamic"
    )

    # Indexes
    __table_args__ = (
        Index("ix_vehicles_city", "city"),
        Index("ix_vehicles_type_active", "vehicle_type", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<Vehicle {self.vehicle_id} ({self.vehicle_type})>"


# ─────────────────────────────────────────────────────────────
# Table 2: edge_nodes
# ─────────────────────────────────────────────────────────────

class EdgeNode(Base):
    """
    Roadside IoT edge node deployed at each controlled intersection.
    Stores location, hardware config, and live health state.
    """
    __tablename__ = "edge_nodes"

    node_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    location_lat: Mapped[float] = mapped_column(Numeric(10, 7), nullable=False)
    location_lon: Mapped[float] = mapped_column(Numeric(10, 7), nullable=False)
    intersection_name: Mapped[str] = mapped_column(String(150), nullable=False)
    city: Mapped[str] = mapped_column(String(50), nullable=False)
    firmware_version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    controller_type: Mapped[Optional[str]] = mapped_column(
        SAEnum("PLC_NTCIP", "RELAY", "SCOOT", "ECONOLITE", name="controller_type_enum"),
        nullable=True
    )
    preempt_threshold_s: Mapped[int] = mapped_column(SmallInteger, default=45, nullable=False)
    alert_threshold_s: Mapped[int] = mapped_column(SmallInteger, default=90, nullable=False)
    max_green_hold_s: Mapped[int] = mapped_column(SmallInteger, default=60, nullable=False)
    installed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_heartbeat: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_online: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    signal_phases: Mapped[List["SignalPhase"]] = relationship(
        "SignalPhase", back_populates="node", cascade="all, delete-orphan"
    )
    preemption_events: Mapped[List["PreemptionEvent"]] = relationship(
        "PreemptionEvent", back_populates="node", lazy="dynamic"
    )
    faults: Mapped[List["SystemFault"]] = relationship(
        "SystemFault", back_populates="node", lazy="dynamic"
    )

    __table_args__ = (
        Index("ix_edge_nodes_city", "city"),
        Index("ix_edge_nodes_online", "is_online"),
    )

    def __repr__(self) -> str:
        return f"<EdgeNode {self.node_id} @ {self.intersection_name}>"


# ─────────────────────────────────────────────────────────────
# Table 3: signal_phases
# ─────────────────────────────────────────────────────────────

class SignalPhase(Base):
    """
    Signal phase configuration per intersection direction.
    e.g., Phase 1 = Northbound green, 35s normal green, 10s min.
    """
    __tablename__ = "signal_phases"

    phase_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("edge_nodes.node_id", ondelete="CASCADE"), nullable=False
    )
    phase_number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    direction: Mapped[str] = mapped_column(
        SAEnum("NORTH", "SOUTH", "EAST", "WEST", "NORTHEAST", "NORTHWEST",
               "SOUTHEAST", "SOUTHWEST", name="direction_enum"),
        nullable=False
    )
    normal_green_s: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    normal_red_s: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    min_green_s: Mapped[int] = mapped_column(SmallInteger, default=10, nullable=False)
    max_green_s: Mapped[int] = mapped_column(SmallInteger, default=120, nullable=False)
    is_pedestrian_phase: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationship
    node: Mapped["EdgeNode"] = relationship("EdgeNode", back_populates="signal_phases")

    __table_args__ = (
        UniqueConstraint("node_id", "phase_number", name="uq_node_phase"),
        Index("ix_signal_phases_node", "node_id"),
    )

    def __repr__(self) -> str:
        return f"<SignalPhase node={self.node_id} ph={self.phase_number} dir={self.direction}>"


# ─────────────────────────────────────────────────────────────
# Table 4: preemption_events
# ─────────────────────────────────────────────────────────────

class PreemptionEvent(Base):
    """
    Full audit log of every signal preemption triggered by an emergency vehicle.
    Used for legal compliance, performance analytics, and KPI measurement.
    """
    __tablename__ = "preemption_events"

    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    vehicle_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("vehicles.vehicle_id"), nullable=False
    )
    node_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("edge_nodes.node_id"), nullable=False
    )
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cleared_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    eta_at_trigger_s: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="Predicted ETA when preemption was triggered")
    actual_arrival_s: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="Actual seconds from trigger to vehicle arrival")
    approach_phase: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    sensor_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="Sensor fusion confidence score 0.0-1.0")
    trigger_method: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, comment="e.g. LORA+CAMERA+AUDIO"
    )
    outcome: Mapped[str] = mapped_column(
        SAEnum("CLEARED", "ABORTED", "TIMEOUT", "MANUAL", name="preempt_outcome_enum"),
        default="CLEARED", nullable=False
    )
    green_hold_duration_s: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    vehicle: Mapped["Vehicle"] = relationship("Vehicle", back_populates="preemption_events")
    node: Mapped["EdgeNode"] = relationship("EdgeNode", back_populates="preemption_events")

    __table_args__ = (
        Index("ix_preemption_vehicle_id", "vehicle_id"),
        Index("ix_preemption_node_id", "node_id"),
        Index("ix_preemption_triggered_at", "triggered_at"),
        Index("ix_preemption_outcome", "outcome"),
    )

    def __repr__(self) -> str:
        return f"<PreemptionEvent {self.event_id} v={self.vehicle_id} n={self.node_id}>"


# ─────────────────────────────────────────────────────────────
# Table 5: system_faults
# ─────────────────────────────────────────────────────────────

class SystemFault(Base):
    """
    Hardware and software faults reported by edge nodes.
    Tracked for SLA/uptime monitoring and maintenance scheduling.
    """
    __tablename__ = "system_faults"

    fault_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("edge_nodes.node_id"), nullable=False
    )
    fault_type: Mapped[str] = mapped_column(
        SAEnum(
            "CAMERA_FAIL", "MIC_FAIL", "LORA_FAIL", "LTE_FAIL", "BLE_FAIL",
            "CONTROLLER_UNRESPONSIVE", "GPS_DEGRADED", "POWER_LOW",
            "OVERHEAT", "ENCLOSURE_TAMPER", "WATCHDOG_RESET",
            name="fault_type_enum"
        ),
        nullable=False
    )
    severity: Mapped[str] = mapped_column(
        SAEnum("LOW", "MEDIUM", "HIGH", "CRITICAL", name="fault_severity_enum"),
        nullable=False
    )
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationship
    node: Mapped["EdgeNode"] = relationship("EdgeNode", back_populates="faults")

    __table_args__ = (
        Index("ix_faults_node_id", "node_id"),
        Index("ix_faults_severity_resolved", "severity", "is_resolved"),
        Index("ix_faults_detected_at", "detected_at"),
    )

    def __repr__(self) -> str:
        return f"<SystemFault {self.fault_type} @ {self.node_id} [{self.severity}]>"


# ─────────────────────────────────────────────────────────────
# Table 6: users
# ─────────────────────────────────────────────────────────────

class User(Base):
    """
    Dashboard admin users with role-based access control (RBAC).
    Passwords stored as bcrypt hashes — never plaintext.
    """
    __tablename__ = "users"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False, comment="bcrypt hash")
    role: Mapped[str] = mapped_column(
        SAEnum("SUPER_ADMIN", "OPERATIONS", "AUDITOR", name="user_role_enum"),
        nullable=False
    )
    email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    city_access: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
        comment="NULL = all cities. Set to restrict access to one city."
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        Index("ix_users_role", "role"),
        Index("ix_users_active", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<User {self.username} [{self.role}]>"
