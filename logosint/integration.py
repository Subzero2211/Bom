"""
logosint/integration.py

Mevcut main.py'ye LOGOSİNT pipeline'ını entegre eden patch.
Mevcut main.py'nin en altına şunu ekle:

    from logosint.integration import setup_logosint
    setup_logosint(app, collectors=COLLECTORS)

Bu kadar. Geri her şey otomatik çalışır.
"""

from __future__ import annotations
import logging
from typing import Any

log = logging.getLogger("Integration")


def _build_collector_fn(collectors: dict) -> callable:
    """
    Mevcut COLLECTORS dict'inden collector_fn üret.
    Her collector'ın .run() metodunu çağırır,
    çıktıyı {source: [raw_items]} formatına dönüştürür.
    """
    def collect_all() -> dict[str, list[dict]]:
        outputs = {}
        for name, collector in collectors.items():
            try:
                events = collector.run()
                # RawEvent → dict
                raw_items = []
                for ev in events:
                    if hasattr(ev, "to_dict"):
                        raw_items.append(ev.to_dict())
                    elif hasattr(ev, "__dict__"):
                        raw_items.append(ev.__dict__)
                    elif isinstance(ev, dict):
                        raw_items.append(ev)
                outputs[name] = raw_items
                log.debug("[%s] %d item toplandı", name, len(raw_items))
            except Exception as e:
                log.error("[%s] collect hatası: %s", name, e)
                outputs[name] = []
        return outputs

    return collect_all


def setup_logosint(flask_app, collectors: dict = None, interval_seconds: int = 3600):
    """
    LOGOSİNT pipeline'ını Flask uygulamasına entegre et.
    V2 runtime — atomik, lock'lu, timezone-safe, double-decay fix.
    """
    from logosint.scoring.runtime_v2 import init_runtime
    from logosint.schedulers.scoring_scheduler import ScoringScheduler
    import logosint.schedulers.scoring_scheduler as sched_module
    from logosint.api.routes import bp
    from logosint.storage.db_writer import get_writer

    # DB writer'ı başlat
    get_writer()

    # DB tablolarını oluştur
    init_runtime()

    # Blueprint kaydet
    if "logosint" not in flask_app.blueprints:
        flask_app.register_blueprint(bp)
        log.info("LOGOSİNT API blueprint kaydedildi")

    # Rapor blueprint'i kaydet
    try:
        from logosint.reports.report_routes import rb
        if "reports" not in flask_app.blueprints:
            flask_app.register_blueprint(rb)
            log.info("Rapor blueprint kaydedildi: /reports/archive")
    except Exception as e:
        log.warning("Rapor blueprint yüklenemedi: %s", e)

    # Collector fn
    collector_fn = _build_collector_fn(collectors or {})

    # Scoring Scheduler
    scheduler = ScoringScheduler(
        interval_seconds = interval_seconds,
        collector_fn     = collector_fn,
    )
    sched_module._scheduler = scheduler
    scheduler.start()

    # Rapor Scheduler
    try:
        from logosint.reports.report_scheduler import get_report_scheduler
        rscheduler = get_report_scheduler()
        rscheduler.start()
        log.info("Rapor zamanlayıcısı başladı")
    except Exception as e:
        log.warning("Rapor zamanlayıcısı başlatılamadı: %s", e)

    # Graceful shutdown
    import atexit
    from logosint.storage.db_writer import shutdown_writer
    atexit.register(scheduler.stop)
    atexit.register(shutdown_writer)

    log.info("LOGOSİNT v2 pipeline aktif (interval: %ds)", interval_seconds)
    return scheduler


# ═══════════════════════════════════════════════════════════
# TESTLER
# ═══════════════════════════════════════════════════════════

"""
logosint/tests/test_normalizers.py
"""


def test_opensky_normalizer():
    from logosint.normalizers.base import OpenSkyNormalizer
    n = OpenSkyNormalizer()
    raw = {
        "icao": "LTFM", "name": "İstanbul",
        "lat": 41.27, "lon": 28.74,
        "region": "istanbul_canakkale",
        "current": 210, "baseline": 420,
        "delta_pct": -50.0, "zscore": -2.8,
        "timestamp": "2024-01-01T12:00:00",
    }
    signals = n.normalize(raw)
    assert len(signals) == 1
    s = signals[0]
    assert s.source == "opensky"
    assert s.geography == "istanbul_canakkale"
    assert s.normalized_value is not None
    assert 0.0 <= s.normalized_value <= 1.0
    assert s.severity.value in ("medium", "high", "critical")
    print("✓ OpenSky normalizer")


