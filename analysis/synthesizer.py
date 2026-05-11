"""
analysis/synthesizer.py

İstihbarat sentez motoru.
Anomalileri ve korelasyon kümelerini alır,
nihai IntelligenceReport üretir.
"""

import uuid
import logging
from datetime import datetime
from collections import defaultdict
from models.event import Severity, Domain
from models.intelligence import IntelligenceReport, CorrelationCluster
from config import SOURCE_WEIGHTS

log = logging.getLogger("Synthesizer")

# Severity sıralaması
SEV_ORDER = {Severity.OK: 0, Severity.INFO: 1, Severity.WARNING: 2, Severity.CRITICAL: 3}


def _system_status(clusters: list[CorrelationCluster], anomalies: list) -> Severity:
    """Genel sistem durumunu belirle."""
    if not anomalies and not clusters:
        return Severity.OK

    crit_clusters = [c for c in clusters if c.severity == Severity.CRITICAL]
    crit_anomalies = [a for a in anomalies if a.severity == Severity.CRITICAL]

    if crit_clusters or len(crit_anomalies) >= 2:
        return Severity.CRITICAL

    warn_clusters = [c for c in clusters if c.severity == Severity.WARNING]
    warn_anomalies = [a for a in anomalies if a.severity == Severity.WARNING]

    if warn_clusters or len(warn_anomalies) >= 3:
        return Severity.WARNING

    return Severity.INFO


def _domain_summary(anomalies: list) -> dict:
    """Her domain için özet istatistik."""
    summary = defaultdict(lambda: {"total": 0, "critical": 0, "warning": 0, "info": 0})
    for a in anomalies:
        d = a.raw.domain.value
        summary[d]["total"] += 1
        summary[d][a.severity.value] = summary[d].get(a.severity.value, 0) + 1
    return dict(summary)


def _region_summary(anomalies: list, clusters: list[CorrelationCluster]) -> dict:
    """Her bölge için anomali ve korelasyon sayısı."""
    summary = defaultdict(lambda: {"anomalies": 0, "clusters": 0, "max_severity": "ok"})

    for a in anomalies:
        for r in a.raw.affected_regions:
            summary[r]["anomalies"] += 1
            curr = SEV_ORDER.get(Severity(summary[r]["max_severity"]), 0)
            new = SEV_ORDER.get(a.severity, 0)
            if new > curr:
                summary[r]["max_severity"] = a.severity.value

    for c in clusters:
        for r in c.regions_involved:
            summary[r]["clusters"] += 1

    return dict(summary)


def _source_stats(anomalies: list) -> dict:
    """Kaynak başına anomali sayısı."""
    stats = defaultdict(int)
    for a in anomalies:
        stats[a.raw.source] += 1
    return dict(stats)


def _key_findings(clusters: list[CorrelationCluster], anomalies: list) -> list[str]:
    """
    En önemli 5 bulguyu üret.
    Önce kritik kümeler, sonra kritik tekil anomaliler.
    """
    findings = []

    # Kritik kümeler
    for c in clusters:
        if c.severity in (Severity.CRITICAL, Severity.WARNING):
            domain_str = " + ".join(c.domains_involved[:3])
            region_str = ", ".join(c.regions_involved[:2]) or "bilinmeyen bölge"
            ctype = {"cascade": "zincirleme", "divergent": "pivot", "parallel": "eş zamanlı"}.get(
                c.correlation_type, c.correlation_type
            )
            findings.append(
                f"[{c.severity.value.upper()}] {region_str}: "
                f"{domain_str} domain'lerinde {ctype} korelasyon "
                f"(güven: {c.confidence:.0%})"
            )
        if len(findings) >= 3:
            break

    # Kritik tekil anomaliler (kümeye girmemiş)
    clustered_ids = {eid for c in clusters for eid in c.event_ids}
    solo_crits = [
        a for a in anomalies
        if a.severity == Severity.CRITICAL and a.raw.event_id not in clustered_ids
    ]
    for a in solo_crits[:2]:
        findings.append(
            f"[KRİTİK] {a.raw.source.upper()}: {a.raw.title[:100]}"
        )

    return findings[:5]


def _watch_list(clusters: list[CorrelationCluster], anomalies: list) -> list[str]:
    """
    Yakından takip edilmesi gereken bölge/konu kombinasyonları.
    """
    watch = []

    # Cascade kümeler — haber → fiziksel sinyal zinciri en önemli uyarı
    for c in clusters:
        if c.correlation_type == "cascade" and c.severity != Severity.OK:
            regions = ", ".join(c.regions_involved[:2]) or "bölge belirsiz"
            kw = ", ".join(c.keywords_common[:2])
            watch.append(
                f"ZINCIRLEME: {regions} — [{kw}] — "
                f"haber sinyali fiziksel anomaliye dönüşüyor"
            )

    # Divergent kümeler — trafik pivot
    for c in clusters:
        if c.correlation_type == "divergent":
            watch.append(
                f"PİVOT: {', '.join(c.regions_involved[:2])} — "
                f"{' → '.join(c.domains_involved)} trafik kayması"
            )

    # Yüksek frekanslı haber spike'ları
    news_crits = [
        a for a in anomalies
        if a.severity == Severity.CRITICAL
        and a.raw.domain in (Domain.NEWS, Domain.SOCIAL)
    ]
    for a in news_crits[:2]:
        kw = ", ".join(a.raw.keywords_matched[:3])
        watch.append(f"HABER SPİKE: [{kw}] — {a.raw.source}: {a.raw.title[:80]}")

    return watch[:5]


def synthesize(
    anomalies: list,
    clusters: list[CorrelationCluster],
) -> IntelligenceReport:
    """
    Anomaliler ve kümelerden nihai istihbarat raporu üret.
    """
    log.info("Sentez başlıyor: %d anomali, %d küme", len(anomalies), len(clusters))

    report = IntelligenceReport(
        report_id=f"RPT-{datetime.utcnow().strftime('%Y%m%d-%H%M')}-{uuid.uuid4().hex[:4].upper()}",
        generated_at=datetime.utcnow(),
        system_status=_system_status(clusters, anomalies),
        active_anomalies=len([a for a in anomalies if a.severity != Severity.OK]),
        active_correlations=len(clusters),
        clusters=clusters,
        domain_summary=_domain_summary(anomalies),
        region_summary=_region_summary(anomalies, clusters),
        key_findings=_key_findings(clusters, anomalies),
        watch_list=_watch_list(clusters, anomalies),
        source_stats=_source_stats(anomalies),
    )

    log.info(
        "Rapor üretildi: %s | Durum: %s | %d bulgu | %d izleme",
        report.report_id,
        report.system_status.value,
        len(report.key_findings),
        len(report.watch_list),
    )
    return report
