#!/usr/bin/env bash
# run_local_mac.sh
# ------------------------------
# Orchestrates FastAPI services and Dashboard simultaneously.

echo "🚀 Booting Smart Signal System (MacOS Native Layer)..."

# Ensure runtime paths
export PYTHONPATH="$(pwd)"
export POSTGRES_URL="sqlite+aiosqlite:///dev.db"

# Source virtualenv
if [ -f ".venv_new/bin/activate" ]; then
    source .venv_new/bin/activate
elif [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
else
    echo "⚠️  No virtual environment found!"
    exit 1
fi

# Cleanup and Trap
mkdir -p .logs
trap 'echo "🛑 Shutting down..."; kill $(jobs -p) 2>/dev/null; exit' SIGINT SIGTERM

echo "🟢 Spinning up APIs..."

# Boot APIs into background
uvicorn cloud.services.event_service.main:app --port 8001 > .logs/event.log 2>&1 &
uvicorn cloud.services.health_monitor.main:app --port 8002 > .logs/health.log 2>&1 &
uvicorn cloud.services.ota_service.main:app --port 8003 > .logs/ota.log 2>&1 &
uvicorn cloud.services.priority_queue.main:app --port 8004 > .logs/priority.log 2>&1 &
uvicorn cloud.services.route_engine.main:app --port 8005 > .logs/route.log 2>&1 &
uvicorn cloud.services.vehicle_registry.main:app --port 8006 > .logs/registry.log 2>&1 &

echo "✨ Services are attached to Ports 8001-8006 (Check .logs/ directory for metrics)"

echo "🖥️  Booting Dashboard..."
cd dashboard && zsh -ic "npm run dev" &

# Wait for completion trap
wait
