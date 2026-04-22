# 🚦 IoT Smart Signal System — Emergency Vehicle Clearance

An intelligent, real-time IoT-based traffic signal management system that detects approaching emergency vehicles and dynamically adjusts signal timing to clear their path — reducing emergency response times by 30–50%.

---

## 📁 Project Structure

```
smart-signal-system/
├── vsu/                    # Vehicle-Side Unit firmware (Raspberry Pi Zero 2W)
│   ├── src/                # Python source: GPS, LoRa TX, BLE, MQTT, siren sensor
│   ├── config/             # Environment configs, secrets template
│   └── tests/              # Unit tests for VSU modules
│
├── edge-node/              # Roadside Edge Node software (Raspberry Pi 4)
│   ├── src/
│   │   ├── sensors/        # LoRa RX, BLE scanner, camera (YOLOv8), mic (FFT)
│   │   ├── fusion/         # Multi-sensor fusion engine
│   │   ├── eta/            # ETA calculation algorithm
│   │   ├── signal/         # Signal controller interface (RS-485 / relay GPIO)
│   │   └── mqtt/           # MQTT pub/sub client
│   ├── config/
│   └── tests/
│
├── cloud/                  # Cloud backend microservices (Python FastAPI)
│   ├── services/
│   │   ├── vehicle-registry/   # Vehicle CRUD + auth
│   │   ├── route-engine/       # OSMnx A* route prediction
│   │   ├── priority-queue/     # Multi-vehicle conflict resolution
│   │   ├── event-service/      # Preemption event logging + analytics
│   │   └── ota-service/        # Firmware OTA update delivery
│   ├── shared/             # Shared models, DB connectors, MQTT utils
│   └── config/
│
├── dashboard/              # Admin web dashboard (Next.js + React)
│   ├── src/
│   │   ├── components/     # Reusable UI components
│   │   ├── pages/          # Next.js page routes
│   │   ├── hooks/          # Custom React hooks (WebSocket, auth)
│   │   └── utils/          # API clients, formatters
│   └── public/
│
├── infra/                  # Infrastructure as code
│   ├── docker/             # Dockerfiles + docker-compose
│   ├── k8s/                # Kubernetes manifests
│   ├── terraform/          # AWS infrastructure (EC2, RDS, InfluxDB, ElastiCache)
│   └── scripts/            # Setup, seed, and migration scripts
│
└── docs/                   # Technical documentation
    ├── api/                # OpenAPI specs
    ├── hardware/           # Wiring diagrams, BOM
    └── deployment/         # Deployment + runbook
```

---

## 🚀 Quick Start

**Note:** For a comprehensive, step-by-step guide on how to run this project natively on your local machine (macOS/Linux), please see the [**Local Setup & Installation Guide**](SETUP.md).

### Prerequisites
- Python 3.11+
- Node.js 20+
- Docker + Docker Compose
- PostgreSQL 15
- InfluxDB 2.x

### 1. Clone and set up environment
```bash
git clone <repo-url>
cd smart-signal-system
cp .env.example .env   # fill in your secrets
```

### 2. Start all services (local dev)
```bash
docker-compose -f infra/docker/docker-compose.yml up -d
```

### 3. Run database migrations
```bash
cd infra/scripts
python run_migrations.py
```

### 4. Start cloud backend
```bash
cd cloud
pip install -r requirements.txt
uvicorn services.vehicle-registry.main:app --reload --port 8001
```

### 5. Start dashboard
```bash
cd dashboard
npm install
npm run dev
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| VSU Firmware | Python 3.11, paho-mqtt, pyserial, RPi.GPIO |
| Edge Node | Python 3.11, YOLOv8-nano, OpenCV, librosa, scipy |
| Cloud | FastAPI, PostgreSQL, InfluxDB 2.x, Redis, Kafka, EMQX |
| Dashboard | Next.js 14, React 18, Mapbox GL, Chart.js, Socket.IO |
| Security | TLS 1.3, ECDSA-P256, JWT, X.509 certs |
| DevOps | Docker, Kubernetes, Terraform, GitHub Actions |

---

## 📄 License
MIT License — © 2026 IoT Smart Signal System Project
