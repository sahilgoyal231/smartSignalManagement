import asyncio
from fastapi import FastAPI
from contextlib import asynccontextmanager
from loguru import logger

from cloud.shared.event_bus import EventProducer, EventConsumer
from .resolver import PriorityResolver

# ─────────────────────────────────────────────
# Clients & Resolver
# ─────────────────────────────────────────────
event_producer = EventProducer()

# Listen to edge nodes AND route-engine
event_preempt_consumer = EventConsumer(
    topics=["node.preempt"], 
    group_id="priority-queue-processor"
)

# 30-second stale timeout
resolver = PriorityResolver(stale_timeout_s=30.0)

# ─────────────────────────────────────────────
# Core Processor Task
# ─────────────────────────────────────────────

async def broadcast_winner(node_id: str):
    """
    Constructs and fires a `node.alert` over Kafka which instructs
    the target node to actually execute the preemption.
    """
    winner_req = resolver.get_winner_payload(node_id)
    
    if winner_req:
        # A vehicle holds the intersection
        payload = {
            "event_type": "PREEMPT_COMMAND",
            "target_node_id": node_id,
            "vehicle_id": winner_req["vehicle_id"],
            "city": winner_req.get("city", "Mumbai, India"),
            "action": "HOLD_GREEN",
            "eta_s": winner_req["eta_s"],
            "priority_class": winner_req["priority_class"]
        }
        logger.info(f"Commanding {node_id} to hold GREEN for {payload['vehicle_id']} (Priority {payload['priority_class']})")
    else:
        # No more active vehicles, clear the intersection
        payload = {
            "event_type": "PREEMPT_COMMAND",
            "target_node_id": node_id,
            "vehicle_id": "NONE",
            "city": "Mumbai, India", # Ideally, we'd cache the city independently if it's required for MQTT routing later
            "action": "NORMAL_OPERATION",
            "eta_s": 0,
            "priority_class": 0
        }
        logger.info(f"Commanding {node_id} to resume NORMAL_OPERATION")

    await event_producer.send_event(
        topic="node.alert",
        payload=payload,
        key=node_id
    )

async def process_preempt_requests():
    """
    Main loop consuming incoming requests and feeding the state engine.
    """
    logger.info("Starting Priority Queue Event Bus processor...")
    try:
        await event_preempt_consumer.start()
        
        async for topic, payload in event_preempt_consumer:
            if payload.get("event_type") == "PREEMPT_TRIGGER":
                # Valid trigger envelope received
                try:
                    changed = resolver.add_request(payload)
                    if changed:
                        # Only broadcast to intersection if the alpha vehicle changed
                        await broadcast_winner(payload["target_node_id"])
                        
                except Exception as e:
                    logger.error(f"Failed to process preempt request payload: {e}")
                    
    except asyncio.CancelledError:
        logger.info("Priority Queue processor task cancelled.")
    except Exception as e:
        logger.error(f"Critical error in Priority Queue processor: {e}")

async def stale_pruning_loop():
    """
    Background loop that scrubs out dead drops if a vehicle crashes, turns off its siren,
    or diverges off the predicted path and stops emitting updates.
    """
    while True:
        try:
            await asyncio.sleep(10.0) # Check every 10 seconds
            changed_nodes = resolver.prune_stale_requests()
            for node_id in changed_nodes:
                # The state changed (e.g., the winner timed out, passing control to next vehicle, or back to normal)
                await broadcast_winner(node_id)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in stale pruning loop: {e}")

# ─────────────────────────────────────────────
# FastAPI Application & Lifespan
# ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Priority Queue dependencies...")
    
    processor_task = None
    
    try:
        await event_producer.start()
    except Exception as e:
        logger.warning(f"Event Bus not available: {e}")
    
    # Launch background tasks only if infra is available
    if event_producer._started:
        processor_task = asyncio.create_task(process_preempt_requests())
    else:
        logger.warning("Event Bus processor disabled — REST APIs still operational.")
    pruner_task = asyncio.create_task(stale_pruning_loop())
    
    yield
    
    logger.info("Shutting down Priority Queue dependencies...")
    if processor_task:
        processor_task.cancel()
    pruner_task.cancel()
    
    tasks = [t for t in [processor_task, pruner_task] if t]
    await asyncio.gather(*tasks, return_exceptions=True)
    
    try:
        await event_preempt_consumer.stop()
    except Exception:
        pass
    try:
        await event_producer.stop()
    except Exception:
        pass

app = FastAPI(
    title="Smart Signal - Priority Queue Service",
    description="Microservice resolving conflicting vehicle requests for signal priority.",
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
    """Basic health check and state introspection."""
    return {
        "status": "up",
        "service": "priority-queue",
        "event_producer_ready": event_producer._started,
        "tracked_intersections_count": len(resolver.active_requests)
    }
