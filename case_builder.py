"""
case_builder.py — Tarihsel Vaka İmzası Oluşturucu

GDELT'ten belirli bir olay dönemine ait haber anomali profilini otomatik çıkarır.
Oluşturulan taslak JSON'u sen fiziksel veri ve bağlamla tamamlarsın.

Kullanım:
    python case_builder.py

    Ya da doğrudan:
    builder = CaseBuilder()
    builder.build(
        name="Kaşıkçı Cinayeti",
        event_date="2018-10-02",
        pre_days=14,
        post_days=7,
        countries=["Turkey", "Saudi Arabia"],
        regions=["marmara", "levant"],
        keywords=["Saudi", "journalist", "Istanbul", "Khashoggi"]
    )
"""

import json
import time
import logging
import requests
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("CaseBuilder")

CASES_DIR = Path("cases")
GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/search"
GDELT_GEO_API = "https://api.gdeltproject.org/api/v2/geo/search"


# ═══════════════════════════════════════════════════════════════
# GDELT SORGU KATMANI
# ═══════════════════════════════════════════════════════════════

def gdelt_query(
    query: str,
    start: datetime,
    end: datetime,
    mode: str = "artlist",
    max_records: int = 50,
) -> list[dict]:
    """
    GDELT Doc 2.0 API — belirli bir zaman aralığında sorgu.
    GDELT zaman formatı: YYYYMMDDHHMMSS
    """
    params = {
        "query":      query,
        "mode":       mode,
        "maxrecords": max_records,
        "format":     "json",
        "startdatetime": start.strftime("%Y%m%d%H%M%S"),
        "enddatetime":   end.strftime("%Y%m%d%H%M%S"),
        "sort":       "hybridrel",
    }
    try:
        r = requests.get(GDELT_DOC_API, params=params, timeout=20)
        if r.status_code == 200:
            return r.json().get("articles", [])
        log.warning("GDELT HTTP %d — %s", r.status_code, r.text[:100])
        return []
    except Exception as e:
        log.error("GDELT sorgu hatası: %s", e)
        return []


def gdelt_tone_query(
    query: str,
    start: datetime,
    end: datetime,
) -> dict:
    """
    GDELT tonlama analizi — pozitif/negatif haber dengesi.
    mode=tonechart: zaman içinde ton değişimi
    """
    params = {
        "query":         query,
        "mode":          "tonechart",
        "format":        "json",
        "startdatetime": start.strftime("%Y%m%d%H%M%S"),
        "enddatetime":   end.strftime("%Y%m%d%H%M%S"),
    }
    try:
        r = requests.get(GDELT_DOC_API, params=params, timeout=20)
        if r.status_code == 200:
            return r.json()
        return {}
    except Exception as e:
        log.error("GDELT ton sorgu hatası: %s", e)
        return {}


# ═══════════════════════════════════════════════════════════════
# ZAMAN DİLİMLERİ ANALİZİ
# Olaydan önce: 30 gün, 14 gün, 7 gün, 3 gün, 1 gün
# Olaydan sonra: 1 gün, 3 gün, 7 gün, 30 gün
# ═══════════════════════════════════════════════════════════════

WINDOWS_PRE = [
    ("30_gün_önce",  30, 14),
    ("14_gün_önce",  14,  7),
    ("7_gün_önce",    7,  3),
    ("3_gün_önce",    3,  1),
    ("1_gün_önce",    1,  0),
]

WINDOWS_POST = [
    ("1_gün_sonra",   0,  1),
    ("3_gün_sonra",   0,  3),
    ("7_gün_sonra",   0,  7),
    ("30_gün_sonra",  0, 30),
]


def _window_query(
    base_query: str,
    event_date: datetime,
    days_before: int,
    days_after: int,
) -> tuple[list, int]:
    """Belirli pencerede makale çek, sayı döndür."""
    start = event_date - timedelta(days=days_before)
    end   = event_date + timedelta(days=days_after)
    articles = gdelt_query(base_query, start, end, max_records=100)
    return articles, len(articles)


def _extract_goldstein(articles: list) -> float:
    """Makalelerin ortalama Goldstein skorunu hesapla (-10 şiddet, +10 işbirliği)."""
    scores = []
    for a in articles:
        g = a.get("goldstein")
        if g is not None:
            try:
                scores.append(float(g))
            except Exception:
                pass
    return round(sum(scores) / len(scores), 3) if scores else 0.0


