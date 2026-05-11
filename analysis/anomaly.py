"""
analysis/anomaly.py

İstatistiksel anomali motoru.
Sayısal kaynaklar (OpenSky, Marine) için Z-score hesaplar.
Metin kaynakları (RSS, Reddit) için frekans bazlı spike tespiti yapar.
"""

import math
import logging
from datetime import datetime
from typing import Optional
from models.event import RawEvent, AnomalyEvent, Severity, Domain
from storage.db import push_timeseries, get_timeseries
from config import ANOMALY, SOURCE_WEIGHTS

log = logging.getLogger("Anomaly")


# ═══════════════════════════════════════════════════════════════
# Z-SCORE — sayısal kaynaklar için (uçuş/gemi sayısı, ekonomik veri)
# ═══════════════════════════════════════════════════════════════

def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = mean(values)
    variance = sum((v - m) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(variance)


def zscore(value: float, history: list[float]) -> Optional[float]:
    if len(history) < ANOMALY["min_baseline"]:
        return None
    m = mean(history)
    s = std(history)
    if s == 0:
        return None
    return (value - m) / s


def severity_from_zscore(z: Optional[float]) -> Severity:
    if z is None:
        return Severity.INFO
    az = abs(z)
    if az >= ANOMALY["zscore_crit"]:
        return Severity.CRITICAL
    if az >= ANOMALY["zscore_warn"]:
        return Severity.WARNING
    return Severity.OK


def analyze_numeric(
    station_key: str,
    current_value: float,
    source: str,
    event: RawEvent,
    description_template: str = "",
) -> AnomalyEvent:
    """
    Sayısal bir ölçümü geçmiş verilerle karşılaştır.
    station_key: "opensky_LTFM", "marine_TRISA", "fred_UNRATE" vb.
    """
    # Geçmişe kaydet
    push_timeseries(station_key, current_value)

    # Geçmişi al
    history = get_timeseries(station_key, ANOMALY["history_window"])

    if len(history) <= 1:
        return AnomalyEvent(
            raw=event,
            severity=Severity.INFO,
            current_value=current_value,
            baseline_value=current_value,
            anomaly_description="Baseline oluşturuluyor",
            confidence=SOURCE_WEIGHTS.get(source, 0.5),
        )

    # Mevcut değeri hariç tut (son push'u dahil etme)
    history_without_current = history[:-1] if len(history) > 1 else history

    z = zscore(current_value, history_without_current)
    baseline = mean(history_without_current)
    delta_pct = ((current_value - baseline) / baseline * 100) if baseline else 0
    sev = severity_from_zscore(z)

    direction = "artış" if delta_pct > 0 else "düşüş"
    desc = description_template or (
        f"{abs(delta_pct):.1f}% {direction} "
        f"(baseline: {baseline:.1f}, güncel: {current_value:.1f}"
        f"{f', z={z:.2f}' if z else ''})"
    )

    return AnomalyEvent(
        raw=event,
        severity=sev,
        current_value=current_value,
        baseline_value=round(baseline, 2),
        zscore=round(z, 3) if z else None,
        delta_pct=round(delta_pct, 2),
        anomaly_description=desc,
        confidence=SOURCE_WEIGHTS.get(source, 0.5),
    )


# ═══════════════════════════════════════════════════════════════
# HABER SPIKE TESPİTİ — RSS, GDELT, Reddit için
# ═══════════════════════════════════════════════════════════════

def analyze_news_frequency(
    topic_key: str,         # "news_military_levant", "reddit_crisis_korfez" vb.
    current_count: int,     # bu periyottaki makale/post sayısı
    source: str,
    event: RawEvent,
) -> AnomalyEvent:
    """
    Belirli bir konu + bölge kombinasyonu için haber frekansı anomalisi.
    Geçmiş periyotlarla karşılaştırır.
    """
    push_timeseries(topic_key, float(current_count))
    history = get_timeseries(topic_key, ANOMALY["history_window"])

    if len(history) <= 1:
        return AnomalyEvent(
            raw=event,
            severity=Severity.INFO,
            current_value=float(current_count),
            anomaly_description="Haber baseline oluşturuluyor",
            confidence=SOURCE_WEIGHTS.get(source, 0.5),
        )

    history_prev = history[:-1]
    baseline = mean(history_prev)
    z = zscore(float(current_count), history_prev)

    if baseline == 0:
        if current_count > 0:
            sev = Severity.WARNING
            desc = f"Daha önce sıfır olan konuda {current_count} haber/post"
        else:
            sev = Severity.OK
            desc = "Haber yok"
    else:
        ratio = current_count / baseline
        if ratio >= ANOMALY["news_crit_mult"]:
            sev = Severity.CRITICAL
        elif ratio >= ANOMALY["news_spike_mult"]:
            sev = Severity.WARNING
        else:
            sev = Severity.OK
        delta_pct = (current_count - baseline) / baseline * 100
        direction = "artış" if delta_pct > 0 else "düşüş"
        desc = f"Haber frekansı {abs(delta_pct):.0f}% {direction} (baseline: {baseline:.1f}/periyot, güncel: {current_count})"

    return AnomalyEvent(
        raw=event,
        severity=sev,
        current_value=float(current_count),
        baseline_value=round(baseline, 2),
        zscore=round(z, 3) if z else None,
        delta_pct=round((current_count - baseline) / baseline * 100, 2) if baseline else 0,
        anomaly_description=desc,
        confidence=SOURCE_WEIGHTS.get(source, 0.5),
    )


# ═══════════════════════════════════════════════════════════════
# TEK OLAY ANALİZİ — ACLED, GDACS gibi olay bazlı kaynaklar
# ═══════════════════════════════════════════════════════════════

def analyze_event_severity(
    event: RawEvent,
    source: str,
    fatalities: int = 0,
    event_type_severity: str = "low",  # "low" | "medium" | "high" | "critical"
) -> AnomalyEvent:
    """
    ACLED / GDACS gibi kaynaklarda olay kendi başına anomali.
    Ölü sayısı ve olay tipi ağırlıklı severity.
    """
    sev_map = {
        "low": Severity.INFO,
        "medium": Severity.WARNING,
        "high": Severity.CRITICAL,
        "critical": Severity.CRITICAL,
    }
    sev = sev_map.get(event_type_severity, Severity.INFO)

    # Ölü sayısı varsa severity'yi yukarı çek
    if fatalities >= 100:
        sev = Severity.CRITICAL
    elif fatalities >= 20:
        sev = max([sev, Severity.WARNING], key=lambda s: ["ok","info","warning","critical"].index(s.value))

    desc = event.title
    if fatalities:
        desc += f" ({fatalities} kayıp)"

    return AnomalyEvent(
        raw=event,
        severity=sev,
        current_value=float(fatalities),
        anomaly_description=desc,
        confidence=SOURCE_WEIGHTS.get(source, 0.5),
    )
