"""
config.py — Tüm konfigürasyon buradan yönetilir.
API keylerini buraya yaz, başka hiçbir dosyaya dokunma.
"""

# ═══════════════════════════════════════════════════════════════
# API KEYLERİ
# ═══════════════════════════════════════════════════════════════

OPENSKY = {
    "user": "",          # https://opensky-network.org — ücretsiz kayıt
    "password": "",
}

AISHUB = {
    "user": "",          # https://www.aishub.net — ücretsiz (AIS paylaşımı gerekir)
}

MARINETRAFFIC = {
    "api_key": "",       # https://marinetraffic.com — free tier: 100 istek/gün
}

NEWSAPI = {
    "api_key": "",       # https://newsapi.org — free tier: 100 istek/gün
}

ACLED = {
    "api_key": "",       # https://acleddata.com — ücretsiz akademik kayıt
    "email": "",
}

FRED = {
    "api_key": "",       # https://fred.stlouisfed.org/docs/api — ücretsiz
}

REDDIT = {
    "client_id": "",     # https://www.reddit.com/prefs/apps — ücretsiz
    "client_secret": "",
    "user_agent": "OSINT-Engine/1.0",
}

# ── LLM Entegrasyonu ────────────────────────────────────────

ANTHROPIC = {
    "api_key": "",       # https://console.anthropic.com — buraya API key gir
    # Sen nerede olursan ol çalışır — internet yeterli
    # Fiyat: ~$0.003/1K token (Sonnet). Günlük analiz için < $0.50
    "model":   "claude-sonnet-4-20250514",
}

OLLAMA = {
    # Yerel Llama — bilgisayar açık olmalı
    # Kurulum: https://ollama.com → ollama pull llama3.1:8b
    "url":   "http://localhost:11434",
    "model": "llama3.1:8b",
}

# ── SentinelHub / Copernicus ────────────────────────────────

SENTINELHUB = {
    # https://dataspace.copernicus.eu → ücretsiz kayıt
    # Sonra: https://shapps.dataspace.copernicus.eu/dashboard/
    # "OAuth clients" bölümünden client_id ve client_secret al
    "client_id":     "",
    "client_secret": "",
}

TELEGRAM = {
    "api_id": "",        # https://my.telegram.org — ücretsiz
    "api_hash": "",
    "phone": "",         # kendi numaran
    # İzlenecek public kanallar (username, @ olmadan)
    "channels": [
        "bbcnewsturkce",
        "cnnturk",
        "Reuters",
        "AlJazeeraEnglish",
        "conflicts",
        "intelslava",
        "rybar",          # Askeri analiz (Rusça)
        "wartranslated",
    ],
}

# ═══════════════════════════════════════════════════════════════
# RSS KAYNAKLARI — API key gerekmez
# ═══════════════════════════════════════════════════════════════

RSS_FEEDS = {
    "BBC World":        "https://feeds.bbci.co.uk/news/world/rss.xml",
    "BBC Middle East":  "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml",
    "Reuters World":    "https://feeds.reuters.com/reuters/worldNews",
    "Reuters Business": "https://feeds.reuters.com/reuters/businessNews",
    "Al Jazeera":       "https://www.aljazeera.com/xml/rss/all.xml",
    "AP World":         "https://rsshub.app/apnews/topics/world-news",
    "AP Business":      "https://rsshub.app/apnews/topics/business",
    "Defence Blog":     "https://defence-blog.com/feed/",
    "USNI News":        "https://news.usni.org/feed",           # Deniz kuvvetleri haberleri
    "Jane's":           "https://www.janes.com/feeds/news",
    "Middle East Eye":  "https://www.middleeasteye.net/rss",
    "Haaretz EN":       "https://www.haaretz.com/srv/haaretz-latest-articles.xml",
    "Hurriyet EN":      "https://www.hurriyet.com.tr/rss/economy",
    "TRT World":        "https://www.trtworld.com/rss",
    "Eurasianet":       "https://eurasianet.org/rss.xml",
}

# ═══════════════════════════════════════════════════════════════
# REDDIT SUBREDDITLERİ
# ═══════════════════════════════════════════════════════════════

REDDIT_SUBS = [
    "worldnews",
    "geopolitics",
    "CredibleDefense",
    "europes",
    "middleeast",
    "Turkey",
    "iran",
    "ukraine",
    "Economics",
    "worldpolitics",
]

# ═══════════════════════════════════════════════════════════════
# İZLENECEK BÖLGELER — (lat_min, lat_max, lon_min, lon_max)
# ═══════════════════════════════════════════════════════════════

REGIONS = {
    "marmara":          (40.0, 42.0, 27.0, 31.0),
    "ege":              (36.0, 40.5, 25.0, 28.5),
    "akdeniz_tr":       (35.5, 37.5, 29.0, 37.0),
    "karadeniz":        (41.0, 47.0, 27.0, 42.0),
    "levant":           (29.0, 35.0, 33.0, 38.0),
    "korfez":           (22.0, 28.5, 48.0, 60.0),
    "hurmuz":           (24.0, 27.0, 55.0, 60.0),
    "kizil_deniz":      (12.0, 30.0, 32.0, 44.0),
    "suez":             (28.0, 32.5, 31.0, 35.0),
    "dogu_akdeniz":     (32.0, 38.0, 22.0, 36.0),
    "iran":             (25.0, 40.0, 44.0, 64.0),
    "kafkasya":         (38.0, 44.0, 38.0, 50.0),
    "ukrayna":          (44.0, 52.0, 22.0, 40.0),
    "rusya_guney":      (42.0, 48.0, 36.0, 44.0),
}

