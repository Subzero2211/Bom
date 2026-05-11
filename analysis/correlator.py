"""
analysis/correlator.py

Korelasyon motoru: anomali eventlerini üç eksende eşleştirir.
1. Coğrafi  — Haversine ≤ config.CORR_DISTANCE_KM
2. Zamansal — ±config.CORR_TIME_HOURS penceresi
3. Tematik  — Ortak keyword grubu

Eşleşen eventler CorrelationCluster'a toplanır.
Cluster tipi:
  parallel  → aynı yön (hepsi artıyor veya düşüyor, aynı konuya işaret ediyor)
  divergent → ters yön (pivot: bir domain azalırken diğeri artıyor)
  cascade   → zincirleme (haber → fiziksel sinyal sırası)
"""

import math
import uuid
import logging
from datetime import datetime, timedelta
from itertools import combinations
from typing import Optional
from models.event import AnomalyEvent, Severity, GeoPoint, Domain
from models.intelligence import CorrelationCluster
from config import ANOMALY

log = logging.getLogger("Correlator")


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """İki koordinat arası mesafe (km)."""
    R = 6371
    d2r = math.pi / 180
    dlat = (lat2 - lat1) * d2r
    dlon = (lon2 - lon1) * d2r
    a = (math.sin(dlat/2)**2
         + math.cos(lat1*d2r) * math.cos(lat2*d2r) * math.sin(dlon/2)**2)
    return R * 2 * math.asin(math.sqrt(max(0, a)))


def _geo_close(a: AnomalyEvent, b: AnomalyEvent) -> bool:
    """İki event coğrafi olarak yeterince yakın mı?"""
    la = a.raw.location
    lb = b.raw.location
    if not la or not lb:
        # Konum yoksa bölge bazlı kontrol
        ar = set(a.raw.affected_regions)
        br = set(b.raw.affected_regions)
        return bool(ar & br)
    dist = haversine(la.lat, la.lon, lb.lat, lb.lon)
    return dist <= ANOMALY["corr_distance_km"]


def _time_close(a: AnomalyEvent, b: AnomalyEvent) -> bool:
    """İki event zamansal pencere içinde mi?"""
    diff = abs((a.raw.timestamp - b.raw.timestamp).total_seconds())
    return diff <= ANOMALY["corr_time_hours"] * 3600


def _thematic_overlap(a: AnomalyEvent, b: AnomalyEvent) -> list[str]:
    """Ortak keyword gruplarını döndür."""
    ka = set(a.raw.keywords_matched)
    kb = set(b.raw.keywords_matched)
    return list(ka & kb)


def _correlation_type(events: list[AnomalyEvent]) -> str:
    """
    Kümedeki eventlerin tipini belirle.
    cascade: news → (air|sea|conflict) sırası mevcut
    divergent: aynı bölgede bir domain artarken diğeri azalıyor
    parallel: hepsi aynı yönde
    """
    domains = [e.raw.domain for e in events]

    # Cascade kontrolü: news + fiziksel domain
    physical = {Domain.AIR, Domain.SEA, Domain.CONFLICT}
    has_news = Domain.NEWS in domains or Domain.SOCIAL in domains
    has_physical = any(d in physical for d in domains)

    if has_news and has_physical:
        # Haber mi önce geldi?
        news_events = [e for e in events if e.raw.domain in (Domain.NEWS, Domain.SOCIAL)]
        phys_events = [e for e in events if e.raw.domain in physical]
        if news_events and phys_events:
            earliest_news = min(e.raw.timestamp for e in news_events)
            earliest_phys = min(e.raw.timestamp for e in phys_events)
            if earliest_news < earliest_phys:
                return "cascade"

    # Divergent kontrolü: numeric eventlerde ters yönlü delta
    numeric = [e for e in events if e.delta_pct is not None]
    if len(numeric) >= 2:
        signs = [1 if e.delta_pct > 0 else -1 for e in numeric if e.delta_pct != 0]
        if signs and len(set(signs)) > 1:
            return "divergent"

    return "parallel"


def _weighted_centroid(events: list[AnomalyEvent]) -> Optional[GeoPoint]:
    """Eventlerin confidence-ağırlıklı coğrafi merkezini hesapla."""
    points = [(e for e in events if e.raw.location)]
    locs = [e for e in events if e.raw.location]
    if not locs:
        return None
    total_w = sum(e.confidence for e in locs)
    if total_w == 0:
        return None
    lat = sum(e.raw.location.lat * e.confidence for e in locs) / total_w
    lon = sum(e.raw.location.lon * e.confidence for e in locs) / total_w
    return GeoPoint(lat=lat, lon=lon)


