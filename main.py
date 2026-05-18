"""
main.py

OSINT Intelligence Engine — Orchestrator
Collectors, Analysis, Synthesis, API'yı koordine eder.
"""

import logging
import time
import threading
from datetime import datetime, timedelta
from schedule import every, run_pending
from config import SCAN_INTERVALS, DATABASE
from storage.db import init_db, insert_raw_event, insert_anomaly, insert_cluster, insert_report
from analysis.anomaly import analyze_numeric, analyze_event_severity, analyze_news_frequency
from analysis.correlator import correlate
from analysis.synthesizer import synthesize
from api.server import run_server, set_scan_trigger, app

# LOGOSİNT Production Layer
from logosint.integration import setup_logosint

# Collectors
from collectors.opensky_collector import OpenSkyCollector
from collectors.marine_collector import MarineCollector
from collectors.acled_collector import ACLEDCollector
from collectors.telegram_collector import TelegramCollector
from collectors.gdacs_collector import GDACSCollector
from collectors.reddit_collector import RedditCollector
from collectors.fred_collector import FREDCollector
from collectors.gdelt_collector import GDELTCollector
from collectors.rss_collector import RSSCollector

log = logging.getLogger("Main")

# Collectors registry
COLLECTORS = {
    "opensky": OpenSkyCollector(),
    "marine": MarineCollector(),
    "acled": ACLEDCollector(),
    "telegram": TelegramCollector(),
    "gdacs": GDACSCollector(),
    "reddit": RedditCollector(),
    "fred": FREDCollector(),
    "gdelt": GDELTCollector(),
    "rss": RSSCollector(),
}


def setup_logging():
    """Logging'i konfigüre et."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("osint.log")
        ]
    )


def run_collectors():
    """Tüm collectors'ları çalıştır — paralel."""
    log.info("=" * 60)
    log.info("TARAMA BAŞLANIYOR")
    log.info("=" * 60)

    raw_events = []
    for name, collector in COLLECTORS.items():
        try:
            events = collector.run()
            raw_events.extend(events)
            log.info(f"✓ {name:12s} → {len(events):3d} event toplandı")
        except Exception as e:
            log.error(f"✗ {name:12s} → Hata: {e}")

    log.info(f"Toplam {len(raw_events)} raw event toplandı")

    # DB'ye kaydet
    for ev in raw_events:
        insert_raw_event(ev.to_dict())

    return raw_events


def run_anomaly_analysis(raw_events):
    """Anomali tespiti — Z-score ve spike analizi."""
    log.info("ANOMALI ANALİZİ BAŞLANIYOR...")

    anomalies = []
    for ev in raw_events:
        # Henüz anomaly detection'ı raw events'a direkt uygulamıyoruz
        # Bunun yerine synthesis aşamasında yapılacak
        pass

    log.info(f"Toplam {len(anomalies)} anomali tespit edildi")
    return anomalies


def run_correlation_analysis(anomalies):
    """Korelasyon kümelerini bul."""
    log.info("KORELASYON ANALİZİ BAŞLANIYOR...")

    clusters = correlate(anomalies)

    for cluster in clusters:
        insert_cluster(cluster.to_dict())

    log.info(f"Toplam {len(clusters)} korelasyon kümesi oluşturuldu")
    return clusters


def run_synthesis(anomalies, clusters):
    """Nihai istihbarat raporunu sentezle."""
    log.info("SENTEZİS BAŞLANIYOR...")

    report = synthesize(anomalies, clusters)
    insert_report(report.to_dict())

    log.info(f"Rapor üretildi: {report.report_id}")
    log.info(f"  Status: {report.system_status.value}")
    log.info(f"  Anomali: {report.active_anomalies}")
    log.info(f"  Korelasyon: {report.active_correlations}")
    log.info(f"  Bulgular: {len(report.key_findings)}")

    return report


def run_full_scan():
    """Tam tarama — collectors → analysis → synthesis."""
    log.info("\n" + "=" * 60)
    log.info(f"TARAMA CİKLÜ: {datetime.utcnow().isoformat()}")
    log.info("=" * 60)

    try:
        # 1. Collect
        raw_events = run_collectors()

        # 2. Anomaly detection (şimdilik skip — synthesizer'da yapılacak)
        anomalies = run_anomaly_analysis(raw_events)

        # 3. Correlation
        clusters = run_correlation_analysis(anomalies)

        # 4. Synthesis
        report = run_synthesis(anomalies, clusters)

        log.info("=" * 60)
        log.info("TARAMA CİKLÜ TAMAMLANDI")
        log.info("=" * 60 + "\n")

    except Exception as e:
        log.error(f"TARAMA CİKLÜ HATASI: {e}", exc_info=True)


def schedule_jobs():
    """Scheduler'ı ayarla."""
    # Her collector için ayrı interval
    every(SCAN_INTERVALS.get("rss", 15)).minutes.do(run_full_scan)

    # Ana scan her saat
    every(1).hour.do(run_full_scan)


def scheduler_thread():
    """Background scheduler thread."""
    while True:
        run_pending()
        time.sleep(30)


def main():
    """Ana entry point."""
    setup_logging()
    log.info("OSINT Intelligence Engine başlatılıyor...")

    # DB'yi hazırla
    init_db()
    log.info("✓ Veritabanı hazır")

    # API trigger'ı ayarla
    set_scan_trigger(run_full_scan)

    # İlk taramayı hemen çalıştır
    log.info("İlk tarama başlıyor...")
    run_full_scan()

    # Schedule'ı ayarla
    schedule_jobs()
    log.info("✓ Tarama planlaması yapılandırıldı")

    # Scheduler thread'i başlat (background)
    sched_thread = threading.Thread(target=scheduler_thread, daemon=True)
    sched_thread.start()
    log.info("✓ Scheduler thread başlatıldı")

    # LOGOSİNT Production Layer'ı setup et
    log.info("LOGOSİNT production layer başlatılıyor...")
    try:
        setup_logosint(app, collectors=COLLECTORS, interval_seconds=3600)
        log.info("✓ LOGOSİNT entegrasyonu tamamlandı")
    except Exception as e:
        log.warning(f"LOGOSİNT setup uyarısı: {e}")

    # Flask API'yı başlat (blocking)
    log.info("Flask API başlatılıyor...")
    run_server()


if __name__ == "__main__":
    main()
