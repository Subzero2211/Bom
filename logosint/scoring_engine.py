"""
logosint/scoring_engine.py

LOGOSİNT — Çok Katmanlı Senaryo Puanlama Motoru

Mimari:
- 10 motor → 45 kenar → 40 senaryo → 1800 ağırlık
- 50 coğrafya × 40 senaryo = 2000 bölgesel skor (saatlik)
- Kayan + referans baseline
- 5 eşik seviyesi (0-4)
"""

import sqlite3
import json
import math
import logging
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

log = logging.getLogger("ScoringEngine")

DB_PATH = "logosint.db"

# ═══════════════════════════════════════════════════════════
# MOTORLAR
# ═══════════════════════════════════════════════════════════

MOTORS = [
    "opensky",
    "marine",
    "gdelt",
    "telegram",
    "acled",
    "fred",
    "gdacs",
    "sentinelhub",
    "comtrade",
    "telecom",
]

# ═══════════════════════════════════════════════════════════
# SENARYOLAR
# ═══════════════════════════════════════════════════════════

SCENARIOS = {
    # Askeri & Güvenlik
    1:  "Bölgesel askeri operasyon",
    2:  "Sınır ötesi hava harekâtı",
    3:  "Deniz ablukası",
    4:  "Kara işgali",
    5:  "Gizli operasyon / suikast",
    6:  "Paralı asker / vekil güç aktivasyonu",
    7:  "Terör saldırısı",
    8:  "İç savaş başlangıcı",
    9:  "Nükleer / KBY tehdit",
    10: "Siber saldırı + fiziksel etki",
    11: "Altyapı sabotajı",
    12: "Hava sahası kapanması",
    # Diplomatik & Politik
    13: "Diplomatik kriz",
    14: "Yaptırım paketi",
    15: "Darbe girişimi",
    16: "Hükümet çöküşü",
    17: "Seçim krizi",
    18: "İttifak değişikliği",
    19: "Toprak anlaşmazlığı tırmanması",
    20: "Uluslararası mahkeme kararı",
    # Ekonomik
    21: "Enerji arz şoku",
    22: "Finansal kriz",
    23: "Tedarik zinciri kopuşu",
    24: "Gıda / su krizi",
    25: "Ticaret savaşı / ambargo",
    26: "Stratejik hammadde krizi",
    # Doğal Afet
    27: "Büyük deprem",
    28: "Tsunami",
    29: "Sel / taşkın",
    30: "Volkanik aktivite",
    31: "Aşırı kuraklık",
    32: "Kasırga / siklon",
    # İnsani & Sosyal
    33: "Kitlesel göç dalgası",
    34: "Mülteci krizi",
    35: "Salgın hastalık başlangıcı",
    36: "Kitlesel protesto / devrim",
    37: "İnsani kriz / kıtlık",
    # Yapısal
    38: "Devlet çöküşü",
    39: "Bölgesel güç yeniden konuşlanması",
    40: "Hibrit savaş kampanyası",
}

# ═══════════════════════════════════════════════════════════
# KENARLAR — (motor_a, motor_b) çiftleri
# ═══════════════════════════════════════════════════════════

EDGES = [
    # Grup A — Fiziksel trafik
    (1,  "opensky",    "marine"),
    (2,  "opensky",    "gdacs"),
    (3,  "marine",     "gdacs"),
    (4,  "opensky",    "sentinelhub"),
    (5,  "marine",     "sentinelhub"),
    (6,  "gdacs",      "sentinelhub"),
    # Grup B — Haber + Sosyal
    (7,  "gdelt",      "telegram"),
    (8,  "gdelt",      "acled"),
    (9,  "telegram",   "acled"),
    (10, "gdelt",      "fred"),
    (11, "telegram",   "fred"),
    (12, "acled",      "fred"),
    # Grup C — Fiziksel + Haber
    (13, "opensky",    "gdelt"),
    (14, "opensky",    "telegram"),
    (15, "opensky",    "acled"),
    (16, "opensky",    "fred"),
    (17, "marine",     "gdelt"),
    (18, "marine",     "telegram"),
    (19, "marine",     "acled"),
    (20, "marine",     "fred"),
    (21, "gdacs",      "gdelt"),
    (22, "gdacs",      "telegram"),
    (23, "gdacs",      "acled"),
    (24, "sentinelhub","gdelt"),
    # Grup D — Ekonomi
    (25, "fred",       "comtrade"),
    (26, "fred",       "sentinelhub"),
    (27, "comtrade",   "marine"),
    (28, "comtrade",   "gdelt"),
    (29, "comtrade",   "telegram"),
    (30, "comtrade",   "acled"),
    # Grup E — Telecom
    (31, "telecom",    "opensky"),
    (32, "telecom",    "marine"),
    (33, "telecom",    "gdelt"),
    (34, "telecom",    "telegram"),
    (35, "telecom",    "acled"),
    (36, "telecom",    "fred"),
    (37, "telecom",    "gdacs"),
    (38, "telecom",    "sentinelhub"),
    (39, "telecom",    "comtrade"),
    # Grup F — SentinelHub kalan
    (40, "sentinelhub","telegram"),
    (41, "sentinelhub","acled"),
    (42, "sentinelhub","fred"),
    (43, "sentinelhub","comtrade"),
    # 44 = sentinelhub↔telecom = kenar 38
    # 45 = sentinelhub↔marine  = kenar 5
]

# ═══════════════════════════════════════════════════════════
# 1800 AĞIRLIK MATRİSİ
# Format: {edge_id: {scenario_id: weight}}
# ═══════════════════════════════════════════════════════════

