#!/usr/bin/env bash
# ============================================================
# 🚦 Smart Signal System — Full Stack Startup Script
# ============================================================
# Starts all services in the correct order:
#   1. Infrastructure (PostgreSQL, InfluxDB, Redis)
#   2. Messaging (EMQX, Zookeeper, Kafka)
#   3. Application (Cloud API)
#   4. Monitoring (Grafana)
#   5. Runs DB migrations + InfluxDB setup
#
# Usage:
#   chmod +x infra/scripts/start.sh
#   ./infra/scripts/start.sh
# ============================================================

set -euo pipefail

COMPOSE="docker-compose -f infra/docker/docker-compose.yml"
ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

echo "🚦 Smart Signal System — Starting All Services"
echo "================================================"

# ── Load .env ────────────────────────────────────────────────
if [ -f "$ROOT_DIR/.env" ]; then
    echo "📄 Loading .env ..."
    set -a; source "$ROOT_DIR/.env"; set +a
else
    echo "⚠️  .env not found — copy .env.example to .env first!"
    exit 1
fi

# ── Start infrastructure layer ────────────────────────────────
echo ""
echo "🗄  Starting infrastructure (PostgreSQL, InfluxDB, Redis)..."
$COMPOSE up -d postgres influxdb redis

echo "⏳ Waiting for PostgreSQL to be ready..."
until $COMPOSE exec -T postgres pg_isready -U "${POSTGRES_USER:-ss_admin}" \
      -d "${POSTGRES_DB:-smart_signal}" > /dev/null 2>&1; do
    sleep 2
done
echo "   ✅ PostgreSQL ready"

echo "⏳ Waiting for InfluxDB to be ready..."
until $COMPOSE exec -T influxdb influx ping > /dev/null 2>&1; do
    sleep 2
done
echo "   ✅ InfluxDB ready"

# ── Start messaging layer ─────────────────────────────────────
echo ""
echo "📡 Starting messaging (EMQX, Zookeeper, Kafka)..."
$COMPOSE up -d emqx zookeeper

echo "⏳ Waiting for Zookeeper..."
sleep 5
$COMPOSE up -d kafka

echo "⏳ Waiting for Kafka..."
until $COMPOSE exec -T kafka kafka-broker-api-versions \
      --bootstrap-server localhost:9092 > /dev/null 2>&1; do
    sleep 3
done
echo "   ✅ Kafka ready"

echo "⏳ Waiting for EMQX..."
until $COMPOSE exec -T emqx emqx ping > /dev/null 2>&1; do
    sleep 2
done
echo "   ✅ EMQX ready"

# ── Run DB migrations ─────────────────────────────────────────
echo ""
echo "🔄 Running Alembic migrations..."
cd "$ROOT_DIR/cloud"
alembic upgrade head
echo "   ✅ Migrations applied"

# ── Set up InfluxDB buckets ────────────────────────────────────
echo ""
echo "📊 Setting up InfluxDB buckets & tasks..."
cd "$ROOT_DIR"
python infra/scripts/setup_influx.py
echo "   ✅ InfluxDB configured"

# ── Seed database ─────────────────────────────────────────────
read -r -p "Seed database with test data? [y/N] " seed_choice
if [[ "$seed_choice" =~ ^[Yy]$ ]]; then
    echo "🌱 Seeding database..."
    python infra/scripts/seed.py
fi

# ── Start application + monitoring ────────────────────────────
echo ""
echo "🚀 Starting Cloud API and Grafana..."
$COMPOSE up -d cloud-api grafana

echo ""
echo "================================================"
echo "✅ Smart Signal System is UP!"
echo ""
echo "   🌐 Cloud API:    http://localhost:8000"
echo "   📖 API Docs:     http://localhost:8000/docs"
echo "   📊 Grafana:      http://localhost:3001"
echo "   📡 EMQX Console: http://localhost:18083"
echo "   🗄  InfluxDB:     http://localhost:8086"
echo "================================================"