# ═══════════════════════════════════════════════════════════════
# ANOMALİ EŞİKLERİ
# ═══════════════════════════════════════════════════════════════

ANOMALY = {
    "zscore_warn":      2.0,    # |z| > 2.0 → uyarı
    "zscore_crit":      3.0,    # |z| > 3.0 → kritik
    "history_window":   48,     # rolling baseline için tarama sayısı
    "min_baseline":     5,      # baseline için minimum veri noktası
    "corr_distance_km": 400,    # coğrafi korelasyon mesafe eşiği
    "corr_time_hours":  12,     # zamansal korelasyon penceresi (saat)
    "news_spike_mult":  2.5,    # haberlerde X kat artış → uyarı
    "news_crit_mult":   5.0,    # haberlerde X kat artış → kritik
}

# ═══════════════════════════════════════════════════════════════
# TARAMA ARALIKLARI (dakika)
# ═══════════════════════════════════════════════════════════════

SCAN_INTERVALS = {
    "rss":          15,     # RSS beslemeleri
    "gdelt":        30,     # GDELT (fazla istek atma)
    "opensky":      20,     # OpenSky — rate limit var
    "marine":       20,     # Marine — 100/gün bütçe
    "acled":        360,    # ACLED günlük güncelleniyor
    "reddit":       30,     # Reddit
    "telegram":     5,      # Telegram (gerçek zamanlı)
    "fred":         1440,   # FRED — günlük yeterli
    "gdacs":        60,     # Afet uyarıları
    "synthesis":    60,     # Sentez raporu üretimi
}

# ═══════════════════════════════════════════════════════════════
# VERİTABANI
# ═══════════════════════════════════════════════════════════════

DATABASE = {
    "path": "osint_data.db",
    "keep_days": 30,        # 30 günden eski → arşivle (silme)
    "archive_dir": "archive",  # archive/YYYY-MM/osint_archive_YYYY-MM.db
}

# ═══════════════════════════════════════════════════════════════
# FLASK API
# ═══════════════════════════════════════════════════════════════

API = {
    "host": "0.0.0.0",
    "port": 5055,
    "debug": False,
}

# ═══════════════════════════════════════════════════════════════
# ANAHTAR KELİME GRUPLARİ — tematik korelasyon için
# ═══════════════════════════════════════════════════════════════

KEYWORDS = {
    "military": [
        "military", "troops", "army", "navy", "air force", "missile",
        "strike", "attack", "defense", "NATO", "warship", "drone",
        "askeri", "ordu", "füze", "saldırı", "savunma", "muharebe",
    ],
    "sanctions": [
        "sanction", "embargo", "ban", "restrict", "freeze", "asset",
        "yaptırım", "ambargo", "yasak", "kısıtlama", "dondurma",
    ],
    "energy": [
        "oil", "gas", "pipeline", "LNG", "OPEC", "crude", "refinery",
        "petrol", "doğalgaz", "boru hattı", "enerji", "rafineri",
    ],
    "crisis": [
        "crisis", "emergency", "escalat", "conflict", "war", "tension",
        "kriz", "acil durum", "çatışma", "savaş", "gerilim", "tırmanma",
    ],
    "diplomacy": [
        "diplomat", "treaty", "agreement", "summit", "negotiat", "sanction",
        "diplomasi", "antlaşma", "anlaşma", "zirve", "müzakere",
    ],
    "economy": [
        "inflation", "recession", "GDP", "trade", "export", "import",
        "currency", "devaluation", "default", "debt",
        "enflasyon", "resesyon", "ticaret", "ihracat", "ithalat", "döviz",
    ],
    "maritime": [
        "ship", "vessel", "tanker", "port", "strait", "blockade", "sea",
        "gemi", "tanker", "liman", "boğaz", "abluka", "deniz",
    ],
    "aviation": [
        "airspace", "flight", "ban", "close", "airport", "aircraft",
        "hava sahası", "uçuş", "yasak", "havalimanı", "uçak",
    ],
}

# ═══════════════════════════════════════════════════════════════
# SENTEZ AĞIRLIKLARI — hangi kaynak ne kadar önemli
# ═══════════════════════════════════════════════════════════════

SOURCE_WEIGHTS = {
    "opensky":      0.85,   # Fiziksel gerçeklik — yüksek güvenilirlik
    "marine":       0.85,
    "acled":        0.90,   # Doğrulanmış çatışma verisi
    "gdelt":        0.70,   # Haber agregasyonu — iyi ama gürültülü
    "rss":          0.65,   # Ham haber — doğrulama gerekir
    "reddit":       0.45,   # Sosyal medya — düşük güvenilirlik
    "telegram":     0.50,   # Gri alan — doğrulama kritik
    "fred":         0.80,   # Resmi ekonomik veri
    "gdacs":        0.95,   # Resmi afet verisi
}

# ── Piyasa / Market ─────────────────────────────────────────────────────────

MARKET = {
    # yfinance ücretsiz — API key gerektirmez
    # Alpha Vantage (opsiyonel, daha fazla veri): alphavantage.co
    "alpha_vantage_key": "",
    # Hangi saatlerde çalışsın (UTC) — piyasa açık saatleri
    "active_hours": list(range(7, 22)),   # 07-22 UTC
}

# ── Satellite Vision ─────────────────────────────────────────────────────────

SATELLITE_VISION = {
    # SENTINELHUB ile aynı key kullanır
    # YOLO model path (boş bırakırsan yolov8n.pt otomatik indirilir)
    "yolo_model": "",       # örn: "models/sar_ship_yolov8.pt"
    # Kaç AOI her çalıştırmada işlensin (öncelik sırasına göre)
    "max_aois_per_run": 5,
}