EDGE_WEIGHTS = {
    # ── Kenar 1: OpenSky ↔ Marine ──────────────────────────
    1: {
        1:9, 2:8, 3:9, 4:7, 5:4, 6:3, 7:5, 8:6, 9:8, 10:4,
        11:6,12:9,13:3,14:6,15:5,16:4,17:2,18:2,19:5,20:1,
        21:7,22:3,23:7,24:5,25:6,26:6,27:7,28:8,29:5,30:6,
        31:2,32:7,33:6,34:5,35:7,36:3,37:4,38:5,39:4,40:3,
    },
    # ── Kenar 2: OpenSky ↔ GDACS ───────────────────────────
    2: {
        1:3, 2:2, 3:2, 4:2, 5:1, 6:1, 7:3, 8:2, 9:5, 10:3,
        11:2,12:6,13:1,14:1,15:3,16:2,17:1,18:1,19:2,20:0,
        21:2,22:1,23:2,24:3,25:1,26:1,27:10,28:10,29:7,30:9,
        31:4,32:8,33:4,34:3,35:5,36:2,37:4,38:2,39:1,40:1,
    },
    # ── Kenar 3: Marine ↔ GDACS ────────────────────────────
    3: {
        1:4, 2:2, 3:3, 4:2, 5:1, 6:1, 7:3, 8:2, 9:6, 10:3,
        11:4,12:2,13:1,14:2,15:2,16:2,17:1,18:1,19:3,20:0,
        21:4,22:2,23:5,24:4,25:3,26:4,27:9,28:10,29:6,30:8,
        31:3,32:8,33:6,34:5,35:4,36:2,37:4,38:2,39:2,40:1,
    },
    # ── Kenar 4: OpenSky ↔ SentinelHub ─────────────────────
    4: {
        1:8, 2:9, 3:4, 4:7, 5:8, 6:4, 7:5, 8:6, 9:9, 10:4,
        11:7,12:8,13:1,14:2,15:5,16:2,17:1,18:2,19:5,20:0,
        21:5,22:1,23:3,24:4,25:1,26:3,27:8,28:7,29:6,30:10,
        31:6,32:7,33:5,34:4,35:4,36:3,37:5,38:3,39:7,40:3,
    },
    # ── Kenar 5: Marine ↔ SentinelHub ──────────────────────
    5: {
        1:7, 2:4, 3:9, 4:5, 5:4, 6:3, 7:4, 8:4, 9:6, 10:4,
        11:7,12:2,13:2,14:6,15:3,16:2,17:1,18:3,19:7,20:1,
        21:9,22:2,23:7,24:5,25:5,26:6,27:7,28:9,29:5,30:6,
        31:4,32:8,33:6,34:5,35:4,36:2,37:5,38:3,39:8,40:4,
    },
    # ── Kenar 6: GDACS ↔ SentinelHub ───────────────────────
    6: {
        1:3, 2:4, 3:2, 4:3, 5:2, 6:1, 7:3, 8:4, 9:7, 10:3,
        11:5,12:5,13:0,14:0,15:1,16:1,17:0,18:0,19:2,20:0,
        21:5,22:0,23:3,24:7,25:0,26:4,27:10,28:10,29:9,30:10,
        31:9,32:9,33:5,34:4,35:5,36:2,37:6,38:2,39:3,40:1,
    },
    # ── Kenar 7: GDELT ↔ Telegram ──────────────────────────
    7: {
        1:8, 2:7, 3:5, 4:8, 5:8, 6:8, 7:9, 8:8, 9:7, 10:8,
        11:8,12:5,13:9,14:7,15:9,16:8,17:8,18:6,19:7,20:5,
        21:6,22:7,23:5,24:6,25:6,26:5,27:7,28:6,29:5,30:5,
        31:4,32:5,33:7,34:7,35:8,36:9,37:6,38:8,39:7,40:9,
    },
    # ── Kenar 8: GDELT ↔ ACLED ─────────────────────────────
    8: {
        1:9, 2:8, 3:4, 4:9, 5:7, 6:8, 7:10,8:10,9:6, 10:5,
        11:7,12:4,13:6,14:5,15:9,16:7,17:6,18:4,19:7,20:3,
        21:4,22:3,23:3,24:6,25:3,26:4,27:5,28:4,29:4,30:3,
        31:4,32:4,33:7,34:7,35:5,36:9,37:7,38:9,39:6,40:8,
    },
    # ── Kenar 9: Telegram ↔ ACLED ──────────────────────────
    9: {
        1:9, 2:9, 3:5, 4:9, 5:10,6:10,7:9, 8:10,9:6, 10:7,
        11:9,12:3,13:5,14:4,15:10,16:7,17:6,18:3,19:7,20:2,
        21:3,22:3,23:3,24:6,25:3,26:4,27:6,28:5,29:5,30:3,
        31:3,32:4,33:7,34:7,35:5,36:10,37:7,38:9,39:8,40:10,
    },
    # ── Kenar 10: GDELT ↔ FRED ─────────────────────────────
    10: {
        1:7, 2:6, 3:7, 4:7, 5:4, 6:3, 7:6, 8:5, 9:7, 10:6,
        11:7,12:4,13:7,14:10,15:6,16:7,17:5,18:5,19:5,20:4,
        21:10,22:10,23:7,24:6,25:9,26:8,27:5,28:4,29:3,30:3,
        31:5,32:4,33:5,34:4,35:6,36:5,37:5,38:6,39:4,40:7,
    },
    # ── Kenar 11: Telegram ↔ FRED ──────────────────────────
    11: {
        1:5, 2:4, 3:5, 4:5, 5:4, 6:3, 7:5, 8:5, 9:6, 10:6,
        11:5,12:3,13:6,14:9,15:6,16:7,17:6,18:4,19:4,20:3,
        21:8,22:10,23:6,24:6,25:8,26:7,27:4,28:3,29:3,30:2,
        31:4,32:3,33:5,34:5,35:6,36:6,37:5,38:7,39:3,40:7,
    },
    # ── Kenar 12: ACLED ↔ FRED ─────────────────────────────
    12: {
        1:8, 2:6, 3:7, 4:8, 5:5, 6:5, 7:7, 8:8, 9:7, 10:6,
        11:8,12:3,13:6,14:9,15:7,16:7,17:5,18:4,19:6,20:3,
        21:9,22:8,23:6,24:7,25:7,26:7,27:5,28:4,29:4,30:3,
        31:5,32:4,33:6,34:5,35:5,36:6,37:6,38:7,39:5,40:7,
    },
    # ── Kenar 13: OpenSky ↔ GDELT ──────────────────────────
    13: {
        1:9, 2:9, 3:5, 4:8, 5:7, 6:5, 7:8, 8:7, 9:8, 10:6,
        11:7,12:10,13:6,14:7,15:8,16:6,17:4,18:3,19:6,20:2,
        21:6,22:4,23:5,24:5,25:5,26:4,27:8,28:7,29:6,30:8,
        31:3,32:7,33:7,34:6,35:8,36:6,37:6,38:6,39:5,40:7,
    },
    # ── Kenar 14: OpenSky ↔ Telegram ───────────────────────
    14: {
        1:8, 2:9, 3:4, 4:8, 5:9, 6:7, 7:8, 8:7, 9:8, 10:6,
        11:7,12:9,13:5,14:6,15:9,16:7,17:5,18:3,19:6,20:2,
        21:5,22:4,23:4,24:5,25:4,26:4,27:7,28:6,29:5,30:6,
        31:3,32:6,33:7,34:6,35:7,36:7,37:6,38:7,39:6,40:8,
    },
    # ── Kenar 15: OpenSky ↔ ACLED ──────────────────────────
    15: {
        1:9, 2:9, 3:4, 4:9, 5:7, 6:6, 7:9, 8:10,9:7, 10:5,
        11:7,12:9,13:5,14:6,15:8,16:6,17:5,18:3,19:7,20:2,
        21:5,22:3,23:4,24:6,25:3,26:4,27:6,28:5,29:5,30:4,
        31:3,32:5,33:8,34:7,35:6,36:8,37:7,38:8,39:5,40:7,
    },
    # ── Kenar 16: OpenSky ↔ FRED ───────────────────────────
    16: {
        1:7, 2:6, 3:6, 4:6, 5:4, 6:3, 7:6, 8:5, 9:7, 10:5,
        11:6,12:7,13:6,14:9,15:6,16:6,17:5,18:4,19:5,20:2,
        21:9,22:8,23:6,24:5,25:7,26:6,27:5,28:4,29:3,30:4,
        31:4,32:4,33:5,34:4,35:6,36:5,37:4,38:6,39:4,40:6,
    },
    # ── Kenar 17: Marine ↔ GDELT ───────────────────────────
    17: {
        1:7, 2:4, 3:10,4:5, 5:6, 6:4, 7:6, 8:5, 9:6, 10:5,
        11:8,12:2,13:5,14:8,15:4,16:4,17:2,18:3,19:6,20:2,
        21:10,22:4,23:9,24:7,25:8,26:8,27:5,28:7,29:4,30:4,
        31:3,32:6,33:6,34:6,35:5,36:4,37:6,38:5,39:7,40:6,
    },
    # ── Kenar 18: Marine ↔ Telegram ────────────────────────
    18: {
        1:7, 2:4, 3:10,4:4, 5:8, 6:5, 7:7, 8:5, 9:6, 10:6,
        11:9,12:2,13:4,14:7,15:3,16:3,17:2,18:3,19:7,20:2,
        21:9,22:4,23:8,24:6,25:7,26:7,27:5,28:7,29:4,30:4,
        31:2,32:6,33:7,34:7,35:4,36:4,37:6,38:5,39:7,40:7,
    },
    # ── Kenar 19: Marine ↔ ACLED ───────────────────────────
    19: {
        1:8, 2:5, 3:10,4:5, 5:7, 6:6, 7:7, 8:7, 9:6, 10:5,
        11:9,12:2,13:4,14:7,15:4,16:4,17:2,18:3,19:8,20:2,
        21:8,22:3,23:7,24:7,25:6,26:6,27:5,28:6,29:4,30:3,
        31:3,32:5,33:8,34:8,35:4,36:5,37:8,38:6,39:7,40:7,
    },
    # ── Kenar 20: Marine ↔ FRED ────────────────────────────
    20: {
        1:7, 2:4, 3:9, 4:5, 5:4, 6:3, 7:5, 8:5, 9:6, 10:5,
        11:8,12:2,13:5,14:9,15:4,16:5,17:2,18:3,19:5,20:2,
        21:10,22:7,23:9,24:6,25:9,26:8,27:4,28:5,29:3,30:3,
        31:4,32:4,33:5,34:4,35:4,36:3,37:5,38:5,39:6,40:6,
    },
    # ── Kenar 21: GDACS ↔ GDELT ────────────────────────────
    21: {
        1:2, 2:2, 3:2, 4:2, 5:1, 6:1, 7:3, 8:2, 9:6, 10:3,
        11:4,12:5,13:1,14:1,15:2,16:2,17:1,18:1,19:2,20:0,
        21:5,22:2,23:4,24:7,25:1,26:3,27:10,28:10,29:9,30:9,
        31:8,32:9,33:6,34:5,35:7,36:2,37:7,38:2,39:1,40:2,
    },
    # ── Kenar 22: GDACS ↔ Telegram ─────────────────────────
    22: {
        1:2, 2:2, 3:2, 4:2, 5:1, 6:1, 7:4, 8:3, 9:5, 10:4,
        11:4,12:4,13:1,14:1,15:3,16:3,17:2,18:1,19:2,20:0,
        21:4,22:2,23:3,24:7,25:1,26:3,27:9,28:9,29:8,30:8,
        31:6,32:8,33:7,34:7,35:7,36:3,37:8,38:3,39:1,40:2,
    },
    # ── Kenar 23: GDACS ↔ ACLED ────────────────────────────
    23: {
        1:3, 2:3, 3:2, 4:3, 5:1, 6:2, 7:4, 8:6, 9:5, 10:3,
        11:5,12:3,13:1,14:2,15:4,16:5,17:2,18:1,19:3,20:0,
        21:4,22:2,23:4,24:9,25:2,26:4,27:8,28:7,29:7,30:6,
        31:7,32:7,33:9,34:9,35:6,36:5,37:10,38:8,39:2,40:3,
    },
    # ── Kenar 24: SentinelHub ↔ GDELT ──────────────────────
    24: {
        1:9, 2:8, 3:5, 4:8, 5:7, 6:6, 7:6, 8:7, 9:9, 10:5,
        11:8,12:6,13:4,14:5,15:6,16:4,17:2,18:4,19:8,20:1,
        21:6,22:2,23:5,24:7,25:4,26:6,27:9,28:8,29:8,30:9,
        31:9,32:8,33:6,34:5,35:6,36:5,37:6,38:5,39:9,40:6,
    },
    # ── Kenar 25: FRED ↔ Comtrade ──────────────────────────
    25: {
        1:6, 2:4, 3:7, 4:5, 5:3, 6:3, 7:4, 8:5, 9:6, 10:5,
        11:7,12:3,13:6,14:10,15:5,16:5,17:3,18:4,19:4,20:3,
        21:9,22:8,23:9,24:7,25:10,26:9,27:4,28:4,29:3,30:3,
        31:5,32:4,33:4,34:4,35:5,36:4,37:5,38:6,39:4,40:7,
    },
    # ── Kenar 26: FRED ↔ SentinelHub ───────────────────────
    26: {
        1:6, 2:6, 3:5, 4:5, 5:5, 6:4, 7:4, 8:5, 9:8, 10:5,
        11:9,12:4,13:3,14:6,15:4,16:3,17:2,18:3,19:5,20:1,
        21:9,22:5,23:6,24:7,25:5,26:8,27:7,28:6,29:6,30:7,
        31:9,32:7,33:4,34:4,35:4,36:3,37:5,38:4,39:7,40:5,
    },
    # ── Kenar 27: Comtrade ↔ Marine ────────────────────────
    27: {
        1:7, 2:4, 3:10,4:6, 5:4, 6:3, 7:5, 8:6, 9:6, 10:5,
        11:8,12:2,13:6,14:10,15:5,16:5,17:2,18:4,19:6,20:2,
        21:9,22:7,23:10,24:8,25:10,26:9,27:6,28:7,29:5,30:4,
        31:5,32:6,33:6,34:5,35:5,36:4,37:6,38:6,39:7,40:7,
    },
    # ── Kenar 28: Comtrade ↔ GDELT ─────────────────────────
    28: {
        1:6, 2:4, 3:7, 4:5, 5:4, 6:3, 7:5, 8:5, 9:6, 10:5,
        11:6,12:3,13:7,14:10,15:5,16:5,17:3,18:5,19:5,20:3,
        21:8,22:7,23:8,24:7,25:10,26:8,27:5,28:4,29:4,30:3,
        31:5,32:4,33:5,34:5,35:6,36:5,37:6,38:6,39:5,40:7,
    },
    # ── Kenar 29: Comtrade ↔ Telegram ──────────────────────
    29: {
        1:5, 2:3, 3:6, 4:4, 5:4, 6:3, 7:4, 8:5, 9:5, 10:5,
        11:5,12:2,13:6,14:9,15:5,16:5,17:3,18:4,19:4,20:3,
        21:7,22:8,23:7,24:6,25:9,26:7,27:4,28:3,29:3,30:2,
        31:4,32:3,33:5,34:5,35:5,36:5,37:5,38:6,39:4,40:6,
    },
    # ── Kenar 30: Comtrade ↔ ACLED ─────────────────────────
    30: {
        1:8, 2:6, 3:8, 4:8, 5:5, 6:6, 7:6, 8:9, 9:6, 10:5,
        11:8,12:3,13:5,14:9,15:6,16:6,17:3,18:4,19:7,20:3,
        21:7,22:6,23:7,24:7,25:8,26:7,27:5,28:4,29:4,30:3,
        31:5,32:4,33:7,34:7,35:5,36:6,37:8,38:8,39:6,40:7,
    },
    # ── Kenar 31: Telecom ↔ OpenSky ────────────────────────
    31: {
        1:8, 2:8, 3:4, 4:7, 5:6, 6:4, 7:7, 8:7, 9:9, 10:7,
        11:7,12:9,13:4,14:5,15:10,16:7,17:5,18:3,19:5,20:2,
        21:4,22:5,23:3,24:5,25:3,26:3,27:9,28:8,29:6,30:7,
        31:3,32:8,33:9,34:8,35:8,36:7,37:7,38:7,39:5,40:6,
    },
    # ── Kenar 32: Telecom ↔ Marine ─────────────────────────
    32: {
        1:7, 2:4, 3:9, 4:5, 5:5, 6:4, 7:5, 8:6, 9:7, 10:6,
        11:7,12:3,13:4,14:6,15:5,16:5,17:3,18:3,19:5,20:1,
        21:7,22:5,23:7,24:6,25:5,26:5,27:8,28:10,29:7,30:6,
        31:3,32:9,33:9,34:9,35:7,36:5,37:8,38:6,39:6,40:6,
    },
    # ── Kenar 33: Telecom ↔ GDELT ──────────────────────────
    33: {
        1:7, 2:6, 3:4, 4:6, 5:7, 6:5, 7:7, 8:7, 9:7, 10:10,
        11:8,12:5,13:6,14:6,15:10,16:8,17:8,18:4,19:5,20:2,
        21:5,22:6,23:4,24:5,25:4,26:4,27:7,28:6,29:5,30:5,
        31:3,32:6,33:7,34:6,35:7,36:9,37:6,38:8,39:5,40:9,
    },
    # ── Kenar 34: Telecom ↔ Telegram ───────────────────────
    34: {
        1:7, 2:6, 3:4, 4:6, 5:8, 6:6, 7:7, 8:8, 9:7, 10:9,
        11:8,12:5,13:5,14:5,15:10,16:8,17:8,18:3,19:5,20:2,
        21:4,22:6,23:3,24:4,25:3,26:3,27:6,28:5,29:4,30:4,
        31:2,32:5,33:7,34:6,35:6,36:10,37:6,38:8,39:5,40:9,
    },
    # ── Kenar 35: Telecom ↔ ACLED ──────────────────────────
    35: {
        1:9, 2:7, 3:5, 4:9, 5:7, 6:7, 7:9, 8:10,9:6, 10:8,
        11:9,12:5,13:4,14:4,15:9,16:7,17:6,18:3,19:7,20:2,
        21:4,22:4,23:3,24:5,25:3,26:3,27:5,28:4,29:4,30:3,
        31:2,32:5,33:8,34:7,35:5,36:8,37:7,38:8,39:6,40:8,
    },
    # ── Kenar 36: Telecom ↔ FRED ───────────────────────────
    36: {
        1:6, 2:4, 3:5, 4:5, 5:4, 6:3, 7:5, 8:6, 9:6, 10:7,
        11:6,12:3,13:6,14:9,15:7,16:7,17:6,18:4,19:4,20:3,
        21:7,22:10,23:6,24:5,25:8,26:7,27:4,28:3,29:3,30:2,
        31:4,32:4,33:5,34:4,35:6,36:6,37:4,38:7,39:4,40:7,
    },
    # ── Kenar 37: Telecom ↔ GDACS ──────────────────────────
    37: {
        1:4, 2:3, 3:3, 4:3, 5:2, 6:1, 7:4, 8:5, 9:7, 10:6,
        11:6,12:6,13:1,14:1,15:4,16:4,17:2,18:1,19:2,20:0,
        21:3,22:2,23:3,24:6,25:1,26:2,27:10,28:10,29:8,30:8,
        31:5,32:10,33:7,34:6,35:7,36:3,37:7,38:5,39:2,40:4,
    },
    # ── Kenar 38: Telecom ↔ SentinelHub ────────────────────
    38: {
        1:7, 2:7, 3:4, 4:6, 5:6, 6:4, 7:5, 8:6, 9:9, 10:7,
        11:9,12:5,13:3,14:4,15:6,16:4,17:3,18:3,19:6,20:1,
        21:6,22:3,23:3,24:6,25:2,26:3,27:8,28:7,29:7,30:8,
        31:6,32:8,33:6,34:5,35:5,36:4,37:6,38:5,39:8,40:6,
    },
    # ── Kenar 39: Telecom ↔ Comtrade ───────────────────────
    39: {
        1:6, 2:4, 3:7, 4:5, 5:4, 6:3, 7:4, 8:6, 9:6, 10:8,
        11:7,12:3,13:5,14:9,15:6,16:6,17:4,18:4,19:4,20:2,
        21:6,22:8,23:7,24:6,25:8,26:6,27:5,28:5,29:4,30:3,
        31:3,32:5,33:5,34:4,35:5,36:5,37:5,38:7,39:4,40:7,
    },
    # ── Kenar 40: SentinelHub ↔ Telegram ───────────────────
    40: {
        1:9, 2:9, 3:5, 4:8, 5:9, 6:7, 7:7, 8:8, 9:9, 10:6,
        11:9,12:6,13:3,14:4,15:6,16:5,17:3,18:4,19:7,20:1,
        21:6,22:3,23:4,24:7,25:3,26:5,27:8,28:7,29:7,30:8,
        31:7,32:8,33:7,34:6,35:5,36:6,37:7,38:6,39:9,40:7,
    },
    # ── Kenar 41: SentinelHub ↔ ACLED ──────────────────────
    41: {
        1:10,2:9, 3:5, 4:10,5:7, 6:8, 7:8, 8:10,9:8, 10:6,
        11:9,12:5,13:4,14:5,15:7,16:6,17:4,18:4,19:9,20:1,
        21:6,22:3,23:4,24:7,25:3,26:5,27:7,28:6,29:6,30:6,
        31:7,32:7,33:8,34:7,35:5,36:7,37:8,38:8,39:9,40:8,
    },
    # ── Kenar 42: SentinelHub ↔ FRED ───────────────────────
    42: {
        1:7, 2:6, 3:5, 4:5, 5:5, 6:4, 7:4, 8:5, 9:8, 10:5,
        11:9,12:4,13:3,14:6,15:4,16:4,17:2,18:3,19:6,20:1,
        21:10,22:5,23:6,24:8,25:5,26:8,27:7,28:6,29:6,30:7,
        31:9,32:7,33:4,34:4,35:4,36:3,37:5,38:4,39:7,40:5,
    },
    # ── Kenar 43: SentinelHub ↔ Comtrade ───────────────────
    43: {
        1:7, 2:5, 3:7, 4:6, 5:5, 6:4, 7:4, 8:6, 9:7, 10:5,
        11:8,12:3,13:5,14:7,15:4,16:4,17:2,18:4,19:8,20:2,
        21:8,22:5,23:7,24:8,25:7,26:9,27:6,28:5,29:5,30:5,
        31:8,32:6,33:5,34:4,35:4,36:4,37:6,38:6,39:9,40:6,
    },
}