def test_acled_normalizer():
    from logosint.normalizers.base import ACLEDNormalizer
    n = ACLEDNormalizer()
    raw = {
        "event_date": "2024-01-01",
        "event_type": "Battles",
        "latitude": 33.26, "longitude": 44.23,
        "fatalities": 45,
        "country": "Iraq",
        "location": "Baghdad",
        "actor1": "ISF", "actor2": "ISIS",
    }
    signals = n.normalize(raw)
    assert len(signals) == 1
    s = signals[0]
    assert s.signal_type.value == "conflict"
    assert s.severity.value in ("high", "critical")
    print("✓ ACLED normalizer")


def test_signal_adapter():
    from logosint.normalizers.base import OpenSkyNormalizer, GDACSNormalizer
    from logosint.adapters.signal_adapter_v2 import SignalAdapterV2
    from logosint.utils.time_utils import utcnow
    now = utcnow()
    n_air = OpenSkyNormalizer()
    n_dis = GDACSNormalizer()
    signals = []
    signals.extend(n_air.normalize({
        "icao": "LTFM", "name": "İstanbul",
        "lat": 41.27, "lon": 28.74,
        "region": "istanbul_canakkale",
        "current": 100, "baseline": 420,
        "delta_pct": -76.0, "zscore": -3.8,
        "timestamp": now.isoformat(),
    }))
    signals.extend(n_dis.normalize({
        "lat": 40.5, "lon": 29.0,
        "alert_level": "Red",
        "event_type": "EQ",
        "country": "Turkey",
        "timestamp": now.isoformat(),
    }))
    adapter = SignalAdapterV2()
    features = adapter.adapt(signals, "istanbul_canakkale", now)
    assert len(features) > 0
    for f in features:
        assert 0.0 <= f.value <= 1.0
        assert f.decay_factor == 1.0, "Double decay bug: decay_factor feature'a kopyalanmamalı"
    print(f"✓ SignalAdapter v2: {len(features)} feature, no double decay")


def test_motor_signals_format():
    from logosint.normalizers.base import OpenSkyNormalizer
    from logosint.adapters.signal_adapter_v2 import SignalAdapterV2
    from logosint.utils.time_utils import utcnow
    now = utcnow()
    n = OpenSkyNormalizer()
    signals = n.normalize({
        "icao": "OMDB", "name": "Dubai",
        "lat": 25.25, "lon": 55.36,
        "region": "korfez",
        "current": 200, "baseline": 680,
        "delta_pct": -70.6, "zscore": -3.5,
        "timestamp": now.isoformat(),
    })
    adapter = SignalAdapterV2()
    features_by_region = {"korfez": adapter.adapt(signals, "korfez", now)}
    motor_signals = adapter.to_motor_signals(features_by_region)
    assert isinstance(motor_signals, dict)
    print(f"✓ Motor signals format: {list(motor_signals.keys())}")


def test_feature_repo():
    from logosint.repositories.feature_repo import init_feature_store, get_scores, get_heatmap
    init_feature_store()
    scores  = get_scores(hours=1, limit=10)
    heatmap = get_heatmap(hours=1)
    assert isinstance(scores, list)
    assert isinstance(heatmap, list)
    print("✓ Feature repo sorguları çalışıyor")


def test_db_writer():
    from logosint.storage.db_writer import DBWriter
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        tmp = f.name
    w = DBWriter(db_path=tmp)
    w.start()
    w.execute("CREATE TABLE IF NOT EXISTS t (x TEXT)", wait=True)
    ok = w.execute("INSERT INTO t VALUES (?)", ("hello",), wait=True)
    assert ok
    rows = w.query("SELECT * FROM t")
    assert len(rows) == 1
    w.stop()
    os.unlink(tmp)
    print("✓ DBWriter single-writer queue")


def test_scan_lock():
    from logosint.schedulers.scan_lock import ScanStatus
    s = ScanStatus()
    assert s.try_acquire("A") is True
    assert s.try_acquire("B") is False
    s.release("A", success=True)
    assert s.try_acquire("C") is True
    s.release("C")
    print("✓ ScanLock concurrent scan önleme")


def test_timezone_utils():
    from logosint.utils.time_utils import utcnow, to_utc
    from datetime import timezone
    now = utcnow()
    assert now.tzinfo == timezone.utc
    naive = to_utc("2024-01-01T12:00:00")
    assert naive.tzinfo == timezone.utc
    gdelt = to_utc("20240115T143000")
    assert gdelt.tzinfo == timezone.utc
    print("✓ Timezone utils UTC-aware")


def run_all_tests():
    print("\n═══ LOGOSİNT TEST SUITE v2 ═══")
    test_opensky_normalizer()
    test_acled_normalizer()
    test_signal_adapter()
    test_motor_signals_format()
    test_feature_repo()
    test_db_writer()
    test_scan_lock()
    test_timezone_utils()
    print("═══ TÜM TESTLER GEÇTİ ═══\n")


if __name__ == "__main__":
    run_all_tests()
