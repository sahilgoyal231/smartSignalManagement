import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi import status

import os

# Mock required environment variables before loading any app code
os.environ["POSTGRES_PASSWORD"] = "testpass"
os.environ["INFLUX_TOKEN"] = "testtoken"
os.environ["MQTT_BROKER_USER"] = "testuser"
os.environ["MQTT_BROKER_PASSWORD"] = "testpass"
os.environ["JWT_SECRET_KEY"] = "testsecret"

from cloud.shared.db_models import Base
from cloud.shared.database import get_db

import importlib
vehicle_registry_main = importlib.import_module("cloud.services.vehicle_registry.main")
app = vehicle_registry_main.app

# ─────────────────────────────────────────────
# Setup In-Memory SQLite for Tests
# ─────────────────────────────────────────────
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=AsyncSession)

async def override_get_db():
    async with TestingSessionLocal() as session:
        yield session

app.dependency_overrides[get_db] = override_get_db

@pytest_asyncio.fixture(scope="function", autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest_asyncio.fixture
async def async_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

# ─────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_check(async_client: AsyncClient):
    response = await async_client.get("/health")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["service"] == "vehicle-registry"

@pytest.mark.asyncio
async def test_register_vehicle_success(async_client: AsyncClient):
    payload = {
        "vehicle_id": "AMB-MH-100",
        "vehicle_type": "AMBULANCE",
        "priority_class": 2,
        "license_plate": "MH01AB1234",
        "agency_name": "City Hospital",
        "city": "Mumbai",
        "cert_pem": "-----BEGIN CERTIFICATE-----\nMOCK_CERT_DATA\n-----END CERTIFICATE-----"
    }
    
    response = await async_client.post("/api/v1/vehicles", json=payload)
    
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["vehicle_id"] == "AMB-MH-100"
    assert data["vehicle_type"] == "AMBULANCE"
    assert data["city"] == "Mumbai"
    assert data["is_active"] is True
    assert "registered_at" in data

@pytest.mark.asyncio
async def test_register_duplicate_vehicle_id(async_client: AsyncClient):
    payload = {
        "vehicle_id": "AMB-MH-100",
        "vehicle_type": "AMBULANCE",
        "priority_class": 2,
        "license_plate": "MH01AB1234",
        "agency_name": "City Hospital",
        "city": "Mumbai",
        "cert_pem": "-----BEGIN CERTIFICATE-----\nMOCK_CERT_DATA\n-----END CERTIFICATE-----"
    }
    
    # First request
    response1 = await async_client.post("/api/v1/vehicles", json=payload)
    assert response1.status_code == status.HTTP_201_CREATED
    
    # Second request with identical vehicle ID
    payload2 = {**payload, "license_plate": "MH01AB9999"}
    response2 = await async_client.post("/api/v1/vehicles", json=payload2)
    assert response2.status_code == status.HTTP_409_CONFLICT
    assert "already registered" in response2.json()["detail"]

@pytest.mark.asyncio
async def test_register_duplicate_license_plate(async_client: AsyncClient):
    payload = {
        "vehicle_id": "AMB-MH-100",
        "vehicle_type": "AMBULANCE",
        "priority_class": 2,
        "license_plate": "MH01AB1234",
        "agency_name": "City Hospital",
        "city": "Mumbai",
        "cert_pem": "-----BEGIN CERTIFICATE-----\nMOCK_CERT_DATA\n-----END CERTIFICATE-----"
    }
    
    # First request
    response1 = await async_client.post("/api/v1/vehicles", json=payload)
    assert response1.status_code == status.HTTP_201_CREATED
    
    # Second request with identical license plate
    payload2 = {**payload, "vehicle_id": "AMB-MH-200"}
    response2 = await async_client.post("/api/v1/vehicles", json=payload2)
    assert response2.status_code == status.HTTP_409_CONFLICT
    assert "already registered" in response2.json()["detail"]

@pytest.mark.asyncio
async def test_list_vehicles(async_client: AsyncClient):
    # Register vehicle 1
    await async_client.post("/api/v1/vehicles", json={
        "vehicle_id": "AMB-1", "vehicle_type": "AMBULANCE", "priority_class": 2,
        "license_plate": "PL-1", "agency_name": "A1", "city": "NYC", "cert_pem": "test"
    })
    
    # Register vehicle 2
    await async_client.post("/api/v1/vehicles", json={
        "vehicle_id": "AMB-2", "vehicle_type": "FIRE", "priority_class": 3,
        "license_plate": "PL-2", "agency_name": "A2", "city": "SF", "cert_pem": "test"
    })
    
    # List vehicles
    response = await async_client.get("/api/v1/vehicles")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) == 2
    assert any(v["vehicle_id"] == "AMB-1" for v in data)
    assert any(v["vehicle_id"] == "AMB-2" for v in data)