# ═══════════════════════════════════════════════════════════
# GÜVENİLİRLİK KATSAYILARI
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
# EŞİK SEVİYELERİ
# ═══════════════════════════════════════════════════════════

THRESHOLDS = {
    0: 0,   # Her zaman aktif — genel skor
    1: 30,  # Aktör analizi başlar
    2: 55,  # Ardışık zincir takibi
    3: 75,  # LLM analizi + kritik uyarı
    4: 90,  # Kritik pencere aktif
}

# ═══════════════════════════════════════════════════════════
# COĞRAFYALAR — 50 bölge
# ═══════════════════════════════════════════════════════════

GEOGRAPHIES = {
    # Kara
    "korfez":           {"lat": 25.5,  "lon": 54.0,  "tier": 1},
    "levant":           {"lat": 33.0,  "lon": 36.0,  "tier": 1},
    "irak":             {"lat": 33.5,  "lon": 44.0,  "tier": 1},
    "iran":             {"lat": 32.0,  "lon": 54.0,  "tier": 1},
    "yemen":            {"lat": 15.5,  "lon": 48.0,  "tier": 1},
    "turkiye":          {"lat": 39.0,  "lon": 35.0,  "tier": 1},
    "kafkasya":         {"lat": 41.5,  "lon": 44.0,  "tier": 1},
    "orta_asya":        {"lat": 42.0,  "lon": 63.0,  "tier": 1},
    "afganistan_pak":   {"lat": 33.0,  "lon": 68.0,  "tier": 1},
    "kuzey_afrika":     {"lat": 28.0,  "lon": 18.0,  "tier": 1},
    "boynuz_afrika":    {"lat": 8.0,   "lon": 45.0,  "tier": 1},
    "dogu_afrika":      {"lat": 2.0,   "lon": 38.0,  "tier": 2},
    "orta_afrika":      {"lat": 5.0,   "lon": 22.0,  "tier": 2},
    "bati_afrika":      {"lat": 10.0,  "lon": -5.0,  "tier": 2},
    "guney_afrika":     {"lat":-28.0,  "lon": 25.0,  "tier": 2},
    "sahel":            {"lat": 14.0,  "lon": 2.0,   "tier": 1},
    "dogu_avrupa":      {"lat": 48.0,  "lon": 30.0,  "tier": 1},
    "orta_avrupa":      {"lat": 48.0,  "lon": 12.0,  "tier": 2},
    "bati_avrupa":      {"lat": 48.0,  "lon": 3.0,   "tier": 2},
    "iskandinavya":     {"lat": 63.0,  "lon": 15.0,  "tier": 2},
    "cin_tayvan":       {"lat": 27.0,  "lon": 118.0, "tier": 1},
    "guney_asya":       {"lat": 20.0,  "lon": 78.0,  "tier": 1},
    "guneydogu_asya":   {"lat": 5.0,   "lon": 110.0, "tier": 1},
    "japonya_kore":     {"lat": 36.0,  "lon": 133.0, "tier": 1},
    "okyanusya":        {"lat":-25.0,  "lon": 135.0, "tier": 2},
    "kuzey_amerika":    {"lat": 45.0,  "lon":-100.0, "tier": 2},
    "karayipler":       {"lat": 18.0,  "lon":-73.0,  "tier": 2},
    "guney_amerika_k":  {"lat": 5.0,   "lon":-60.0,  "tier": 2},
    "guney_amerika_g":  {"lat":-35.0,  "lon":-65.0,  "tier": 2},
    "arktik":           {"lat": 80.0,  "lon": 0.0,   "tier": 2},
    # Deniz & Boğazlar
    "istanbul_canakkale":{"lat": 40.7, "lon": 27.5,  "tier": 1},
    "hurmuz":           {"lat": 26.5,  "lon": 56.5,  "tier": 1},
    "bab_el_mandeb":    {"lat": 12.5,  "lon": 43.5,  "tier": 1},
    "malakka":          {"lat": 2.5,   "lon": 101.5, "tier": 1},
    "tayvan_bogazi":    {"lat": 24.0,  "lon": 120.5, "tier": 1},
    "danimarka_bogazi": {"lat": 55.0,  "lon": 10.0,  "tier": 2},
    "dover_bogazi":     {"lat": 51.0,  "lon": 1.5,   "tier": 2},
    "suveys":           {"lat": 30.5,  "lon": 32.4,  "tier": 1},
    "panama":           {"lat": 9.0,   "lon":-79.7,  "tier": 2},
    "karadeniz":        {"lat": 43.0,  "lon": 34.0,  "tier": 1},
    "hazar":            {"lat": 41.0,  "lon": 51.0,  "tier": 1},
    "dogu_akdeniz":     {"lat": 35.0,  "lon": 29.0,  "tier": 1},
    "bati_akdeniz":     {"lat": 39.0,  "lon": 5.0,   "tier": 2},
    "sari_deniz":       {"lat": 35.0,  "lon": 123.0, "tier": 1},
    "japon_denizi":     {"lat": 39.0,  "lon": 133.0, "tier": 1},
    "guney_cin_denizi": {"lat": 12.0,  "lon": 115.0, "tier": 1},
    "kuzey_denizi":     {"lat": 57.0,  "lon": 4.0,   "tier": 2},
    "kuzey_atlantik":   {"lat": 45.0,  "lon":-35.0,  "tier": 2},
    "hint_okyanusu":    {"lat": 5.0,   "lon": 72.0,  "tier": 1},
    "pasifik":          {"lat": 10.0,  "lon": 170.0, "tier": 2},
}

