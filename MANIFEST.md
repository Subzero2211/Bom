# LOGOSİNT — Dosya Manifest

Bu dosya tüm proje dosyalarının ne işe yaradığını ve hangi versiyonun kullanıldığını gösterir.

---

## KÖK DİZİN

| Dosya | Durum | Açıklama |
|-------|-------|----------|
| `main.py` | ESKİ | Orchestrator. **Sonuna `from logosint.integration import setup_logosint; setup_logosint(app, COLLECTORS)` eklenmeli** |
| `config.py` | ESKİ | API key'ler, kaynak ayarları. Burada API key'leri gir |
| `nodes.py` | GÜNCEL | 67 havalimanı + 94 liman + 15 boğaz + 47 bölge |
| `case_builder.py` | GÜNCEL | GDELT'ten tarihsel vaka imzası çıkarır |
| `case_trainer.py` | GÜNCEL | İnsan etiketli senaryo öğretme (CLI) |
| `requirements.txt` | ESKİ | Paket bağımlılıkları — `pip install -r requirements.txt` |
| `README.md` | ESKİ | Proje açıklaması |

---

## collectors/ — Veri toplayıcılar

| Dosya | Durum | Açıklama |
|-------|-------|----------|
| `base.py` | ESKİ | BaseCollector arayüzü, RawEvent dataclass |
| `opensky_collector.py` | GÜNCEL | Hava trafiği — `nodes.py`'den import eder |
| `marine_collector.py` | GÜNCEL | Deniz trafiği — `nodes.py`'den import eder |
| `gdelt_collector.py` | ESKİ | GDELT haber akışı |
| `acled_collector.py` | ESKİ | ACLED çatışma verisi |
| `rss_collector.py` | ESKİ | BBC/Reuters/AJ/AP feeds |
| `reddit_collector.py` | ESKİ | r/worldnews, r/geopolitics |
| `telegram_collector.py` | ESKİ | Public Telegram kanalları |
| `fred_collector.py` | ESKİ | ABD Fed ekonomik veriler |
| `gdacs_collector.py` | ESKİ | BM afet uyarıları |
| `other_collectors.py` | ESKİ | Ekstra/deneysel |

---

## analysis/ — Eski analiz katmanı

Mevcut sistem hala kullanılıyor — `logosint/` ile paralel çalışır.

| Dosya | Durum | Açıklama |
|-------|-------|----------|
| `anomaly.py` | ESKİ | Z-score anomali tespiti |
| `correlator.py` | ESKİ | Geo + zamansal + tematik korelasyon |
| `interpreter.py` | ESKİ-GÜNCELLENDİ | Senaryo pattern matching + öğrenilmiş vakaları yükler |
| `synthesizer.py` | ESKİ | Saatlik rapor sentezi |
| `pattern_matcher.py` | ESKİ | Pattern eşleştirme |

---

## logosint/ — YENİ PRODUCTION KATMANI

Phase 1-3 hardening ile tüm production fix'leri burada.

### logosint/ kökü

| Dosya | Durum | Açıklama |
|-------|-------|----------|
| `scoring_engine.py` | **GÜNCEL** | 1800 ağırlık matrisi + 50 coğrafya + `compute_scoring_cycle()` pure computation |
| `integration.py` | **GÜNCEL** | main.py'ye tek satır ekleme noktası + test suite |
| `config.py` | **YENİ** | Tüm magic number'lar tek dosyada (anomaly floor, eşikler, decay, vs) |
| `explain.py` | **YENİ** | Her skorun nedenini açıklayan engine + `/api/explain` |
| `DEPLOYMENT.md` | GÜNCEL | Kurulum ve API kullanım rehberi |
| `STRUCTURE.py` | GÜNCEL | Proje yapısı dokümantasyonu |

### logosint/models/

| Dosya | Durum | Açıklama |
|-------|-------|----------|
| `signals.py` | **GÜNCEL** | UnifiedSignal, ScenarioFeature, Coordinates pydantic modelleri |
| `scoring.py` | **GÜNCEL** | ScoringOutput, Prediction modelleri |
| `health.py` | **GÜNCEL** | CollectorHealth, HealthSnapshot |

### logosint/normalizers/

| Dosya | Durum | Açıklama |
|-------|-------|----------|
| `base.py` | **GÜNCEL** | BaseNormalizer + tüm kaynak normalizer'ları (OpenSky, Marine, GDELT, ACLED, FRED, GDACS, Telegram, Reddit) |

### logosint/adapters/

| Dosya | Durum | Açıklama |
|-------|-------|----------|
| `signal_adapter_v2.py` | **GÜNCEL** | Production: double decay fix, geo cache, frozenset keywords, min evidence |

> Not: Eski `signal_adapter.py` silindi.

### logosint/repositories/

| Dosya | Durum | Açıklama |
|-------|-------|----------|
| `feature_repo.py` | **GÜNCEL** | SQLite feature store — signals, features, scores, predictions tabloları |

### logosint/scoring/

| Dosya | Durum | Açıklama |
|-------|-------|----------|
| `runtime_v2.py` | **GÜNCEL** | Production runtime: atomic transaction, scan lock, pure compute entegrasyonu |

> Not: Eski `runtime.py` silindi.

### logosint/schedulers/