def _extract_top_themes(articles: list, n: int = 10) -> list[str]:
    """En sık geçen temalar."""
    theme_count = defaultdict(int)
    for a in articles:
        themes = a.get("themes", "").split(";") if a.get("themes") else []
        for t in themes:
            t = t.strip()
            if t:
                theme_count[t] += 1
    return [t for t, _ in sorted(theme_count.items(), key=lambda x: -x[1])[:n]]


def _extract_top_sources(articles: list, n: int = 5) -> list[str]:
    """En çok haber yapan kaynaklar."""
    src_count = defaultdict(int)
    for a in articles:
        d = a.get("domain", "")
        if d:
            src_count[d] += 1
    return [s for s, _ in sorted(src_count.items(), key=lambda x: -x[1])[:n]]


def _extract_geo_spread(articles: list) -> dict:
    """Haberlerin coğrafi dağılımı."""
    country_count = defaultdict(int)
    for a in articles:
        c = a.get("sourcecountry", "")
        if c:
            country_count[c] += 1
    return dict(sorted(country_count.items(), key=lambda x: -x[1])[:10])


def _compute_spike(counts: dict, baseline_key: str, comparison_key: str) -> float:
    """İki pencere arasındaki artış oranı."""
    base = counts.get(baseline_key, 1)
    comp = counts.get(comparison_key, 0)
    if base == 0:
        return float("inf") if comp > 0 else 0.0
    return round(comp / base, 2)


# ═══════════════════════════════════════════════════════════════
# ANA VAKA OLUŞTURUCU
# ═══════════════════════════════════════════════════════════════