# ═══════════════════════════════════════════════════════════
# VERİTABANI
# ═══════════════════════════════════════════════════════════

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript("""
        -- Motor sinyalleri
        CREATE TABLE IF NOT EXISTS motor_signals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            motor       TEXT NOT NULL,
            geography   TEXT NOT NULL,
            value       REAL NOT NULL,
            normalized  REAL NOT NULL,  -- 0-1 arası normalize
            timestamp   TEXT NOT NULL,
            scan_id     TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ms_motor ON motor_signals(motor, geography);
        CREATE INDEX IF NOT EXISTS idx_ms_ts    ON motor_signals(timestamp);

        -- Kenar skorları (her taramada 45 kenar × coğrafya)
        CREATE TABLE IF NOT EXISTS edge_scores (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            edge_id     INTEGER NOT NULL,
            geography   TEXT NOT NULL,
            signal_strength REAL NOT NULL,  -- iki motorun normalize ortalama gücü
            timestamp   TEXT NOT NULL,
            scan_id     TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_es_edge ON edge_scores(edge_id, geography);

        -- Senaryo skorları (her taramada 40 senaryo × coğrafya)
        CREATE TABLE IF NOT EXISTS scenario_scores (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            scenario_id INTEGER NOT NULL,
            scenario_name TEXT NOT NULL,
            geography   TEXT NOT NULL,
            score       REAL NOT NULL,        -- 0-100
            threshold   INTEGER NOT NULL,     -- aktif eşik seviyesi 0-4
            timestamp   TEXT NOT NULL,
            scan_id     TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ss_scen ON scenario_scores(scenario_id, geography);
        CREATE INDEX IF NOT EXISTS idx_ss_ts   ON scenario_scores(timestamp);

        -- Rolling baseline (kayan)
        CREATE TABLE IF NOT EXISTS rolling_baseline (
            geography   TEXT NOT NULL,
            scenario_id INTEGER NOT NULL,
            mean_7d     REAL,
            mean_30d    REAL,
            std_7d      REAL,
            updated_at  TEXT,
            PRIMARY KEY (geography, scenario_id)
        );

        -- Referans baseline (sabit, kullanıcı onaylar)
        CREATE TABLE IF NOT EXISTS reference_baseline (
            geography   TEXT NOT NULL,
            scenario_id INTEGER NOT NULL,
            ref_mean    REAL,
            approved_at TEXT,
            approved_by TEXT DEFAULT 'system',
            PRIMARY KEY (geography, scenario_id)
        );

        -- Uyarılar
        CREATE TABLE IF NOT EXISTS alerts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            geography   TEXT NOT NULL,
            scenario_id INTEGER NOT NULL,
            scenario_name TEXT,
            score       REAL NOT NULL,
            threshold   INTEGER NOT NULL,
            anomaly_type TEXT,  -- 'rolling_spike' | 'ref_spike' | 'both'
            delta_rolling REAL,
            delta_ref     REAL,
            timestamp   TEXT NOT NULL,
            scan_id     TEXT NOT NULL,
            acknowledged INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_al_geo ON alerts(geography, scenario_id);
        CREATE INDEX IF NOT EXISTS idx_al_ts  ON alerts(timestamp);

        -- Scan log
        CREATE TABLE IF NOT EXISTS scan_log (
            scan_id     TEXT PRIMARY KEY,
            started_at  TEXT,
            finished_at TEXT,
            geographies INTEGER,
            total_scores INTEGER,
            alerts_generated INTEGER
        );
        """)
    log.info("DB hazır: %s", DB_PATH)


