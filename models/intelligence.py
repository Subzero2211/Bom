"""
models/intelligence.py

İstihbarat sentez modelleri — CorrelationCluster, IntelligenceReport.
Anomali analizinin çıktısı.
"""

from dataclasses import dataclass, asdict, field
from typing import Optional, List
from datetime import datetime
from enum import Enum
from models.event import Severity, GeoPoint


@dataclass
class CorrelationCluster:
    """Korelasyon kümesi — birden fazla anomali arasındaki ilişki."""
    cluster_id: str                      # "CLU-a1b2c3d4" vb.
    severity: Severity
    event_ids: List[str]                 # Kümeye dahil olan event ID'leri
    domains_involved: List[str]          # ["air", "sea", "news"]
    regions_involved: List[str]          # ["levant", "korfez"]
    keywords_common: List[str]           # Ortak anahtar kelimeler
    centroid: Optional[GeoPoint] = None  # Kümeler coğrafi merkezi
    first_seen: datetime = field(default_factory=datetime.utcnow)
    last_seen: datetime = field(default_factory=datetime.utcnow)
    correlation_type: str = "parallel"   # "parallel" | "divergent" | "cascade"
    summary: str = ""                    # İnsan okunabilir özet
    confidence: float = 0.5              # 0.0-1.0 güvenilirlik

    def to_dict(self):
        d = asdict(self)
        d['severity'] = self.severity.value
        if self.centroid:
            d['centroid'] = self.centroid.to_dict()
        d['first_seen'] = self.first_seen.isoformat()
        d['last_seen'] = self.last_seen.isoformat()
        return d

    def centroid_lat(self):
        return self.centroid.lat if self.centroid else None

    def centroid_lon(self):
        return self.centroid.lon if self.centroid else None

    def centroid_name(self):
        return self.centroid.name if self.centroid else None


@dataclass
class IntelligenceReport:
    """Nihai istihbarat raporu — sistem tarafından üretilen özet."""
    report_id: str
    generated_at: datetime
    system_status: Severity
    active_anomalies: int
    active_correlations: int
    clusters: List[CorrelationCluster] = field(default_factory=list)
    key_findings: List[str] = field(default_factory=list)
    watch_list: List[str] = field(default_factory=list)
    domain_summary: dict = field(default_factory=dict)
    region_summary: dict = field(default_factory=dict)
    source_stats: dict = field(default_factory=dict)

    def to_dict(self):
        return {
            "report_id": self.report_id,
            "generated_at": self.generated_at.isoformat(),
            "system_status": self.system_status.value,
            "active_anomalies": self.active_anomalies,
            "active_correlations": self.active_correlations,
            "clusters": [c.to_dict() for c in self.clusters],
            "key_findings": self.key_findings,
            "watch_list": self.watch_list,
            "domain_summary": self.domain_summary,
            "region_summary": self.region_summary,
            "source_stats": self.source_stats,
        }
