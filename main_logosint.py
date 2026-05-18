"""
main.py — OSINT Intelligence Engine giriş noktası.

Çalıştırma:
    pip install -r requirements.txt
    python main.py

API:
    http://localhost:5055/api/status
    http://localhost:5055/api/report
    http://localhost:5055/api/anomalies
    http://localhost:5055/api/clusters
    http://localhost:5055/api/events
"""

import logging
import threading
import schedule
import time
import sys
import uuid
from datetime import datetime
import colorlog

# ── Loglama ayarı ─────────────────────────────────────────────
handler = colorlog.StreamHandler()
handler.setFormatter(colorlog.ColoredFormatter(
    "%(log_color)s%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    log_colors={
        "DEBUG":    "cyan",
        "INFO":     "green",
        "WARNING":  "yellow",
        "ERROR":    "red",
        "CRITICAL": "bold_red",
    }
))
logging.basicConfig(handlers=[handler], level=logging.INFO)
log = logging.getLogger("MAIN")

# ── İçe aktarmalar ─────────────────────────────────────────────
from storage.db import init_db, cleanup_old_records, insert_anomaly, insert_cluster, insert_report
from collectors.rss_collector import RSSCollector
from collectors.gdelt_collector import GDELTCollector
from collectors.gdelt_events_collector import GDELTEventsCollector
from collectors.opensky_collector import OpenSkyCollector
from collectors.marine_collector import MarineCollector
from collectors.acled_collector import ACLEDCollector
from collectors.reddit_collector import RedditCollector
from collectors.fred_collector import FREDCollector
from collectors.gdacs_collector import GDACSCollector
from collectors.telegram_collector import TelegramCollector
from collectors.sentinelhub_collector import SentinelHubCollector
from collectors.satellite_vision_collector import SatelliteVisionCollector
from collectors.market_collector import MarketCollector
from analysis.correlator import correlate
from analysis.synthesizer import synthesize
from analysis.anomaly import analyze_news_frequency
from models.event import Domain, RawEvent
from api.server import run_server, set_scan_trigger
from config import SCAN_INTERVALS, SENTINELHUB

# ── Collector'lar ─────────────────────────────────────────────
COLLECTORS = {
    "rss":              RSSCollector(),
    "gdelt":            GDELTCollector(),
    "gdelt_events":     GDELTEventsCollector(),
    "opensky":          OpenSkyCollector(),
    "marine":           MarineCollector(),
    "acled":            ACLEDCollector(),
    "reddit":           RedditCollector(),
    "fred":             FREDCollector(),
    "gdacs":            GDACSCollector(),
    "telegram":         TelegramCollector(),
    "sentinelhub":      SentinelHubCollector(SENTINELHUB),
    "satellite_vision": SatelliteVisionCollector(SENTINELHUB),
    "market":           MarketCollector(),
}

# Global anomali ve event deposu (RAM — son tarama)
_latest_anomalies = []
_latest_events = []
_scan_lock = threading.Lock()


# ═══════════════════════════════════════════════════════════════
# HABER FREKANS ANALİZİ
# Toplanan haberleri bölge × konu matrisine indir
# ═══════════════════════════════════════════════════════════════

from config import REGIONS, KEYWORDS

def analyze_news_patterns(events: list[RawEvent]) -> list:
    """
    RSS, GDELT, Reddit haberlerini bölge × konu bazında frekans anomalisine dönüştür.
    Örnek: "levant" bölgesinde "military" keyword'ü son saatte 12 haber çıktı,
    baseline 3 iken → kritik anomali.
    """
    from collections import defaultdict
    anomalies = []

    # Bölge × konu × kaynak sayımı
    counts = defaultdict(int)

    news_events = [e for e in events if e.domain in (Domain.NEWS, Domain.SOCIAL)]
    for ev in news_events:
        for region in ev.affected_regions:
            for kw in ev.keywords_matched:
                key = f"{ev.source.split('_')[0]}_{kw}_{region}"
                counts[key] += 1

    # Her kombinasyon için anomali analizi
    for key, count in counts.items():
        parts = key.split("_", 2)
        if len(parts) < 3:
            continue
        src, kw, region = parts

        # En az 2 haber varsa analiz et
        if count < 2:
            continue

        # Yer tutucu RawEvent
        placeholder = RawEvent(
            source=f"{src}_aggregated",
            domain=Domain.NEWS,
            event_id=f"freq_{key}_{datetime.utcnow().strftime('%Y%m%d%H')}",
            title=f"{region.upper()} / {kw}: {count} haber/post",
            timestamp=datetime.utcnow(),
            affected_regions=[region],
            keywords_matched=[kw],
        )

        anomaly = analyze_news_frequency(
            topic_key=f"news_{key}",
            current_count=count,
            source=src,
            event=placeholder,
        )

        if anomaly.severity.value in ("warning", "critical"):
            anomalies.append(anomaly)
            insert_anomaly(anomaly.to_dict())
            log.warning(
                "Haber anomali: %s | %s",
                key, anomaly.anomaly_description
            )

    return anomalies