# ═══════════════════════════════════════════════════════════
# NORMALIZASYON
# ═══════════════════════════════════════════════════════════

def normalize_signal(value: float, history: list[float]) -> float:
    """
    Motor sinyalini 0-1 arasına normalize et.
    History yoksa 0.5 döner (nötr).
    """
    if not history or len(history) < 3:
        return 0.5
    mn = min(history)
    mx = max(history)
    if mx == mn:
        return 0.5
    return max(0.0, min(1.0, (value - mn) / (mx - mn)))


# ═══════════════════════════════════════════════════════════
# KENAR SINYAL GÜCÜ
# ═══════════════════════════════════════════════════════════

def edge_signal_strength(
    motor_a: str, signal_a: float,
    motor_b: str, signal_b: float,
) -> float:
    """
    İki motorun normalize sinyallerinden kenar gücü hesapla.
    Güvenilirlik katsayısıyla ağırlıklandırılmış geometrik ortalama.
    """
    rel_a = SOURCE_RELIABILITY.get(motor_a, 0.5)
    rel_b = SOURCE_RELIABILITY.get(motor_b, 0.5)
    weighted_a = signal_a * rel_a
    weighted_b = signal_b * rel_b
    return math.sqrt(weighted_a * weighted_b)


# ═══════════════════════════════════════════════════════════
# SENARYO PUANLAMA
# ═══════════════════════════════════════════════════════════

