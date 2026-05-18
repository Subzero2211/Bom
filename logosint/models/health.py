"""
logosint/models/health.py
"""

from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class CollectorStatus(str, Enum):
    OK       = "ok"
    DEGRADED = "degraded"
    STALE    = "stale"
    FAILED   = "failed"
    NO_KEY   = "no_key"


class CollectorHealth(BaseModel):
    name:             str
    status:           CollectorStatus
    last_run:         Optional[datetime] = None
    last_success:     Optional[datetime] = None
    consecutive_errors: int = 0
    ingestion_lag_s:  Optional[float]   = None   # saniye
    signals_last_hour: int = 0
    api_key_present:  bool = False
    note:             Optional[str]     = None

    @property
    def is_healthy(self) -> bool:
        return self.status == CollectorStatus.OK

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class HealthSnapshot(BaseModel):
    snapshot_id:  str
    timestamp:    datetime
    collectors:   list[CollectorHealth] = Field(default_factory=list)
    scoring_latency_ms: Optional[float] = None
    last_scan_id: Optional[str]         = None
    last_scan_at: Optional[datetime]    = None
    alerts_last_hour: int = 0
    system_ok:    bool = True

    @property
    def degraded_collectors(self) -> list[CollectorHealth]:
        return [c for c in self.collectors if not c.is_healthy]

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}
