import asyncio
from datetime import datetime, timezone
from typing import Optional
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from contextlib import asynccontextmanager
from loguru import logger
from sqlalchemy import select, update

from cloud.shared.event_bus import EventProducer, EventConsumer
from cloud.shared.database import get_db
from cloud.shared.db_models import EdgeNode, SystemFault

# ─────────────────────────────────────────────
# Clients & Models
# ─────────────────────────────────────────────
event_producer = EventProducer()

# Listen to edge nodes diagnostic feeds
event_health_consumer = EventConsumer(
    topics=["node.heartbeat", "system.fault"], 
    group_id="health-monitor-processor"
)

# How many seconds since `last_heartbeat` before marking a node as offline
STALE_THRESHOLD_SECONDS = 300 # 5 minutes

class OTAUpdateRequest(BaseModel):
    target_version: str
    download_url: str

# ─────────────────────────────────────────────
# Core Processor Tasks
# ─────────────────────────────────────────────

async def process_health_events():
    """Consumes Redis Pub/Sub messages matching heartbeat and fault topics."""
    logger.info("Starting Health Monitor Event Bus processor...")
    try:
        await event_health_consumer.start()
        
        async for topic, payload in event_health_consumer:
            node_id = payload.get("node_id")
            if not node_id:
                continue

            try:
                # To avoid blocking the consumer excessively, we handle DB ops quickly
                if topic == "node.heartbeat":
                    await _handle_heartbeat(node_id, payload)
                elif topic == "system.fault":
                    await _handle_fault(node_id, payload)
            except Exception as e:
                logger.error(f"Error processing health event for {node_id}: {e}")
                    
    except asyncio.CancelledError:
        logger.info("Health Monitor processor task cancelled.")
    except Exception as e:
        logger.error(f"Critical error in Health Monitor processor: {e}")

async def _handle_heartbeat(node_id: str, payload: dict):
    """Updates the EdgeNode last heartbeat timestamp and firmware version."""
    firmware_version = payload.get("firmware_version")
    
    async for db in get_db():
        result = await db.execute(select(EdgeNode).where(EdgeNode.node_id == node_id))
        node = result.scalars().first()
        
        if node:
            node.last_heartbeat = datetime.now(timezone.utc).replace(tzinfo=None)
            node.is_online = True
            if firmware_version:
                node.firmware_version = firmware_version
            await db.commit()
            logger.debug(f"Processed heartbeat for {node_id}")
        else:
            logger.warning(f"Received heartbeat for unknown node: {node_id}")
        break

async def _handle_fault(node_id: str, payload: dict):
    """Records hardware/software faults reported by nodes to the database."""
    fault_type = payload.get("fault_type")
    severity = payload.get("severity", "MEDIUM")
    detail = payload.get("detail", "")
    
    if not fault_type:
        return
        
    async for db in get_db():
        # Verify node exists
        result = await db.execute(select(EdgeNode).where(EdgeNode.node_id == node_id))
        if not result.scalars().first():
            break
            
        fault = SystemFault(
            node_id=node_id,
            fault_type=fault_type,
            severity=severity,
            detail=detail
        )
        db.add(fault)
        await db.commit()
        
        if severity == "CRITICAL":
            logger.critical(f"CRITICAL FAULT recorded on {node_id}: {fault_type}. {detail}")
        else:
            logger.warning(f"Fault {fault_type} recorded on {node_id}")
        break

async def stale_node_checker():
    """
    Periodically checks the database for EdgeNodes whose last_heartbeat
    exceeds the STALE_THRESHOLD_SECONDS and flags them as offline.
    """
    while True:
        try:
            await asyncio.sleep(60.0) # Check every minute
            
            async for db in get_db():
                # We do this logic in Python memory for cross-db compatibility avoiding complex SQL dates
                result = await db.execute(select(EdgeNode).where(EdgeNode.is_online == True))
                nodes = result.scalars().all()
                
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                stale_count = 0
                
                for node in nodes:
                    if node.last_heartbeat:
                        # Make timezone-naive for comparison if necessary, but DB should save UTC
                        delta = (now - node.last_heartbeat.replace(tzinfo=None)).total_seconds()
                        if delta > STALE_THRESHOLD_SECONDS:
                            node.is_online = False
                            stale_count += 1
                            logger.error(f"Node {node.node_id} marked offline! (No heartbeat in {delta}s)")
                
                if stale_count > 0:
                    await db.commit()
                    
                break # Close DB session
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in stale node checker loop: {e}")