def compute_scenario_scores(
    edge_strengths: dict[int, float],  # {edge_id: strength 0-1}
) -> dict[int, float]:
    """
    Kenar güçlerinden senaryo skorlarını hesapla.
    Skor: ağırlıklı kenar katkılarının toplamı, 0-100'e normalize.
    """
    raw_scores = defaultdict(float)
    max_possible = defaultdict(float)

    for edge_id, strength in edge_strengths.items():
        weights = EDGE_WEIGHTS.get(edge_id, {})
        for scenario_id, weight in weights.items():
            raw_scores[scenario_id] += strength * weight
            max_possible[scenario_id] += weight  # max strength=1

    scores = {}
    for scenario_id in SCENARIOS:
        mx = max_possible.get(scenario_id, 1)
        raw = raw_scores.get(scenario_id, 0)
        scores[scenario_id] = min(100.0, (raw / mx * 100)) if mx > 0 else 0.0

    return scores


def get_threshold_level(score: float) -> int:
    """Skora göre eşik seviyesi döndür."""
    for level in sorted(THRESHOLDS.keys(), reverse=True):
        if score >= THRESHOLDS[level]:
            return level
    return 0


# ═══════════════════════════════════════════════════════════
# ANOMALİ TESPİTİ
# ═══════════════════════════════════════════════════════════

