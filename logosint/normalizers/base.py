"""
logosint/normalizers/base.py

BaseNormalizer arayüzü ve kaynak-spesifik normalizer'lar.
Her normalizer collector ham çıktısını → UnifiedSignal'e dönüştürür.
"""

from __future__ import annotations
import logging
import math
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Optional

from logosint.models.signals import (
    UnifiedSignal, SignalType, Severity, Coordinates, SourceReliability
)

log = logging.getLogger("Normalizer")


# ═══════════════════════════════════════════════════════════
# YARDIMCI
# ═══════════════════════════════════════════════════════════

def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _severity_from_zscore(z: Optional[float]) -> Severity:
    if z is None:
        return Severity.LOW
    az = abs(z)
    if az >= 3.5: return Severity.CRITICAL
    if az >= 2.5: return Severity.HIGH
    if az >= 1.5: return Severity.MEDIUM
    return Severity.LOW


def _normalize_minmax(value: float, mn: float, mx: float) -> float:
    if mx == mn:
        return 0.5
    return max(0.0, min(1.0, (value - mn) / (mx - mn)))


def _geo_to_region(lat: float, lon: float) -> str:
    """
    Koordinattan GEOGRAPHIES key'ini döndür.
    nodes.py'deki bounding box'larla eşleştir.
    """
    from logosint.scoring_engine import GEOGRAPHIES
    best = "unknown"
    best_area = float("inf")
    for name, info in GEOGRAPHIES.items():
        # basit proximity — lat/lon mesafesi
        dlat = abs(lat - info["lat"])
        dlon = abs(lon - info["lon"])
        dist = math.sqrt(dlat**2 + dlon**2)
        if dist < best_area:
            best_area = dist
            best = name
    return best


# ═══════════════════════════════════════════════════════════
# BASE
# ═══════════════════════════════════════════════════════════

class BaseNormalizer(ABC):
    source: str = "unknown"
    signal_type: SignalType = SignalType.TEXT_EVENT
    reliability: float = 0.5

    @abstractmethod
    def normalize(self, raw: dict[str, Any]) -> list[UnifiedSignal]:
        """Ham collector çıktısını UnifiedSignal listesine dönüştür."""
        raise NotImplementedError

    def _base_signal(self, geography: str, timestamp: datetime) -> UnifiedSignal:
        return UnifiedSignal(
            timestamp=timestamp,
            source=self.source,
            signal_type=self.signal_type,
            geography=geography,
            confidence=self.reliability,
        )

    def safe_normalize(self, raw: dict[str, Any]) -> list[UnifiedSignal]:
        try:
            return self.normalize(raw)
        except Exception as e:
            log.error("[%s] normalize hatası: %s", self.source, e)
            return []


# ═══════════════════════════════════════════════════════════
# OPENSKY NORMALIZER
# ═══════════════════════════════════════════════════════════

class OpenSkyNormalizer(BaseNormalizer):
    source      = "opensky"
    signal_type = SignalType.AIRCRAFT
    reliability = SourceReliability.OPENSKY

    # Havalimanı başına tarihsel baseline (başlangıç — sistem öğrendikçe güncellenir)
    _baselines: dict[str, float] = {}

    def normalize(self, raw: dict[str, Any]) -> list[UnifiedSignal]:
        """
        raw = {
            "icao": "LTFM",
            "name": "İstanbul",
            "lat": 41.27, "lon": 28.74,
            "region": "istanbul_canakkale",
            "current": 245,
            "baseline": 420,
            "delta_pct": -41.7,
            "zscore": -2.8,
        }
        """
        signals = []
        icao    = raw.get("icao", "")
        region  = raw.get("region") or _geo_to_region(raw.get("lat", 0), raw.get("lon", 0))
        current = float(raw.get("current", 0))
        baseline= float(raw.get("baseline", current or 1))
        delta   = raw.get("delta_pct", 0.0)
        zscore  = raw.get("zscore")
        ts      = raw.get("timestamp") or _now()
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)

        normalized = _normalize_minmax(current, 0, baseline * 2) if baseline > 0 else 0.5

        sig = UnifiedSignal(
            timestamp        = ts,
            source           = self.source,
            signal_type      = self.signal_type,
            geography        = region,
            coordinates      = Coordinates(lat=raw["lat"], lon=raw["lon"]) if raw.get("lat") else None,
            confidence       = self.reliability,
            severity         = _severity_from_zscore(zscore),
            value            = current,
            normalized_value = normalized,
            keywords         = ["aviation"],
            metadata         = {
                "icao": icao, "baseline": baseline,
                "delta_pct": delta, "zscore": zscore,
            },
        )
        signals.append(sig)
        return signals


