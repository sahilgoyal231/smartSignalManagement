import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from contextlib import asynccontextmanager
from loguru import logger

from cloud.shared.mqtt_client import CloudMQTTClient
from cloud.shared.event_bus import EventProducer, EventConsumer

# ─────────────────────────────────────────────
# Clients
# ─────────────────────────────────────────────
mqtt_client = CloudMQTTClient(client_id_suffix="event-router")
event_producer = EventProducer()

# Consumers for internal EventBus -> MQTT routing
event_alert_consumer = EventConsumer(
    topics=["node.alert"], 
    group_id="event-service-alert-router"
)

# ─────────────────────────────────────────────
# WebSocket Manager (Dashboard Streaming)
# ─────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Dashboard client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"Dashboard client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        if not self.active_connections:
            return
        dead_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except RuntimeError: # Catch disconnection errors
                dead_connections.append(connection)
        for dead in dead_connections:
            self.disconnect(dead)

manager = ConnectionManager()


# ─────────────────────────────────────────────
# Router Tasks
# ─────────────────────────────────────────────

async def route_mqtt_to_eventbus():
    """
    Listens to ALL smartsignal/# MQTT topics and bridges them to specific Event Bus topics.
    """
    logger.info("Starting MQTT -> Event Bus router task...")
    try:
        async for topic, payload in mqtt_client.subscribe_and_listen("smartsignal/#"):
            parts = topic.split('/')
            
            # Format: smartsignal/<city>/vehicle/<vehicle_id>/beacon
            if len(parts) >= 5 and parts[2] == "vehicle" and parts[4] == "beacon":
                vehicle_id = parts[3]
                await event_producer.send_event("vehicle.update", payload, key=vehicle_id)
                # Stream to dashboard
                await manager.broadcast({
                    "type": "vehicle.update",
                    "vehicle_id": vehicle_id,
                    "data": payload
                })
                
            # Format: smartsignal/<city>/node/<node_id>/<action>
            elif len(parts) >= 5 and parts[2] == "node":
                node_id = parts[3]
                action = parts[4]
                
                if action == "preempt":
                    await event_producer.send_event("node.preempt", payload, key=node_id)
                    await manager.broadcast({"type": "node.preempt", "node_id": node_id, "data": payload})
                elif action == "fault":
                    await event_producer.send_event("system.fault", payload, key=node_id)
                    await manager.broadcast({"type": "system.fault", "node_id": node_id, "data": payload})
                elif action == "heartbeat":
                    await event_producer.send_event("node.heartbeat", payload, key=node_id)
                    await manager.broadcast({"type": "node.heartbeat", "node_id": node_id, "data": payload})
                else:
                    logger.debug(f"Ignoring unmapped MQTT topic: {topic}")
            else:
                logger.debug(f"Ignoring unmapped MQTT topic: {topic}")
                
    except asyncio.CancelledError:
        logger.info("MQTT -> Event Bus router task cancelled.")
    except Exception as e:
        logger.error(f"Critical error in MQTT -> Event Bus router: {e}")


async def route_eventbus_to_mqtt():
    """
    Listens to targeted Event Bus topics and bridges them out to EMQX for the Edge Nodes.
    """
    logger.info("Starting Event Bus -> MQTT router task...")
    try:
        await event_alert_consumer.start()
        
        async for topic, payload in event_alert_consumer:
            if topic == "node.alert":
                # Expected payload must contain 'target_node_id' and 'city' to build the MQTT topic
                node_id = payload.get("target_node_id")
                city = payload.get("city", "unknown")
                
                if not node_id:
                    logger.error(f"Cannot route node.alert: Missing target_node_id. Payload: {payload}")
                    continue
                    
                mqtt_topic = f"smartsignal/{city}/node/{node_id}/alert"
                await mqtt_client.publish(mqtt_topic, payload)
                
    except asyncio.CancelledError:
        logger.info("Event Bus -> MQTT router task cancelled.")
    except Exception as e:
        logger.error(f"Critical error in Event Bus -> MQTT router: {e}")


# ─────────────────────────────────────────────
# FastAPI Application & Lifespan
# ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup Setup
    logger.info("Starting Event Service dependencies...")
    
    mqtt_task = None
    eventbus_task = None
    
    try:
        await mqtt_client.connect()
    except Exception as e:
        logger.warning(f"MQTT broker not available (running without Docker?): {e}")
    
    try:
        await event_producer.start()
    except Exception as e:
        logger.warning(f"Event Bus not available (running without Docker?): {e}")
    
    # Launch background bridges only if infra is available
    if event_producer._started:
        mqtt_task = asyncio.create_task(route_mqtt_to_eventbus())
        eventbus_task = asyncio.create_task(route_eventbus_to_mqtt())
    else:
        logger.warning("Streaming bridges disabled — Event Bus/MQTT not available. REST APIs still operational.")
    
    yield  # App runs here
    
    # Teardown
    logger.info("Shutting down Event Service dependencies...")
    if mqtt_task:
        mqtt_task.cancel()
    if eventbus_task:
        eventbus_task.cancel()
    
    tasks_to_cancel = [t for t in [mqtt_task, eventbus_task] if t]
    if tasks_to_cancel:
        await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
    
    try:
        await event_alert_consumer.stop()
    except Exception:
        pass
    try:
        await event_producer.stop()
    except Exception:
        pass
    await mqtt_client.disconnect()


