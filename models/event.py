"""
models/event.py

Veri modelleri — RawEvent, AnomalyEvent, Domain, Severity, GeoPoint
Tüm kütüphane tarafından kullanılan temel data structures.
"""

from enum import Enum
from dataclasses import dataclass, asdict, field
from typing import Optional, List
from datetime import datetime


class Domain(Enum):
    """Veri kaynağı domain'i."""
    NEWS = "news"          # Haber (RSS, GDELT, Reddit, Telegram)
    AIR = "air"            # Hava trafiği (OpenSky)
    SEA = "sea"            # Deniz trafiği (MarineTraffic, AISHub)
    CONFLICT = "conflict"  # Çatışma (ACLED)
    DISASTER = "disaster"  # Afet (GDACS)
    ECONOMIC = "economic"  # Ekonomik (FRED)
    SOCIAL = "social"      # Sosyal medya (Reddit, Telegram)


class Severity(Enum):
    """Olay şiddeti."""
    OK = "ok"              # Normal — anomali yok
    INFO = "info"          # Bilgilendirme — baseline oluşturuluyor
    WARNING = "warning"    # Uyarı — |z| ≥ 2.0
    CRITICAL = "critical"  # Kritik — |z| ≥ 3.0


@dataclass
class GeoPoint:
    """Coğrafi konum."""
    lat: float
    lon: float
    name: Optional[str] = None
    country: Optional[str] = None
    region: Optional[str] = None

    def to_dict(self):
        return asdict(self)


@dataclass
class RawEvent:
    """Ham olay — kaynaktan olduğu gibi alınan veri."""
    source: str                          # "opensky", "rss_bbc", "reddit_worldnews" vb.
    domain: Domain                       # Hangi kategori
    event_id: str                        # Benzersiz ID
    title: str
    timestamp: datetime
    body: Optional[str] = None
    url: Optional[str] = None
    location: Optional[GeoPoint] = None
    affected_regions: List[str] = field(default_factory=list)
    keywords_matched: List[str] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)  # Ülkeler, kişiler vb.
    raw_data: dict = field(default_factory=dict)       # Source-specific extra data

    def to_dict(self):
        d = asdict(self)
        d['domain'] = self.domain.value
        d['timestamp'] = self.timestamp.isoformat()
        if self.location:
            d['location'] = self.location.to_dict()
        d['raw_data'] = self.raw_data
        return d


@dataclass
class AnomalyEvent:
    """Anomali olayı — analiz sonrası."""
    raw: RawEvent
    severity: Severity
    current_value: Optional[float] = None
    baseline_value: Optional[float] = None
    zscore: Optional[float] = None
    delta_pct: Optional[float] = None  # Yüzde değişim
    anomaly_description: str = ""
    confidence: float = 0.5
    correlated_event_ids: List[str] = field(default_factory=list)

    @property
    def event_id(self):
        return f"anom_{self.raw.source}_{self.raw.event_id}"

    @property
    def timestamp(self):
        return self.raw.timestamp

    @property
    def region(self):
        return self.raw.location.region if self.raw.location else None

    @property
    def lat(self):
        return self.raw.location.lat if self.raw.location else None

    @property
    def lon(self):
        return self.raw.location.lon if self.raw.location else None

    def to_dict(self):
        return {
            "event_id": self.event_id,
            "source": self.raw.source,
            "domain": self.raw.domain.value,
            "severity": self.severity.value,
            "current_value": self.current_value,
            "baseline_value": self.baseline_value,
            "zscore": self.zscore,
            "delta_pct": self.delta_pct,
            "anomaly_description": self.anomaly_description,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat(),
            "region": self.region,
            "lat": self.lat,
            "lon": self.lon,
            "correlated_event_ids": self.correlated_event_ids,
        }
