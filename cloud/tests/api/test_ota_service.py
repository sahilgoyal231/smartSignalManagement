"""
Tests: OTA Service
"""
import io
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from fastapi import status

import os
os.environ.setdefault("POSTGRES_PASSWORD", "testpass")
os.environ.setdefault("INFLUX_TOKEN",      "testtoken")
os.environ.setdefault("MQTT_BROKER_USER",     "testuser")
os.environ.setdefault("MQTT_BROKER_PASSWORD", "testpass")
os.environ.setdefault("JWT_SECRET_KEY",       "testsecret")

import importlib
_ota_module = importlib.import_module("cloud.services.ota_service.main")
app       = _ota_module.app
_ota_jobs = _ota_module._ota_jobs
KNOWN_NODES = _ota_module.KNOWN_NODES


@pytest_asyncio.fixture(autouse=True)
async def reset_state():
    """Reset in-memory stores before each test."""
    _ota_jobs.clear()
    yield
    _ota_jobs.clear()


@pytest_asyncio.fixture
async def async_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


KNOWN_NODE = next(iter(KNOWN_NODES))   # e.g. "NODE-MUM-001"
UNKNOWN_NODE = "NODE-DOES-NOT-EXIST"


# ─────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_check(async_client: AsyncClient):
    response = await async_client.get("/health")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "up"
    assert data["service"] == "ota-service"
    assert "firmware_version" in data


# ─────────────────────────────────────────────
# Firmware manifest
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_latest_firmware(async_client: AsyncClient):
    response = await async_client.get("/api/v1/firmware/latest")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "version" in data
    assert "sha256" in data
    assert "size_bytes" in data
    assert "release_notes" in data
    assert "released_at" in data


@pytest.mark.asyncio
async def test_upload_firmware(async_client: AsyncClient):
    """Uploading a new firmware binary updates the manifest."""
    fake_binary = b"\x00\xFF" * 512   # 1 KB dummy binary
    response = await async_client.post(
        "/api/v1/firmware/upload",
        params={"version": "3.0.0", "release_notes": "Test upload"},
        files={"file": ("firmware.bin", io.BytesIO(fake_binary), "application/octet-stream")},
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["version"] == "3.0.0"
    assert data["size_bytes"] == len(fake_binary)
    assert len(data["sha256"]) == 64   # SHA-256 hex length


@pytest.mark.asyncio
async def test_upload_empty_firmware(async_client: AsyncClient):
    """Uploading an empty file returns 400."""
    response = await async_client.post(
        "/api/v1/firmware/upload",
        params={"version": "3.0.1", "release_notes": "Bad upload"},
        files={"file": ("empty.bin", io.BytesIO(b""), "application/octet-stream")},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


# ─────────────────────────────────────────────
# OTA trigger
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_trigger_ota_success(async_client: AsyncClient):
    """Triggering OTA for a known node returns 202 and a job."""
    response = await async_client.post(f"/api/v1/ota/trigger/{KNOWN_NODE}", json={"force": False})
    assert response.status_code == status.HTTP_202_ACCEPTED
    data = response.json()
    assert data["node_id"] == KNOWN_NODE
    assert data["status"] == "PENDING"
    assert "job_id" in data
    assert "firmware_version" in data


@pytest.mark.asyncio
async def test_trigger_ota_unknown_node(async_client: AsyncClient):
    """Triggering OTA for unknown node returns 404."""
    response = await async_client.post(f"/api/v1/ota/trigger/{UNKNOWN_NODE}", json={"force": False})
    assert response.status_code == status.HTTP_404_NOT_FOUND


# ─────────────────────────────────────────────
# OTA status
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_ota_status_pending(async_client: AsyncClient):
    """After triggering OTA, status should be PENDING."""
    await async_client.post(f"/api/v1/ota/trigger/{KNOWN_NODE}", json={"force": False})
    response = await async_client.get(f"/api/v1/ota/status/{KNOWN_NODE}")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "PENDING"
    assert data["job"] is not None
    assert data["job"]["node_id"] == KNOWN_NODE


@pytest.mark.asyncio
async def test_get_ota_status_not_scheduled(async_client: AsyncClient):
    """Nodes with no OTA job return NOT_SCHEDULED."""
    response = await async_client.get(f"/api/v1/ota/status/{KNOWN_NODE}")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "NOT_SCHEDULED"
    assert data["job"] is None