class CaseBuilder:

    def build(
        self,
        name: str,
        event_date: str,           # "YYYY-MM-DD"
        pre_days: int = 30,
        post_days: int = 14,
        countries: list[str] = None,
        regions: list[str] = None,
        keywords: list[str] = None,
        extra_queries: list[str] = None,
        notes: str = "",
    ) -> Optional[dict]:
        """
        Olay için GDELT'ten tarihsel imza çıkar.

        Parametreler:
            name        : Olay adı (dosya adı olarak kullanılır)
            event_date  : Olayın tarihi "YYYY-MM-DD"
            pre_days    : Öncesine kaç güne bakılacak
            post_days   : Sonrasına kaç güne bakılacak
            countries   : İzlenecek ülke isimleri (GDELT sorguya eklenir)
            regions     : config.REGIONS key'leri (meta veri için)
            keywords    : Olaya özgü anahtar kelimeler
            extra_queries: Ek GDELT sorguları
            notes       : Elle not ekle
        """
        CASES_DIR.mkdir(exist_ok=True)

        event_dt = datetime.strptime(event_date, "%Y-%m-%d")
        log.info("═" * 60)
        log.info("VAKA OLUŞTURULUYOR: %s (%s)", name, event_date)

        # Ana sorgu oluştur
        country_str = " OR ".join(countries or [])
        kw_str = " OR ".join(keywords or [])
        base_query_parts = [p for p in [country_str, kw_str] if p]
        base_query = " ".join(base_query_parts) if base_query_parts else name

        log.info("Sorgu: %s", base_query[:80])

        # ── ZAMAN PENCERELERİ ANALİZİ ───────────────────────
        window_counts = {}
        window_details = {}

        all_windows = [
            ("30_gun_once",  30,  0),
            ("14_gun_once",  14,  0),
            ("7_gun_once",    7,  0),
            ("3_gun_once",    3,  0),
            ("1_gun_once",    1,  0),
            ("olay_gunu",     0,  1),
            ("3_gun_sonra",   0,  3),
            ("7_gun_sonra",   0,  7),
            ("30_gun_sonra",  0, 30),
        ]

        for label, before, after in all_windows:
            log.info("  Pencere: %s...", label)
            start = event_dt - timedelta(days=before)
            end   = event_dt + timedelta(days=after)

            # Zaman aralığı çok dar ise minimum 1 gün
            if start >= end:
                end = start + timedelta(days=1)

            articles = gdelt_query(base_query, start, end, max_records=100)
            window_counts[label] = len(articles)
            window_details[label] = {
                "count":          len(articles),
                "avg_goldstein":  _extract_goldstein(articles),
                "top_themes":     _extract_top_themes(articles, 8),
                "top_sources":    _extract_top_sources(articles, 5),
                "geo_spread":     _extract_geo_spread(articles),
                "sample_titles":  [a.get("title","")[:100] for a in articles[:5]],
            }
            time.sleep(1.5)   # GDELT rate limit koruması

        # ── SPİKE HESAPLA ────────────────────────────────────
        # Baseline: 30-14 gün arası ortalama haber yoğunluğu
        baseline_count = max(1, window_counts.get("30_gun_once", 1))
        spikes = {
            label: round(window_counts.get(label, 0) / baseline_count, 2)
            for label in window_counts
        }

        # En yüksek spike noktası
        peak_window = max(window_counts, key=window_counts.get)
        peak_spike  = spikes.get(peak_window, 0)

        # ── TEMA ANALİZİ ─────────────────────────────────────
        # Olay günü + 3 gün öncesindeki temalar
        pre_articles, _ = _window_query(base_query, event_dt, 7, 0)
        dominant_themes = _extract_top_themes(pre_articles, 15)

        # Olay sonrası temalar
        post_articles, _ = _window_query(base_query, event_dt, 0, 7)
        post_themes = _extract_top_themes(post_articles, 10)

        # ── TON ANALİZİ ──────────────────────────────────────
        log.info("  Ton analizi yapılıyor...")
        pre_tone  = _extract_goldstein(pre_articles)
        post_tone = _extract_goldstein(post_articles)
        tone_shift = round(post_tone - pre_tone, 3)

        # ── EK SORGULAR ──────────────────────────────────────
        extra_results = {}
        for eq in (extra_queries or []):
            log.info("  Ek sorgu: %s", eq[:50])
            arts = gdelt_query(
                eq,
                event_dt - timedelta(days=pre_days),
                event_dt + timedelta(days=post_days),
                max_records=50,
            )
            extra_results[eq[:40]] = {
                "count": len(arts),
                "themes": _extract_top_themes(arts, 5),
                "goldstein": _extract_goldstein(arts),
            }
            time.sleep(1.0)

        # ── VAKA İMZASI OLUŞTUR ──────────────────────────────
        # Bu imza interpreter.py'nin pattern matching'inde kullanılacak
        signal_signature = _infer_signal_signature(
            window_counts, spikes, dominant_themes, pre_tone, post_tone
        )

        # ── VAKA DOSYASI ─────────────────────────────────────
        case = {
            # Meta
            "id":          _make_id(name, event_date),
            "name":        name,
            "event_date":  event_date,
            "created_at":  datetime.utcnow().isoformat(),
            "source":      "gdelt_auto",
            "notes":       notes,

            # Coğrafya
            "countries":   countries or [],
            "regions":     regions or [],
            "keywords":    keywords or [],

            # GDELT pencere analizi
            "window_counts":  window_counts,
            "window_details": window_details,
            "spikes":         spikes,
            "peak_window":    peak_window,
            "peak_spike":     peak_spike,

            # Tema profili
            "pre_event_themes":  dominant_themes,
            "post_event_themes": post_themes,
            "new_post_themes":   [t for t in post_themes if t not in dominant_themes],

            # Ton
            "pre_tone":   pre_tone,
            "post_tone":  post_tone,
            "tone_shift": tone_shift,

            # Ek sorgular
            "extra_queries": extra_results,

            # İmza — interpreter.py bu alanı kullanır
            "signal_signature": signal_signature,

            # Manuel tamamlama için boş alanlar
            # Bunları sen doldurursun
            "physical_signals": {
                "air":      {},    # {"LTFM": -0.15, "OMDB": +0.40} gibi
                "sea":      {},    # {"TRISA": -0.30} gibi
                "economic": {},    # {"oil_price": +0.22} gibi
                "conflict": [],    # ["saldırı türü", "lokasyon"] gibi
            },
            "outcome": "",         # "Diplomatik kriz", "Savaş", "Anlaşma" vb.
            "pattern_type": signal_signature.get("inferred_pattern", "unknown"),
            "lead_time_days": _estimate_lead_time(spikes),
            "confidence_in_signature": 0.7,  # Sen güncellersin

            # Gelecekte pattern matching için eşik
            "matching_thresholds": {
                "min_spike_ratio":    2.0,
                "min_tone_shift":    -1.0,
                "required_themes":    dominant_themes[:3],
            },
        }

        # Dosyaya kaydet
        filename = CASES_DIR / f"{case['id']}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(case, f, ensure_ascii=False, indent=2)

        log.info("═" * 60)
        log.info("Vaka kaydedildi: %s", filename)
        log.info("Peak spike: %s → %.1fx baseline", peak_window, peak_spike)
        log.info("Ton değişimi: %.2f → %.2f (Δ%.2f)", pre_tone, post_tone, tone_shift)
        log.info("Baskın öncesi temalar: %s", ", ".join(dominant_themes[:5]))
        log.info("")
        log.info("MANUEL TAMAMLAMA GEREKİYOR:")
        log.info("  physical_signals: Uçuş/gemi verilerini elle ekle")
        log.info("  outcome: Olayın sonucunu yaz")
        log.info("  pattern_type: '%s' — doğru mu?", case["pattern_type"])
        log.info("═" * 60)

        return case


