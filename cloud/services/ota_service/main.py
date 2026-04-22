"""
OTA Service — FastAPI Microservice
====================================
Manages firmware manifests, upload, and OTA update orchestration for Edge Nodes.

All state is held in-memory (dict-based stores).
In production, replace with Redis / PostgreSQL-backed stores.

Endpoints:
    GET  /health
    GET  /api/v1/firmware/latest
    POST /api/v1/firmware/upload       (multipart form)
    POST /api/v1/ota/trigger/{node_id}
    GET  /api/v1/ota/status/{node_id}
"""
import uuid
from datetime import datetime, timezone
from typing import Dict

from fastapi import FastAPI, HTTPException, UploadFile, File, status
from loguru import logger

from .models import (
    FirmwareManifest,
    OTAJob,
    OTAJobStatus,
    OTATriggerRequest,
    OTAStatusResponse,
)

# ── Known node IDs (in production, query vehicle-registry / edge-node DB) ─────
KNOWN_NODES: set[str] = {
    "NODE-MUM-001", "NODE-MUM-002", "NODE-MUM-003",
    "NODE-MUM-004", "NODE-MUM-005", "NODE-PUN-001",
    "NODE-PUN-002", "NODE-PUN-003",
}

# ── In-memory stores ──────────────────────────────────────────────────────────
_firmware_manifest: FirmwareManifest = FirmwareManifest(
    version="2.3.1",
    sha256="a3f892bc1d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0",
    size_bytes=1_048_576,   # 1 MB placeholder
    release_notes=(
        "v2.3.1 — LoRa sensitivity +3 dBm, ECDSA replay window extended to 64, "
        "YOLO nano model updated to YOLOv8n-v2026Q1."
    ),
    released_at=datetime(2026, 3, 1, 9, 0, 0, tzinfo=timezone.utc),
)

_ota_jobs: Dict[str, OTAJob] = {}   # node_id → latest OTAJob


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Smart Signal - OTA Service",
    description="Firmware management and over-the-air update orchestration for Edge Nodes.",
    version="1.0.0",
)

from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    return {
        "status":           "up",
        "service":          "ota-service",
        "firmware_version": _firmware_manifest.version,
        "tracked_jobs":     len(_ota_jobs),
    }


# ── Firmware manifest ─────────────────────────────────────────────────────────

@app.get("/api/v1/firmware/latest", response_model=FirmwareManifest)
async def get_latest_firmware():
    """Returns the current production firmware manifest."""
    return _firmware_manifest


@app.post("/api/v1/firmware/upload", response_model=FirmwareManifest, status_code=status.HTTP_201_CREATED)
async def upload_firmware(
    version: str,
    release_notes: str,
    file: UploadFile = File(...),
):
    """
    Upload a new firmware binary.
    Reads the file, computes SHA-256, and updates the in-memory manifest.
    """
    import hashlib

    global _firmware_manifest

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")

    sha256 = hashlib.sha256(contents).hexdigest()

    _firmware_manifest = FirmwareManifest(
        version=version,
        sha256=sha256,
        size_bytes=len(contents),
        release_notes=release_notes,
        released_at=datetime.now(timezone.utc),
    )

    logger.success(f"New firmware uploaded: v{version} sha256={sha256[:12]}… size={len(contents)} bytes")
    return _firmware_manifest


# ── OTA trigger & status ──────────────────────────────────────────────────────

@app.post(
    "/api/v1/ota/trigger/{node_id}",
    response_model=OTAJob,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_ota(node_id: str, body: OTATriggerRequest = OTATriggerRequest()):
    """
    Schedule an OTA update for a specific edge node.
    Returns the created OTAJob immediately; the node polls for status.
    """
    if node_id not in KNOWN_NODES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node '{node_id}' is not registered in this deployment.",
        )

    # If already running and not forced, reject
    existing = _ota_jobs.get(node_id)
    if existing and existing.status == OTAJobStatus.IN_PROGRESS and not body.force:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Node '{node_id}' already has an OTA update in progress. Use force=true to override.",
        )

    job = OTAJob(
        job_id=str(uuid.uuid4()),
        node_id=node_id,
        firmware_version=_firmware_manifest.version,
        status=OTAJobStatus.PENDING,
        scheduled_at=datetime.now(timezone.utc),
    )
    _ota_jobs[node_id] = job
    logger.info(f"OTA job {job.job_id} scheduled for {node_id} → v{_firmware_manifest.version}")
    return job


@app.get("/api/v1/ota/status/{node_id}", response_model=OTAStatusResponse)
async def get_ota_status(node_id: str):
    """
    Returns the current OTA job status for a node.
    If no job has ever been triggered, returns NOT_SCHEDULED.
    """
    job = _ota_jobs.get(node_id)
    if not job:
        return OTAStatusResponse(node_id=node_id, status=OTAJobStatus.NOT_SCHEDULED)
    return OTAStatusResponse(node_id=node_id, status=job.status, job=job)
