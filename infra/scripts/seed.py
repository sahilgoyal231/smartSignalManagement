"""
Seed Script — Populates the database with realistic test data.
=====================================================================
Run with:  python infra/scripts/seed.py
Requires:  PostgreSQL running + .env configured

Seeds:
  - 2 cities (Mumbai, Delhi)
  - 2 admin users (super_admin + operations)
  - 6 emergency vehicles (3 ambulance, 2 fire, 1 police) per city
  - 4 edge nodes per city with signal phases
  - Sample preemption events and system faults
"""
import asyncio
import sys
import os
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from sqlalchemy.ext.asyncio import AsyncSession
from cloud.shared.database import AsyncSessionLocal, init_db
from cloud.shared.db_models import (
    Vehicle, EdgeNode, SignalPhase, PreemptionEvent, SystemFault, User
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
now = datetime.now(timezone.utc)

# ─────────────────────────────────────────────────────────────
# Seed Data
# ─────────────────────────────────────────────────────────────

USERS = [
    User(
        username="superadmin",
        password_hash=pwd_context.hash("Admin@Secure#2026"),
        role="SUPER_ADMIN",
        email="admin@smartsignal.city",
        full_name="System Administrator",
        city_access=None,           # Access to all cities
    ),
    User(
        username="ops_mumbai",
        password_hash=pwd_context.hash("Ops@Mumbai#2026"),
        role="OPERATIONS",
        email="ops.mumbai@smartsignal.city",
        full_name="Mumbai Operations",
        city_access="Mumbai",
    ),
    User(
        username="auditor",
        password_hash=pwd_context.hash("Audit@Secure#2026"),
        role="AUDITOR",
        email="auditor@smartsignal.city",
        full_name="System Auditor",
        city_access=None,
    ),
]

VEHICLES = [
    # Mumbai Ambulances
    Vehicle(
        vehicle_id="AMB-MH-001", vehicle_type="AMBULANCE", priority_class=2,
        license_plate="MH01AB0001", agency_name="KEM Hospital Mumbai",
        city="Mumbai", vsu_cert_hash="a" * 64, vsu_cert_pem="PLACEHOLDER_PEM",
        is_active=True, last_seen=now - timedelta(hours=2),
    ),
    Vehicle(
        vehicle_id="AMB-MH-002", vehicle_type="AMBULANCE", priority_class=2,
        license_plate="MH01AB0002", agency_name="Bombay Hospital",
        city="Mumbai", vsu_cert_hash="b" * 64, vsu_cert_pem="PLACEHOLDER_PEM",
        is_active=True, last_seen=now - timedelta(minutes=30),
    ),
    Vehicle(
        vehicle_id="AMB-MH-003", vehicle_type="AMBULANCE", priority_class=2,
        license_plate="MH01AB0003", agency_name="Lilavati Hospital",
        city="Mumbai", vsu_cert_hash="c" * 64, vsu_cert_pem="PLACEHOLDER_PEM",
        is_active=True, last_seen=now - timedelta(days=1),
    ),
    # Mumbai Fire
    Vehicle(
        vehicle_id="FIRE-MH-001", vehicle_type="FIRE", priority_class=3,
        license_plate="MH01FB0001", agency_name="Mumbai Fire Brigade",
        city="Mumbai", vsu_cert_hash="d" * 64, vsu_cert_pem="PLACEHOLDER_PEM",
        is_active=True,
    ),
    Vehicle(
        vehicle_id="FIRE-MH-002", vehicle_type="FIRE", priority_class=3,
        license_plate="MH01FB0002", agency_name="Mumbai Fire Brigade",
        city="Mumbai", vsu_cert_hash="e" * 64, vsu_cert_pem="PLACEHOLDER_PEM",
        is_active=True,
    ),
    # Mumbai Police
    Vehicle(
        vehicle_id="POL-MH-001", vehicle_type="POLICE", priority_class=4,
        license_plate="MH01PB0001", agency_name="Mumbai Police",
        city="Mumbai", vsu_cert_hash="f" * 64, vsu_cert_pem="PLACEHOLDER_PEM",
        is_active=True,
    ),
    # Delhi Ambulances
    Vehicle(
        vehicle_id="AMB-DL-001", vehicle_type="AMBULANCE", priority_class=2,
        license_plate="DL01AB0001", agency_name="AIIMS Delhi",
        city="Delhi", vsu_cert_hash="g" * 64, vsu_cert_pem="PLACEHOLDER_PEM",
        is_active=True,
    ),
    Vehicle(
        vehicle_id="AMB-DL-002", vehicle_type="AMBULANCE", priority_class=2,
        license_plate="DL01AB0002", agency_name="Safdarjung Hospital",
        city="Delhi", vsu_cert_hash="h" * 64, vsu_cert_pem="PLACEHOLDER_PEM",
        is_active=True,
    ),
    Vehicle(
        vehicle_id="FIRE-DL-001", vehicle_type="FIRE", priority_class=3,
        license_plate="DL01FB0001", agency_name="Delhi Fire Services",
        city="Delhi", vsu_cert_hash="i" * 64, vsu_cert_pem="PLACEHOLDER_PEM",
        is_active=True,
    ),
]

# Mumbai edge nodes (4 intersections)
EDGE_NODES = [
    EdgeNode(
        node_id="NODE-MH-001", intersection_name="BKC Junction - Western Expressway",
        city="Mumbai", location_lat=19.0654, location_lon=72.8647,
        firmware_version="v1.0.0", controller_type="PLC_NTCIP",
        is_online=True, last_heartbeat=now - timedelta(seconds=25),
    ),
    EdgeNode(
        node_id="NODE-MH-002", intersection_name="Dharavi - Sion Road Junction",
        city="Mumbai", location_lat=19.0396, location_lon=72.8544,
        firmware_version="v1.0.0", controller_type="RELAY",
        is_online=True, last_heartbeat=now - timedelta(seconds=10),
    ),
    EdgeNode(
        node_id="NODE-MH-003", intersection_name="Dadar - LBS Marg",
        city="Mumbai", location_lat=19.0178, location_lon=72.8478,
        firmware_version="v1.0.0", controller_type="PLC_NTCIP",
        is_online=True, last_heartbeat=now - timedelta(minutes=1),
    ),
    EdgeNode(
        node_id="NODE-MH-004", intersection_name="Parel - Elphinstone Road",
        city="Mumbai", location_lat=18.9986, location_lon=72.8399,
        firmware_version="v1.0.0", controller_type="RELAY",
        is_online=False,   # Simulated offline node
        last_heartbeat=now - timedelta(hours=3),
    ),
    # Delhi edge nodes
    EdgeNode(
        node_id="NODE-DL-001", intersection_name="Connaught Place - Janpath",
        city="Delhi", location_lat=28.6330, location_lon=77.2194,
        firmware_version="v1.0.0", controller_type="PLC_NTCIP",
        is_online=True, last_heartbeat=now - timedelta(seconds=15),
    ),
    EdgeNode(
        node_id="NODE-DL-002", intersection_name="AIIMS Flyover - Ring Road",
        city="Delhi", location_lat=28.5672, location_lon=77.2100,
        firmware_version="v1.0.0", controller_type="PLC_NTCIP",
        is_online=True, last_heartbeat=now - timedelta(seconds=30),
    ),
]

# Signal phases per node (4 phases = N/S/E/W per intersection)
def make_phases(node_id: str) -> list[SignalPhase]:
    configs = [
        ("NORTH", 1, 35, 55), ("SOUTH", 2, 35, 55),
        ("EAST",  3, 25, 65), ("WEST",  4, 25, 65),
    ]
    return [
        SignalPhase(
            node_id=node_id, phase_number=ph,
            direction=direction,
            normal_green_s=green, normal_red_s=red,
            min_green_s=10, max_green_s=120,
        )
        for direction, ph, green, red in configs
    ]

# Preemption events
PREEMPTION_EVENTS = [
    PreemptionEvent(
        vehicle_id="AMB-MH-001", node_id="NODE-MH-001",
        triggered_at=now - timedelta(hours=6, minutes=22),
        cleared_at=now - timedelta(hours=6, minutes=21),
        eta_at_trigger_s=38.5, actual_arrival_s=40.1,
        approach_phase=3, sensor_confidence=0.96,
        trigger_method="LORA+CAMERA+AUDIO",
        outcome="CLEARED", green_hold_duration_s=42.3,
    ),
    PreemptionEvent(
        vehicle_id="AMB-MH-002", node_id="NODE-MH-002",
        triggered_at=now - timedelta(hours=3, minutes=10),
        cleared_at=now - timedelta(hours=3, minutes=9),
        eta_at_trigger_s=41.0, actual_arrival_s=44.0,
        approach_phase=1, sensor_confidence=0.88,
        trigger_method="LORA+BLE",
        outcome="CLEARED", green_hold_duration_s=45.0,
    ),
    PreemptionEvent(
        vehicle_id="FIRE-MH-001", node_id="NODE-MH-003",
        triggered_at=now - timedelta(hours=1, minutes=5),
        cleared_at=now - timedelta(hours=1, minutes=3, seconds=30),
        eta_at_trigger_s=35.0, actual_arrival_s=37.8,
        approach_phase=2, sensor_confidence=0.92,
        trigger_method="LORA+CAMERA",
        outcome="CLEARED", green_hold_duration_s=39.0,
    ),
]

# System faults
FAULTS = [
    SystemFault(
        node_id="NODE-MH-004", fault_type="LTE_FAIL",
        severity="HIGH", detail="4G modem unresponsive — SIM not registered",
        detected_at=now - timedelta(hours=3), is_resolved=False,
    ),
    SystemFault(
        node_id="NODE-MH-002", fault_type="CAMERA_FAIL",
        severity="MEDIUM", detail="Camera module timeout — restarted successfully",
        detected_at=now - timedelta(hours=5),
        resolved_at=now - timedelta(hours=4, minutes=45), is_resolved=True,
    ),
    SystemFault(
        node_id="NODE-DL-001", fault_type="GPS_DEGRADED",
        severity="LOW", detail="GPS accuracy > 8m — urban canyon effect",
        detected_at=now - timedelta(hours=1), is_resolved=False,
    ),
]


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────

async def seed() -> None:
    print("🌱 Initialising DB schema...")
    await init_db()

    async with AsyncSessionLocal() as session:
        print("👤 Seeding users...")
        session.add_all(USERS)
        await session.flush()

        print("🚗 Seeding vehicles...")
        session.add_all(VEHICLES)
        await session.flush()

        print("📍 Seeding edge nodes...")
        session.add_all(EDGE_NODES)
        await session.flush()

        print("🚦 Seeding signal phases...")
        for node in EDGE_NODES:
            session.add_all(make_phases(node.node_id))
        await session.flush()

        print("⚡ Seeding preemption events...")
        session.add_all(PREEMPTION_EVENTS)
        await session.flush()

        print("🔧 Seeding system faults...")
        session.add_all(FAULTS)

        await session.commit()

    print("\n✅ Seed complete!")
    print(f"   Users:              {len(USERS)}")
    print(f"   Vehicles:           {len(VEHICLES)}")
    print(f"   Edge nodes:         {len(EDGE_NODES)}")
    print(f"   Signal phases:      {len(EDGE_NODES) * 4}")
    print(f"   Preemption events:  {len(PREEMPTION_EVENTS)}")
    print(f"   System faults:      {len(FAULTS)}")


if __name__ == "__main__":
    asyncio.run(seed())
