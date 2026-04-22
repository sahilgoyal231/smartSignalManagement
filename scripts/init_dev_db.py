"""
Quick dev script: Create SQLite tables and seed sample data for local demo.
Usage: OVERRIDE_DB_URL="sqlite+aiosqlite:///dev.db" python3 scripts/init_dev_db.py
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
import random
import hashlib

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Set environment before imports
os.environ.setdefault("POSTGRES_URL", "sqlite+aiosqlite:///dev.db")
os.environ.setdefault("POSTGRES_PASSWORD", "dev")
os.environ.setdefault("INFLUX_TOKEN", "dev")
os.environ.setdefault("MQTT_BROKER_USER", "dev")
os.environ.setdefault("MQTT_BROKER_PASSWORD", "dev")
os.environ.setdefault("JWT_SECRET_KEY", "dev-secret-key-not-for-production")

from cloud.shared.database import init_db, AsyncSessionLocal
from cloud.shared.db_models import Vehicle, EdgeNode, PreemptionEvent, SystemFault


# ── Helpers ──────────────────────────────────────────────────────────────────

def make_cert_pem(vehicle_id: str) -> str:
    """Generate a realistic-looking PEM certificate stub."""
    vid_clean = vehicle_id.replace('-', '')
    return (
        "-----BEGIN CERTIFICATE-----\n"
        "MIIBkTCB+wIJAL0sQ5VhDSv+MA0GCSqGSIb3DQEBCwUAMBExDzANBgNVBAMMBnZz\n"
        "dS1jYTAeFw0yNTAxMDEwMDAwMDBaFw0yNjAxMDEwMDAwMDBaMBkxFzAVBgNVBAMM\n"
        f"DnZzdS1{vid_clean}MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE\n"
        f"SmartSignalVSU{vid_clean}CertificateData\n"
        "-----END CERTIFICATE-----"
    )


def make_cert_hash(pem: str) -> str:
    return hashlib.sha256(pem.encode('utf-8')).hexdigest()


NOW = datetime.now(timezone.utc)

# ── SEED DATA ────────────────────────────────────────────────────────────────

SEED_VEHICLES = []
VEHICLE_DEFS = [
    ("AMB-MH-001", "AMBULANCE", 1, "MH01AB1234", "KEM Hospital EMS",                "Mumbai"),
    ("AMB-MH-002", "AMBULANCE", 2, "MH01CD5678", "Lilavati Hospital Ambulance",      "Mumbai"),
    ("AMB-MH-003", "AMBULANCE", 2, "MH02EF9012", "Nanavati Max Ambulance",           "Mumbai"),
    ("FIRE-MH-001", "FIRE",     3, "MH01GH3456", "Mumbai Fire Brigade - Station 7",  "Mumbai"),
    ("FIRE-MH-002", "FIRE",     3, "MH01IJ7890", "Mumbai Fire Brigade - Station 12", "Mumbai"),
    ("POL-MH-001", "POLICE",    1, "MH01KL1357", "Mumbai Police - Zone 3",           "Mumbai"),
    ("POL-MH-002", "POLICE",    2, "MH01MN2468", "Mumbai Traffic Police",            "Mumbai"),
    ("DIS-MH-001", "DISASTER",  1, "MH01OP3690", "NDRF - Mumbai Detachment",         "Mumbai"),
]

for vid, vtype, pri, plate, agency, city in VEHICLE_DEFS:
    pem = make_cert_pem(vid)
    SEED_VEHICLES.append(Vehicle(
        vehicle_id=vid,
        vehicle_type=vtype,
        priority_class=pri,
        license_plate=plate,
        agency_name=agency,
        city=city,
        vsu_cert_hash=make_cert_hash(pem),
        vsu_cert_pem=pem,
        is_active=True,
        last_seen=NOW - timedelta(minutes=random.randint(1, 120)),
    ))

# Mark one vehicle as inactive for demo purposes
SEED_VEHICLES[-1].is_active = False


SEED_NODES = [
    EdgeNode(
        node_id="NODE-MUM-001", location_lat=19.0760, location_lon=72.8777,
        intersection_name="CST Junction", city="Mumbai", is_online=True,
        firmware_version="2.3.1", controller_type="PLC_NTCIP",
        last_heartbeat=NOW - timedelta(seconds=45),
    ),
    EdgeNode(
        node_id="NODE-MUM-002", location_lat=19.0540, location_lon=72.8400,
        intersection_name="Haji Ali Signal", city="Mumbai", is_online=True,
        firmware_version="2.3.1", controller_type="PLC_NTCIP",
        last_heartbeat=NOW - timedelta(seconds=30),
    ),
    EdgeNode(
        node_id="NODE-MUM-003", location_lat=19.0896, location_lon=72.8656,
        intersection_name="Dadar TT Circle", city="Mumbai", is_online=True,
        firmware_version="2.3.0", controller_type="SCOOT",
        last_heartbeat=NOW - timedelta(seconds=60),
    ),
    EdgeNode(
        node_id="NODE-MUM-004", location_lat=19.1075, location_lon=72.8374,
        intersection_name="Bandra Reclamation", city="Mumbai", is_online=False,
        firmware_version="2.1.0", controller_type="RELAY",
        last_heartbeat=NOW - timedelta(hours=6),
    ),
    EdgeNode(
        node_id="NODE-MUM-005", location_lat=19.0622, location_lon=72.8353,
        intersection_name="Mahalaxmi Race Course", city="Mumbai", is_online=True,
        firmware_version="2.3.1", controller_type="PLC_NTCIP",
        last_heartbeat=NOW - timedelta(seconds=15),
    ),
    EdgeNode(
        node_id="NODE-MUM-006", location_lat=19.0178, location_lon=72.8478,
        intersection_name="Colaba Causeway Junction", city="Mumbai", is_online=True,
        firmware_version="2.3.1", controller_type="ECONOLITE",
        last_heartbeat=NOW - timedelta(seconds=50),
    ),
    EdgeNode(
        node_id="NODE-MUM-007", location_lat=19.1197, location_lon=72.8464,
        intersection_name="Andheri Flyover Signal", city="Mumbai", is_online=True,
        firmware_version="2.2.0", controller_type="PLC_NTCIP",
        last_heartbeat=NOW - timedelta(seconds=20),
    ),
    EdgeNode(
        node_id="NODE-MUM-008", location_lat=19.0330, location_lon=72.8410,
        intersection_name="Marine Drive Promenade", city="Mumbai", is_online=True,
        firmware_version="2.3.1", controller_type="SCOOT",
        last_heartbeat=NOW - timedelta(seconds=40),
    ),
]

# ── Preemption Events (last 7 days) ──────────────────────────────────────────

PREEMPTION_EVENTS = []
VEHICLE_IDS = [v.vehicle_id for v in SEED_VEHICLES if v.is_active]
NODE_IDS = [n.node_id for n in SEED_NODES if n.is_online]
OUTCOMES = ["CLEARED", "CLEARED", "CLEARED", "CLEARED", "ABORTED", "TIMEOUT"]  # weighted
TRIGGER_METHODS = [
    "LORA+CAMERA+AUDIO", "LORA+CAMERA", "CAMERA+AUDIO",
    "LORA+BLE", "CAMERA+GPS", "LORA+CAMERA+AUDIO+GPS"
]

for i in range(20):
    triggered = NOW - timedelta(
        days=random.randint(0, 6),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59)
    )
    eta = round(random.uniform(15.0, 90.0), 1)
    outcome = random.choice(OUTCOMES)
    cleared = triggered + timedelta(seconds=random.randint(20, 120)) if outcome == "CLEARED" else None
    actual = round(eta + random.uniform(-10.0, 15.0), 1) if outcome == "CLEARED" else None

    PREEMPTION_EVENTS.append(PreemptionEvent(
        event_id=uuid.uuid4(),
        vehicle_id=random.choice(VEHICLE_IDS),
        node_id=random.choice(NODE_IDS),
        triggered_at=triggered,
        cleared_at=cleared,
        eta_at_trigger_s=eta,
        actual_arrival_s=actual,
        approach_phase=random.randint(1, 4),
        sensor_confidence=round(random.uniform(0.75, 0.99), 2),
        trigger_method=random.choice(TRIGGER_METHODS),
        outcome=outcome,
        green_hold_duration_s=round(random.uniform(15.0, 55.0), 1) if outcome == "CLEARED" else None,
    ))

# ── System Faults ────────────────────────────────────────────────────────────

SEED_FAULTS = [
    SystemFault(
        node_id="NODE-MUM-004",
        fault_type="LTE_FAIL",
        severity="HIGH",
        detail="LTE modem lost carrier signal. Last RSSI: -110 dBm. Node went offline.",
        detected_at=NOW - timedelta(hours=6),
        is_resolved=False,
    ),
    SystemFault(
        node_id="NODE-MUM-003",
        fault_type="CAMERA_FAIL",
        severity="MEDIUM",
        detail="Camera feed dropped frames for 45s. Auto-recovered after watchdog restart.",
        detected_at=NOW - timedelta(days=2),
        resolved_at=NOW - timedelta(days=2, hours=-1),
        is_resolved=True,
    ),
    SystemFault(
        node_id="NODE-MUM-007",
        fault_type="OVERHEAT",
        severity="LOW",
        detail="Enclosure temperature reached 52°C. Cooling fan activated.",
        detected_at=NOW - timedelta(days=1),
        resolved_at=NOW - timedelta(hours=22),
        is_resolved=True,
    ),
]


# ── Main ─────────────────────────────────────────────────────────────────────

async def main():
    print("🗄️  Creating database tables...")
    await init_db()

    print("🌱 Seeding demo data...")
    async with AsyncSessionLocal() as session:
        # Check if data already exists
        from sqlalchemy import select, func
        count = await session.scalar(select(func.count()).select_from(Vehicle))
        if count > 0:
            print(f"   Database already has {count} vehicles — clearing and re-seeding...")
            await session.execute(Vehicle.__table__.delete())
            await session.execute(EdgeNode.__table__.delete())
            await session.execute(PreemptionEvent.__table__.delete())
            await session.execute(SystemFault.__table__.delete())
            await session.commit()

        # Seed nodes first (preemption events FK to nodes)
        for n in SEED_NODES:
            session.add(n)
        await session.flush()

        # Then vehicles
        for v in SEED_VEHICLES:
            session.add(v)
        await session.flush()

        # Then events
        for e in PREEMPTION_EVENTS:
            session.add(e)

        # Then faults
        for f in SEED_FAULTS:
            session.add(f)

        await session.commit()

    print(f"✅ Seeded:")
    print(f"   • {len(SEED_VEHICLES)} vehicles (7 active, 1 inactive)")
    print(f"   • {len(SEED_NODES)} edge nodes (7 online, 1 offline)")
    print(f"   • {len(PREEMPTION_EVENTS)} preemption events (last 7 days)")
    print(f"   • {len(SEED_FAULTS)} system faults")
    print(f"   Database: {os.environ['OVERRIDE_DB_URL']}")


if __name__ == "__main__":
    asyncio.run(main())
