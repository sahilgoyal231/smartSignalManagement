from fastapi import FastAPI, Depends, HTTPException, status
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import hashlib

from cloud.shared.database import get_db, check_db_connection
from cloud.shared.models import (
    VehicleRegisterRequest,
    VehicleResponse
)
from cloud.shared.db_models import Vehicle

app = FastAPI(
    title="Smart Signal - Vehicle Registry Service",
    description="Microservice for registering and managing emergency vehicles and their VSU hardware credentials.",
    version="1.0.0"
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
async def health_check(db: AsyncSession = Depends(get_db)):
    """Basic health check endpoint."""
    db_ok = await check_db_connection()
    return {
        "status": "up" if db_ok else "degraded",
        "service": "vehicle-registry",
        "database": "connected" if db_ok else "disconnected"
    }

@app.post("/api/v1/vehicles", response_model=VehicleResponse, status_code=status.HTTP_201_CREATED)
async def register_vehicle(request: VehicleRegisterRequest, db: AsyncSession = Depends(get_db)):
    """
    Registers a new emergency vehicle with the system.
    Expects X.509 certificate (PEM format) from the VSU for later beacon signature verification.
    """
    # 1. Check if vehicle_id already exists
    stmt = select(Vehicle).where(Vehicle.vehicle_id == request.vehicle_id)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Vehicle with ID '{request.vehicle_id}' already registered."
        )

    # 2. Check if license plate is already used
    stmt = select(Vehicle).where(Vehicle.license_plate == request.license_plate)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"License plate '{request.license_plate}' already registered."
        )

    # 3. Hash the provided certificate
    cert_hash = hashlib.sha256(request.cert_pem.encode('utf-8')).hexdigest()

    # 4. Create DB model
    new_vehicle = Vehicle(
        vehicle_id=request.vehicle_id,
        vehicle_type=request.vehicle_type.value,
        priority_class=request.priority_class.value,
        license_plate=request.license_plate,
        agency_name=request.agency_name,
        city=request.city,
        vsu_cert_hash=cert_hash,
        vsu_cert_pem=request.cert_pem,
        is_active=True
    )

    db.add(new_vehicle)
    await db.commit()
    await db.refresh(new_vehicle)

    # 5. Return response (SQLAlchemy object will be mapped to Pydantic VehicleResponse)
    return new_vehicle

@app.get("/api/v1/vehicles", response_model=List[VehicleResponse])
async def list_vehicles(active_only: bool = True, db: AsyncSession = Depends(get_db)):
    """Retrieves all registered vehicles. Defaults to active vehicles only."""
    stmt = select(Vehicle)
    if active_only:
        stmt = stmt.where(Vehicle.is_active == True)
        
    result = await db.execute(stmt)
    vehicles = result.scalars().all()
    return vehicles

@app.get("/api/v1/vehicles/{vehicle_id}", response_model=VehicleResponse)
async def get_vehicle(vehicle_id: str, db: AsyncSession = Depends(get_db)):
    """Retrieve details for a specific vehicle by ID."""
    stmt = select(Vehicle).where(Vehicle.vehicle_id == vehicle_id)
    result = await db.execute(stmt)
    vehicle = result.scalar_one_or_none()
    
    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vehicle '{vehicle_id}' not found."
        )
        
    return vehicle


@app.patch("/api/v1/vehicles/{vehicle_id}/deactivate", response_model=VehicleResponse)
async def deactivate_vehicle(vehicle_id: str, db: AsyncSession = Depends(get_db)):
    """
    Deactivate a vehicle — prevents it from participating in signal preemption.
    The VSU certificate remains on file for audit purposes.
    """
    from datetime import datetime, timezone

    stmt = select(Vehicle).where(Vehicle.vehicle_id == vehicle_id)
    result = await db.execute(stmt)
    vehicle = result.scalar_one_or_none()

    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vehicle '{vehicle_id}' not found."
        )

    if not vehicle.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Vehicle '{vehicle_id}' is already inactive."
        )

    vehicle.is_active = False
    vehicle.last_seen = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(vehicle)
    return vehicle


@app.patch("/api/v1/vehicles/{vehicle_id}/activate", response_model=VehicleResponse)
async def activate_vehicle(vehicle_id: str, db: AsyncSession = Depends(get_db)):
    """
    Re-activate a previously deactivated vehicle.
    """
    stmt = select(Vehicle).where(Vehicle.vehicle_id == vehicle_id)
    result = await db.execute(stmt)
    vehicle = result.scalar_one_or_none()

    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vehicle '{vehicle_id}' not found."
        )

    if vehicle.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Vehicle '{vehicle_id}' is already active."
        )

    vehicle.is_active = True
    await db.commit()
    await db.refresh(vehicle)
    return vehicle


@app.delete("/api/v1/vehicles/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vehicle(vehicle_id: str, db: AsyncSession = Depends(get_db)):
    """
    Permanently removes a vehicle record from the registry.
    Use deactivate instead for reversible removal.
    """
    stmt = select(Vehicle).where(Vehicle.vehicle_id == vehicle_id)
    result = await db.execute(stmt)
    vehicle = result.scalar_one_or_none()

    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vehicle '{vehicle_id}' not found."
        )

    await db.delete(vehicle)
    await db.commit()

