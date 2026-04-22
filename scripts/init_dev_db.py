"""
Quick dev script: Create SQLite tables and seed sample data for local demo.
Usage: OVERRIDE_DB_URL="sqlite+aiosqlite:///dev.db" python3 scripts/init_dev_db.py
"""
import asyncio
import os
import sys

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Set environment before imports
os.environ.setdefault("OVERRIDE_DB_URL", "sqlite+aiosqlite:////tmp/smart_signal_dev.db")
os.environ.setdefault("POSTGRES_PASSWORD", "dev")
os.environ.setdefault("INFLUX_TOKEN", "dev")
os.environ.setdefault("MQTT_BROKER_USER", "dev")
os.environ.setdefault("MQTT_BROKER_PASSWORD", "dev")
os.environ.setdefault("JWT_SECRET_KEY", "dev-secret-key-not-for-production")

from cloud.shared.database import init_db, AsyncSessionLocal
from cloud.shared.db_models import Vehicle, EdgeNode


SEED_VEHICLES = [
    Vehicle(vehicle_id="AMB-MH-001", vehicle_type="AMBULANCE", priority_class=2,
            license_plate="MH01AB1234", agency_name="KEM Hospital EMS", city="Mumbai",
            vsu_cert_hash="a"*64, vsu_cert_pem="DEV_CERT", is_active=True),
    Vehicle(vehicle_id="AMB-MH-002", vehicle_type="AMBULANCE", priority_class=2,
            license_plate="MH01CD5678", agency_name="Lilavati Ambulance", city="Mumbai",
            vsu_cert_hash="b"*64, vsu_cert_pem="DEV_CERT", is_active=True),
    Vehicle(vehicle_id="FIRE-MH-001", vehicle_type="FIRE", priority_class=3,
            license_plate="MH01EF9012", agency_name="Mumbai Fire Brigade", city="Mumbai",
            vsu_cert_hash="c"*64, vsu_cert_pem="DEV_CERT", is_active=True),
    Vehicle(vehicle_id="POL-MH-001", vehicle_type="POLICE", priority_class=1,
            license_plate="MH01GH3456", agency_name="Mumbai Police", city="Mumbai",
            vsu_cert_hash="d"*64, vsu_cert_pem="DEV_CERT", is_active=True),
]

SEED_NODES = [
    EdgeNode(node_id="NODE-MUM-001", location_lat=19.0760, location_lon=72.8777,
             intersection_name="CST Junction", city="Mumbai", is_online=True,
             firmware_version="v1.5.0"),
    EdgeNode(node_id="NODE-MUM-002", location_lat=19.0540, location_lon=72.8400,
             intersection_name="Haji Ali Signal", city="Mumbai", is_online=True,
             firmware_version="v1.5.0"),
    EdgeNode(node_id="NODE-MUM-003", location_lat=19.0896, location_lon=72.8656,
             intersection_name="Dadar TT Circle", city="Mumbai", is_online=True,
             firmware_version="v1.4.2"),
    EdgeNode(node_id="NODE-MUM-004", location_lat=19.1075, location_lon=72.8374,
             intersection_name="Bandra Reclamation", city="Mumbai", is_online=False,
             firmware_version="v1.3.0"),
    EdgeNode(node_id="NODE-MUM-005", location_lat=19.0622, location_lon=72.8353,
             intersection_name="Mahalaxmi Race Course", city="Mumbai", is_online=True,
             firmware_version="v1.5.0"),
]


async def main():
    print("🗄️  Creating database tables...")
    await init_db()

    print("🌱 Seeding demo data...")
    async with AsyncSessionLocal() as session:
        # Check if data already exists
        from sqlalchemy import select, func
        count = await session.scalar(select(func.count()).select_from(Vehicle))
        if count > 0:
            print(f"   Database already has {count} vehicles — skipping seed.")
            return

        for v in SEED_VEHICLES:
            session.add(v)
        for n in SEED_NODES:
            session.add(n)
        await session.commit()

    print(f"✅ Seeded {len(SEED_VEHICLES)} vehicles and {len(SEED_NODES)} edge nodes.")
    print(f"   Database: {os.environ['OVERRIDE_DB_URL']}")


if __name__ == "__main__":
    asyncio.run(main())
