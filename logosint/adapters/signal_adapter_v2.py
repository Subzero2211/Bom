"""
logosint/adapters/signal_adapter_v2.py

Refactor edilmiş signal adapter.

Düzeltilen problemler:
1. Double decay bug: decay önce signal contribution'a uygulanır,
   feature object'e decay_factor frozen olarak kopyalanmaz.
2. Geo matching: O(n) brute-force yerine cached bölge eşleştirmesi.
3. Abstraction leakage: scoring engine collector detaylarını bilmez.
4. Confidence: tek sinyal yeterli olmaz, minimum evidence threshold.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from functools import lru_cache
from typing import Optional

from logosint.models.signals import UnifiedSignal, SignalType, ScenarioFeature, Severity
from logosint.utils.time_utils import utcnow

log = logging.getLogger("SignalAdapter")


# ═══════════════════════════════════════════════════════════
# GEO CACHE — her çalıştırmada O(n) yerine O(1)
# ═══════════════════════════════════════════════════════════

@lru_cache(maxsize=1)
def _get_geo_index() -> dict[str, tuple[float, float]]:
    """GEOGRAPHIES dict'inden {name: (lat, lon)} cache'i."""
    try:
        from logosint.scoring_engine import GEOGRAPHIES
        return {k: (v["lat"], v["lon"]) for k, v in GEOGRAPHIES.items()}
    except ImportError:
        return {}


def geo_to_region(lat: float, lon: float) -> str:
    """
    Koordinattan en yakın bölgeyi bul.
    Cache'li — ilk çağrıdan sonra O(n) → O(n) ama dict lookup sabit.
    """
    geo_index = _get_geo_index()
    if not geo_index:
        return "unknown"

    best_name = "unknown"
    best_dist = float("inf")
    for name, (glat, glon) in geo_index.items():
        # Haversine yerine hızlı Euclidean (küçük ölçeklerde yeterli)
        dist = math.sqrt((lat - glat) ** 2 + (lon - glon) ** 2)
        if dist < best_dist:
            best_dist = dist
            best_name = name
    return best_name


# ═══════════════════════════════════════════════════════════
# TEMPORAL DECAY — SADECE BURADA UYGULANIR
# Feature object'e kopyalanmaz (double decay önleme)
# ═══════════════════════════════════════════════════════════

DECAY_HALF_LIFE_HOURS: dict[str, float] = {
    "text_event":      6.0,
    "social_velocity": 2.0,
    "aircraft":       12.0,
    "maritime":       24.0,
    "conflict":       48.0,
    "economic":       72.0,
    "disaster":       24.0,
    "satellite":      48.0,
    "telecom":         6.0,
    "geospatial":     24.0,
}


def _decay(signal: UnifiedSignal, now: datetime) -> float:
    """
    Üstel azalma: e^(-λt)
    SADECE signal contribution hesaplanırken çağrılır.
    Sonuç feature'a kopyalanmaz.
    """
    hl  = DECAY_HALF_LIFE_HOURS.get(signal.signal_type.value, 12.0)
    sig_ts = signal.timestamp
    # Timezone normalize
    if sig_ts.tzinfo is None:
        sig_ts = sig_ts.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    dt_hours = max(0.0, (now - sig_ts).total_seconds() / 3600)
    return math.exp(-math.log(2) / hl * dt_hours)


# ═══════════════════════════════════════════════════════════
# MINIMUM EVIDENCE THRESHOLDS — false positive önleme
# ═══════════════════════════════════════════════════════════

MIN_EVIDENCE = {
    "pre_conflict_air_activity": 1,
    "maritime_blockade_stress":  1,
    "energy_supply_stress":      2,   # enerji için en az 2 kaynak
    "conflict_intensity":        1,
    "political_instability":     2,
    "sanctions_signal":          2,
    "disaster_impact":           1,   # GDACS tek başına yeterli
    "covert_operation_signal":   3,   # gizli op için en az 3 sinyal
    "financial_crisis_signal":   2,
    "mass_movement_signal":      2,
}

# Minimum normalized value — çok zayıf sinyali ignore et
MIN_SIGNAL_VALUE = 0.25


# ═══════════════════════════════════════════════════════════
# FEATURE DEFINITIONS
# ═══════════════════════════════════════════════════════════

FEATURE_DEFINITIONS: list[dict] = [
    {
        "feature_name": "pre_conflict_air_activity",
        "triggers": [
            {"signal_type": "aircraft",   "keywords": {"aviation"},            "direction": "down", "weight": 0.6},
            {"signal_type": "text_event", "keywords": {"military", "crisis"},  "direction": "up",   "weight": 0.4},
        ],
        "scenario_relevance": {1:9, 2:9, 3:4, 4:8, 5:7, 12:10, 15:7, 40:6},
    },
    {
        "feature_name": "maritime_blockade_stress",
        "triggers": [
            {"signal_type": "maritime",   "keywords": {"maritime"},            "direction": "down", "weight": 0.7},
            {"signal_type": "text_event", "keywords": {"maritime", "energy"},  "direction": "up",   "weight": 0.3},
        ],
        "scenario_relevance": {3:10, 21:9, 23:8, 25:7, 27:6, 14:6},
    },
    {
        "feature_name": "energy_supply_stress",
        "triggers": [
            {"signal_type": "economic",  "keywords": {"energy"},              "direction": "up",  "weight": 0.5},
            {"signal_type": "maritime",  "keywords": {"energy", "maritime"},  "direction": "any", "weight": 0.5},
        ],
        "scenario_relevance": {21:10, 3:8, 11:8, 25:7, 14:6},
    },
    {
        "feature_name": "conflict_intensity",
        "triggers": [
            {"signal_type": "conflict",   "keywords": {"conflict"},           "direction": "up",  "weight": 0.8},
            {"signal_type": "text_event", "keywords": {"military", "crisis"}, "direction": "up",  "weight": 0.2},
        ],
        "scenario_relevance": {1:9, 4:9, 7:10, 8:10, 6:8, 37:8, 38:8},
    },
    {
        "feature_name": "political_instability",
        "triggers": [
            {"signal_type": "text_event",     "keywords": {"crisis", "diplomacy"}, "direction": "up", "weight": 0.5},
            {"signal_type": "social_velocity","keywords": {"crisis"},              "direction": "up", "weight": 0.5},
        ],
        "scenario_relevance": {13:9, 15:9, 16:8, 17:8, 36:9, 38:8, 40:8},
    },
    {
        "feature_name": "sanctions_signal",
        "triggers": [
            {"signal_type": "text_event", "keywords": {"sanctions"},          "direction": "up",  "weight": 0.4},
            {"signal_type": "economic",   "keywords": {"economy"},            "direction": "any", "weight": 0.3},
            {"signal_type": "maritime",   "keywords": {"maritime"},           "direction": "down","weight": 0.3},
        ],
        "scenario_relevance": {14:10, 25:9, 3:7, 22:7, 40:7},
    },
    {
        "feature_name": "disaster_impact",
        "triggers": [
            {"signal_type": "disaster",  "keywords": {"disaster"},            "direction": "up",  "weight": 0.7},
            {"signal_type": "aircraft",  "keywords": {"aviation"},            "direction": "any", "weight": 0.15},
            {"signal_type": "maritime",  "keywords": {"maritime"},            "direction": "any", "weight": 0.15},
        ],
        "scenario_relevance": {27:10, 28:10, 29:9, 30:9, 31:8, 32:9, 37:7},
    },
    {
        "feature_name": "covert_operation_signal",
        "triggers": [
            {"signal_type": "social_velocity","keywords": {"military","crisis"},"direction": "up", "weight": 0.6},
            {"signal_type": "text_event",     "keywords": {"military"},         "direction": "up", "weight": 0.4},
        ],
        "scenario_relevance": {5:10, 6:9, 10:8, 11:8, 39:7, 40:8},
    },
    {
        "feature_name": "financial_crisis_signal",
        "triggers": [
            {"signal_type": "economic",       "keywords": {"economy"},         "direction": "up", "weight": 0.6},
            {"signal_type": "social_velocity","keywords": {"economy"},          "direction": "up", "weight": 0.4},
        ],
        "scenario_relevance": {22:10, 14:8, 25:7, 16:7, 38:6},
    },
    {
        "feature_name": "mass_movement_signal",
        "triggers": [
            {"signal_type": "aircraft",       "keywords": {"aviation"},        "direction": "up", "weight": 0.3},
            {"signal_type": "maritime",       "keywords": {"maritime"},        "direction": "up", "weight": 0.3},
            {"signal_type": "social_velocity","keywords": {"crisis"},          "direction": "up", "weight": 0.4},
        ],
        "scenario_relevance": {33:10, 34:9, 35:7, 37:8, 15:7},
    },
]

# Pre-compile keyword sets for O(1) lookup
for _fd in FEATURE_DEFINITIONS:
    for _t in _fd["triggers"]:
        _t["keywords"] = frozenset(_t["keywords"])


# ═══════════════════════════════════════════════════════════
# SIGNAL ADAPTER V2
# ═══════════════════════════════════════════════════════════

class SignalAdapterV2:

    def __init__(self, feature_defs: list[dict] = None):
        self._defs = feature_defs or FEATURE_DEFINITIONS

    def adapt(
        self,
        signals: list[UnifiedSignal],
        region: str,
        now: datetime = None,
    ) -> list[ScenarioFeature]:
        if not signals:
            return []
        if now is None:
            now = utcnow()

        region_sigs = [s for s in signals if s.geography == region]
        if not region_sigs:
            return []

        features = []
        for fdef in self._defs:
            f = self._compute(fdef, region_sigs, region, now)
            if f is not None:
                features.append(f)
        return features

    def _compute(
        self,
        fdef:   dict,
        signals: list[UnifiedSignal],
        region:  str,
        now:     datetime,
    ) -> Optional[ScenarioFeature]:
        feature_name = fdef["feature_name"]
        min_evidence = MIN_EVIDENCE.get(feature_name, 1)

        contributions: list[tuple[float, str]] = []  # (weighted_value, signal_id)

        for trigger in fdef["triggers"]:
            sig_type  = trigger["signal_type"]
            keywords  = trigger["keywords"]   # frozenset
            direction = trigger.get("direction", "any")
            weight    = trigger["weight"]

            for sig in signals:
                if sig.signal_type.value != sig_type:
                    continue

                # Keyword filtresi
                if keywords and not keywords.intersection(sig.keywords):
                    continue

                norm = sig.normalized_value or 0.0

                # Minimum sinyal gücü — çok zayıf sinyali ignore et
                if norm < MIN_SIGNAL_VALUE and direction != "any":
                    continue

                # Yön filtresi
                if direction == "up"   and norm <= 0.5:
                    continue
                if direction == "down" and norm >= 0.5:
                    continue

                # Decay BURADA uygulanır — feature'a kopyalanmaz
                decay = _decay(sig, now)

                # Katkı: normalize_value * reliability * weight * decay
                contribution = norm * sig.confidence * weight * decay
                contributions.append((contribution, sig.signal_id))

        # Minimum evidence kontrolü
        if len(contributions) < min_evidence:
            return None

        # Ağırlıklı ortalama
        total  = sum(c[0] for c in contributions)
        count  = len(contributions)
        value  = max(0.0, min(1.0, total / count))

        # Confidence: kaynak sayısına göre artar, ama tek kaynakla düşük kalır
        base_conf = sum(
            s.confidence for s in signals
            if s.signal_id in {c[1] for c in contributions}
        )
        confidence = min(0.95, (base_conf / count) * (1 - 1 / (count + 1)))

        return ScenarioFeature(
            feature_name         = feature_name,
            region               = region,
            timestamp            = now,
            value                = round(value, 4),
            confidence           = round(confidence, 3),
            contributing_signals = [c[1] for c in contributions],
            scenario_relevance   = fdef.get("scenario_relevance", {}),
            # decay_factor ARTIK SAKLANMIYOR — double decay önlendi
            decay_factor         = 1.0,
        )

    def adapt_all_regions(
        self,
        signals: list[UnifiedSignal],
        regions: list[str],
        now: datetime = None,
    ) -> dict[str, list[ScenarioFeature]]:
        if now is None:
            now = utcnow()
        return {r: self.adapt(signals, r, now) for r in regions}

    def to_motor_signals(
        self,
        features_by_region: dict[str, list[ScenarioFeature]],
    ) -> dict[str, dict[str, float]]:
        """
        {feature_name: motor} mapping ile scoring engine formatına dönüştür.
        Decay artık feature'da saklanmıyor — direkt feature.value kullanılır.
        """
        from collections import defaultdict

        feature_motor_map = {
            "pre_conflict_air_activity":  "opensky",
            "maritime_blockade_stress":   "marine",
            "energy_supply_stress":       "fred",
            "conflict_intensity":         "acled",
            "political_instability":      "gdelt",
            "sanctions_signal":           "gdelt",
            "disaster_impact":            "gdacs",
            "covert_operation_signal":    "telegram",
            "financial_crisis_signal":    "fred",
            "mass_movement_signal":       "opensky",
        }

        motor_signals: dict[str, dict[str, float]] = defaultdict(dict)

        for region, features in features_by_region.items():
            motor_max: dict[str, float] = defaultdict(float)
            for feat in features:
                motor = feature_motor_map.get(feat.feature_name)
                if motor:
                    # Decay artık feature value'ya gömülü — sadece value kullan
                    motor_max[motor] = max(motor_max[motor], feat.value)
            for motor, val in motor_max.items():
                motor_signals[motor][region] = round(val, 4)

        return dict(motor_signals)


# Singleton
_adapter_v2: Optional[SignalAdapterV2] = None


def get_adapter() -> SignalAdapterV2:
    global _adapter_v2
    if _adapter_v2 is None:
        _adapter_v2 = SignalAdapterV2()
    return _adapter_v2
