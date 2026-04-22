# Local Setup & Installation Guide

This guide provides step-by-step instructions on how to set up and run the Smart Signal System on any local machine (macOS/Linux). It covers environment configuration, database seeding, and orchestrating the microservices.

## 1. Prerequisites
Ensure you have the following installed on your machine:
- **Python 3.11+**
- **Node.js 20+**
- **Git**

*(Note: If you plan to run the production stack, you will also need Docker and Docker Compose. This guide focuses on running the native local development stack.)*

---

## 2. Clone the Repository
Open your terminal and clone the repository:
```bash
git clone https://github.com/sahilgoyal231/smartSignalManagement.git
cd smart-signal-system
```

---

## 3. Environment Configuration
The project requires an environment file to store secrets and database URLs.
Copy the example environment file:
```bash
cp .env.example .env
```
Open `.env` in your text editor and fill in any required secrets (e.g., Mapbox tokens if needed for the dashboard). For local development, the defaults usually suffice.

---

## 4. Backend Setup (Python APIs)

The cloud microservices are built with FastAPI. You need to set up a Python virtual environment to isolate dependencies.

### Create and Activate Virtual Environment
```bash
python3 -m venv .venv_new
source .venv_new/bin/activate
```

### Install Dependencies
Navigate to the `cloud` directory (or use the root requirements if unified) and install the required packages:
```bash
# If requirements are in the cloud folder:
pip install -r cloud/requirements.txt
```

### Initialize the Local Database
We provide a script to generate a local SQLite database (`seed.db`) populated with realistic test data (vehicles, edge nodes, etc.) for local development.
```bash
python scripts/init_dev_db.py
```
*(This will create a `seed.db` or `dev.db` file in your root directory containing mock Mumbai traffic data.)*

---

## 5. Frontend Setup (Next.js Dashboard)

The admin dashboard is a Next.js application located in the `dashboard` folder.

```bash
cd dashboard
npm install
cd ..
```

---

## 6. Running the System

You can run the entire system (all 6 microservices + the Next.js dashboard) simultaneously using the provided bash script.

```bash
# Make sure your virtual environment is still activated!
source .venv_new/bin/activate

# Execute the local orchestrator script
bash infra/scripts/run_local_mac.sh
```

### What happens when you run this?
1. The script boots 6 FastAPI microservices in the background (Ports 8001–8006).
2. It redirects their logs to the `.logs/` directory (e.g., `.logs/event.log`).
3. It boots the Next.js Dashboard on **Port 3000**.

### Accessing the System
Once the script says `Ready`, open your web browser and navigate to:
👉 **http://localhost:3000**

---

## 7. Troubleshooting

- **Port in Use Error:** If Next.js fails to start, you might have a stale process. Run `pkill -f node` and `pkill -f uvicorn` to kill dangling background processes, then try again.
- **Next.js Lock Error:** If you see `Unable to acquire lock at .../.next/dev/lock`, delete the `.next` folder inside the `dashboard` directory: `rm -rf dashboard/.next`.
- **Database Not Found:** Ensure `scripts/init_dev_db.py` ran successfully and generated the SQLite `.db` file. The local orchestrator script is configured to read from `sqlite+aiosqlite:///seed.db` via the `OVERRIDE_DB_URL` environment variable.
