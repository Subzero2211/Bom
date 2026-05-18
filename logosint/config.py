"""
logosint/config.py

Tüm magic number'lar tek dosyada.
Yeni değer ekleyince burada güncelle, başka yerde arama.
"""

from __future__ import annotations


# ═══════════════════════════════════════════════════════════
# ANOMALİ TESPİTİ
# ═══════════════════════════════════════════════════════════

# Z-score volatility floor — std küçük olduğunda z-score patlamasın
# Sistem yeni kurulduğunda baseline gürültülü, false positive üretmesin
ANOMALY_STD_FLOOR        = 3.0   # min std değeri (puan cinsinden)
ANOMALY_ZSCORE_THRESHOLD = 2.5
ANOMALY_REF_DELTA_PCT    = 0.40  # referans baseline'dan %40 sapma
ANOMALY_BOTH_DELTA_PCT   = 0.25  # rolling + ref birlikte

# Ardışık doğrulama — tek scan spike yerine 2 ardışık scan'de görülürse alert
ANOMALY_REQUIRE_PERSISTENCE = False  # True yapınca ardışık 2 scan ister
ANOMALY_PERSISTENCE_WINDOW  = 2

# ═══════════════════════════════════════════════════════════
# EŞİK SEVİYELERİ
# ═══════════════════════════════════════════════════════════

THRESHOLD_L0 = 0    # genel
THRESHOLD_L1 = 30   # aktör analizi başlar
THRESHOLD_L2 = 55   # ardışık zincir takibi
THRESHOLD_L3 = 75   # kritik uyarı + LLM
THRESHOLD_L4 = 90   # kritik pencere aktif

# ═══════════════════════════════════════════════════════════
# SCORING
# ═══════════════════════════════════════════════════════════

# Hybrid edge fusion: geometric + arithmetic mean kombinasyonu
EDGE_FUSION_GEOMETRIC_WEIGHT  = 0.6
EDGE_FUSION_ARITHMETIC_WEIGHT = 0.4

# Probability sigmoid — score → 0-1 probability dönüşümü
PROBABILITY_MIDPOINT = 50.0
PROBABILITY_SLOPE    = 15.0

# ═══════════════════════════════════════════════════════════
# SIGNAL ADAPTER
# ═══════════════════════════════════════════════════════════

# Minimum sinyal değeri — bu altında ignore
MIN_SIGNAL_VALUE = 0.25

# Confidence base — adapter'da feature confidence hesabı
ADAPTER_BASE_CONFIDENCE = 0.5
ADAPTER_MAX_CONFIDENCE  = 0.95
ADAPTER_MIN_CONFIDENCE  = 0.30

# Feature düzeyinde "anlamlı katkı" eşiği
FEATURE_SIGNIFICANT_VALUE = 0.30

# ═══════════════════════════════════════════════════════════
# TEMPORAL DECAY (saat cinsinden half-life)
# ═══════════════════════════════════════════════════════════

DECAY_HALF_LIFE_HOURS = {
    "text_event":      6.0,
    "social_velocity": 2.0,
    "aircraft":       12.0,
    "maritime":       24.0,
    "conflict":       48.0,
    "economic":       72.0,
    "disaster":       24.0,
    "satellite":      48.0,
    "telecom":         6.0,
    "geospatial":     24.0,
}

# ═══════════════════════════════════════════════════════════
# MINIMUM EVIDENCE — feature başına minimum sinyal sayısı
# ═══════════════════════════════════════════════════════════

MIN_EVIDENCE = {
    "pre_conflict_air_activity": 1,
    "maritime_blockade_stress":  1,
    "energy_supply_stress":      2,
    "conflict_intensity":        1,
    "political_instability":     2,
    "sanctions_signal":          2,
    "disaster_impact":           1,
    "covert_operation_signal":   3,
    "financial_crisis_signal":   2,
    "mass_movement_signal":      2,
}

# ═══════════════════════════════════════════════════════════
# SCHEDULER
# ═══════════════════════════════════════════════════════════

SCAN_INTERVAL_SECONDS    = 3600   # 1 saat
SCHEDULER_STARTUP_DELAY  = 30     # collector'ların ısınması
SCAN_TIMEOUT_SECONDS     = 600    # 10 dk max scan süresi
MAX_QUEUED_MANUAL_SCANS  = 5

# ═══════════════════════════════════════════════════════════
# DB
# ═══════════════════════════════════════════════════════════

DB_QUEUE_SIZE       = 10_000
DB_BUSY_TIMEOUT_MS  = 5000
DB_WRITE_TIMEOUT_S  = 30.0
DB_SHUTDOWN_TIMEOUT = 10.0

# ═══════════════════════════════════════════════════════════
# KAYNAK GÜVENİLİRLİK KATSAYILARI
# ═══════════════════════════════════════════════════════════

SOURCE_RELIABILITY = {
    "gdacs":        0.95,
    "acled":        0.90,
    "sentinelhub":  0.90,
    "opensky":      0.85,
    "marine":       0.85,
    "fred":         0.90,
    "comtrade":     0.85,
    "rss_reuters":  0.80,
    "rss_bbc":      0.78,
    "rss_ap":       0.78,
    "rss_aj":       0.70,
    "gdelt":        0.70,
    "telecom":      0.75,
    "reddit":       0.45,
    "telegram":     0.50,
}

# ═══════════════════════════════════════════════════════════
# EXPLAINABILITY
# ═══════════════════════════════════════════════════════════

# Açıklamada gösterilecek max öğe sayısı
EXPLAIN_TOP_EDGES      = 5
EXPLAIN_TOP_MOTORS     = 5
EXPLAIN_TOP_GEOGRAPHIES = 5
