import asyncio
from fastapi import FastAPI
from contextlib import AsyncExitStack, asynccontextmanager

from cloud.services.event_service.main import app as event_app, lifespan as event_lifespan
from cloud.services.health_monitor.main import app as health_app, lifespan as health_lifespan
from cloud.services.ota_service.main import app as ota_app
from cloud.services.priority_queue.main import app as priority_app, lifespan as priority_lifespan
from cloud.services.route_engine.main import app as route_app, lifespan as route_lifespan
from cloud.services.vehicle_registry.main import app as vehicle_app

@asynccontextmanager
async def global_lifespan(app: FastAPI):
    """
    Manages the lifespans of all mounted microservices so their background tasks
    and MQTT/Redis Pub/Sub connections start up and tear down cleanly in a single process.
    """
    async with AsyncExitStack() as stack:
        await stack.enter_async_context(event_lifespan(event_app))
        await stack.enter_async_context(health_lifespan(health_app))
        await stack.enter_async_context(priority_lifespan(priority_app))
        await stack.enter_async_context(route_lifespan(route_app))
        yield

app = FastAPI(
    title="Smart Signal Monolith (Free Tier)",
    description="Consolidated backend allowing 1-click free deployment on Render.",
    version="1.0.0",
    lifespan=global_lifespan
)

from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root_health():
    return {"status": "up", "mode": "monolith"}

# Mount the individual microservices under specific paths
app.mount("/events", event_app)
app.mount("/health", health_app)
app.mount("/ota", ota_app)
app.mount("/priority", priority_app)
app.mount("/route", route_app)
app.mount("/vehicles", vehicle_app)
