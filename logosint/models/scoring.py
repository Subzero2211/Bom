"""
logosint/models/scoring.py

Scoring çıktı modelleri ve prediction registry.
"""

from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
import uuid


class ScoringOutput(BaseModel):
    output_id:            str      = Field(default_factory=lambda: str(uuid.uuid4()))
    scan_id:              str
    timestamp:            datetime
    scenario_id:          int
    scenario_name:        str
    region:               str
    score:                float    = Field(..., ge=0.0, le=100.0)
    probability:          float    = Field(..., ge=0.0, le=1.0)
    confidence:           float    = Field(..., ge=0.0, le=1.0)
    threshold_level:      int      = Field(..., ge=0, le=4)
    contributing_factors: list[str] = Field(default_factory=list)
    edge_contributions:   dict[str, float] = Field(default_factory=dict)

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class PredictionStatus(str, Enum):
    PENDING   = "pending"
    VERIFIED  = "verified"
    EXPIRED   = "expired"
    CANCELLED = "cancelled"


class Prediction(BaseModel):
    prediction_id:   str      = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at:      datetime
    scenario_id:     int
    scenario_name:   str
    region:          str
    probability:     float    = Field(..., ge=0.0, le=1.0)
    confidence:      float    = Field(..., ge=0.0, le=1.0)
    horizon_hours:   int      = 24       # kaç saat içinde
    status:          PredictionStatus = PredictionStatus.PENDING
    outcome:         Optional[bool]   = None
    brier_score:     Optional[float]  = None
    verified_at:     Optional[datetime] = None
    source_scan_id:  str      = ""

    def compute_brier(self) -> Optional[float]:
        """Brier skoru: (p - outcome)^2. Düşük = iyi."""
        if self.outcome is None:
            return None
        o = 1.0 if self.outcome else 0.0
        return round((self.probability - o) ** 2, 4)

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}