| Dosya | Durum | Açıklama |
|-------|-------|----------|
| `scoring_scheduler.py` | **GÜNCEL** | Saatlik scoring scheduler — runtime_v2 kullanır |
| `scan_lock.py` | **GÜNCEL** | ScanStatus state machine + bounded manual scan queue |

### logosint/monitoring/

| Dosya | Durum | Açıklama |
|-------|-------|----------|
| `health_monitor.py` | **GÜNCEL** | Heartbeat sistemi + HealthSnapshot üretimi |

### logosint/storage/

| Dosya | Durum | Açıklama |
|-------|-------|----------|
| `db_writer.py` | **GÜNCEL** | Single-writer queue: WAL mode, accepting_writes state, dropped_count metrik |
| `scan_transaction.py` | **GÜNCEL** | Atomik scan transaction — tek batch'te commit veya rollback |

### logosint/utils/

| Dosya | Durum | Açıklama |
|-------|-------|----------|
| `time_utils.py` | **GÜNCEL** | UTC-aware datetime yardımcıları |

### logosint/api/

| Dosya | Durum | Açıklama |
|-------|-------|----------|
| `routes.py` | **GÜNCEL** | Flask blueprint: 9 endpoint (scores, heatmap, trends, features, signals, predictions, health, scan, scan/status, explain) |

---

## api/ — Eski API

| Dosya | Durum | Açıklama |
|-------|-------|----------|
| `server.py` | ESKİ-GÜNCELLENDİ | Mevcut Flask app — dashboard route'u + yeni LOGOSİNT blueprint kayıtlı |

---

## storage/ — Eski DB

| Dosya | Durum | Açıklama |
|-------|-------|----------|
| `db.py` | ESKİ | Mevcut SQLite işlemleri (anomali, korelasyon, rapor tabloları) |

---

## models/ — Eski modeller

| Dosya | Durum | Açıklama |
|-------|-------|----------|
| `event.py` | ESKİ | RawEvent, NormalizedEvent dataclass'ları |
| `intelligence.py` | ESKİ | IntelligenceReport, ScenarioMatch |

---

## reports/

| Dosya | Durum | Açıklama |
|-------|-------|----------|
| `pdf_reporter.py` | ESKİ | reportlab ile saatlik PDF üretimi |
| `pdf_generator.py` | ESKİ | Yardımcı PDF formatlayıcı |

---

## templates/

| Dosya | Durum | Açıklama |
|-------|-------|----------|
| `dashboard.html` | **GÜNCEL** | 7 sekmeli production dashboard (Ana, Harita, Hava, Deniz, Haberler, Raporlar, Sağlık) |

---

# ENTEGRASYON

`main.py`'nin sonuna **tek satır** ekle:

```python
from logosint.integration import setup_logosint
setup_logosint(app, collectors=COLLECTORS, interval_seconds=3600)
```

Bu kadar. Sistem otomatik olarak:
- DBWriter'ı başlatır (single-writer queue)
- Scoring scheduler'ı çalıştırır (saatlik)
- API blueprint'i kaydeder
- Health monitor'u aktive eder
- Graceful shutdown handler'ları kaydeder

---

# YAPILAN PRODUCTION FİX'LERİ

## Phase 1 — Stabilization

| Sorun | Çözüm | Dosya |
|-------|-------|-------|
| SQLite concurrent write | Single-writer queue | `storage/db_writer.py` |
| Partial scan persistence | Atomic ScanTransaction | `storage/scan_transaction.py` |
| Concurrent scan race | Scheduler kilidi | `schedulers/scan_lock.py` |
| Naive datetime | UTC-aware everywhere | `utils/time_utils.py` |
| Double decay bug | adapter_v2 — decay sadece contribution'da | `adapters/signal_adapter_v2.py` |

## Phase 2 — Integration

| Sorun | Çözüm | Dosya |
|-------|-------|-------|
| Signal adapter leakage | Temiz pipeline | `adapters/signal_adapter_v2.py` |
| Scoring disconnected | runtime_v2 + compute_scoring_cycle | `scoring/runtime_v2.py` + `scoring_engine.py` |
| Eksik API endpoints | 9 endpoint | `api/routes.py` |

## Phase 3 — Reliability

| Sorun | Çözüm | Dosya |
|-------|-------|-------|
| Silent write failure | dropped_count + accepting_writes | `storage/db_writer.py` |
| Manual scan loss | Bounded FIFO queue (max 5) | `schedulers/scan_lock.py` |
| Survivorship bias | Tüm threshold≥1 predictions kaydedilir | `scoring/runtime_v2.py` |
| Volatility floor | std min=3.0, false positive azaltır | `scoring_engine.py` |
| Magic numbers | config.py'de toplandı | `config.py` |
| Black-box scoring | Explainability engine + `/api/explain` | `explain.py` |

---

# TEST

```bash
cd osint_engine
python -c "from logosint.integration import run_all_tests; run_all_tests()"
```

Beklenen çıktı:
- OpenSky normalizer ✓
- ACLED normalizer ✓
- SignalAdapter v2 (no double decay) ✓
- Motor signals format ✓
- Feature repo sorguları ✓
- DBWriter single-writer queue ✓
- ScanLock concurrent scan önleme ✓
- Timezone utils UTC-aware ✓