# ═══════════════════════════════════════════════════════════
# MARINE NORMALIZER
# ═══════════════════════════════════════════════════════════

class MarineNormalizer(BaseNormalizer):
    source      = "marine"
    signal_type = SignalType.MARITIME
    reliability = SourceReliability.MARINE

    def normalize(self, raw: dict[str, Any]) -> list[UnifiedSignal]:
        """
        raw = {
            "locode": "AEJEA",
            "name": "Jebel Ali",
            "lat": 24.97, "lon": 55.06,
            "region": "korfez",
            "current": 85,
            "baseline": 220,
            "delta_pct": -61.4,
            "zscore": -3.2,
            "vessel_type": "cargo",
            "flag_country": "AE",
        }
        """
        region  = raw.get("region") or _geo_to_region(raw.get("lat", 0), raw.get("lon", 0))
        current = float(raw.get("current", 0))
        baseline= float(raw.get("baseline", current or 1))
        zscore  = raw.get("zscore")
        ts      = raw.get("timestamp") or _now()
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)

        normalized = _normalize_minmax(current, 0, baseline * 2) if baseline > 0 else 0.5

        keywords = ["maritime"]
        if raw.get("vessel_type") in ("tanker",):
            keywords.append("energy")

        return [UnifiedSignal(
            timestamp        = ts,
            source           = self.source,
            signal_type      = self.signal_type,
            geography        = region,
            coordinates      = Coordinates(lat=raw["lat"], lon=raw["lon"]) if raw.get("lat") else None,
            confidence       = self.reliability,
            severity         = _severity_from_zscore(zscore),
            value            = current,
            normalized_value = normalized,
            keywords         = keywords,
            metadata         = {
                "locode": raw.get("locode"),
                "baseline": baseline,
                "delta_pct": raw.get("delta_pct"),
                "zscore": zscore,
                "vessel_type": raw.get("vessel_type"),
                "flag_country": raw.get("flag_country"),
            },
        )]


# ═══════════════════════════════════════════════════════════
# GDELT NORMALIZER
# ═══════════════════════════════════════════════════════════

class GDELTNormalizer(BaseNormalizer):
    source      = "gdelt"
    signal_type = SignalType.TEXT_EVENT
    reliability = SourceReliability.GDELT

    def normalize(self, raw: dict[str, Any]) -> list[UnifiedSignal]:
        """
        raw = GDELT makale veya event dict'i.
        """
        ts = raw.get("seendate") or raw.get("timestamp") or _now()
        if isinstance(ts, str):
            try:
                ts = datetime.strptime(ts[:14], "%Y%m%dT%H%M%S")
            except Exception:
                try:
                    ts = datetime.fromisoformat(ts)
                except Exception:
                    ts = _now()

        lat = raw.get("geolat") or raw.get("lat")
        lon = raw.get("geolong") or raw.get("lon")
        region = raw.get("region", "unknown")
        if lat and lon and region == "unknown":
            region = _geo_to_region(float(lat), float(lon))

        goldstein = float(raw.get("goldstein", 0) or 0)
        # Goldstein -10..+10 → normalize 0..1 (negatif = tehlikeli = yüksek sinyal)
        normalized = _normalize_minmax(-goldstein, -10, 10)

        severity = Severity.LOW
        if goldstein <= -7: severity = Severity.CRITICAL
        elif goldstein <= -4: severity = Severity.HIGH
        elif goldstein <= -1: severity = Severity.MEDIUM

        return [UnifiedSignal(
            timestamp        = ts,
            source           = self.source,
            signal_type      = self.signal_type,
            geography        = region,
            coordinates      = Coordinates(lat=float(lat), lon=float(lon)) if lat and lon else None,
            confidence       = self.reliability,
            severity         = severity,
            value            = goldstein,
            normalized_value = normalized,
            keywords         = raw.get("keywords_matched", []),
            entities         = raw.get("entities", []),
            metadata         = {
                "title": raw.get("title", "")[:200],
                "url": raw.get("url", ""),
                "goldstein": goldstein,
                "sourcecountry": raw.get("sourcecountry", ""),
            },
        )]


