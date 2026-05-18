"""
logosint/models/signals.py

Unified signal ve scenario feature modelleri.
Tüm collector çıktıları UnifiedSignal'e normalize edilir.
"""

from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator
import uuid


# ═══════════════════════════════════════════════════════════
# ENUM'LAR
# ═══════════════════════════════════════════════════════════

class SignalType(str, Enum):
    TEXT_EVENT      = "text_event"
    GEOSPATIAL      = "geospatial"
    ECONOMIC        = "economic"
    AIRCRAFT        = "aircraft"
    MARITIME        = "maritime"
    CONFLICT        = "conflict"
    SOCIAL_VELOCITY = "social_velocity"
    DISASTER        = "disaster"
    SATELLITE       = "satellite"
    TELECOM         = "telecom"


class Severity(str, Enum):
    NEGLIGIBLE = "negligible"
    LOW        = "low"
    MEDIUM     = "medium"
    HIGH       = "high"
    CRITICAL   = "critical"


class SourceReliability(float, Enum):
    GDACS       = 0.95
    ACLED       = 0.90
    SENTINELHUB = 0.90
    OPENSKY     = 0.85
    MARINE      = 0.85
    FRED        = 0.90
    COMTRADE    = 0.85
    GDELT       = 0.70
    TELECOM     = 0.75
    REDDIT      = 0.45
    TELEGRAM    = 0.50
    RSS         = 0.72


# ═══════════════════════════════════════════════════════════
# KOORDİNAT
# ═══════════════════════════════════════════════════════════

class Coordinates(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)

    def __str__(self) -> str:
        return f"{self.lat:.4f},{self.lon:.4f}"


# ═══════════════════════════════════════════════════════════
# UNİFİED SİGNAL
# ═══════════════════════════════════════════════════════════

class UnifiedSignal(BaseModel):
    """
    Tüm collector çıktılarının normalize edildiği ortak şema.
    """
    signal_id:           str         = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp:           datetime
    source:              str                         # "opensky", "gdelt", "acled" vb.
    signal_type:         SignalType
    geography:           str                         # nodes.py GEOGRAPHIES key'i
    coordinates:         Optional[Coordinates] = None
    confidence:          float = Field(..., ge=0.0, le=1.0)
    severity:            Severity = Severity.LOW
    value:               Optional[float] = None      # sayısal sinyal için
    normalized_value:    Optional[float] = None      # 0-1 normalize
    keywords:            list[str] = Field(default_factory=list)
    entities:            list[str] = Field(default_factory=list)
    metadata:            dict[str, Any] = Field(default_factory=dict)
    raw_payload_ref:     Optional[str] = None        # DB'deki ham kayıt ID'si

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, v))

    @field_validator("normalized_value")
    @classmethod
    def clamp_normalized(cls, v: Optional[float]) -> Optional[float]:
        if v is not None:
            return max(0.0, min(1.0, v))
        return v

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


# ═══════════════════════════════════════════════════════════
# SCENARIO FEATURE
# ═══════════════════════════════════════════════════════════

class ScenarioFeature(BaseModel):
    """
    Signal adapter'ın ürettiği senaryo özelliği.
    Birden fazla UnifiedSignal birleşerek bir feature üretir.
    """
    feature_id:           str      = Field(default_factory=lambda: str(uuid.uuid4()))
    feature_name:         str      # "pre_conflict_air_activity", "energy_supply_stress" vb.
    region:               str
    timestamp:            datetime
    value:                float    = Field(..., ge=0.0, le=1.0)
    confidence:           float    = Field(..., ge=0.0, le=1.0)
    contributing_signals: list[str] = Field(default_factory=list)  # signal_id listesi
    scenario_relevance:   dict[int, float] = Field(default_factory=dict)  # {scenario_id: weight}
    decay_factor:         float    = 1.0   # zamansal azalma

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


# ═══════════════════════════════════════════════════════════
# FEATURE BATCH — toplu işlem için
# ═══════════════════════════════════════════════════════════

class FeatureBatch(BaseModel):
    scan_id:   str
    timestamp: datetime
    region:    str
    features:  list[ScenarioFeature] = Field(default_factory=list)

    def to_motor_signals(self) -> dict[str, float]:
        """
        scoring_engine.run_scoring_cycle() için
        {feature_name: value} formatına dönüştür.
        """
        return {f.feature_name: f.value for f in self.features}
