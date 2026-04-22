"""
OTA Service Pydantic Models
============================
All in-memory — no database dependency.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class OTAJobStatus(str, Enum):
    PENDING       = "PENDING"
    IN_PROGRESS   = "IN_PROGRESS"
    SUCCESS       = "SUCCESS"
    FAILED        = "FAILED"
    NOT_SCHEDULED = "NOT_SCHEDULED"


class FirmwareManifest(BaseModel):
    version:        str
    sha256:         str
    size_bytes:     int
    release_notes:  str
    released_at:    datetime


class OTATriggerRequest(BaseModel):
    force: bool = Field(
        False,
        description="If True, trigger OTA even if node is already on the latest firmware version"
    )


class OTAJob(BaseModel):
    job_id:     str
    node_id:    str
    firmware_version: str
    status:     OTAJobStatus
    scheduled_at: datetime
    completed_at: Optional[datetime] = None
    error_msg:  Optional[str] = None


class OTAStatusResponse(BaseModel):
    node_id: str
    status:  OTAJobStatus
    job:     Optional[OTAJob] = None