# ═══════════════════════════════════════════════════════════
# ACLED NORMALIZER
# ═══════════════════════════════════════════════════════════

class ACLEDNormalizer(BaseNormalizer):
    source      = "acled"
    signal_type = SignalType.CONFLICT
    reliability = SourceReliability.ACLED

    _severity_map = {
        "Battles":                     Severity.CRITICAL,
        "Explosions/Remote violence":  Severity.CRITICAL,
        "Violence against civilians":  Severity.HIGH,
        "Protests":                    Severity.MEDIUM,
        "Riots":                       Severity.MEDIUM,
        "Strategic developments":      Severity.LOW,
    }

    def normalize(self, raw: dict[str, Any]) -> list[UnifiedSignal]:
        ts = raw.get("event_date") or _now()
        if isinstance(ts, str):
            try:
                ts = datetime.strptime(ts, "%Y-%m-%d")
            except Exception:
                ts = _now()

        lat = float(raw.get("latitude", 0) or 0)
        lon = float(raw.get("longitude", 0) or 0)
        region = _geo_to_region(lat, lon) if lat and lon else "unknown"

        fatalities = int(raw.get("fatalities", 0) or 0)
        event_type = raw.get("event_type", "")
        severity = self._severity_map.get(event_type, Severity.LOW)
        if fatalities >= 100:
            severity = Severity.CRITICAL
        elif fatalities >= 20 and severity == Severity.LOW:
            severity = Severity.MEDIUM

        # Normalize: fatality count → 0-1 (log scale)
        normalized = min(1.0, math.log1p(fatalities) / math.log1p(500))

        return [UnifiedSignal(
            timestamp        = ts,
            source           = self.source,
            signal_type      = self.signal_type,
            geography        = region,
            coordinates      = Coordinates(lat=lat, lon=lon) if lat and lon else None,
            confidence       = self.reliability,
            severity         = severity,
            value            = float(fatalities),
            normalized_value = normalized,
            keywords         = ["conflict", "military"] if "Battle" in event_type else ["conflict"],
            entities         = [raw.get("country", "")],
            metadata         = {
                "event_type": event_type,
                "fatalities": fatalities,
                "location": raw.get("location", ""),
                "country": raw.get("country", ""),
                "actor1": raw.get("actor1", ""),
                "actor2": raw.get("actor2", ""),
            },
        )]


# ═══════════════════════════════════════════════════════════
# FRED NORMALIZER
# ═══════════════════════════════════════════════════════════

class FREDNormalizer(BaseNormalizer):
    source      = "fred"
    signal_type = SignalType.ECONOMIC
    reliability = SourceReliability.FRED

    # Seri bazlı yön — artış tehlikeli mi değil mi
    _danger_direction = {
        "DCOILWTICO":       "up",    # petrol artarsa tehlike
        "DCOILBRENTEU":     "up",
        "BAMLH0A0HYM2":     "up",    # spread artarsa tehlike
        "DEXTRUS":          "up",    # USD/TRY artarsa tehlike
        "GOLDAMGBD228NLBM": "up",    # altın artarsa tehlike (güvenli liman)
        "T10Y2Y":           "down",  # eğri tersine dönerse tehlike
        "DEXUSEU":          "down",  # EUR/USD düşerse tehlike
    }

    def normalize(self, raw: dict[str, Any]) -> list[UnifiedSignal]:
        series_id = raw.get("series_id", "")
        value     = float(raw.get("value", 0) or 0)
        zscore    = raw.get("zscore")
        ts        = raw.get("timestamp") or _now()
        if isinstance(ts, str):
            try:
                ts = datetime.strptime(ts, "%Y-%m-%d")
            except Exception:
                ts = _now()

        direction = self._danger_direction.get(series_id, "up")
        if direction == "up":
            normalized = _normalize_minmax(value, raw.get("hist_min", 0), raw.get("hist_max", value * 2))
        else:
            raw_norm = _normalize_minmax(value, raw.get("hist_min", 0), raw.get("hist_max", value * 2))
            normalized = 1.0 - raw_norm

        severity = _severity_from_zscore(zscore)

        return [UnifiedSignal(
            timestamp        = ts,
            source           = self.source,
            signal_type      = self.signal_type,
            geography        = "global",
            confidence       = self.reliability,
            severity         = severity,
            value            = value,
            normalized_value = normalized,
            keywords         = ["economy", raw.get("keyword_group", "")],
            metadata         = {
                "series_id": series_id,
                "description": raw.get("desc", ""),
                "zscore": zscore,
            },
        )]