@pytest.mark.asyncio
async def test_get_vehicle_by_id(async_client: AsyncClient):
    # Register
    await async_client.post("/api/v1/vehicles", json={
        "vehicle_id": "AMB-1", "vehicle_type": "AMBULANCE", "priority_class": 2,
        "license_plate": "PL-1", "agency_name": "A1", "city": "NYC", "cert_pem": "test"
    })
    
    # Get by ID
    response = await async_client.get("/api/v1/vehicles/AMB-1")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["vehicle_id"] == "AMB-1"

@pytest.mark.asyncio
async def test_get_missing_vehicle(async_client: AsyncClient):
    response = await async_client.get("/api/v1/vehicles/NONEXISTENT")
    assert response.status_code == status.HTTP_404_NOT_FOUND


# ─────────────────────────────────────────────
# PATCH deactivate / activate
# ─────────────────────────────────────────────

SAMPLE_VEHICLE = {
    "vehicle_id": "AMB-MH-100",
    "vehicle_type": "AMBULANCE",
    "priority_class": 2,
    "license_plate": "MH01AB1234",
    "agency_name": "City Hospital",
    "city": "Mumbai",
    "cert_pem": "-----BEGIN CERTIFICATE-----\nMOCK\n-----END CERTIFICATE-----"
}

@pytest.mark.asyncio
async def test_deactivate_vehicle(async_client: AsyncClient):
    """Deactivating an active vehicle returns is_active=False."""
    await async_client.post("/api/v1/vehicles", json=SAMPLE_VEHICLE)

    response = await async_client.patch(f"/api/v1/vehicles/{SAMPLE_VEHICLE['vehicle_id']}/deactivate")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["is_active"] is False

@pytest.mark.asyncio
async def test_deactivate_already_inactive(async_client: AsyncClient):
    """Deactivating an already inactive vehicle returns 409."""
    await async_client.post("/api/v1/vehicles", json=SAMPLE_VEHICLE)
    await async_client.patch(f"/api/v1/vehicles/{SAMPLE_VEHICLE['vehicle_id']}/deactivate")

    response = await async_client.patch(f"/api/v1/vehicles/{SAMPLE_VEHICLE['vehicle_id']}/deactivate")
    assert response.status_code == status.HTTP_409_CONFLICT

@pytest.mark.asyncio
async def test_activate_vehicle(async_client: AsyncClient):
    """Re-activating a deactivated vehicle returns is_active=True."""
    await async_client.post("/api/v1/vehicles", json=SAMPLE_VEHICLE)
    await async_client.patch(f"/api/v1/vehicles/{SAMPLE_VEHICLE['vehicle_id']}/deactivate")

    response = await async_client.patch(f"/api/v1/vehicles/{SAMPLE_VEHICLE['vehicle_id']}/activate")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["is_active"] is True

@pytest.mark.asyncio
async def test_activate_already_active(async_client: AsyncClient):
    """Activating an active vehicle returns 409."""
    await async_client.post("/api/v1/vehicles", json=SAMPLE_VEHICLE)

    response = await async_client.patch(f"/api/v1/vehicles/{SAMPLE_VEHICLE['vehicle_id']}/activate")
    assert response.status_code == status.HTTP_409_CONFLICT


# ─────────────────────────────────────────────
# DELETE
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_vehicle(async_client: AsyncClient):
    """Deleting a vehicle returns 204 and subsequent GET returns 404."""
    await async_client.post("/api/v1/vehicles", json=SAMPLE_VEHICLE)

    delete_resp = await async_client.delete(f"/api/v1/vehicles/{SAMPLE_VEHICLE['vehicle_id']}")
    assert delete_resp.status_code == status.HTTP_204_NO_CONTENT

    get_resp = await async_client.get(f"/api/v1/vehicles/{SAMPLE_VEHICLE['vehicle_id']}")
    assert get_resp.status_code == status.HTTP_404_NOT_FOUND

@pytest.mark.asyncio
async def test_delete_nonexistent_vehicle(async_client: AsyncClient):
    """Deleting a vehicle that doesn't exist returns 404."""
    response = await async_client.delete("/api/v1/vehicles/DOES-NOT-EXIST")
    assert response.status_code == status.HTTP_404_NOT_FOUND

