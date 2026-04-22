"""
Tests: Event Service — Preemption Events REST API
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi import status
from datetime import datetime, timezone, timedelta

import os
os.environ.setdefault("POSTGRES_PASSWORD",    "testpass")
os.environ.setdefault("INFLUX_TOKEN",         "testtoken")
os.environ.setdefault("MQTT_BROKER_USER",     "testuser")
os.environ.setdefault("MQTT_BROKER_PASSWORD", "testpass")
os.environ.setdefault("JWT_SECRET_KEY",       "testsecret")

# Use importlib to handle the hyphenated folder name (event-service)
import importlib
from unittest.mock import MagicMock, patch
import cloud.shared.event_bus

# Patch MQTT + Event Bus clients before importing the app module
with (
    patch("cloud.shared.mqtt_client.CloudMQTTClient", MagicMock()),
    patch("cloud.shared.event_bus.EventProducer", MagicMock()),
    patch("cloud.shared.event_bus.EventConsumer", MagicMock()),
):
    _event_module = importlib.import_module("cloud.services.event_service.main")
    app = _event_module.app

from cloud.shared.db_models import Base, Vehicle, EdgeNode
from cloud.shared.database import get_db

# ─────────────────────────────────────────────
# In-memory SQLite test DB
# ─────────────────────────────────────────────

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = async_sessionmaker(
    autocommit=False, autoflush=False, bind=engine, class_=AsyncSession
)


async def override_get_db():
    async with TestingSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture(scope="function", autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Pre-populate with one vehicle and one node to satisfy FK constraints
    async with TestingSessionLocal() as session:
        session.add(Vehicle(
            vehicle_id="AMB-TEST-01", vehicle_type="AMBULANCE",
            priority_class=1, license_plate="MH-TEST-01",
            agency_name="Test EMS", city="Mumbai",
            vsu_cert_hash="a" * 64, vsu_cert_pem="CERT", is_active=True,
        ))
        session.add(EdgeNode(
            node_id="NODE-TEST-01", location_lat=19.0, location_lon=72.8,
            intersection_name="Test Junction", city="Mumbai", is_online=True,
        ))
        await session.commit()
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def async_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ── Helper ──────────────────────────────────────────────────────────────────

SAMPLE_EVENT = {
    "vehicle_id":        "AMB-TEST-01",
    "node_id":           "NODE-TEST-01",
    "triggered_at":      datetime.now(timezone.utc).isoformat(),
    "eta_at_trigger_s":  12.5,
    "approach_phase":    2,
    "sensor_confidence": 0.95,
    "trigger_method":    "LORA+CAMERA",
}


# ─────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_log_event(async_client: AsyncClient):
    """POST /api/v1/events creates and returns a new event."""
    response = await async_client.post("/api/v1/events", json=SAMPLE_EVENT)
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["vehicle_id"] == SAMPLE_EVENT["vehicle_id"]
    assert data["node_id"]    == SAMPLE_EVENT["node_id"]
    assert "event_id" in data
    assert data["outcome"] == "CLEARED"    # default


@pytest.mark.asyncio
async def test_list_events_empty(async_client: AsyncClient):
    """GET /api/v1/events on an empty table returns []."""
    response = await async_client.get("/api/v1/events")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_events_returns_logged(async_client: AsyncClient):
    """After logging an event it should appear in the list."""
    await async_client.post("/api/v1/events", json=SAMPLE_EVENT)
    response = await async_client.get("/api/v1/events")
    assert response.status_code == status.HTTP_200_OK
    assert len(response.json()) == 1


@pytest.mark.asyncio
async def test_list_events_filter_by_vehicle(async_client: AsyncClient):
    """Filtering by vehicle_id returns only matching events."""
    await async_client.post("/api/v1/events", json=SAMPLE_EVENT)
    response = await async_client.get(
        "/api/v1/events", params={"vehicle_id": SAMPLE_EVENT["vehicle_id"]}
    )
    assert response.status_code == status.HTTP_200_OK
    assert all(e["vehicle_id"] == SAMPLE_EVENT["vehicle_id"] for e in response.json())

    # Filter for unknown vehicle should return 0
    response2 = await async_client.get("/api/v1/events", params={"vehicle_id": "UNKNOWN"})
    assert response2.json() == []


@pytest.mark.asyncio
async def test_get_event_by_id(async_client: AsyncClient):
    """GET /api/v1/events/{id} returns the correct event."""
    post_resp = await async_client.post("/api/v1/events", json=SAMPLE_EVENT)
    event_id  = post_resp.json()["event_id"]

    response = await async_client.get(f"/api/v1/events/{event_id}")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["event_id"] == event_id


@pytest.mark.asyncio
async def test_get_event_not_found(async_client: AsyncClient):
    """GET /api/v1/events/{unknown-id} returns 404."""
    response = await async_client.get("/api/v1/events/00000000-0000-0000-0000-000000000000")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_clear_event(async_client: AsyncClient):
    """PATCH /clear updates cleared_at and actual_arrival_s."""
    post_resp = await async_client.post("/api/v1/events", json=SAMPLE_EVENT)
    event_id  = post_resp.json()["event_id"]

    response = await async_client.patch(
        f"/api/v1/events/{event_id}/clear",
        params={"actual_arrival_s": 11.2}
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["outcome"] == "CLEARED"
    assert data["actual_arrival_s"] == pytest.approx(11.2, abs=0.01)
    assert data["cleared_at"] is not None