# ─────────────────────────────────────────────
# FastAPI Application & Lifespan
# ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Health Monitor dependencies...")
    
    processor_task = None
    
    try:
        await event_producer.start()
    except Exception as e:
        logger.warning(f"Event Bus not available: {e}")
    
    # Launch background tasks
    if event_producer._started:
        processor_task = asyncio.create_task(process_health_events())
    else:
        logger.warning("Event Bus processor disabled — REST APIs still operational.")
    checker_task = asyncio.create_task(stale_node_checker())
    
    yield
    
    logger.info("Shutting down Health Monitor dependencies...")
    if processor_task:
        processor_task.cancel()
    checker_task.cancel()
    
    tasks = [t for t in [processor_task, checker_task] if t]
    await asyncio.gather(*tasks, return_exceptions=True)
    
    try:
        await event_health_consumer.stop()
    except Exception:
        pass
    try:
        await event_producer.stop()
    except Exception:
        pass

app = FastAPI(
    title="Smart Signal - Health Monitor & OTA Service",
    description="Microservice tracking edge unit uptime and emitting OTA upgrade triggers.",
    version="1.0.0",
    lifespan=lifespan
)

from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    """Basic health check and readiness probe."""
    return {
        "status": "up",
        "service": "health-monitor",
        "event_producer_ready": event_producer._started
    }

@app.post("/api/v1/nodes/{node_id}/ota-update", status_code=status.HTTP_202_ACCEPTED)
async def trigger_ota_update(node_id: str, request: OTAUpdateRequest):
    """
    Triggers an Over-The-Air firmware update on a specific EdgeNode.
    Emits a command payload to the `node.alert` Redis Pub/Sub channel for routing.
    """
    if not event_producer._started:
        raise HTTPException(status_code=503, detail="Event producer not ready")
        
    payload = {
        "event_type": "OTA_UPGRADE",
        "target_node_id": node_id,
        "target_version": request.target_version,
        "download_url": request.download_url
    }
    
    # Publish to node.alert, which the Event Service Router maps backwards to MQTT
    await event_producer.send_event(
        topic="node.alert",
        payload=payload,
        key=node_id
    )
    
    logger.info(f"Triggered OTA upgrade for {node_id} to version {request.target_version}")
    return {"message": "OTA sequence initiated", "node_id": node_id}

@app.get("/api/v1/nodes")
async def list_nodes():
    """Retrieve all EdgeNodes from the database for the dashboard."""
    async for db in get_db():
        result = await db.execute(select(EdgeNode))
        nodes = result.scalars().all()
        return nodes


@app.post("/api/v1/nodes", status_code=status.HTTP_201_CREATED)
async def create_node(body: dict):
    """Register a new edge node in the system."""
    from datetime import datetime, timezone

    async for db in get_db():
        # Check if node_id already exists
        existing = await db.execute(select(EdgeNode).where(EdgeNode.node_id == body["node_id"]))
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Node '{body['node_id']}' already exists."
            )

        node = EdgeNode(
            node_id=body["node_id"],
            intersection_name=body["intersection_name"],
            city=body.get("city", "Mumbai"),
            location_lat=body["location_lat"],
            location_lon=body["location_lon"],
            firmware_version=body.get("firmware_version", "2.3.1"),
            controller_type=body.get("controller_type", "PLC_NTCIP"),
            is_online=body.get("is_online", True),
            last_heartbeat=datetime.now(timezone.utc),
        )
        db.add(node)
        await db.commit()
        await db.refresh(node)
        logger.info(f"Registered new edge node: {node.node_id} at {node.intersection_name}")
        return node