def _cluster_severity(events: list[AnomalyEvent]) -> Severity:
    """Kümedeki en yüksek severity'yi döndür."""
    order = [Severity.OK, Severity.INFO, Severity.WARNING, Severity.CRITICAL]
    return max(events, key=lambda e: order.index(e.severity)).severity


def _cluster_confidence(events: list[AnomalyEvent]) -> float:
    """
    Küme güvenilirliği:
    - Kaynak sayısı arttıkça güvenilirlik artar
    - Farklı domain'lerden gelen sinyaller güvenilirliği artırır
    - Bireysel source weight'lerin ağırlıklı ortalaması
    """
    if not events:
        return 0.0
    base_conf = sum(e.confidence for e in events) / len(events)
    n_domains = len(set(e.raw.domain for e in events))
    n_sources = len(set(e.raw.source for e in events))
    # Her ekstra domain +5%, her ekstra source +3%, max +25%
    bonus = min(0.25, (n_domains - 1) * 0.05 + (n_sources - 1) * 0.03)
    return min(1.0, base_conf + bonus)


def _generate_summary(events: list[AnomalyEvent], corr_type: str) -> str:
    """İnsan okunabilir küme özeti üret."""
    domains = list(set(e.raw.domain.value for e in events))
    regions = list(set(r for e in events for r in e.raw.affected_regions))
    keywords = list(set(k for e in events for k in e.raw.keywords_matched))
    n = len(events)

    type_desc = {
        "parallel":  "eş zamanlı anomali",
        "divergent": "trafik pivot/kayması",
        "cascade":   "haber-fiziksel zincirleme",
    }.get(corr_type, "korelasyon")

    domain_str = " + ".join(domains[:3])
    region_str = ", ".join(regions[:2]) if regions else "belirsiz bölge"
    kw_str = ", ".join(keywords[:3]) if keywords else ""

    summary = (
        f"{region_str.upper()} bölgesinde {n} kaynakta {type_desc} tespit edildi. "
        f"Domain: [{domain_str}]."
    )
    if kw_str:
        summary += f" Tematik: [{kw_str}]."

    return summary


def correlate(anomalies: list[AnomalyEvent]) -> list[CorrelationCluster]:
    """
    Anomali listesini al, korelasyon kümelerini döndür.
    Grafik tabanlı gruplama: iki event arasında 3 eksende bağlantı varsa aynı kümeye girer.
    """
    if len(anomalies) < 2:
        return []

    # Bağlantı matrisini oluştur
    n = len(anomalies)
    edges = set()

    for i in range(n):
        for j in range(i + 1, n):
            a, b = anomalies[i], anomalies[j]

            # En az 2 eksen eşleşmeli
            geo = _geo_close(a, b)
            time = _time_close(a, b)
            theme = bool(_thematic_overlap(a, b))

            if sum([geo, time, theme]) >= 2:
                edges.add((i, j))

    if not edges:
        return []

    # Union-Find ile bağlı bileşenleri bul
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    for i, j in edges:
        union(i, j)

    # Kümeleri oluştur
    clusters_map: dict[int, list[int]] = {}
    for idx in range(n):
        root = find(idx)
        clusters_map.setdefault(root, []).append(idx)

    clusters = []
    for root, indices in clusters_map.items():
        if len(indices) < 2:
            continue

        evs = [anomalies[i] for i in indices]
        corr_type = _correlation_type(evs)
        centroid = _weighted_centroid(evs)
        sev = _cluster_severity(evs)
        conf = _cluster_confidence(evs)
        summary = _generate_summary(evs, corr_type)

        timestamps = [e.raw.timestamp for e in evs]
        common_kw = list(set(k for e in evs for k in e.raw.keywords_matched))
        domains = list(set(e.raw.domain.value for e in evs))
        regions = list(set(r for e in evs for r in e.raw.affected_regions))

        cluster = CorrelationCluster(
            cluster_id=f"CLU-{uuid.uuid4().hex[:8].upper()}",
            severity=sev,
            event_ids=[e.raw.event_id for e in evs],
            domains_involved=domains,
            regions_involved=regions,
            keywords_common=common_kw,
            centroid=centroid,
            first_seen=min(timestamps),
            last_seen=max(timestamps),
            correlation_type=corr_type,
            summary=summary,
            confidence=conf,
        )
        clusters.append(cluster)

    # Confidence'a göre sırala
    clusters.sort(key=lambda c: (
        ["ok","info","warning","critical"].index(c.severity.value),
        c.confidence
    ), reverse=True)

    log.info("%d anomaliden %d korelasyon kümesi oluşturuldu", len(anomalies), len(clusters))
    return clusters