# ═══════════════════════════════════════════════════════════
# GDACS NORMALIZER
# ═══════════════════════════════════════════════════════════

class GDACSNormalizer(BaseNormalizer):
    source      = "gdacs"
    signal_type = SignalType.DISASTER
    reliability = SourceReliability.GDACS

    _alert_severity = {
        "Red":    Severity.CRITICAL,
        "Orange": Severity.HIGH,
        "Green":  Severity.MEDIUM,
    }
    _alert_normalized = {"Red": 0.9, "Orange": 0.6, "Green": 0.3}

    def normalize(self, raw: dict[str, Any]) -> list[UnifiedSignal]:
        lat = float(raw.get("lat", 0) or 0)
        lon = float(raw.get("lon", 0) or 0)
        region = _geo_to_region(lat, lon) if lat and lon else "unknown"
        alert_level = raw.get("alert_level", "Green")
        ts = raw.get("timestamp") or _now()
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)

        return [UnifiedSignal(
            timestamp        = ts,
            source           = self.source,
            signal_type      = self.signal_type,
            geography        = region,
            coordinates      = Coordinates(lat=lat, lon=lon) if lat and lon else None,
            confidence       = self.reliability,
            severity         = self._alert_severity.get(alert_level, Severity.LOW),
            value            = self._alert_normalized.get(alert_level, 0.3),
            normalized_value = self._alert_normalized.get(alert_level, 0.3),
            keywords         = ["disaster"],
            entities         = [raw.get("country", "")],
            metadata         = {
                "alert_level": alert_level,
                "event_type": raw.get("event_type", ""),
                "country": raw.get("country", ""),
            },
        )]


# ═══════════════════════════════════════════════════════════
# TELEGRAM / REDDIT NORMALIZER
# ═══════════════════════════════════════════════════════════

class SocialNormalizer(BaseNormalizer):
    """Telegram ve Reddit için ortak normalizer."""
    signal_type = SignalType.SOCIAL_VELOCITY
    reliability = SourceReliability.TELEGRAM

    def __init__(self, source: str = "telegram"):
        self.source = source
        self.reliability = (
            SourceReliability.TELEGRAM if source == "telegram"
            else SourceReliability.REDDIT
        )

    def normalize(self, raw: dict[str, Any]) -> list[UnifiedSignal]:
        ts = raw.get("timestamp") or _now()
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)

        keywords = raw.get("keywords_matched", [])
        entities = raw.get("entities", [])
        geography = raw.get("geography", "unknown")

        # Viral velocity: views/forwards → normalized
        views    = float(raw.get("views", 0) or 0)
        forwards = float(raw.get("forwards", 0) or 0)
        score    = raw.get("score", 0) or 0   # reddit score
        velocity = views * 0.001 + forwards * 0.01 + score * 0.0001
        normalized = min(1.0, velocity / 100.0)

        severity = Severity.LOW
        if normalized > 0.7: severity = Severity.HIGH
        elif normalized > 0.4: severity = Severity.MEDIUM

        return [UnifiedSignal(
            timestamp        = ts,
            source           = self.source,
            signal_type      = self.signal_type,
            geography        = geography,
            confidence       = self.reliability,
            severity         = severity,
            value            = velocity,
            normalized_value = normalized,
            keywords         = keywords,
            entities         = entities,
            metadata         = raw.get("metadata", {}),
        )]


# ═══════════════════════════════════════════════════════════
# NORMALIZER REGISTRY
# ═══════════════════════════════════════════════════════════

NORMALIZER_REGISTRY: dict[str, BaseNormalizer] = {
    "opensky":  OpenSkyNormalizer(),
    "marine":   MarineNormalizer(),
    "gdelt":    GDELTNormalizer(),
    "acled":    ACLEDNormalizer(),
    "fred":     FREDNormalizer(),
    "gdacs":    GDACSNormalizer(),
    "telegram": SocialNormalizer("telegram"),
    "reddit":   SocialNormalizer("reddit"),
}


def get_normalizer(source: str) -> Optional[BaseNormalizer]:
    return NORMALIZER_REGISTRY.get(source)