def _make_id(name: str, date: str) -> str:
    safe = name.lower().replace(" ", "_").replace("/", "_")[:30]
    year = date[:4]
    return f"{safe}_{year}"


def _estimate_lead_time(spikes: dict) -> int:
    """
    Spike'ın ne kadar önceden başladığını tahmin et.
    """
    if spikes.get("3_gun_once", 0) >= 2.0:
        return 3
    if spikes.get("7_gun_once", 0) >= 2.0:
        return 7
    if spikes.get("14_gun_once", 0) >= 2.0:
        return 14
    return 30


def _infer_signal_signature(
    counts: dict,
    spikes: dict,
    themes: list,
    pre_tone: float,
    post_tone: float,
) -> dict:
    """
    Haber profilinden otomatik sinyal imzası çıkar.
    interpreter.py'nin pattern'larıyla uyumlu format.
    """
    theme_str = " ".join(themes).lower()

    # Pattern tahmini
    pattern = "unknown"
    if any(w in theme_str for w in ["military", "war", "attack", "battle", "weapons"]):
        pattern = "military_op_prep"
    elif any(w in theme_str for w in ["sanction", "embargo", "ban", "restrict"]):
        pattern = "economic_sanctions"
    elif any(w in theme_str for w in ["diplomat", "ambassador", "treaty", "summit"]):
        pattern = "diplomatic_incident"
    elif any(w in theme_str for w in ["oil", "gas", "pipeline", "energy", "opec"]):
        pattern = "energy_supply_shock"
    elif any(w in theme_str for w in ["refugee", "humanitarian", "civilian", "displacement"]):
        pattern = "humanitarian_crisis"
    elif any(w in theme_str for w in ["coup", "revolution", "protest", "uprising"]):
        pattern = "military_op_prep"   # Darbe öncesi de benzer imza
    elif any(w in theme_str for w in ["earthquake", "flood", "hurricane", "tsunami"]):
        pattern = "natural_disaster_geopolitical"

    # Anomali yoğunluğu
    max_spike = max(spikes.values()) if spikes else 0
    intensity = "critical" if max_spike >= 5 else "warning" if max_spike >= 2.5 else "info"

    # Öncü sinyal penceresi
    early_warning = spikes.get("7_gun_once", 0) >= 2.0 or spikes.get("14_gun_once", 0) >= 2.0

    return {
        "inferred_pattern":  pattern,
        "intensity":         intensity,
        "max_spike":         round(max_spike, 2),
        "early_warning":     early_warning,
        "tone_direction":    "negative" if post_tone < pre_tone - 0.5 else "positive" if post_tone > pre_tone + 0.5 else "neutral",
        "dominant_domain":   "news",   # GDELT haber ağırlıklı — fiziksel veri manuel
        "keywords_in_themes": themes[:5],
    }


# ═══════════════════════════════════════════════════════════════
# TOPLU VAKA OLUŞTURMA
# ═══════════════════════════════════════════════════════════════

