# 🚀 Free Cloud Deployment — Complete Walkthrough

> **Goal:** Deploy the entire Smart Signal System — 6 microservices, an admin dashboard, 4 managed databases/brokers — for **$0/month** using generous PaaS free tiers.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Prerequisites](#2-prerequisites)
3. [Step 1 — Provision Cloud Databases & Brokers](#3-step-1--provision-cloud-databases--brokers)
4. [Step 2 — Deploy the Backend on Render](#4-step-2--deploy-the-backend-on-render)
5. [Step 3 — Deploy the Dashboard on Vercel](#5-step-3--deploy-the-dashboard-on-vercel)
6. [Step 4 — Wire Everything Together](#6-step-4--wire-everything-together)
7. [Verification Checklist](#7-verification-checklist)
8. [Free Tier Limits & Gotchas](#8-free-tier-limits--gotchas)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CLOUD LAYER                                 │
│                                                                     │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐          │
│   │ Vercel       │    │ Render.com   │    │ Upstash      │          │
│   │ ─────────    │    │ ──────────   │    │ ────────     │          │
│   │ Next.js      │◄──►│ FastAPI      │◄──►│ Redis        │          │
│   │ Dashboard    │    │ Monolith     │    │ (Event Bus + │          │
│   │              │    │ (6 services) │    │  State Cache)│          │
│   └──────────────┘    └──────┬───────┘    └──────────────┘          │
│                              │                                      │
│                   ┌──────────┼──────────┐                           │
│                   │          │          │                            │
│            ┌──────▼───┐ ┌───▼────┐ ┌───▼──────┐                    │
│            │ Supabase  │ │InfluxDB│ │ HiveMQ   │                    │
│            │ ────────  │ │ Cloud  │ │ Cloud    │                    │
│            │ PostgreSQL│ │ ─────  │ │ ──────   │                    │
│            │ (Vehicles,│ │ Time-  │ │ MQTT     │                    │
│            │  Nodes,   │ │ series │ │ Broker   │                    │
│            │  Events)  │ │ data   │ │ (IoT)    │                    │
│            └───────────┘ └────────┘ └──────────┘                    │
└─────────────────────────────────────────────────────────────────────┘
                                ▲
                                │ MQTT over TLS
                    ┌───────────┴───────────┐
                    │    EDGE LAYER          │
                    │  (Raspberry Pi 4)      │
                    │  Edge Nodes at         │
                    │  Intersections         │
                    └───────────────────────┘
```

### Services Deployed on Render (Monolith Mode)

| Service | Path Mount | Purpose |
|---------|-----------|---------|
| **Event Service** | `/events` | MQTT ↔ Redis bridge, WebSocket streaming, preemption event CRUD |
| **Health Monitor** | `/health` | Edge Node heartbeat tracking, stale detection, OTA triggers |
| **OTA Service** | `/ota` | Firmware release & rollout management |
| **Priority Queue** | `/priority` | Multi-vehicle conflict resolution at intersections |
| **Route Engine** | `/route` | OSMnx A* route prediction, ETA calculation |
| **Vehicle Registry** | `/vehicles` | Emergency vehicle fleet CRUD & authentication |

> **Key Design Decision:** For the free tier, all 6 services run as a **single monolith process** (`cloud/main_monolith.py`) instead of 6 separate containers. This avoids burning 6 Render free-tier slots and keeps event communication in-process.

---

## 2. Prerequisites

Before you begin, make sure you have:

- [ ] A **GitHub account** with this repository pushed (Render & Vercel deploy from GitHub)
- [ ] Accounts on the following (all have free tiers — no credit card needed):
  - [Supabase](https://supabase.com/)
  - [Upstash](https://upstash.com/)
  - [InfluxDB Cloud](https://cloud2.influxdata.com/)
  - [HiveMQ Cloud](https://www.hivemq.com/mqtt-cloud-broker/)
  - [Render](https://render.com/)
  - [Vercel](https://vercel.com/)

---

## 3. Step 1 — Provision Cloud Databases & Brokers

Set up the 4 managed services your backend needs. Each takes ~2 minutes.

---

### 3.1 PostgreSQL → Supabase

Stores vehicles, edge nodes, preemption events, system faults.

1. Go to [supabase.com](https://supabase.com/) → **New Project**
2. Choose a region close to your Render deployment (e.g., `South Asia (Mumbai)`)
3. Set a strong database password and **save it somewhere safe**
4. Once provisioned, go to **Project Settings → Database**
5. Under **Connection string → URI**, copy the connection string

**Your value:**
```
POSTGRES_URL=postgresql+asyncpg://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres
```

> ⚠️ **Important:** Replace `postgresql://` with `postgresql+asyncpg://` at the start — SQLAlchemy requires the async driver prefix.

---

### 3.2 Redis (Event Bus + Cache) → Upstash

Serves as both the real-time state cache AND the internal event streaming backbone (via Redis Pub/Sub — replacing traditional Kafka).

1. Go to [console.upstash.com](https://console.upstash.com/) → **Create Database**
2. Choose the region closest to your Render deployment
3. Select **TLS enabled** (recommended)
4. Once created, go to the database **Details** tab
5. Under **Connect your database**, find the **TCP (TLS)** section
6. Copy the full connection URL

**Your value:**
```
REDIS_URL=rediss://default:[PASSWORD]@[ENDPOINT].upstash.io:6379
```

> **Which endpoint?**  Use the **TCP (TLS)** endpoint — `rediss://` protocol (double `s`). This is what the Python `redis[asyncio]` library needs. Do NOT use the HTTPS/REST endpoint here.

---

### 3.3 Time-Series Database → InfluxDB Cloud

Stores high-frequency telemetry data (sensor readings, GPS traces, signal timing).

1. Go to [cloud2.influxdata.com](https://cloud2.influxdata.com/) → Sign up
2. Create an organization (e.g., `SmartSignal`)
3. Create a bucket named `telemetry`
4. Go to **API Tokens** → **Generate API Token** → **Custom API Token**
   - Grant Read/Write access to your `telemetry` bucket
5. Copy the token and note your region URL

**Your values:**
```
INFLUX_URL=https://us-east-1-1.aws.cloud2.influxdata.com   # your region
INFLUX_TOKEN=[YOUR-API-TOKEN]
INFLUX_ORG=SmartSignal
INFLUX_BUCKET=telemetry
```

---

### 3.4 MQTT Broker → HiveMQ Cloud

Handles all IoT communication between Edge Nodes (Raspberry Pi) and the Cloud.

1. Go to [hivemq.com/mqtt-cloud-broker](https://www.hivemq.com/mqtt-cloud-broker/) → **Get Started Free**
2. Create a **Serverless** cluster
3. Once provisioned, go to **Access Management** → Create credentials:
   - Username: e.g., `cloud_backend`
   - Password: generate a strong one
4. Note the cluster hostname from the **Overview** tab

**Your values:**
```
MQTT_BROKER_HOST=[CLUSTER-ID].s2.eu.hivemq.cloud
MQTT_BROKER_PORT=8883
MQTT_BROKER_USER=cloud_backend
MQTT_BROKER_PASSWORD=[YOUR-PASSWORD]
```

---

### 3.5 Generate a JWT Secret

Generate a random 64-character secret for JWT token signing:

```bash
openssl rand -hex 32
```

**Your value:**
```
JWT_SECRET_KEY=[64-char-hex-output]
JWT_ALGORITHM=RS256
JWT_EXPIRE_MINUTES=60
```

---

### 📋 Summary — All Backend Environment Variables

After completing Steps 3.1–3.5, you should have the following complete set:

```env
# Project
PROJECT_NAME=SmartSignalSystem
ENVIRONMENT=production
LOG_LEVEL=INFO

# PostgreSQL (Supabase)
POSTGRES_URL=postgresql+asyncpg://postgres:****@db.****.supabase.co:5432/postgres

# InfluxDB Cloud
INFLUX_URL=https://******.aws.cloud2.influxdata.com
INFLUX_TOKEN=****
INFLUX_ORG=SmartSignal
INFLUX_BUCKET=telemetry

# Redis (Upstash — Event Bus + Cache)
REDIS_URL=rediss://default:****@****.upstash.io:6379

# MQTT (HiveMQ Cloud)
MQTT_BROKER_HOST=****.s2.eu.hivemq.cloud
MQTT_BROKER_PORT=8883
MQTT_BROKER_USER=cloud_backend
MQTT_BROKER_PASSWORD=****
MQTT_CLIENT_ID_PREFIX=cloud-service

# JWT
JWT_SECRET_KEY=****
JWT_ALGORITHM=RS256
JWT_EXPIRE_MINUTES=60
```

Save this somewhere safe — you'll paste these into Render and Vercel in the next steps.

---

## 4. Step 2 — Deploy the Backend on Render

### Option A: Monolith Deploy (Recommended for Free Tier) ⭐

Deploys all 6 services as a single process on 1 free Render instance.

1. Go to [render.com](https://render.com/) → **New → Web Service**
2. Connect your GitHub repository
3. Configure:

   | Setting | Value |
   |---------|-------|
   | **Name** | `smart-signal-api` |
   | **Region** | Same as your Supabase region |
   | **Branch** | `main` |
   | **Runtime** | `Python 3` |
   | **Build Command** | `pip install -r cloud/requirements-light.txt` |
   | **Start Command** | `uvicorn cloud.main_monolith:app --host 0.0.0.0 --port 10000` |
   | **Instance Type** | `Free` |

4. Go to **Environment** → Add all variables from the [Summary](#-summary--all-backend-environment-variables) above
5. Also add:
   ```
   PYTHONPATH=/opt/render/project/src
   PORT=10000
   ```
6. Click **Deploy**

After ~2–3 minutes, your backend will be live at:
```
https://smart-signal-api-xxxx.onrender.com
```

Verify by hitting:
```
https://smart-signal-api-xxxx.onrender.com/
# Expected: {"status": "up", "mode": "monolith"}
```

### Option B: Microservices Deploy (Uses 6 Free Slots)

If you want each service on its own URL (uses the pre-configured `render.yaml`):

1. Go to [render.com](https://render.com/) → **New → Blueprint**
2. Connect your GitHub repository
3. Render reads `render.yaml` and creates 6 web services automatically
4. Go to **Environment Groups** and paste all env variables

> ⚠️ Render's free tier allows limited services. Option A is recommended unless you need independent scaling.

---

## 5. Step 3 — Deploy the Dashboard on Vercel

1. Go to [vercel.com](https://vercel.com/) → **Add New → Project**
2. Import your GitHub repository
3. Configure:

   | Setting | Value |
   |---------|-------|
   | **Framework Preset** | `Next.js` (auto-detected) |
   | **Root Directory** | `dashboard/` |
   | **Build Command** | `npm run build` (default) |
   | **Output Directory** | `.next` (default) |

4. In **Environment Variables**, add the following (adjust URLs based on your Render deployment):

   **For Monolith deploy (Option A):**
   ```env
   NEXT_PUBLIC_VEHICLE_REGISTRY_URL=https://smart-signal-api-xxxx.onrender.com/vehicles
   NEXT_PUBLIC_EDGE_REGISTRY_URL=https://smart-signal-api-xxxx.onrender.com/health
   NEXT_PUBLIC_EVENT_SERVICE_URL=https://smart-signal-api-xxxx.onrender.com/events
   NEXT_PUBLIC_PRIORITY_QUEUE_URL=https://smart-signal-api-xxxx.onrender.com/priority
   NEXT_PUBLIC_ROUTE_ENGINE_URL=https://smart-signal-api-xxxx.onrender.com/route
   NEXT_PUBLIC_OTA_SERVICE_URL=https://smart-signal-api-xxxx.onrender.com/ota
   NEXT_PUBLIC_EVENT_WS_URL=wss://smart-signal-api-xxxx.onrender.com/events/api/v1/stream
   ```

   **For Microservices deploy (Option B):**
   ```env
   NEXT_PUBLIC_VEHICLE_REGISTRY_URL=https://vehicle-registry-xxxx.onrender.com
   NEXT_PUBLIC_EDGE_REGISTRY_URL=https://health-monitor-xxxx.onrender.com
   NEXT_PUBLIC_EVENT_SERVICE_URL=https://event-service-xxxx.onrender.com
   NEXT_PUBLIC_PRIORITY_QUEUE_URL=https://priority-queue-xxxx.onrender.com
   NEXT_PUBLIC_ROUTE_ENGINE_URL=https://route-engine-xxxx.onrender.com
   NEXT_PUBLIC_OTA_SERVICE_URL=https://ota-service-xxxx.onrender.com
   NEXT_PUBLIC_EVENT_WS_URL=wss://event-service-xxxx.onrender.com/api/v1/stream
   ```

5. Click **Deploy**

Within 2 minutes, your dashboard will be live at:
```
https://smart-signal-dashboard.vercel.app
```

---

## 6. Step 4 — Wire Everything Together

### 6.1 Initialize the Database

The first time the backend starts, the database tables need to be created. The app's `init_db()` function handles this automatically for development. For production with Supabase PostgreSQL, you can either:

- **Option A:** Let SQLAlchemy auto-create tables on first startup (works with the current `init_db()`)
- **Option B:** Run Alembic migrations manually:
  ```bash
  # SSH into Render shell or run locally pointing at the production DB:
  POSTGRES_URL=postgresql+asyncpg://... alembic upgrade head
  ```

### 6.2 Seed Test Data (Optional)

To populate the database with realistic Mumbai traffic intersection data:

```bash
# Run locally, pointing at the production Supabase DB:
POSTGRES_URL=postgresql+asyncpg://... python scripts/init_dev_db.py
```

### 6.3 Verify the Full Pipeline

```
┌──────────┐     MQTT      ┌──────────┐    Redis     ┌──────────┐
│ Edge Node├──────────────►│  Event   ├───Pub/Sub───►│  Health  │
│ (Pi 4)   │   TLS:8883    │  Service │              │  Monitor │
└──────────┘               └────┬─────┘              └──────────┘
                                │ WebSocket
                           ┌────▼─────┐
                           │ Dashboard│
                           │ (Vercel) │
                           └──────────┘
```

---

## 7. Verification Checklist

After deployment, verify each layer is working:

| # | Check | URL / Command | Expected |
|---|-------|---------------|----------|
| 1 | Backend health | `GET /` | `{"status": "up", "mode": "monolith"}` |
| 2 | Event Service | `GET /events/health` | `{"status": "up", "service": "event-service"}` |
| 3 | Health Monitor | `GET /health/health` | `{"status": "up", "service": "health-monitor"}` |
| 4 | Vehicle Registry | `GET /vehicles/health` | `{"status": "up", "service": "vehicle-registry"}` |
| 5 | Dashboard loads | Visit Vercel URL | Login page renders |
| 6 | Supabase DB | Check Supabase Table Editor | Tables created |
| 7 | Redis connected | Check Render logs | `Event Producer connected to Redis at *.upstash.io:6379` |
| 8 | MQTT connected | Check Render logs | `Connected to MQTT broker` |

---

## 8. Free Tier Limits & Gotchas

| Service | Free Tier Limit | Impact |
|---------|----------------|--------|
| **Render** | Spins down after 15 min inactivity | First request takes ~30s to cold-start |
| **Supabase** | 500 MB database, pauses after 1 week inactivity | Re-activate in dashboard if paused |
| **Upstash Redis** | 10,000 commands/day, 256 MB | Sufficient for demo/dev workloads |
| **InfluxDB Cloud** | 30-day retention, limited writes | Fine for telemetry demos |
| **HiveMQ Cloud** | 100 concurrent connections | Enough for ~50 edge nodes in a demo |
| **Vercel** | 100 GB bandwidth/month | More than sufficient for dashboards |

### Tips to Stay Within Limits

- **Render cold starts:** Add a free cron service (like [cron-job.org](https://cron-job.org/)) to ping your backend every 14 minutes to keep it warm
- **Supabase pausing:** Log into Supabase weekly or set up the same cron ping
- **Redis commands:** The event bus only fires on actual IoT events, so idle usage is near zero

---

## 9. Troubleshooting

### Backend won't start on Render

| Symptom | Solution |
|---------|----------|
| `ModuleNotFoundError: cloud.services...` | Ensure `PYTHONPATH=/opt/render/project/src` is set |
| `pydantic_settings.ValidationError` | Missing env vars — double-check all required vars are set |
| `redis.exceptions.ConnectionError` | Verify `REDIS_URL` uses `rediss://` (double `s`) for Upstash TLS |
| `sqlalchemy.exc.OperationalError` | Verify `POSTGRES_URL` starts with `postgresql+asyncpg://` |

### Dashboard shows "Network Error"

| Symptom | Solution |
|---------|----------|
| API calls fail with CORS | Backend already has `allow_origins=["*"]` — check URL prefixes match |
| WebSocket won't connect | For monolith, use `wss://...onrender.com/events/api/v1/stream` |
| Data not loading | Backend may be cold-starting — wait 30s and refresh |

### MQTT not connecting

| Symptom | Solution |
|---------|----------|
| `MQTT Configuration failed` | Verify HiveMQ credentials and that port 8883 is used |
| Edge nodes can't connect | Create separate MQTT credentials for edge devices in HiveMQ dashboard |

---

## 🎉 You're Done!

You now have a fully operational, enterprise-grade IoT traffic management system running globally — **completely free**:

| Component | URL |
|-----------|-----|
| **Dashboard** | `https://your-app.vercel.app` |
| **Backend API** | `https://smart-signal-api-xxxx.onrender.com` |
| **API Docs (Swagger)** | `https://smart-signal-api-xxxx.onrender.com/docs` |
| **Database** | Supabase Dashboard |
| **Redis Monitor** | Upstash Console |
| **MQTT Monitor** | HiveMQ Console |
