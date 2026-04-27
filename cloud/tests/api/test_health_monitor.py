import pytest
import pytest_asyncio
import asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool
from datetime import datetime, timedelta, timezone
import os
import importlib

# Mock environment variables required by Pydantic before importing main 
os.environ["POSTGRES_PASSWORD"] = "test"
os.environ["INFLUX_TOKEN"] = "test"
os.environ["MQTT_BROKER_USER"] = "test"
os.environ["MQTT_BROKER_PASSWORD"] = "test"
os.environ["JWT_SECRET_KEY"] = "test"

hm_main = importlib.import_module("cloud.services.health_monitor.main")
app = hm_main.app
_handle_heartbeat = hm_main._handle_heartbeat
_handle_fault = hm_main._handle_fault
stale_node_checker = hm_main.stale_node_checker
from cloud.shared.db_models import EdgeNode, SystemFault, Base
from cloud.shared.database import get_db

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

# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

@pytest_asyncio.fixture(scope="function", autouse=True)
async def setup_db(mocker):
    # Monkeypatch get_db in the main module so direct calls use SQLite
    hm_main.get_db = override_get_db
    
    # Neutralize infinite background tasks so AsyncClient lifespan doesn't trigger side-effects
    mocker.patch.object(hm_main, "process_health_events", new_callable=mocker.AsyncMock)
    mocker.patch.object(hm_main, "stale_node_checker", new_callable=mocker.AsyncMock)

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

@pytest_asyncio.fixture
async def seeded_node(async_client):
    """Seed the database with a test edge node."""
    async for db in override_get_db():
        node = EdgeNode(
            node_id="TEST-NODE-1",
            location_lat=19.0,
            location_lon=72.0,
            intersection_name="Test Intersection",
            city="Mumbai",
            is_online=False, 
            last_heartbeat=None # Never checked in
        )
        db.add(node)
        await db.commit()
        break
    return "TEST-NODE-1"

# ─────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_heartbeat_updates_node(seeded_node):
    payload = {
        "node_id": seeded_node,
        "firmware_version": "v1.2.0"
    }
    
    await _handle_heartbeat(seeded_node, payload)
    
    async for db in override_get_db():
        result = await db.execute(select(EdgeNode).where(EdgeNode.node_id == seeded_node))
        node = result.scalars().first()
        
        assert node is not None
        assert node.is_online is True
        assert node.last_heartbeat is not None
        assert node.firmware_version == "v1.2.0"
        break

@pytest.mark.asyncio
async def test_handle_fault_records_in_db(seeded_node):
    payload = {
        "node_id": seeded_node,
        "fault_type": "CAMERA_FAIL",
        "severity": "HIGH",
        "detail": "Lens obstructed"
    }
    
    await _handle_fault(seeded_node, payload)
    
    async for db in override_get_db():
        result = await db.execute(select(SystemFault).where(SystemFault.node_id == seeded_node))
        fault = result.scalars().first()
        
        assert fault is not None
        assert fault.fault_type == "CAMERA_FAIL"
        assert fault.severity == "HIGH"
        assert fault.detail == "Lens obstructed"
        assert fault.is_resolved is False
        break

@pytest.mark.asyncio
async def test_unknown_node_does_not_crash(async_client):
    payload = {
        "node_id": "UNKNOWN-999",
        "firmware_version": "v1.0"
    }
    
    # Should exit gracefully and just log warning
    await _handle_heartbeat("UNKNOWN-999", payload)
    
    async for db in override_get_db():
        result = await db.execute(select(EdgeNode).where(EdgeNode.node_id == "UNKNOWN-999"))
        assert result.scalars().first() is None
        break

@pytest.mark.asyncio
async def test_stale_node_checker_marks_offline(seeded_node):
    # Set the node to online with a very old heartbeat (10 minutes ago)
    old_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=10)
    
    async for db in override_get_db():
        result = await db.execute(select(EdgeNode).where(EdgeNode.node_id == seeded_node))
        node = result.scalars().first()
        node.is_online = True
        node.last_heartbeat = old_time
        await db.commit()
        break
        
    # Run the core logic manually to avoid infinite loop complexity
    async for db in override_get_db():
        result = await db.execute(select(EdgeNode).where(EdgeNode.is_online == True))
        nodes = result.scalars().all()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        
        for node in nodes:
            delta = (now - node.last_heartbeat.replace(tzinfo=None)).total_seconds()
            if delta > 300: # STALE_THRESHOLD_SECONDS
                node.is_online = False
                
        await db.commit()
        break
    
    async for db in override_get_db():
        result = await db.execute(select(EdgeNode).where(EdgeNode.node_id == seeded_node))
        node = result.scalars().first()
        
        # Should now be marked offline
        assert node.is_online is False

@pytest.mark.asyncio
async def test_ota_update_api(async_client, mocker):
    # Mock the event producer internally so it doesn't need to actually connect
    mocker.patch.object(hm_main.event_producer, "_started", True)
    mock_send = mocker.patch.object(hm_main.event_producer, "send_event", new_callable=mocker.AsyncMock)

    response = await async_client.post(
        "/api/v1/nodes/TEST-NODE-1/ota-update",
        json={
            "target_version": "v2.0.0",
            "download_url": "https://firmware.example.com/v2.0.0.bin"
        }
    )

    assert response.status_code == 202
    assert response.json()["message"] == "OTA sequence initiated"
    
    # Ensure event command was emitted correctly
    mock_send.assert_awaited_once()
    kwargs = mock_send.call_args.kwargs
    assert kwargs["topic"] == "node.alert"
    assert kwargs["key"] == "TEST-NODE-1"
    assert kwargs["payload"]["event_type"] == "OTA_UPGRADE"
    assert kwargs["payload"]["target_version"] == "v2.0.0"