PREDEFINED_CASES = [
    {
        "name": "Kaşıkçı Cinayeti",
        "event_date": "2018-10-02",
        "countries": ["Turkey", "Saudi Arabia"],
        "regions": ["marmara", "levant"],
        "keywords": ["Khashoggi", "Saudi Arabia", "Istanbul", "journalist", "murder"],
        "extra_queries": [
            "Saudi Arabia Turkey diplomatic crisis 2018",
            "MBS Mohammed bin Salman journalist",
        ],
        "notes": "Suudi gazeteci Cemal Kaşıkçı İstanbul'daki Suudi konsolosluğunda öldürüldü.",
    },
    {
        "name": "Rusya Ukrayna İşgali",
        "event_date": "2022-02-24",
        "countries": ["Russia", "Ukraine"],
        "regions": ["ukrayna", "rusya_guney", "karadeniz"],
        "keywords": ["Russia", "Ukraine", "invasion", "military", "NATO", "Donbas"],
        "extra_queries": [
            "Russia military buildup Ukraine border 2022",
            "NATO Ukraine tension February 2022",
            "Russia Ukraine gas pipeline 2022",
        ],
        "notes": "Rusya'nın Ukrayna'ya tam ölçekli askeri işgali.",
    },
    {
        "name": "Hamas İsrail Savaşı 7 Ekim",
        "event_date": "2023-10-07",
        "countries": ["Israel", "Palestine", "Gaza"],
        "regions": ["levant"],
        "keywords": ["Hamas", "Israel", "Gaza", "attack", "rockets", "war"],
        "extra_queries": [
            "Israel Gaza military operation October 2023",
            "Hamas attack Israel kibbutz festival",
            "Ben Gurion airport flight cancellations",
        ],
        "notes": "Hamas'ın İsrail'e saldırısı ve İsrail'in Gazze operasyonu.",
    },
    {
        "name": "Türkiye Darbe Girişimi",
        "event_date": "2016-07-15",
        "countries": ["Turkey"],
        "regions": ["marmara", "akdeniz_tr"],
        "keywords": ["Turkey", "coup", "military", "Erdogan", "Gulen", "putsch"],
        "extra_queries": [
            "Turkey military coup attempt July 2016",
            "Ataturk airport Istanbul closure 2016",
            "Turkey purge military 2016",
        ],
        "notes": "Türkiye'de başarısız askeri darbe girişimi.",
    },
    {
        "name": "Suudi Aramco Drone Saldırısı",
        "event_date": "2019-09-14",
        "countries": ["Saudi Arabia", "Iran", "Yemen"],
        "regions": ["korfez", "kizil_deniz"],
        "keywords": ["Aramco", "Saudi Arabia", "drone", "attack", "oil", "Abqaiq"],
        "extra_queries": [
            "Saudi Arabia oil facility attack September 2019",
            "Iran Houthi drone strike Aramco",
            "oil price spike September 2019",
        ],
        "notes": "Suudi Arabistan'ın Abqaiq petrol tesislerine drone saldırısı.",
    },
    {
        "name": "Katar Körfez Ablukası",
        "event_date": "2017-06-05",
        "countries": ["Qatar", "Saudi Arabia", "UAE", "Egypt"],
        "regions": ["korfez"],
        "keywords": ["Qatar", "blockade", "Saudi Arabia", "UAE", "diplomacy", "embargo"],
        "extra_queries": [
            "Qatar diplomatic crisis June 2017",
            "Qatar airways flight ban Gulf",
            "Qatar Turkey food aid 2017",
        ],
        "notes": "Suudi Arabistan liderliğinde Katar'a uygulanan diplomatik ve ekonomik ambargo.",
    },
    {
        "name": "Suriye İç Savaşı Başlangıcı",
        "event_date": "2011-03-15",
        "countries": ["Syria"],
        "regions": ["levant"],
        "keywords": ["Syria", "protest", "Assad", "Deraa", "uprising", "Arab Spring"],
        "extra_queries": [
            "Syria protests March 2011 Deraa",
            "Arab Spring Syria 2011",
            "Syria government crackdown 2011",
        ],
        "notes": "Suriye iç savaşının fitilini ateşleyen Deraa protestoları.",
    },
    {
        "name": "İran JCPOA Çekilme ABD",
        "event_date": "2018-05-08",
        "countries": ["Iran", "United States"],
        "regions": ["iran", "korfez"],
        "keywords": ["Iran", "JCPOA", "nuclear deal", "sanctions", "Trump", "withdrawal"],
        "extra_queries": [
            "Trump Iran nuclear deal withdrawal 2018",
            "Iran sanctions reimposed 2018",
            "Iran oil exports sanctions",
        ],
        "notes": "ABD'nin İran nükleer anlaşmasından çekilmesi ve yaptırımların yeniden başlaması.",
    },
    {
        "name": "Hürmüz Tanker Krizleri",
        "event_date": "2019-06-13",
        "countries": ["Iran", "UAE", "Oman"],
        "regions": ["hurmuz", "korfez"],
        "keywords": ["tanker", "attack", "Hormuz", "Iran", "Gulf of Oman", "mine"],
        "extra_queries": [
            "tanker attack Gulf of Oman June 2019",
            "Iran Strait of Hormuz tension 2019",
            "oil tanker mine attack 2019",
        ],
        "notes": "Hürmüz Boğazı yakınında iki petrol tankerine saldırı.",
    },
    {
        "name": "Ever Given Süveyş Tıkanıklığı",
        "event_date": "2021-03-23",
        "countries": ["Egypt"],
        "regions": ["suez"],
        "keywords": ["Ever Given", "Suez Canal", "blocked", "container ship", "shipping"],
        "extra_queries": [
            "Ever Given Suez Canal blocked March 2021",
            "Suez Canal shipping delay supply chain",
            "Ever Given refloated",
        ],
        "notes": "Ever Given konteyner gemisinin Süveyş Kanalı'nı 6 gün boyunca tıkaması.",
    },
    {
        "name": "Kahramanmaraş Depremi",
        "event_date": "2023-02-06",
        "countries": ["Turkey", "Syria"],
        "regions": ["akdeniz_tr", "levant"],
        "keywords": ["earthquake", "Turkey", "Syria", "Kahramanmaras", "disaster"],
        "extra_queries": [
            "Turkey earthquake February 2023 Kahramanmaras",
            "Turkey Syria earthquake humanitarian aid",
            "Incirlik airbase earthquake Turkey",
        ],
        "notes": "7.8 büyüklüğünde deprem. 50.000'den fazla can kaybı.",
    },
    {
        "name": "Kızıldeniz Husi Saldırıları",
        "event_date": "2023-12-01",
        "countries": ["Yemen", "Saudi Arabia", "Djibouti"],
        "regions": ["kizil_deniz", "suez"],
        "keywords": ["Houthi", "Red Sea", "shipping", "attack", "Yemen", "Bab el-Mandeb"],
        "extra_queries": [
            "Houthi attack Red Sea shipping December 2023",
            "Bab el-Mandeb maritime security 2023",
            "shipping companies Red Sea reroute Cape of Good Hope",
        ],
        "notes": "Husi saldırıları nedeniyle büyük deniz taşımacılığı şirketlerinin Kızıldeniz'i terk etmesi.",
    },
]


