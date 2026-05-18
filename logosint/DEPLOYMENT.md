# LOGOSİNT — Deployment & Integration Notları

## Kurulum

```bash
pip install pydantic>=2.0 flask flask-cors requests feedparser
pip install telethon praw reportlab colorlog schedule
```

## main.py'ye Entegrasyon

Mevcut `main.py` dosyanın sonuna **tek satır** ekle:

```python
# main.py — en alta ekle

from logosint.integration import setup_logosint

# COLLECTORS zaten main.py'de tanımlı
setup_logosint(
    flask_app        = app,
    collectors       = COLLECTORS,
    interval_seconds = 3600,   # saatlik
)
```

Bu kadar. Sistem otomatik olarak:
- DB tablolarını oluşturur
- API blueprint'i kaydeder
- Saatlik scoring döngüsünü başlatır

## Yeni API Endpoints

```
GET  /api/scores        → Senaryo skorları
GET  /api/heatmap       → Bölge ısı haritası
GET  /api/trends        → Trend verisi
GET  /api/features      → Scenario features
GET  /api/signals       → Normalize sinyaller
GET  /api/predictions   → Tahminler
GET  /api/health        → Sistem sağlığı
POST /api/scan          → Manuel tarama
```

## Query Parametreleri

```
/api/scores?region=levant&scenario_id=3&hours=24&min_score=30
/api/heatmap?hours=24
/api/trends?region=hurmuz&scenario_id=21&days=7
/api/features?region=korfez&feature_name=energy_supply_stress
/api/signals?geography=levant&source=gdelt&hours=6
/api/predictions?region=hurmuz&status=pending
/api/health
```

## Testler

```bash
cd osint_engine
python -c "from logosint.integration import run_all_tests; run_all_tests()"
```

## Veri Akışı

```
Collectors (opensky, marine, gdelt, ...)
    ↓
Normalizers → UnifiedSignal
    ↓
SignalAdapter → ScenarioFeature (10 feature type)
    ↓
to_motor_signals() → {motor: {region: value}}
    ↓
scoring_engine.run_scoring_cycle() → 2000 skor
    ↓
ScoringOutput → Prediction (threshold 3+)
    ↓
SQLite (logosint.db)
    ↓
Flask API
```

## Dosya Yapısı

```
logosint/
├── __init__.py
├── scoring_engine.py       ← Mevcut 1800 ağırlık matrisi
├── integration.py          ← main.py entegrasyon noktası + testler
├── models/
│   ├── signals.py          ← UnifiedSignal, ScenarioFeature
│   ├── scoring.py          ← ScoringOutput, Prediction
│   └── health.py           ← HealthSnapshot
├── normalizers/
│   └── base.py             ← Tüm normalizer'lar
├── adapters/
│   └── signal_adapter.py   ← Ontoloji eşleştirme
├── repositories/
│   └── feature_repo.py     ← SQLite feature store
├── scoring/
│   └── runtime.py          ← Full cycle orchestrator
├── schedulers/
│   └── scoring_scheduler.py
├── monitoring/
│   └── health_monitor.py
└── api/
    └── routes.py           ← Flask blueprint
```

## Health Monitor Kullanımı

Collector'larına heartbeat ekle:

```python
from logosint.monitoring.health_monitor import record_heartbeat, CollectorStatus

class OpenSkyCollector(BaseCollector):
    def run(self):
        try:
            events = self.collect()
            record_heartbeat("opensky", CollectorStatus.OK, signals_count=len(events))
            return events
        except Exception as e:
            record_heartbeat("opensky", CollectorStatus.FAILED, error_message=str(e))
            return []
```
