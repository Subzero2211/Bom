# LOGOSİNT — Proje Yapısı
#
# logosint/
# ├── models/
# │   ├── signals.py          ← UnifiedSignal, ScenarioFeature
# │   ├── scoring.py          ← ScoringOutput, Prediction
# │   └── health.py           ← HealthSnapshot
# ├── normalizers/
# │   ├── base.py             ← BaseNormalizer
# │   ├── opensky.py
# │   ├── marine.py
# │   ├── gdelt.py
# │   ├── acled.py
# │   ├── fred.py
# │   ├── gdacs.py
# │   ├── telegram.py
# │   └── reddit.py
# ├── adapters/
# │   ├── signal_adapter.py   ← Ontology mapping
# │   ├── feature_registry.py ← Feature definitions
# │   └── rules.py            ← Adapter rules
# ├── repositories/
# │   ├── base.py
# │   ├── signal_repo.py
# │   ├── feature_repo.py
# │   └── scoring_repo.py
# ├── services/
# │   ├── normalization_service.py
# │   ├── feature_service.py
# │   └── scoring_service.py
# ├── schedulers/
# │   └── scoring_scheduler.py
# ├── monitoring/
# │   ├── health_monitor.py
# │   └── heartbeat.py
# ├── scoring/
# │   └── runtime.py          ← scoring_engine entegrasyonu
# ├── api/
# │   └── routes.py           ← Flask endpoints
# ├── migrations/
# │   └── 001_initial.sql
# └── tests/
#     ├── test_normalizers.py
#     └── test_adapter.py