def build_all(skip_existing: bool = True):
    """Tüm önceden tanımlı vakaları oluştur."""
    builder = CaseBuilder()
    CASES_DIR.mkdir(exist_ok=True)

    for case_def in PREDEFINED_CASES:
        case_id = _make_id(case_def["name"], case_def["event_date"])
        output_file = CASES_DIR / f"{case_id}.json"

        if skip_existing and output_file.exists():
            log.info("Atlanıyor (mevcut): %s", case_id)
            continue

        log.info("\n%s\n", "═" * 60)
        builder.build(**{k: v for k, v in case_def.items()})
        log.info("Bir sonraki vaka için 3 saniye bekleniyor...")
        time.sleep(3)   # GDELT rate limit


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    print("""
╔══════════════════════════════════════════════════════════════╗
║         OSINT CASE BUILDER — Tarihsel Vaka Oluşturucu       ║
╠══════════════════════════════════════════════════════════════╣
║  1. Tüm önceden tanımlı vakaları oluştur                     ║
║  2. Tek vaka oluştur (interaktif)                            ║
║  3. Belirli bir vakaları oluştur (numara gir)                ║
╚══════════════════════════════════════════════════════════════╝
""")
    print("Mevcut vakalar:")
    for i, c in enumerate(PREDEFINED_CASES, 1):
        print(f"  {i:2}. {c['name']} ({c['event_date']})")

    print()
    choice = input("Seçim (1/2/3, Enter=1): ").strip() or "1"

    if choice == "1":
        print("\nTüm vakalar oluşturuluyor (bu birkaç dakika sürebilir)...\n")
        build_all()

    elif choice == "2":
        print("\nInteraktif vaka oluşturma:")
        name       = input("Olay adı: ").strip()
        date       = input("Tarih (YYYY-MM-DD): ").strip()
        countries  = input("Ülkeler (virgülle ayır): ").strip().split(",")
        keywords   = input("Anahtar kelimeler (virgülle ayır): ").strip().split(",")
        notes      = input("Not (opsiyonel): ").strip()
        builder = CaseBuilder()
        builder.build(
            name=name, event_date=date,
            countries=[c.strip() for c in countries],
            keywords=[k.strip() for k in keywords],
            notes=notes,
        )

    elif choice == "3":
        nums = input("Vaka numaraları (virgülle ayır, örn: 1,3,5): ").strip()
        builder = CaseBuilder()
        for n in nums.split(","):
            try:
                idx = int(n.strip()) - 1
                case_def = PREDEFINED_CASES[idx]
                builder.build(**{k: v for k, v in case_def.items()})
                time.sleep(3)
            except (ValueError, IndexError) as e:
                log.error("Geçersiz numara: %s — %s", n, e)
