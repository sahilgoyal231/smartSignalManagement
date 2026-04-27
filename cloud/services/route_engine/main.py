import asyncio
from fastapi import FastAPI
from contextlib import asynccontextmanager
from loguru import logger

from cloud.shared.event_bus import EventProducer, EventConsumer
from cloud.services.route_engine.routing import RouteEngine
from cloud.shared.database import get_db
from cloud.shared.db_models import EdgeNode
from sqlalchemy import select

# ─────────────────────────────────────────────
# Clients & Engine
# ─────────────────────────────────────────────
event_producer = EventProducer()

event_vehicle_consumer = EventConsumer(
    topics=["vehicle.update"], 
    group_id="route-engine-processor"
)

# Initialize engine. For dev we only load a small subset or pre-defined cities to save RAM
route_engine = RouteEngine(cities=["Mumbai, India", "Delhi, India"])

# ─────────────────────────────────────────────
# Core Processor Task
# ─────────────────────────────────────────────

async def refresh_edge_nodes():
    """Periodically fetches the latest active signal controllers from the DB."""
    while True:
        try:
            # We must use the async generator context manager since get_db yields
            async for db in get_db():
                result = await db.execute(
                    select(EdgeNode).where(EdgeNode.is_online == True)
                )
                nodes = result.scalars().all()
                
                # Convert SQLAlchemy models to dicts for the sync route engine
                node_dicts = [
                    {
                        "node_id": n.node_id,
                        "city": n.city,
                        "location_lat": float(n.location_lat),
                        "location_lon": float(n.location_lon)
                    } for n in nodes
                ]
                
                route_engine.update_edge_nodes(node_dicts)
                logger.debug(f"Refreshed {len(node_dicts)} EdgeNodes from DB.")
                break # Only need one successful yield from the generator
                
        except Exception as e:
            logger.error(f"Failed to refresh EdgeNodes from DB: {e}")
            
        await asyncio.sleep(60) # Refresh every minute


async def process_vehicle_updates():
    """
    Listens to vehicle telemetery, predicts routes if there is a destination,
    and fires preemption events for upcoming intersections.
    """
    logger.info("Starting Route Engine Event Bus processor...")
    try:
        await event_vehicle_consumer.start()
        
        async for topic, payload in event_vehicle_consumer:
            # We only route vehicles that have an active siren/priority and a destination
            priority_class = payload.get("priority_class", 0)
            dest_lat = payload.get("dest_lat")
            dest_lon = payload.get("dest_lon")
            city = payload.get("city", "Mumbai, India") # Default for safety
            
            if priority_class == 0:
                continue # Normal vehicle operation, do not route
                
            if not dest_lat or not dest_lon:
                logger.debug(f"Vehicle {payload.get('vehicle_id')} has priority but no destination set. Skipping routing.")
                continue

            vehicle_id = payload["vehicle_id"]
            current_lat = payload["lat"]
            current_lon = payload["lon"]
            speed_kmh = payload.get("speed_kmh", 0.0)

            logger.info(f"Predicting route for {vehicle_id} in {city}...")
            
            # Predict
            # TODO: Move the actual astar_path to a ProcessPoolExecutor if it blocks the loop too heavily in prod
            route_coords = route_engine.predict_route(
                city=city,
                start_lat=current_lat,
                start_lon=current_lon,
                dest_lat=dest_lat,
                dest_lon=dest_lon
            )

            if not route_coords:
                continue

            # Detect Upcoming
            upcoming_nodes = route_engine.detect_upcoming_intersections(
                route_coords=route_coords,
                current_speed_kmh=speed_kmh
            )

            # Fire Preemption Events to Redis Pub/Sub for each upcoming node
            if upcoming_nodes:
                logger.info(f"Vehicle {vehicle_id} will approach {len(upcoming_nodes)} intersections.")
                for node_eta in upcoming_nodes:
                    
                    preempt_payload = {
                        "event_type": "PREEMPT_TRIGGER",
                        "vehicle_id": vehicle_id,
                        "target_node_id": node_eta["node_id"],
                        "city": node_eta["city"],
                        "eta_s": node_eta["eta_s"],
                        "distance_m": node_eta["distance_m"],
                        "priority_class": priority_class,
                        "source": "CLOUD_ROUTE_ENGINE"
                    }
                    
                    # The routing engine calculates ETAs globally. The Priority Queue downstream
                    # will decide which vehicle actually wins the green light if there are conflicts.
                    await event_producer.send_event(
                        topic="node.preempt", 
                        payload=preempt_payload, 
                        key=node_eta["node_id"]
                    )
                
    except asyncio.CancelledError:
        logger.info("Route Engine processor task cancelled.")
    except Exception as e:
        logger.error(f"Critical error in Route Engine processor: {e}")


# ─────────────────────────────────────────────
# FastAPI Application & Lifespan
# ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup Setup
    logger.info("Starting Route Engine dependencies...")
    
    processor_task = None
    
    try:
        await event_producer.start()
    except Exception as e:
        logger.warning(f"Event Bus not available: {e}")
    
    # Launch background bridges
    db_refresh_task = asyncio.create_task(refresh_edge_nodes())
    if event_producer._started:
        processor_task = asyncio.create_task(process_vehicle_updates())
    else:
        logger.warning("Event Bus processor disabled — REST APIs still operational.")
    
    yield  # App runs here
    
    # Teardown
    logger.info("Shutting down Route Engine dependencies...")
    db_refresh_task.cancel()
    if processor_task:
        processor_task.cancel()
    
    tasks = [t for t in [db_refresh_task, processor_task] if t]
    await asyncio.gather(*tasks, return_exceptions=True)
    
    try:
        await event_vehicle_consumer.stop()
    except Exception:
        pass
    try:
        await event_producer.stop()
    except Exception:
        pass


app = FastAPI(
    title="Smart Signal - Route Engine Service",
    description="Microservice predicting ETAs via OSMnx and emitting signal preemption triggers.",
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
        "service": "route-engine",
        "event_producer_ready": event_producer._started,
        "cities_loaded": list(route_engine.graphs.keys())
    }