# ═══════════════════════════════════════════════════════════════
# ANA TARAMA FONKSİYONU
# ═══════════════════════════════════════════════════════════════

def run_scan(collector_names: list[str] = None):
    """
    Belirtilen collector'ları çalıştır, anomali tespiti yap,
    korelasyon kur, rapor üret.
    collector_names=None → tümünü çalıştır.
    """
    with _scan_lock:
        global _latest_anomalies, _latest_events

        collectors_to_run = collector_names or list(COLLECTORS.keys())
        log.info("═" * 60)
        log.info("TARAMA BAŞLIYOR: %s", ", ".join(collectors_to_run))
        start = time.time()

        all_events = []
        all_anomalies = []

        # 1. Veri toplama
        for name in collectors_to_run:
            collector = COLLECTORS.get(name)
            if not collector:
                continue
            log.info("── %s taranıyor...", name.upper())
            events = collector.run()
            all_events.extend(events)

        # 2. Haber frekans anomalisi
        news_anomalies = analyze_news_patterns(all_events)
        all_anomalies.extend(news_anomalies)

        # 3. Veritabanından aktif anomalileri al (numeric collector'ların yazdıkları dahil)
        from storage.db import get_active_anomalies
        db_anomalies = get_active_anomalies(hours=12)
        log.info("%d aktif anomali DB'de mevcut", len(db_anomalies))

        # 4. Anomalileri AnomalyEvent nesnelerine çevir (correlator için)
        from models.event import AnomalyEvent, Severity, GeoPoint
        corr_candidates = []

        for a in db_anomalies:
            try:
                sev = Severity(a.get("severity", "info"))
                raw = RawEvent(
                    source=a.get("source", ""),
                    domain=Domain(a.get("domain", "news")),
                    event_id=a.get("event_id", str(uuid.uuid4())),
                    title=a.get("description", ""),
                    timestamp=datetime.fromisoformat(a["timestamp"]) if a.get("timestamp") else datetime.utcnow(),
                    location=GeoPoint(
                        lat=a["lat"], lon=a["lon"],
                        region=a.get("region")
                    ) if a.get("lat") and a.get("lon") else None,
                    affected_regions=[a["region"]] if a.get("region") else [],
                    keywords_matched=[],  # DB'den kw geri yükleme şimdilik atlandı
                )
                ae = AnomalyEvent(
                    raw=raw,
                    severity=sev,
                    current_value=a.get("current_value"),
                    baseline_value=a.get("baseline_value"),
                    zscore=a.get("zscore"),
                    delta_pct=a.get("delta_pct"),
                    anomaly_description=a.get("description", ""),
                    confidence=a.get("confidence", 0.5),
                )
                corr_candidates.append(ae)
            except Exception as e:
                log.debug("Anomali dönüştürme hata: %s", e)

        corr_candidates.extend(all_anomalies)

        # 5. Korelasyon analizi
        clusters = correlate(corr_candidates)

        # 6. Korelasyonları kaydet
        for c in clusters:
            d = c.to_dict()
            insert_cluster(d)

        # 7. Sentez raporu
        report = synthesize(corr_candidates, clusters)
        insert_report(report.to_dict())

        # 8. Global state güncelle
        _latest_anomalies = corr_candidates
        _latest_events = all_events

        elapsed = time.time() - start
        log.info(
            "TARAMA TAMAMLANDI — %.1fs | %d event | %d anomali | %d küme | Durum: %s",
            elapsed, len(all_events), len(corr_candidates),
            len(clusters), report.system_status.value.upper()
        )
        log.info("═" * 60)

        # Kritik bulgular varsa konsola bas
        for finding in report.key_findings:
            log.warning("📍 %s", finding)
        for watch in report.watch_list:
            log.warning("👁  %s", watch)


# ═══════════════════════════════════════════════════════════════
# ZAMANLAYICI
# ═══════════════════════════════════════════════════════════════

