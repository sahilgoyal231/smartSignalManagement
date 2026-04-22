"""
Initial migration — creates all 6 tables for the Smart Signal System.
Generated: 2026-03-06

Tables:
  1. vehicles           — registered emergency vehicles
  2. edge_nodes         — roadside IoT nodes at intersections
  3. signal_phases      — phase config per node/direction
  4. preemption_events  — full audit log of every signal preemption
  5. system_faults      — hardware/software fault log
  6. users              — dashboard operator accounts
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from alembic import op

# ─────────────────────────────────────────────────────────────
revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None
# ─────────────────────────────────────────────────────────────


def upgrade() -> None:

    # ── Enums ────────────────────────────────────────────────
    vehicle_type = sa.Enum(
        "AMBULANCE", "FIRE", "POLICE", "DISASTER",
        name="vehicle_type_enum"
    )
    controller_type = sa.Enum(
        "PLC_NTCIP", "RELAY", "SCOOT", "ECONOLITE",
        name="controller_type_enum"
    )
    direction_enum = sa.Enum(
        "NORTH", "SOUTH", "EAST", "WEST",
        "NORTHEAST", "NORTHWEST", "SOUTHEAST", "SOUTHWEST",
        name="direction_enum"
    )
    outcome_enum = sa.Enum(
        "CLEARED", "ABORTED", "TIMEOUT", "MANUAL",
        name="preempt_outcome_enum"
    )
    fault_type_enum = sa.Enum(
        "CAMERA_FAIL", "MIC_FAIL", "LORA_FAIL", "LTE_FAIL", "BLE_FAIL",
        "CONTROLLER_UNRESPONSIVE", "GPS_DEGRADED", "POWER_LOW",
        "OVERHEAT", "ENCLOSURE_TAMPER", "WATCHDOG_RESET",
        name="fault_type_enum"
    )
    fault_severity_enum = sa.Enum(
        "LOW", "MEDIUM", "HIGH", "CRITICAL",
        name="fault_severity_enum"
    )
    user_role_enum = sa.Enum(
        "SUPER_ADMIN", "OPERATIONS", "AUDITOR",
        name="user_role_enum"
    )

    # ── Table 1: vehicles ────────────────────────────────────
    op.create_table(
        "vehicles",
        sa.Column("vehicle_id",     sa.String(20),  primary_key=True),
        sa.Column("vehicle_type",   vehicle_type,   nullable=False),
        sa.Column("priority_class", sa.SmallInteger(), nullable=False, server_default="2"),
        sa.Column("license_plate",  sa.String(15),  nullable=False, unique=True),
        sa.Column("agency_name",    sa.String(100), nullable=False),
        sa.Column("city",           sa.String(50),  nullable=False),
        sa.Column("vsu_cert_hash",  sa.String(64),  nullable=False),
        sa.Column("vsu_cert_pem",   sa.Text(),      nullable=False),
        sa.Column("registered_at",  sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_seen",      sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active",      sa.Boolean(),   nullable=False, server_default="true"),
        sa.Column("notes",          sa.Text(),      nullable=True),
    )
    op.create_index("ix_vehicles_city",        "vehicles", ["city"])
    op.create_index("ix_vehicles_type_active", "vehicles", ["vehicle_type", "is_active"])

    # ── Table 2: edge_nodes ──────────────────────────────────
    op.create_table(
        "edge_nodes",
        sa.Column("node_id",              sa.String(20),  primary_key=True),
        sa.Column("location_lat",         sa.Numeric(10, 7), nullable=False),
        sa.Column("location_lon",         sa.Numeric(10, 7), nullable=False),
        sa.Column("intersection_name",    sa.String(150), nullable=False),
        sa.Column("city",                 sa.String(50),  nullable=False),
        sa.Column("firmware_version",     sa.String(20),  nullable=True),
        sa.Column("controller_type",      controller_type, nullable=True),
        sa.Column("preempt_threshold_s",  sa.SmallInteger(), nullable=False, server_default="45"),
        sa.Column("alert_threshold_s",    sa.SmallInteger(), nullable=False, server_default="90"),
        sa.Column("max_green_hold_s",     sa.SmallInteger(), nullable=False, server_default="60"),
        sa.Column("installed_at",         sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_heartbeat",       sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_online",            sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("notes",                sa.Text(), nullable=True),
    )
    op.create_index("ix_edge_nodes_city",   "edge_nodes", ["city"])
    op.create_index("ix_edge_nodes_online", "edge_nodes", ["is_online"])

    # ── Table 3: signal_phases ───────────────────────────────
    op.create_table(
        "signal_phases",
        sa.Column("phase_id",           sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("node_id",            sa.String(20),
                  sa.ForeignKey("edge_nodes.node_id", ondelete="CASCADE"), nullable=False),
        sa.Column("phase_number",       sa.SmallInteger(), nullable=False),
        sa.Column("direction",          direction_enum, nullable=False),
        sa.Column("normal_green_s",     sa.SmallInteger(), nullable=False),
        sa.Column("normal_red_s",       sa.SmallInteger(), nullable=False),
        sa.Column("min_green_s",        sa.SmallInteger(), nullable=False, server_default="10"),
        sa.Column("max_green_s",        sa.SmallInteger(), nullable=False, server_default="120"),
        sa.Column("is_pedestrian_phase", sa.Boolean(), nullable=False, server_default="false"),
        sa.UniqueConstraint("node_id", "phase_number", name="uq_node_phase"),
    )
    op.create_index("ix_signal_phases_node", "signal_phases", ["node_id"])

    # ── Table 4: preemption_events ───────────────────────────
    op.create_table(
        "preemption_events",
        sa.Column("event_id",            UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("vehicle_id",          sa.String(20),
                  sa.ForeignKey("vehicles.vehicle_id"), nullable=False),
        sa.Column("node_id",             sa.String(20),
                  sa.ForeignKey("edge_nodes.node_id"), nullable=False),
        sa.Column("triggered_at",        sa.DateTime(timezone=True), nullable=False),
        sa.Column("cleared_at",          sa.DateTime(timezone=True), nullable=True),
        sa.Column("eta_at_trigger_s",    sa.Float(), nullable=True),
        sa.Column("actual_arrival_s",    sa.Float(), nullable=True),
        sa.Column("approach_phase",      sa.SmallInteger(), nullable=True),
        sa.Column("sensor_confidence",   sa.Float(), nullable=True),
        sa.Column("trigger_method",      sa.String(50), nullable=True),
        sa.Column("outcome",             outcome_enum, nullable=False, server_default="CLEARED"),
        sa.Column("green_hold_duration_s", sa.Float(), nullable=True),
        sa.Column("notes",               sa.Text(), nullable=True),
    )
    op.create_index("ix_preemption_vehicle_id",    "preemption_events", ["vehicle_id"])
    op.create_index("ix_preemption_node_id",        "preemption_events", ["node_id"])
    op.create_index("ix_preemption_triggered_at",   "preemption_events", ["triggered_at"])
    op.create_index("ix_preemption_outcome",        "preemption_events", ["outcome"])

    # ── Table 5: system_faults ───────────────────────────────
    op.create_table(
        "system_faults",
        sa.Column("fault_id",    sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("node_id",     sa.String(20),
                  sa.ForeignKey("edge_nodes.node_id"), nullable=False),
        sa.Column("fault_type",  fault_type_enum, nullable=False),
        sa.Column("severity",    fault_severity_enum, nullable=False),
        sa.Column("detail",      sa.Text(), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_resolved", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_index("ix_faults_node_id",          "system_faults", ["node_id"])
    op.create_index("ix_faults_severity_resolved", "system_faults", ["severity", "is_resolved"])
    op.create_index("ix_faults_detected_at",       "system_faults", ["detected_at"])

    # ── Table 6: users ───────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("user_id",      UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("username",     sa.String(50),  nullable=False, unique=True),
        sa.Column("password_hash", sa.String(128), nullable=False),
        sa.Column("role",          user_role_enum, nullable=False),
        sa.Column("email",         sa.String(100), nullable=False, unique=True),
        sa.Column("full_name",     sa.String(100), nullable=True),
        sa.Column("city_access",   sa.String(50),  nullable=True),
        sa.Column("created_at",    sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_login",    sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active",     sa.Boolean(), nullable=False, server_default="true"),
    )
    op.create_index("ix_users_role",   "users", ["role"])
    op.create_index("ix_users_active", "users", ["is_active"])


def downgrade() -> None:
    """Drop all tables and enums in reverse dependency order."""
    op.drop_table("preemption_events")
    op.drop_table("system_faults")
    op.drop_table("signal_phases")
    op.drop_table("users")
    op.drop_table("edge_nodes")
    op.drop_table("vehicles")

    # Drop enums
    for enum_name in [
        "vehicle_type_enum", "controller_type_enum", "direction_enum",
        "preempt_outcome_enum", "fault_type_enum", "fault_severity_enum", "user_role_enum"
    ]:
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)