def detect_anomaly(
    geography: str,
    scenario_id: int,
    current_score: float,
) -> dict | None:
    """
    Mevcut skor → kayan baseline → referans baseline karşılaştır.
    Anomali varsa dict döndür.

    Volatility floor: std küçükken z-score patlar — floor ile sınırla.
    Persistence: ardışık doğrulama opsiyonel, config'den ayarlanır.
    """
    # Config'den parametreler — fallback default
    try:
        from logosint.config import (
            ANOMALY_STD_FLOOR,
            ANOMALY_ZSCORE_THRESHOLD,
            ANOMALY_REF_DELTA_PCT,
            ANOMALY_BOTH_DELTA_PCT,
            ANOMALY_REQUIRE_PERSISTENCE,
            ANOMALY_PERSISTENCE_WINDOW,
        )
    except ImportError:
        ANOMALY_STD_FLOOR = 3.0
        ANOMALY_ZSCORE_THRESHOLD = 2.5
        ANOMALY_REF_DELTA_PCT = 0.40
        ANOMALY_BOTH_DELTA_PCT = 0.25
        ANOMALY_REQUIRE_PERSISTENCE = False
        ANOMALY_PERSISTENCE_WINDOW = 2

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        roll = conn.execute(
            "SELECT mean_7d, std_7d, mean_30d FROM rolling_baseline WHERE geography=? AND scenario_id=?",
            (geography, scenario_id)
        ).fetchone()
        ref = conn.execute(
            "SELECT ref_mean FROM reference_baseline WHERE geography=? AND scenario_id=?",
            (geography, scenario_id)
        ).fetchone()

    if not roll:
        return None

    mean_7d  = roll["mean_7d"] or 0
    raw_std  = roll["std_7d"] or 0
    mean_30d = roll["mean_30d"] or mean_7d
    ref_mean = ref["ref_mean"] if ref else mean_30d

    # ★ VOLATILITY FLOOR — küçük std'ye karşı koruma
    # Sistem ilk haftalarda baseline gürültülü, std çok küçük olabilir.
    # Bu floor sayesinde z-score patlamaz, false positive azalır.
    std_7d = max(raw_std, ANOMALY_STD_FLOOR)

    delta_rolling  = current_score - mean_7d
    delta_ref      = current_score - ref_mean
    zscore_rolling = delta_rolling / std_7d

    # Anomaly type tespiti
    anomaly_type = None
    abs_z      = abs(zscore_rolling)
    ref_delta_ratio = abs(delta_ref / ref_mean) if ref_mean > 0 else 0

    if abs_z >= ANOMALY_ZSCORE_THRESHOLD and ref_delta_ratio >= ANOMALY_BOTH_DELTA_PCT:
        anomaly_type = "both"
    elif abs_z >= ANOMALY_ZSCORE_THRESHOLD:
        anomaly_type = "rolling_spike"
    elif ref_mean > 0 and delta_ref / ref_mean >= ANOMALY_REF_DELTA_PCT:
        anomaly_type = "ref_spike"

    if not anomaly_type:
        return None

    # ★ PERSISTENCE — ardışık doğrulama (opsiyonel)
    # True ise son N scan içinde de spike olmuş mu kontrol et
    if ANOMALY_REQUIRE_PERSISTENCE:
        if not _check_persistence(
            geography, scenario_id,
            current_score, mean_7d, std_7d,
            ANOMALY_ZSCORE_THRESHOLD,
            ANOMALY_PERSISTENCE_WINDOW,
        ):
            return None

    return {
        "anomaly_type":  anomaly_type,
        "delta_rolling": round(delta_rolling, 2),
        "delta_ref":     round(delta_ref, 2),
        "zscore":        round(zscore_rolling, 3),
        "std_used":      round(std_7d, 3),
        "std_floored":   raw_std < ANOMALY_STD_FLOOR,
    }


def _check_persistence(
    geography:   str,
    scenario_id: int,
    current:     float,
    mean:        float,
    std:         float,
    threshold:   float,
    window:      int,
) -> bool:
    """
    Son N scan içinde de spike olmuş mu kontrol et.
    Tek scan spike'larını filtreler.
    """
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """SELECT score FROM scenario_scores
               WHERE geography=? AND scenario_id=?
               ORDER BY timestamp DESC LIMIT ?""",
            (geography, scenario_id, window),
        ).fetchall()

    if len(rows) < window:
        return False  # yeterli history yok

    count_above = sum(1 for r in rows if abs((r[0] - mean) / std) >= threshold)
    return count_above >= window


# ═══════════════════════════════════════════════════════════
# ROLLING BASELINE GÜNCELLEME
# ═══════════════════════════════════════════════════════════

def update_rolling_baseline(geography: str, scenario_id: int):
    """Son 7 ve 30 günlük ortalama + std güncelle."""
    now = datetime.utcnow()
    cutoff_7d  = (now - timedelta(days=7)).isoformat()
    cutoff_30d = (now - timedelta(days=30)).isoformat()

    with sqlite3.connect(DB_PATH) as conn:
        def stats(cutoff):
            rows = conn.execute(
                "SELECT score FROM scenario_scores WHERE geography=? AND scenario_id=? AND timestamp>=?",
                (geography, scenario_id, cutoff)
            ).fetchall()
            vals = [r[0] for r in rows]
            if not vals:
                return None, None
            m = sum(vals) / len(vals)
            s = math.sqrt(sum((v - m)**2 for v in vals) / len(vals)) if len(vals) > 1 else 0
            return m, s

        m7, s7 = stats(cutoff_7d)
        m30, _  = stats(cutoff_30d)

        conn.execute("""
            INSERT INTO rolling_baseline (geography, scenario_id, mean_7d, mean_30d, std_7d, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(geography, scenario_id) DO UPDATE SET
                mean_7d=excluded.mean_7d,
                mean_30d=excluded.mean_30d,
                std_7d=excluded.std_7d,
                updated_at=excluded.updated_at
        """, (geography, scenario_id, m7, m30, s7, now.isoformat()))


# ═══════════════════════════════════════════════════════════
# ANA TARAMA FONKSİYONU
# ═══════════════════════════════════════════════════════════

def compute_scoring_cycle(
    motor_signals: dict[str, dict[str, float]],
) -> dict:
    """
    PURE COMPUTATION — DB'ye yazmaz.

    Her coğrafya için:
      - kenar güçleri hesapla
      - senaryo skorları üret
      - anomali tespiti yap (DB'den oku, yazma)

    Returns:
      {
        "edge_strengths": {geo: {edge_id: strength}},
        "scores":         {geo: {scenario_id: score}},
        "thresholds":     {geo: {scenario_id: level}},
        "anomalies":      [anomaly_dict, ...],
      }

    runtime_v2 bu dict'i alıp ScanTransaction içinde DB'ye yazar.
    Böylece scoring + signal + feature TEK ATOMİK BATCH'te commit edilir.
    """
    out_edges:      dict[str, dict[int, float]] = {}
    out_scores:     dict[str, dict[int, float]] = {}
    out_thresholds: dict[str, dict[int, int]]   = {}
    out_anomalies:  list[dict] = []

    for geo in GEOGRAPHIES:
        edge_strengths = {}
        for edge_id, motor_a, motor_b in EDGES:
            sig_a = motor_signals.get(motor_a, {}).get(geo, 0.0)
            sig_b = motor_signals.get(motor_b, {}).get(geo, 0.0)
            strength = edge_signal_strength(motor_a, sig_a, motor_b, sig_b)
            edge_strengths[edge_id] = round(strength, 4)
        out_edges[geo] = edge_strengths

        scores = compute_scenario_scores(edge_strengths)
        out_scores[geo]     = {sid: round(s, 2) for sid, s in scores.items()}
        out_thresholds[geo] = {sid: get_threshold_level(s) for sid, s in scores.items()}

        # Anomali tespiti — sadece DB'den OKU (yazma yok)
        for scenario_id, score in scores.items():
            anomaly = detect_anomaly(geo, scenario_id, score)
            if anomaly:
                out_anomalies.append({
                    "geography":      geo,
                    "scenario_id":    scenario_id,
                    "scenario_name":  SCENARIOS[scenario_id],
                    "score":          round(score, 2),
                    "threshold":      get_threshold_level(score),
                    **anomaly,
                })

    return {
        "edge_strengths": out_edges,
        "scores":         out_scores,
        "thresholds":     out_thresholds,
        "anomalies":      out_anomalies,
    }