def run_synthesis():
    """
    Saatlik istihbarat sentezi.
    Collector'lardan bağımsız çalışır —
    DB'deki aktif anomalileri alır, korelasyon + senaryo yorumu yapar, rapor üretir.
    """
    log.info("── SENTEZ BAŞLIYOR")
    try:
        from analysis.interpreter import interpret
        from storage.db import get_active_anomalies, get_active_clusters
        from reports.pdf_reporter import generate_pdf

        anomalies = get_active_anomalies(hours=12)
        clusters_raw = get_active_clusters(hours=24)

        # Senaryo yorumu
        scenarios = interpret(anomalies, clusters_raw)
        if scenarios:
            log.info("Senaryo tahminleri:")
            for s in scenarios:
                log.info("  → %s (güven: %.0f%%)", s.scenario_name, s.confidence * 100)

        # Raporu güncelle — senaryo tahminleriyle birlikte kaydet
        report = get_latest_report()
        if report:
            report["scenarios"] = [s.to_dict() for s in scenarios]
            insert_report(report)   # üzerine yaz

        # PDF üret (her saat)
        try:
            pdf_path = generate_pdf(report or {}, [s.to_dict() for s in scenarios])
            if pdf_path:
                log.info("Saatlik PDF üretildi: %s", pdf_path)
        except Exception as e:
            log.warning("PDF üretim hatası: %s", e)

    except Exception as e:
        log.error("Sentez hatası: %s", e)
    log.info("── SENTEZ TAMAMLANDI")



    """Her collector için ayrı zamanlama."""
    # RSS — 15 dakikada bir
    schedule.every(SCAN_INTERVALS["rss"]).minutes.do(
        lambda: run_scan(["rss"])
    )
    # GDELT — 30 dakikada bir
    schedule.every(SCAN_INTERVALS["gdelt"]).minutes.do(
        lambda: run_scan(["gdelt"])
    )
    # OpenSky — 20 dakikada bir
    schedule.every(SCAN_INTERVALS["opensky"]).minutes.do(
        lambda: run_scan(["opensky"])
    )
    # Marine — 20 dakikada bir
    schedule.every(SCAN_INTERVALS["marine"]).minutes.do(
        lambda: run_scan(["marine"])
    )
    # ACLED — 6 saatte bir
    schedule.every(SCAN_INTERVALS["acled"]).minutes.do(
        lambda: run_scan(["acled"])
    )
    # Reddit — 30 dakikada bir
    schedule.every(SCAN_INTERVALS["reddit"]).minutes.do(
        lambda: run_scan(["reddit"])
    )
    # FRED — günde bir
    schedule.every(SCAN_INTERVALS["fred"]).minutes.do(
        lambda: run_scan(["fred"])
    )
    # GDACS — saatte bir
    schedule.every(SCAN_INTERVALS["gdacs"]).minutes.do(
        lambda: run_scan(["gdacs"])
    )
    # Saatlik sentez + PDF + senaryo yorumu
    schedule.every(60).minutes.do(run_synthesis)

    # Telegram — 5 dakikada bir (gerçek zamanlıya en yakın)
    schedule.every(SCAN_INTERVALS["telegram"]).minutes.do(
        lambda: run_scan(["telegram"])
    )
    # Temizlik — günlük
    schedule.every().day.at("03:00").do(cleanup_old_records)

    log.info("Zamanlayıcı ayarlandı")


def scheduler_loop():
    while True:
        schedule.run_pending()
        time.sleep(10)


# ═══════════════════════════════════════════════════════════════
# BAŞLANGIÇ
# ═══════════════════════════════════════════════════════════════

def main():
    print("""
╔══════════════════════════════════════════════════════════════╗
║         OSINT INTELLIGENCE ENGINE v1.0                      ║
╠══════════════════════════════════════════════════════════════╣
║  Kaynaklar:                                                  ║
║    ✈  OpenSky Network      (ücretsiz)                        ║
║    ⚓  AISHub / MarineTraffic (key gerekli)                  ║
║    📰 RSS — BBC/Reuters/AJ/AP (ücretsiz)                    ║
║    🌐 GDELT Project         (ücretsiz)                       ║
║    ⚔️  ACLED Conflict Data   (ücretsiz akademik)              ║
║    💬 Reddit                (key gerekli)                    ║
║    💰 FRED Economic Data    (key gerekli)                    ║
║    🌪️  GDACS Disasters       (ücretsiz)                       ║
╠══════════════════════════════════════════════════════════════╣
║  API:  http://localhost:5055                                 ║
║  Docs: http://localhost:5055/api/status                      ║
╠══════════════════════════════════════════════════════════════╣
║  config.py dosyasına API keylerini ekle.                     ║
╚══════════════════════════════════════════════════════════════╝
""")

    # Veritabanını başlat
    init_db()

    # API scan trigger bağla
    set_scan_trigger(lambda: run_scan())

    # ── LOGOSİNT v2 pipeline entegrasyonu ─────────────────────
    # Scoring engine, sinyal adapter, LLM analiz, explainability
    try:
        from logosint.integration import setup_logosint
        from api.server import app
        setup_logosint(app, collectors=COLLECTORS, interval_seconds=3600)
        log.info("LOGOSİNT v2 pipeline aktif")
        log.info("Yeni API endpoint'leri: /api/scores /api/heatmap /api/trends")
        log.info("                        /api/explain /api/analyze/region /api/analyze/weekly")
    except Exception as e:
        log.warning("LOGOSİNT pipeline başlatılamadı: %s — eski sistem devam ediyor", e)

    # İlk tam tarama (thread'de)
    log.info("İlk tarama başlatılıyor...")
    t_init = threading.Thread(target=run_scan, daemon=True)
    t_init.start()

    # İlk tarama bittikten sonra sentez başlat
    def _init_then_synthesize():
        t_init.join(timeout=300)
        run_synthesis()

    threading.Thread(target=_init_then_synthesize, daemon=True).start()

    # Zamanlayıcıyı kur ve başlat
    setup_schedule()
    t_sched = threading.Thread(target=scheduler_loop, daemon=True)
    t_sched.start()

    # Flask API — ana thread'de çalıştır
    run_server()


if __name__ == "__main__":
    main()
