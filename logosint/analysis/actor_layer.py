"""
logosint/analysis/actor_layer.py

Aktör katmanı — L1 eşiği (30 puan) geçince aktive olur.

OpenSky'da: tescil ülkesi bazlı uçuş ayrımı
Marine'de: bayrak ülkesi + şirket menşei bazlı gemi ayrımı

Örnek:
- UAE tescilli uçaklar bölgede kalıyor → "yerel aktör güvenli görüyor"
- Alman tescilli uçaklar kaçıyor → "dış aktör kaçıyor"
- İranlı bayraklı gemiler limanda bekliyor → "İran hareketi kısıtlıyor"
- Norveç tankerleri rota değiştirdi → "Batılı operatörler risk görüyor"
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger("ActorLayer")


# ═══════════════════════════════════════════════════════════
# ÜLKE GRUPLARI — jeopolitik aktör sınıflandırması
# ═══════════════════════════════════════════════════════════

ACTOR_GROUPS = {
    "local_gulf": {"AE", "SA", "QA", "KW", "BH", "OM"},
    "iran":       {"IR"},
    "western":    {"US", "GB", "DE", "FR", "NL", "NO", "DK", "SE", "IT", "ES"},
    "nato":       {"US", "GB", "DE", "FR", "TR", "NL", "NO", "DK", "BE", "PL"},
    "russia":     {"RU"},
    "china":      {"CN"},
    "india":      {"IN"},
    "israel":     {"IL"},
    "neutral":    {"CH", "SG", "AE"},   # AE hem local hem neutral sayılır
}

# Operatör yorumlama rehberi
# "bölge sahibi kalıyor ama yabancı çıkıyorsa → lokal güven var, dış risk var"
def interpret_departure_pattern(
    local_staying:   bool,
    western_leaving: bool,
    iran_moving:     bool,
) -> str:
    if local_staying and western_leaving:
        return "local_confidence_western_risk"
    if not local_staying and western_leaving:
        return "broad_evacuation"
    if iran_moving and western_leaving:
        return "iran_activity_western_caution"
    if local_staying and not western_leaving:
        return "normal_operations"
    return "mixed_signals"


# ═══════════════════════════════════════════════════════════
# UÇUŞ AKTÖRLERİ
# ═══════════════════════════════════════════════════════════

@dataclass
class FlightActorSummary:
    region:            str
    total_flights:     int
    by_group:          dict[str, int] = field(default_factory=dict)
    by_country:        dict[str, int] = field(default_factory=dict)
    local_staying:     bool = False
    western_leaving:   bool = False
    interpretation:    str  = ""
    signal_value:      float = 0.5   # normalize 0-1


def analyze_flight_actors(
    flights: list[dict],
    region:  str,
    baseline_by_group: dict[str, int] = None,
) -> FlightActorSummary:
    """
    Uçuş listesini aktör gruplarına göre analiz et.

    flights: [{"registration_country": "AE", "callsign": "EK123", ...}]
    """
    by_group:   dict[str, int] = defaultdict(int)
    by_country: dict[str, int] = defaultdict(int)

    for f in flights:
        cc = (f.get("registration_country") or f.get("origin_country") or "").upper()
        if not cc:
            continue
        by_country[cc] += 1
        for group, countries in ACTOR_GROUPS.items():
            if cc in countries:
                by_group[group] += 1

    # Local gulf kalıyor mu?
    baseline = baseline_by_group or {}
    local_baseline  = baseline.get("local_gulf", 1)
    local_current   = by_group.get("local_gulf", 0)
    western_baseline= baseline.get("western", 1)
    western_current = by_group.get("western", 0)
    iran_current    = by_group.get("iran", 0)

    local_staying   = local_current >= local_baseline * 0.7
    western_leaving = western_current < western_baseline * 0.5

    interpretation = interpret_departure_pattern(
        local_staying, western_leaving, iran_current > 0
    )

    # Signal value: western çıkıyorsa yüksek, local kalıyorsa orta
    if western_leaving and not local_staying:
        signal_value = 0.85
    elif western_leaving and local_staying:
        signal_value = 0.55
    else:
        signal_value = 0.25

    return FlightActorSummary(
        region          = region,
        total_flights   = len(flights),
        by_group        = dict(by_group),
        by_country      = dict(by_country),
        local_staying   = local_staying,
        western_leaving = western_leaving,
        interpretation  = interpretation,
        signal_value    = signal_value,
    )


# ═══════════════════════════════════════════════════════════
# GEMİ AKTÖRLERİ
# ═══════════════════════════════════════════════════════════

@dataclass
class VesselActorSummary:
    region:           str
    total_vessels:    int
    by_flag:          dict[str, int] = field(default_factory=dict)
    by_type:          dict[str, int] = field(default_factory=dict)
    iran_vessels:     int = 0
    western_tankers:  int = 0
    dark_ships:       int = 0   # AIS kapalı
    interpretation:   str = ""
    signal_value:     float = 0.5
    actor_note:       str = ""


def analyze_vessel_actors(
    vessels: list[dict],
    region:  str,
) -> VesselActorSummary:
    """
    Gemi listesini bayrak + tip bazında analiz et.

    vessels: [{
        "flag": "IR",
        "vessel_type": "tanker",
        "ais_active": True,
        "last_port": "IRBND",
        "destination": "AEJEA",
        "mmsi": "...",
    }]
    """
    by_flag: dict[str, int] = defaultdict(int)
    by_type: dict[str, int] = defaultdict(int)
    iran_vessels    = 0
    western_tankers = 0
    dark_ships      = 0

    for v in vessels:
        flag = (v.get("flag") or v.get("country_code") or "").upper()
        vtype= (v.get("vessel_type") or "").lower()

        by_flag[flag] += 1
        by_type[vtype] += 1

        if flag == "IR":
            iran_vessels += 1

        if flag in ACTOR_GROUPS["western"] and "tanker" in vtype:
            western_tankers += 1

        if not v.get("ais_active", True):
            dark_ships += 1

    # Yorum
    notes = []
    if iran_vessels > 0:
        notes.append(f"İran bayrağı {iran_vessels} gemi")
    if dark_ships > 2:
        notes.append(f"{dark_ships} gemi AIS kapalı (potansiyel gizli hareket)")
    if western_tankers == 0 and by_type.get("tanker", 0) > 0:
        notes.append("Batılı tanker yok — Batılı operatörler çekilmiş")

    # Signal value
    if dark_ships > 3 or (iran_vessels > 5 and western_tankers == 0):
        signal_value = 0.80
    elif iran_vessels > 2 or dark_ships > 0:
        signal_value = 0.55
    else:
        signal_value = 0.25

    interp = "normal"
    if dark_ships > 2 and iran_vessels > 2:
        interp = "iran_covert_activity"
    elif western_tankers == 0:
        interp = "western_withdrawal"
    elif iran_vessels > 5:
        interp = "iran_concentration"

    return VesselActorSummary(
        region          = region,
        total_vessels   = len(vessels),
        by_flag         = dict(by_flag),
        by_type         = dict(by_type),
        iran_vessels    = iran_vessels,
        western_tankers = western_tankers,
        dark_ships      = dark_ships,
        interpretation  = interp,
        signal_value    = signal_value,
        actor_note      = " | ".join(notes),
    )


# ═══════════════════════════════════════════════════════════
# CASCADE ORIGIN DETECTION
# ═══════════════════════════════════════════════════════════

def detect_cascade_origin(
    region_score_history: dict[str, list[tuple]],
    threshold:            float = 40.0,
    min_lag_hours:        float = 0.5,
    max_lag_hours:        float = 12.0,
) -> dict:
    """
    Zaman sıralamasına göre anomalinin kaynaklandığı bölgeyi tespit et.

    region_score_history: {region: [(timestamp, score), ...]}

    Returns:
      {
        "origin":      "hurmuz",
        "propagated":  ["korfez", "hint_okyanusu"],
        "confidence":  0.72,
        "lag_hours":   {"korfez": 1.8, "hint_okyanusu": 4.2},
        "explanation": "..."
      }
    """
    from datetime import timezone

    # Her bölge için threshold'u ilk geçtiği zamanı bul
    first_spike: dict[str, float] = {}   # region → Unix timestamp

    for region, history in region_score_history.items():
        sorted_h = sorted(history, key=lambda x: x[0])
        for ts, score in sorted_h:
            if score >= threshold:
                if hasattr(ts, "timestamp"):
                    first_spike[region] = ts.timestamp()
                else:
                    first_spike[region] = float(ts)
                break

    if len(first_spike) < 2:
        return {
            "origin":     None,
            "propagated": [],
            "confidence": 0.0,
            "explanation": "Yeterli bölge spike'ı yok",
        }

    # En erken spike → kaynak
    origin = min(first_spike, key=first_spike.get)
    origin_time = first_spike[origin]

    propagated = []
    lag_hours  = {}

    for region, spike_time in first_spike.items():
        if region == origin:
            continue
        lag = (spike_time - origin_time) / 3600
        if min_lag_hours <= lag <= max_lag_hours:
            propagated.append(region)
            lag_hours[region] = round(lag, 2)

    # Güven: yayılma sayısı + lag tutarlılığı
    confidence = min(0.95, 0.4 + len(propagated) * 0.15)

    explanation = (
        f"{origin} bölgesi en erken spike yaptı. "
        + (f"{', '.join(propagated)} bölgelerine {min(lag_hours.values() or [0]):.1f}-"
           f"{max(lag_hours.values() or [0]):.1f} saat içinde yayıldı."
           if propagated else "Yayılma henüz tespit edilmedi.")
    )

    return {
        "origin":      origin,
        "propagated":  propagated,
        "confidence":  round(confidence, 2),
        "lag_hours":   lag_hours,
        "explanation": explanation,
    }