def run_scoring_cycle(motor_signals: dict[str, dict[str, float]], scan_id: str):
    """
    BACKWARD COMPATIBLE wrapper.

    Eski kullanıcılar için. Yeni kod compute_scoring_cycle() kullanmalı.
    Bu fonksiyon hâlâ DB'ye direkt yazar — sadece legacy entegrasyon için.
    runtime_v2 artık bunu çağırmaz, compute_scoring_cycle kullanır.
    """
    now = datetime.utcnow().isoformat()
    total_scores = 0
    total_alerts = 0

    result = compute_scoring_cycle(motor_signals)

    with sqlite3.connect(DB_PATH) as conn:
        for geo, edges in result["edge_strengths"].items():
            for edge_id, strength in edges.items():
                conn.execute(
                    "INSERT INTO edge_scores (edge_id, geography, signal_strength, timestamp, scan_id) VALUES (?,?,?,?,?)",
                    (edge_id, geo, strength, now, scan_id),
                )
        for geo, scenarios in result["scores"].items():
            for scenario_id, score in scenarios.items():
                threshold = result["thresholds"][geo][scenario_id]
                conn.execute(
                    "INSERT INTO scenario_scores (scenario_id, scenario_name, geography, score, threshold, timestamp, scan_id) VALUES (?,?,?,?,?,?,?)",
                    (scenario_id, SCENARIOS[scenario_id], geo, score, threshold, now, scan_id),
                )
                total_scores += 1
                if score > 10:
                    update_rolling_baseline(geo, scenario_id)

        for anomaly in result["anomalies"]:
            conn.execute("""
                INSERT INTO alerts (geography, scenario_id, scenario_name, score, threshold,
                    anomaly_type, delta_rolling, delta_ref, timestamp, scan_id)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (
                anomaly["geography"], anomaly["scenario_id"],
                anomaly["scenario_name"], anomaly["score"],
                anomaly["threshold"], anomaly["anomaly_type"],
                anomaly["delta_rolling"], anomaly["delta_ref"],
                now, scan_id,
            ))
            total_alerts += 1

    log.info("Tarama %s: %d skor, %d uyarı", scan_id, total_scores, total_alerts)
    return total_scores, total_alerts


# ═══════════════════════════════════════════════════════════
# SORGU FONKSİYONLARI
# ═══════════════════════════════════════════════════════════

def get_top_scenarios(geography: str = None, hours: int = 1, limit: int = 10) -> list[dict]:
    """Son N saatteki en yüksek skorlu senaryolar."""
    since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    where = "WHERE timestamp >= ?"
    params = [since]
    if geography:
        where += " AND geography = ?"
        params.append(geography)
    params.append(limit)

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"""
            SELECT geography, scenario_id, scenario_name,
                   AVG(score) as avg_score, MAX(score) as max_score,
                   MAX(threshold) as max_threshold
            FROM scenario_scores
            {where}
            GROUP BY geography, scenario_id
            ORDER BY avg_score DESC
            LIMIT ?
        """, params).fetchall()
    return [dict(r) for r in rows]


def get_active_alerts(hours: int = 12, geography: str = None) -> list[dict]:
    """Aktif uyarılar."""
    since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    where = "WHERE timestamp >= ? AND acknowledged = 0"
    params = [since]
    if geography:
        where += " AND geography = ?"
        params.append(geography)

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"""
            SELECT * FROM alerts {where}
            ORDER BY score DESC, timestamp DESC
        """, params).fetchall()
    return [dict(r) for r in rows]


def get_trend(geography: str, scenario_id: int, days: int = 7) -> list[dict]:
    """Belirli bir coğrafya + senaryo için trend verisi."""
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT timestamp, AVG(score) as score
            FROM scenario_scores
            WHERE geography=? AND scenario_id=? AND timestamp>=?
            GROUP BY strftime('%Y-%m-%d %H', timestamp)
            ORDER BY timestamp
        """, (geography, scenario_id, since)).fetchall()
    return [dict(r) for r in rows]


def get_geography_heatmap(hours: int = 24) -> list[dict]:
    """Tüm coğrafyalar için max skor ısı haritası."""
    since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT geography, MAX(score) as max_score,
                   COUNT(CASE WHEN threshold >= 3 THEN 1 END) as critical_count
            FROM scenario_scores
            WHERE timestamp >= ?
            GROUP BY geography
            ORDER BY max_score DESC
        """, (since,)).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        geo_info = GEOGRAPHIES.get(r["geography"], {})
        d["lat"] = geo_info.get("lat")
        d["lon"] = geo_info.get("lon")
        result.append(d)
    return result


# ═══════════════════════════════════════════════════════════
# REFERANS BASELINE ONAY
# ═══════════════════════════════════════════════════════════

def approve_reference_baseline(geography: str, scenario_id: int):
    """
    Mevcut 30 günlük ortalamayı referans baseline olarak onayla.
    Kullanıcı "bu yeni normal" dediğinde çağrılır.
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        roll = conn.execute(
            "SELECT mean_30d FROM rolling_baseline WHERE geography=? AND scenario_id=?",
            (geography, scenario_id)
        ).fetchone()
        if not roll or not roll["mean_30d"]:
            log.warning("Yeterli veri yok — baseline onaylanamadı")
            return False
        conn.execute("""
            INSERT INTO reference_baseline (geography, scenario_id, ref_mean, approved_at)
            VALUES (?,?,?,?)
            ON CONFLICT(geography, scenario_id) DO UPDATE SET
                ref_mean=excluded.ref_mean,
                approved_at=excluded.approved_at
        """, (geography, scenario_id, roll["mean_30d"], datetime.utcnow().isoformat()))
        log.info("Referans baseline onaylandı: %s / senaryo %d = %.2f", geography, scenario_id, roll["mean_30d"])
        return True


# ═══════════════════════════════════════════════════════════
# INIT
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()
    print(f"LOGOSİNT Scoring Engine")
    print(f"  Motor:    {len(MOTORS)}")
    print(f"  Kenar:    {len(EDGES)}")
    print(f"  Senaryo:  {len(SCENARIOS)}")
    print(f"  Ağırlık:  {sum(len(v) for v in EDGE_WEIGHTS.values())}")
    print(f"  Coğrafya: {len(GEOGRAPHIES)}")
    print(f"  DB:       {DB_PATH}")