app = FastAPI(
    title="Smart Signal - Event Bridge Service",
    description="Microservice bridging IoT MQTT traffic with the internal Event Bus streaming backbone.",
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
    """Basic health check."""
    return {
        "status": "up",
        "service": "event-service",
        "mqtt_connected": mqtt_client._connected,
        "event_producer_ready": event_producer._started
    }


@app.websocket("/api/v1/stream")
async def websocket_endpoint(websocket: WebSocket):
    """
    Live streaming endpoint for dashboards. Pushes live `vehicle.update`, 
    `node.preempt`, and `node.heartbeat` events directly to the UI layer.
    """
    await manager.connect(websocket)
    try:
        while True:
            # We don't expect client messages, but we keep the loop alive
            # to detect disconnects gracefully.
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.warning(f"WebSocket error: {e}")
        manager.disconnect(websocket)


# ─────────────────────────────────────────────
# Preemption Events REST API
# ─────────────────────────────────────────────

from uuid import UUID
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from cloud.shared.database import get_db
from cloud.shared.db_models import PreemptionEvent
from cloud.shared.models import PreemptionEventCreate, PreemptionEventResponse, PreemptOutcome

events_router = APIRouter(prefix="/api/v1/events", tags=["Preemption Events"])


@events_router.post(
    "",
    response_model=PreemptionEventResponse,
    status_code=http_status.HTTP_201_CREATED,
)
async def log_event(body: PreemptionEventCreate, db: AsyncSession = Depends(get_db)):
    """
    Log a new preemption event to the database.
    Called automatically by the route-engine when a preemption is triggered.
    """
    event = PreemptionEvent(
        vehicle_id=body.vehicle_id,
        node_id=body.node_id,
        triggered_at=body.triggered_at,
        eta_at_trigger_s=body.eta_at_trigger_s,
        approach_phase=body.approach_phase,
        sensor_confidence=body.sensor_confidence,
        trigger_method=body.trigger_method,
        outcome=PreemptOutcome.CLEARED,   # default; update via PATCH /clear
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


@events_router.get("", response_model=List[PreemptionEventResponse])
async def list_events(
    vehicle_id: Optional[str] = Query(None, description="Filter by vehicle ID"),
    node_id:    Optional[str] = Query(None, description="Filter by node ID"),
    outcome:    Optional[PreemptOutcome] = Query(None, description="Filter by outcome"),
    limit:      int = Query(50, ge=1, le=100, description="Max results returned"),
    offset:     int = Query(0, ge=0,           description="Pagination offset"),
    db: AsyncSession = Depends(get_db),
):
    """Paginated, filterable list of preemption events — newest first."""
    stmt = select(PreemptionEvent)
    if vehicle_id:
        stmt = stmt.where(PreemptionEvent.vehicle_id == vehicle_id)
    if node_id:
        stmt = stmt.where(PreemptionEvent.node_id == node_id)
    if outcome:
        stmt = stmt.where(PreemptionEvent.outcome == outcome)
    stmt = stmt.order_by(PreemptionEvent.triggered_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@events_router.get("/{event_id}", response_model=PreemptionEventResponse)
async def get_event(event_id: UUID, db: AsyncSession = Depends(get_db)):
    """Fetch a single preemption event by UUID."""
    stmt = select(PreemptionEvent).where(PreemptionEvent.event_id == event_id)
    result = await db.execute(stmt)
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Event '{event_id}' not found."
        )
    return event


@events_router.patch("/{event_id}/clear", response_model=PreemptionEventResponse)
async def clear_event(
    event_id: UUID,
    actual_arrival_s: Optional[float] = Query(None, description="Measured arrival time in seconds"),
    db: AsyncSession = Depends(get_db),
):
    """
    Mark a preemption event as CLEARED — records the actual arrival time and timestamp.
    """
    stmt = select(PreemptionEvent).where(PreemptionEvent.event_id == event_id)
    result = await db.execute(stmt)
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Event '{event_id}' not found."
        )
    event.cleared_at = datetime.now(timezone.utc)
    event.outcome = PreemptOutcome.CLEARED
    if actual_arrival_s is not None:
        event.actual_arrival_s = actual_arrival_s
    await db.commit()
    await db.refresh(event)
    return event


# Mount router on the main app
app.include_router(events_router)

