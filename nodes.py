"""
nodes.py — Global Stratejik Node Listesi

Tüm izlenecek havalimanları, limanlar, boğazlar ve bölgeler burada tanımlı.
opensky_collector.py ve marine_collector.py bu dosyadan import eder.
Yeni node eklemek için sadece bu dosyayı düzenle.

Bölge mantığı:
  Her node bir veya daha fazla "region" tag'i taşır.
  Korelasyon motoru aynı region'daki nodeları birbirine yakın sayar.
  Boğazlar özel "strait" tag'i alır — geçiş anomalisi kritik önem taşır.
"""

# ═══════════════════════════════════════════════════════════════
# BÖLGE TANIMLARI — (lat_min, lat_max, lon_min, lon_max)
# config.py'deki REGIONS ile senkron tutulmalı
# ═══════════════════════════════════════════════════════════════

REGIONS = {
    # Türkiye
    "marmara":           (40.0, 42.0,  26.0,  31.0),
    "ege":               (36.0, 40.5,  25.0,  28.5),
    "akdeniz_tr":        (35.5, 37.5,  29.0,  37.0),
    "karadeniz":         (41.0, 47.0,  27.0,  42.0),
    "ic_anadolu":        (37.5, 41.0,  31.0,  37.0),
    "guneydogu_tr":      (36.5, 38.5,  37.0,  44.0),

    # Orta Doğu
    "levant":            (29.0, 37.0,  33.0,  38.0),
    "irak":              (29.0, 38.0,  38.0,  49.0),
    "iran":              (25.0, 40.0,  44.0,  64.0),
    "korfez":            (22.0, 28.5,  48.0,  60.0),
    "hurmuz":            (24.0, 27.0,  55.0,  60.0),
    "kizil_deniz":       (11.0, 30.0,  32.0,  44.0),
    "bab_el_mandeb":     (11.0, 13.5,  42.0,  45.5),
    "suez":              (28.5, 32.5,  31.0,  35.5),
    "yemen":             (12.0, 19.0,  42.0,  55.0),
    "misir":             (22.0, 32.5,  24.0,  37.0),

    # Afrika
    "kuzey_afrika":      (19.0, 38.0,  -6.0,  37.0),
    "bati_afrika":       ( 4.0, 16.0, -18.0,   8.0),
    "dogu_afrika":       (-5.0, 15.0,  38.0,  52.0),
    "afrika_boynuzu":    ( 2.0, 15.0,  40.0,  52.0),
    "mozambik_bogazi":   (-27.0, -10.0, 32.0,  42.0),
    "umit_burnu":        (-36.0, -28.0, 15.0,  30.0),

    # Avrupa
    "dogu_akdeniz":      (32.0, 38.0,  22.0,  36.0),
    "bati_akdeniz":      (35.0, 44.0,  -6.0,  15.0),
    "ukrayna":           (44.0, 52.0,  22.0,  40.0),
    "rusya_guney":       (42.0, 48.0,  36.0,  44.0),
    "kafkasya":          (38.0, 44.0,  38.0,  50.0),
    "bati_avrupa":       (42.0, 58.0, -10.0,  10.0),
    "kuzey_avrupa":      (54.0, 70.0,   5.0,  30.0),
    "baltik":            (53.0, 60.0,  14.0,  28.0),
    "danimarkali_bogaz": (54.0, 58.5,   8.0,  15.0),

    # Rusya
    "rusya_bati":        (48.0, 62.0,  28.0,  50.0),
    "rusya_kuzey":       (62.0, 75.0,  28.0,  60.0),
    "arktik":            (70.0, 90.0, -180.0, 180.0),
    "bering":            (52.0, 68.0, 162.0, 190.0),   # -170 + 360

    # Asya-Pasifik
    "hint_okyanusu":     (-20.0, 22.0,  55.0,  95.0),
    "malakka":           ( 1.0,  6.5,   98.0, 105.0),
    "guney_cin_denizi":  ( 0.0, 25.0,  105.0, 122.0),
    "tayvan_bogazi":     (22.0, 26.0,  119.0, 122.5),
    "japonya_denizi":    (32.0, 46.0,  127.0, 142.0),
    "kore_bogazi":       (33.0, 36.0,  128.0, 131.0),
    "cin_kiyisi":        (18.0, 35.0,  108.0, 125.0),
    "japonya":           (30.0, 46.0,  129.0, 146.0),
    "endonezya":         (-9.0,  6.0,   95.0, 141.0),
    "lombok_sunda":      (-9.5, -5.0,  105.0, 116.0),
    "hint_alt_kita":     ( 8.0, 28.0,   68.0,  88.0),

    # Amerika
    "kuzey_atlantik":    (25.0, 60.0,  -80.0, -10.0),
    "karayipler":        (10.0, 25.0,  -85.0, -60.0),
    "kuba_bogazi":       (19.5, 24.0,  -80.0, -74.0),
    "panama_kanali":     ( 7.5, 10.5,  -80.5, -77.5),
    "abd_dogu_yakasi":   (25.0, 47.0,  -82.0, -65.0),
    "abd_bati_yakasi":   (32.0, 50.0, -130.0,-115.0),
    "meksika_korfezi":   (18.0, 30.5,  -98.0, -80.0),
    "latin_amerika":     (-10.0, 15.0, -80.0, -35.0),
    "drake_bogazi":      (-60.0,-55.0, -70.0, -55.0),
}


# ═══════════════════════════════════════════════════════════════
# HAVAALANLARI
# icao, name, lat, lon, region, tags (opsiyonel meta)
# ═══════════════════════════════════════════════════════════════

AIRPORTS = [

    # ── TÜRKİYE ──────────────────────────────────────────────
    {"icao":"LTFM","name":"İstanbul İGA",        "lat":41.27,"lon":28.74,"region":"marmara",      "tags":["hub","nato"]},
    {"icao":"LTBA","name":"İstanbul Sabiha",      "lat":40.90,"lon":29.31,"region":"marmara",      "tags":["hub"]},
    {"icao":"LTAC","name":"Ankara Esenboğa",      "lat":40.12,"lon":32.99,"region":"ic_anadolu",   "tags":["capital","military_nearby"]},
    {"icao":"LTAI","name":"Antalya",              "lat":36.89,"lon":30.79,"region":"akdeniz_tr",   "tags":["tourism"]},
    {"icao":"LTBJ","name":"İzmir Adnan M.",       "lat":38.29,"lon":27.15,"region":"ege",          "tags":["nato","military_nearby"]},
    {"icao":"LTFE","name":"Gaziantep",            "lat":36.95,"lon":37.47,"region":"guneydogu_tr", "tags":["border","conflict_adjacent"]},
    {"icao":"LTCG","name":"Trabzon",              "lat":40.99,"lon":39.79,"region":"karadeniz",    "tags":["karadeniz"]},

    # ── ORTA DOĞU ────────────────────────────────────────────
    {"icao":"OMDB","name":"Dubai Intl",           "lat":25.25,"lon":55.36,"region":"korfez",       "tags":["mega_hub","finance"]},
    {"icao":"OMDW","name":"Dubai Al Maktoum",     "lat":24.90,"lon":55.16,"region":"korfez",       "tags":["cargo","logistics"]},
    {"icao":"OMAA","name":"Abu Dhabi Intl",       "lat":24.43,"lon":54.65,"region":"korfez",       "tags":["hub","sovereign_wealth"]},
    {"icao":"OOMS","name":"Maskat Intl",          "lat":23.59,"lon":58.28,"region":"korfez",       "tags":["hub","neutral"]},
    {"icao":"OEDF","name":"Riyad King Khalid",    "lat":24.96,"lon":46.70,"region":"korfez",       "tags":["capital","military"]},
    {"icao":"OEJN","name":"Cidde King Abdulaziz", "lat":21.68,"lon":39.15,"region":"kizil_deniz",  "tags":["hub","pilgrimage"]},
    {"icao":"LLBG","name":"Tel Aviv Ben Gurion",  "lat":32.00,"lon":34.88,"region":"levant",       "tags":["conflict_adjacent","nato_partner"]},
    {"icao":"OJAM","name":"Amman Queen Alia",     "lat":31.72,"lon":35.99,"region":"levant",       "tags":["hub","refugee_corridor"]},
    {"icao":"ORBI","name":"Bağdat Intl",          "lat":33.26,"lon":44.23,"region":"irak",         "tags":["conflict_adjacent","us_military_nearby"]},
    {"icao":"OIIE","name":"Tahran İmam Humeyni",  "lat":35.41,"lon":51.15,"region":"iran",         "tags":["capital","sanctions_target"]},
    {"icao":"OIII","name":"Tahran Mehrabad",      "lat":35.69,"lon":51.31,"region":"iran",         "tags":["domestic","military"]},
    {"icao":"HECA","name":"Kahire Intl",          "lat":30.12,"lon":31.40,"region":"suez",         "tags":["hub","military_nearby"]},
    {"icao":"OYSN","name":"Sana'a Intl",          "lat":15.48,"lon":44.22,"region":"yemen",        "tags":["conflict","closed_risk"]},
    {"icao":"OBBI","name":"Bahreyn Intl",         "lat":26.27,"lon":50.63,"region":"korfez",       "tags":["us_navy_5th_fleet","nato"]},
    {"icao":"OTBD","name":"Doha Hamad Intl",      "lat":25.26,"lon":51.61,"region":"korfez",       "tags":["hub","us_airbase"]},

    # ── AVRUPA & RUSYA ───────────────────────────────────────
    {"icao":"UUEE","name":"Moskova Şeremetevo",   "lat":55.97,"lon":37.41,"region":"rusya_bati",   "tags":["hub","sanctions_target"]},
    {"icao":"UUWW","name":"Moskova Vnukovo",      "lat":55.60,"lon":37.26,"region":"rusya_bati",   "tags":["government","vip"]},
    {"icao":"URSS","name":"Soçi Adler",           "lat":43.44,"lon":39.94,"region":"rusya_guney",  "tags":["vip","karadeniz"]},
    {"icao":"URKA","name":"Krasnodar",            "lat":45.03,"lon":39.17,"region":"rusya_guney",  "tags":["military_nearby","ukraine_adjacent"]},
    {"icao":"UKBB","name":"Kyiv Boryspil",        "lat":50.34,"lon":30.89,"region":"ukrayna",      "tags":["war_zone_adjacent"]},
    {"icao":"UKFF","name":"Simferopol",           "lat":45.02,"lon":33.97,"region":"ukrayna",      "tags":["occupied","closed"]},
    {"icao":"LGAV","name":"Atina Eleftherios",    "lat":37.94,"lon":23.95,"region":"dogu_akdeniz", "tags":["hub","nato"]},
    {"icao":"LCPH","name":"Lefkoşa Larnaka",      "lat":34.87,"lon":33.62,"region":"dogu_akdeniz", "tags":["intel_hub","uk_base_nearby"]},
    {"icao":"LIRF","name":"Roma Fiumicino",       "lat":41.80,"lon":12.25,"region":"bati_akdeniz", "tags":["hub","nato"]},
    {"icao":"EDDM","name":"Münih",                "lat":48.35,"lon":11.79,"region":"bati_avrupa",  "tags":["hub","nato"]},
    {"icao":"EGLL","name":"Londra Heathrow",      "lat":51.47,"lon":-0.46,"region":"bati_avrupa",  "tags":["mega_hub","5eyes","nato"]},
    {"icao":"LFPG","name":"Paris CDG",            "lat":49.01,"lon": 2.55,"region":"bati_avrupa",  "tags":["mega_hub","nato"]},
    {"icao":"LYBT","name":"Belgrad",              "lat":44.82,"lon":20.31,"region":"bati_avrupa",  "tags":["neutral","russia_corridor"]},
    {"icao":"LQSA","name":"Saraybosna",           "lat":43.82,"lon":18.33,"region":"bati_avrupa",  "tags":["balkans","conflict_history"]},

    # ── AFRİKA ───────────────────────────────────────────────
    {"icao":"HAAB","name":"Addis Ababa Bole",     "lat": 8.98,"lon":38.80,"region":"afrika_boynuzu","tags":["au_hub","strategic"]},
    {"icao":"HDAM","name":"Djibouti Ambouli",     "lat":11.55,"lon":43.16,"region":"bab_el_mandeb", "tags":["us_camp_lemonnier","france","china"]},
    {"icao":"HCMM","name":"Mogadishu Aden Adde",  "lat": 2.01,"lon":45.30,"region":"afrika_boynuzu","tags":["conflict","instability"]},
    {"icao":"DNMM","name":"Lagos Murtala",        "lat": 6.58,"lon": 3.32,"region":"bati_afrika",  "tags":["hub","oil"]},
    {"icao":"FAOR","name":"Johannesburg OR Tambo", "lat":-26.14,"lon":28.24,"region":"umit_burnu",  "tags":["hub","southern_africa"]},
    {"icao":"FMMI","name":"Antananarivo",         "lat":-18.80,"lon":47.48,"region":"hint_okyanusu","tags":["mozambik_bogazi"]},
    {"icao":"DTTA","name":"Tunus Kartaca",        "lat":36.85,"lon":10.23,"region":"kuzey_afrika",  "tags":["migration_route"]},
    {"icao":"HLLT","name":"Trablus Mitiga",       "lat":32.89,"lon":13.28,"region":"kuzey_afrika",  "tags":["conflict","migration"]},

    # ── GÜNEY & ORTA ASYA ─────────────────────────────────────
    {"icao":"VIDP","name":"Delhi IGI",            "lat":28.57,"lon":77.10,"region":"hint_alt_kita", "tags":["mega_hub","quad"]},
    {"icao":"VABB","name":"Mumbai CSIA",          "lat":19.09,"lon":72.87,"region":"hint_alt_kita", "tags":["hub","finance"]},
    {"icao":"OPKC","name":"Karaçi Jinnah",        "lat":24.91,"lon":67.17,"region":"hint_alt_kita", "tags":["strategic","nuclear_state"]},
    {"icao":"OAKB","name":"Kabil Hamid Karzai",   "lat":34.57,"lon":69.21,"region":"hint_alt_kita", "tags":["conflict","us_withdrawal"]},
    {"icao":"UTDD","name":"Duşanbe",              "lat":38.54,"lon":68.77,"region":"hint_alt_kita", "tags":["russia_base","china_adjacent"]},

    # ── DOĞU ASYA & PASİFİK ──────────────────────────────────
    {"icao":"ZBAA","name":"Pekin Capital",        "lat":40.08,"lon":116.59,"region":"cin_kiyisi",   "tags":["mega_hub","government"]},
    {"icao":"ZGSZ","name":"Shenzhen Bao'an",      "lat":22.64,"lon":113.81,"region":"guney_cin_denizi","tags":["taiwan_strait_adjacent"]},
    {"icao":"RCKH","name":"Kaohsiung (Tayvan)",   "lat":22.58,"lon":120.35,"region":"tayvan_bogazi", "tags":["flashpoint","us_partner"]},
    {"icao":"RCTP","name":"Taipei Taoyuan",       "lat":25.08,"lon":121.23,"region":"tayvan_bogazi", "tags":["flashpoint","us_partner"]},
    {"icao":"RJTT","name":"Tokyo Haneda",         "lat":35.55,"lon":139.78,"region":"japonya",       "tags":["hub","quad","us_base_nearby"]},
    {"icao":"RJAA","name":"Tokyo Narita",         "lat":35.77,"lon":140.39,"region":"japonya",       "tags":["hub"]},
    {"icao":"RKSI","name":"Seoul Incheon",        "lat":37.46,"lon":126.44,"region":"kore_bogazi",   "tags":["hub","us_base","north_korea_adjacent"]},
    {"icao":"WMKK","name":"Kuala Lumpur KLIA",    "lat": 2.75,"lon":101.71,"region":"malakka",       "tags":["hub","asean"]},
    {"icao":"WSSS","name":"Singapur Changi",      "lat": 1.36,"lon":103.99,"region":"malakka",       "tags":["mega_hub","us_navy_access","intel"]},
    {"icao":"WIII","name":"Jakarta Soekarno",     "lat":-6.13,"lon":106.65,"region":"endonezya",     "tags":["hub","asean"]},
    {"icao":"VTBS","name":"Bangkok Suvarnabhumi", "lat":13.69,"lon":100.75,"region":"endonezya",     "tags":["hub","asean"]},
    {"icao":"VHHH","name":"Hong Kong Intl",       "lat":22.31,"lon":113.92,"region":"guney_cin_denizi","tags":["finance","china_pressure"]},

    # ── AMERİKA ──────────────────────────────────────────────
    {"icao":"KJFK","name":"New York JFK",         "lat":40.63,"lon":-73.78,"region":"abd_dogu_yakasi","tags":["mega_hub","finance","un_flights"]},
    {"icao":"KIAD","name":"Washington Dulles",    "lat":38.94,"lon":-77.46,"region":"abd_dogu_yakasi","tags":["government","diplomatic"]},
    {"icao":"KLAX","name":"Los Angeles Intl",     "lat":33.94,"lon":-118.41,"region":"abd_bati_yakasi","tags":["mega_hub","pacific"]},
    {"icao":"MUGM","name":"Guantanamo Bay",       "lat":19.91,"lon":-75.21,"region":"kuba_bogazi",    "tags":["us_military","strategic"]},
    {"icao":"MUHA","name":"Havana Jose Marti",    "lat":22.99,"lon":-82.41,"region":"kuba_bogazi",    "tags":["russia_adjacent","strategic"]},
    {"icao":"MPHO","name":"Panama Howard",        "lat": 8.91,"lon":-79.60,"region":"panama_kanali",  "tags":["canal_adjacent"]},
    {"icao":"SCEL","name":"Santiago Arturo M.",   "lat":-33.39,"lon":-70.79,"region":"latin_amerika",  "tags":["hub","southern_cone"]},
    {"icao":"SBGR","name":"São Paulo Guarulhos",  "lat":-23.43,"lon":-46.47,"region":"latin_amerika",  "tags":["mega_hub","brics"]},
]


# ═══════════════════════════════════════════════════════════════
# LİMANLAR
# locode, name, lat, lon, region, type, tags
# ═══════════════════════════════════════════════════════════════

PORTS = [

    # ── TÜRKİYE ──────────────────────────────────────────────
    {"locode":"TRISA","name":"İstanbul Ambarlı",    "lat":40.97,"lon":28.68,"region":"marmara",      "type":"cargo",   "tags":["karadeniz_girisi","bosphorus"]},
    {"locode":"TRGEB","name":"Gebze/Derince",       "lat":40.75,"lon":29.77,"region":"marmara",      "type":"cargo",   "tags":[]},
    {"locode":"TRALI","name":"Aliağa/Nemrut",       "lat":38.83,"lon":26.96,"region":"ege",          "type":"tanker",  "tags":["petrol","rafineri"]},
    {"locode":"TRIZM","name":"İzmir",               "lat":38.43,"lon":27.13,"region":"ege",          "type":"cargo",   "tags":[]},
    {"locode":"TRMRN","name":"Mersin",              "lat":36.79,"lon":34.63,"region":"akdeniz_tr",   "type":"cargo",   "tags":["akdeniz_hub"]},
    {"locode":"TRISB","name":"İskenderun",          "lat":36.58,"lon":36.17,"region":"akdeniz_tr",   "type":"cargo",   "tags":["suriye_siniri"]},
    {"locode":"TRAYT","name":"Antalya",             "lat":36.84,"lon":30.62,"region":"akdeniz_tr",   "type":"cruise",  "tags":["turizm"]},
    {"locode":"TRZGD","name":"Zonguldak",           "lat":41.44,"lon":31.80,"region":"karadeniz",    "type":"cargo",   "tags":["komur","karadeniz"]},
    {"locode":"TRTRAB","name":"Trabzon",            "lat":41.00,"lon":39.72,"region":"karadeniz",    "type":"cargo",   "tags":["karadeniz","rusya_koridoru"]},

    # ── BOĞAZLAR — özel izleme ───────────────────────────────
    {"locode":"STRIST","name":"İstanbul Boğazı",   "lat":41.12,"lon":29.07,"region":"marmara",      "type":"transit", "tags":["strait","critical","karadeniz_kapisi"]},
    {"locode":"STCAN", "name":"Çanakkale Boğazı",  "lat":40.14,"lon":26.40,"region":"ege",          "type":"transit", "tags":["strait","critical","dardanelles"]},
    {"locode":"STHOR", "name":"Hürmüz Boğazı",     "lat":26.57,"lon":56.25,"region":"hurmuz",       "type":"transit", "tags":["strait","critical","petrol","choke_point"]},
    {"locode":"STBAB", "name":"Bab el-Mandeb",     "lat":12.58,"lon":43.47,"region":"bab_el_mandeb","type":"transit", "tags":["strait","critical","choke_point","husi_risk"]},
    {"locode":"STMAL", "name":"Malakka Boğazı",    "lat": 2.50,"lon":101.50,"region":"malakka",     "type":"transit", "tags":["strait","critical","china_japan_energy"]},
    {"locode":"STLOM", "name":"Lombok Boğazı",     "lat":-8.70,"lon":115.70,"region":"lombok_sunda","type":"transit", "tags":["strait","malakka_alternative"]},
    {"locode":"STSUN", "name":"Sunda Boğazı",      "lat":-6.00,"lon":105.80,"region":"lombok_sunda","type":"transit", "tags":["strait","malakka_alternative"]},
    {"locode":"STTAI", "name":"Tayvan Boğazı",     "lat":24.00,"lon":120.50,"region":"tayvan_bogazi","type":"transit", "tags":["strait","critical","flashpoint","us_china"]},
    {"locode":"STKOR", "name":"Kore Boğazı",       "lat":34.50,"lon":129.50,"region":"kore_bogazi", "type":"transit", "tags":["strait","japan_sea"]},
    {"locode":"STDRA", "name":"Drake Geçidi",      "lat":-57.0,"lon":-65.00,"region":"drake_bogazi","type":"transit", "tags":["strait","cape_horn_alternative"]},
    {"locode":"STBER", "name":"Bering Boğazı",     "lat":65.75,"lon":-168.5,"region":"bering",      "type":"transit", "tags":["strait","arctic","russia_usa"]},
    {"locode":"STPAN", "name":"Panama Kanalı",     "lat": 9.00,"lon":-79.70,"region":"panama_kanali","type":"transit", "tags":["canal","critical","pacific_atlantic"]},
    {"locode":"STSUE", "name":"Süveyş Kanalı",     "lat":30.70,"lon":32.35,"region":"suez",         "type":"transit", "tags":["canal","critical","asia_europe"]},
    {"locode":"STDAN", "name":"Danimarkalı Boğaz", "lat":55.00,"lon":10.00,"region":"danimarkali_bogaz","type":"transit","tags":["strait","nato","baltic_access"]},

    # ── KÖRFEZ ───────────────────────────────────────────────
    {"locode":"AEJEA","name":"Jebel Ali",           "lat":24.97,"lon":55.06,"region":"korfez",       "type":"cargo",   "tags":["mega_port","logistics_hub"]},
    {"locode":"AEFJR","name":"Fujairah",            "lat":25.11,"lon":56.34,"region":"korfez",       "type":"tanker",  "tags":["hurmuz_dis","petrol_hub","bunkering"]},
    {"locode":"AEBZH","name":"Abu Dhabi Mina Zayed","lat":24.47,"lon":54.35,"region":"korfez",       "type":"cargo",   "tags":["sovereign_wealth"]},
    {"locode":"OMSOH","name":"Sohar",               "lat":24.36,"lon":56.64,"region":"korfez",       "type":"cargo",   "tags":["hurmuz_dis","bypass"]},
    {"locode":"IRBND","name":"Bandar Abbas",        "lat":27.17,"lon":56.28,"region":"iran",         "type":"cargo",   "tags":["iran_ana_liman","hurmuz"]},
    {"locode":"IRKHK","name":"Kharg Terminali",     "lat":29.24,"lon":50.32,"region":"iran",         "type":"tanker",  "tags":["iran_petrol_ihracat","critical"]},
    {"locode":"IRBUS","name":"Büşehr",              "lat":28.92,"lon":50.83,"region":"iran",         "type":"cargo",   "tags":["nukleer_tesisi_yakin"]},
    {"locode":"IQUMQ","name":"Umm Qasr (Irak)",    "lat":30.03,"lon":47.93,"region":"korfez",       "type":"cargo",   "tags":["irak_tek_deniz_cikisi","petrol"]},
    {"locode":"KWSAA","name":"Shuaiba (Kuveyt)",   "lat":29.04,"lon":48.15,"region":"korfez",       "type":"tanker",  "tags":["petrol"]},
    {"locode":"BHMAM","name":"Bahreyn Mina Salman", "lat":26.21,"lon":50.60,"region":"korfez",       "type":"cargo",   "tags":["us_5th_fleet_adjacent"]},

    # ── KIZIL DENİZ & ADEN ───────────────────────────────────
    {"locode":"YEJIB","name":"Cibuti",             "lat":11.60,"lon":43.15,"region":"bab_el_mandeb","type":"cargo",   "tags":["us_camp_lemonnier","china_base","strategic"]},
    {"locode":"YEADE","name":"Aden",               "lat":12.78,"lon":44.97,"region":"bab_el_mandeb","type":"cargo",   "tags":["bab_el_mandeb","conflict_adjacent"]},
    {"locode":"EGSOU","name":"Süveyş",             "lat":29.96,"lon":32.55,"region":"suez",         "type":"transit", "tags":["kanal_girisi","critical"]},
    {"locode":"EGALY","name":"İskenderiye",        "lat":31.19,"lon":29.88,"region":"misir",        "type":"cargo",   "tags":["misir_ana_liman"]},
    {"locode":"SADHM","name":"Dahban (Cidde)",     "lat":21.48,"lon":39.16,"region":"kizil_deniz",  "type":"cargo",   "tags":["kizil_deniz_hub"]},

    # ── LEVANT ───────────────────────────────────────────────
    {"locode":"ILASH","name":"Aşdod",             "lat":31.82,"lon":34.65,"region":"levant",       "type":"cargo",   "tags":["israil_ana_liman","conflict_adjacent"]},
    {"locode":"ILHFA","name":"Hayfa",             "lat":32.82,"lon":34.98,"region":"levant",       "type":"cargo",   "tags":["israil","nato_partner"]},
    {"locode":"LBBEY","name":"Beyrut",            "lat":33.89,"lon":35.49,"region":"levant",       "type":"cargo",   "tags":["conflict_risk","lübnan"]},
    {"locode":"SYLTK","name":"Lazkiye (Suriye)",  "lat":35.52,"lon":35.77,"region":"levant",       "type":"cargo",   "tags":["rusya_deniz_ussu","tartus_yakin"]},

    # ── KARADENİZ ────────────────────────────────────────────
    {"locode":"UAODS","name":"Odessa",            "lat":46.49,"lon":30.74,"region":"ukrayna",      "type":"cargo",   "tags":["tahil_koridoru","savas_bölgesi"]},
    {"locode":"UAIZM","name":"Pivdenni/Yuzhne",   "lat":46.62,"lon":31.01,"region":"ukrayna",      "type":"tanker",  "tags":["ukrayna_petrol","savas"]},
    {"locode":"RULIM","name":"Novorossiysk",      "lat":44.72,"lon":37.79,"region":"rusya_guney",  "type":"tanker",  "tags":["rusya_karadeniz_ana_liman","tahil","petrol"]},
    {"locode":"RUTUA","name":"Taman",             "lat":45.22,"lon":36.73,"region":"rusya_guney",  "type":"tanker",  "tags":["kercle_bogazi","krim_koridoru"]},
    {"locode":"ROBRA","name":"Köstence (Romanya)","lat":44.17,"lon":28.65,"region":"karadeniz",    "type":"cargo",   "tags":["nato","tahil"]},
    {"locode":"BGSOF","name":"Varna (Bulgaristan)","lat":43.20,"lon":27.92,"region":"karadeniz",   "type":"cargo",   "tags":["nato","karadeniz"]},
    {"locode":"UAOOS","name":"Sevastopol",        "lat":44.62,"lon":33.53,"region":"ukrayna",      "type":"military","tags":["rusya_donanma_ussü","isgal_altinda"]},

    # ── RUSYA BATI ────────────────────────────────────────────
    {"locode":"RUULE","name":"Ust-Luga",          "lat":59.68,"lon":28.42,"region":"rusya_bati",   "type":"cargo",   "tags":["rusya_baltik_ana_liman","sanctions_target"]},
    {"locode":"RUFIN","name":"St. Petersburg",    "lat":59.93,"lon":30.21,"region":"baltik",       "type":"cargo",   "tags":["rusya","baltik","sanctions"]},
    {"locode":"RUGDX","name":"Kaliningrad",       "lat":54.71,"lon":20.51,"region":"baltik",       "type":"military","tags":["nato_kuşatilmiş","rusya_exclave","kritik"]},

    # ── AVRUPA ───────────────────────────────────────────────
    {"locode":"NLRTM","name":"Rotterdam",         "lat":51.92,"lon": 4.48,"region":"bati_avrupa",  "type":"cargo",   "tags":["avrupa_ana_liman","mega_port"]},
    {"locode":"DEHAM","name":"Hamburg",           "lat":53.55,"lon": 9.97,"region":"kuzey_avrupa", "type":"cargo",   "tags":["avrupa_hub"]},
    {"locode":"GRPIR","name":"Pire",              "lat":37.94,"lon":23.63,"region":"dogu_akdeniz", "type":"cargo",   "tags":["cin_cosco_sahibi","avrupa_kapisi"]},
    {"locode":"CYLEM","name":"Limasol",           "lat":34.66,"lon":33.04,"region":"dogu_akdeniz", "type":"cargo",   "tags":["offshore_finance","intel_hub"]},
    {"locode":"MTMLA","name":"Malta Valletta",    "lat":35.90,"lon":14.51,"region":"bati_akdeniz", "type":"cargo",   "tags":["akdeniz_merkezi","bunkering"]},
    {"locode":"ESBAR","name":"Barselona",         "lat":41.35,"lon": 2.16,"region":"bati_akdeniz", "type":"cargo",   "tags":["nato","akdeniz"]},
    {"locode":"ITGOA","name":"Cenova",            "lat":44.41,"lon": 8.93,"region":"bati_akdeniz", "type":"cargo",   "tags":["italya","akdeniz"]},

    # ── AFRİKA ───────────────────────────────────────────────
    {"locode":"ZADRB","name":"Durban",            "lat":-29.87,"lon":31.03,"region":"umit_burnu",  "type":"cargo",   "tags":["guney_afrika","umit_burnu"]},
    {"locode":"MZDZA","name":"Dar es Salaam",     "lat":-6.82,"lon":39.29,"region":"dogu_afrika",  "type":"cargo",   "tags":["tanzanya","hint_okyanusu"]},
    {"locode":"MZMPM","name":"Maputo",            "lat":-25.97,"lon":32.57,"region":"mozambik_bogazi","type":"cargo","tags":["mozambik"]},
    {"locode":"DZALG","name":"Cezayir",           "lat":36.77,"lon": 3.06,"region":"kuzey_afrika", "type":"cargo",   "tags":["gaz_ihracati","avrupa_boru"]},
    {"locode":"LYTBU","name":"Trablus (Libya)",   "lat":32.89,"lon":13.20,"region":"kuzey_afrika", "type":"cargo",   "tags":["petrol","siyasi_kargasa"]},

    # ── HINT OKYANUSU & GÜNEY ASYA ───────────────────────────
    {"locode":"LKCMB","name":"Kolombo",           "lat": 6.95,"lon":79.85,"region":"hint_okyanusu","type":"cargo",   "tags":["cin_brc","hint_okyanusu_stratejik"]},
    {"locode":"MVMLE","name":"Male (Maldivler)",  "lat": 4.18,"lon":73.53,"region":"hint_okyanusu","type":"cargo",   "tags":["hint_okyanusu","ABD_cin_rekabeti"]},
    {"locode":"DJJIB","name":"Djibouti Doraleh",  "lat":11.60,"lon":43.15,"region":"bab_el_mandeb","type":"cargo",   "tags":["cin_ussu","us_camp_lemonnier"]},
    {"locode":"PKQCT","name":"Gwadar (Pakistan)", "lat":25.12,"lon":62.33,"region":"hint_alt_kita","type":"cargo",   "tags":["cpec","cin_stratejik","hurmuz_yakin"]},
    {"locode":"INPAV","name":"Kandla (Hindistan)","lat":23.00,"lon":70.22,"region":"hint_alt_kita","type":"cargo",   "tags":["hint_petrol_girisi"]},
    {"locode":"MMRGU","name":"Rangoon (Myanmar)", "lat":16.77,"lon":96.16,"region":"malakka",      "type":"cargo",   "tags":["cin_koridoru","malakka_bypass"]},

    # ── DOĞU ASYA ────────────────────────────────────────────
    {"locode":"CNSHA","name":"Şangay",            "lat":31.23,"lon":121.47,"region":"cin_kiyisi",  "type":"cargo",   "tags":["dunya_1_konteyner_liman","mega_port"]},
    {"locode":"CNNBO","name":"Ningbo-Zhoushan",   "lat":29.87,"lon":121.55,"region":"cin_kiyisi",  "type":"cargo",   "tags":["dunya_2_konteyner_liman"]},
    {"locode":"CNSZX","name":"Shenzhen",          "lat":22.54,"lon":113.90,"region":"guney_cin_denizi","type":"cargo","tags":["mega_port","taiwan_bogazi"]},
    {"locode":"HKHKG","name":"Hong Kong",         "lat":22.28,"lon":114.18,"region":"guney_cin_denizi","type":"cargo","tags":["finance","transit"]},
    {"locode":"SGSIN","name":"Singapur",          "lat": 1.25,"lon":103.82,"region":"malakka",     "type":"cargo",   "tags":["dunya_2_liman","stratejik_malakka","us_access"]},
    {"locode":"MYPKG","name":"Port Klang",        "lat": 3.00,"lon":101.40,"region":"malakka",     "type":"cargo",   "tags":["malakka","asean_hub"]},
    {"locode":"IDBAT","name":"Batam/Bintan",      "lat": 1.12,"lon":104.06,"region":"malakka",     "type":"cargo",   "tags":["malakka_girisi","freeport"]},
    {"locode":"JPTYO","name":"Tokyo/Yokohama",    "lat":35.46,"lon":139.65,"region":"japonya",     "type":"cargo",   "tags":["japonya_ana_liman","us_7th_fleet"]},
    {"locode":"KRPUS","name":"Busan (Güney Kore)","lat":35.10,"lon":129.04,"region":"kore_bogazi", "type":"cargo",   "tags":["asya_hub","us_base_yakin"]},
    {"locode":"RUNAK","name":"Nahodka/Vostochny", "lat":42.82,"lon":132.89,"region":"japonya_denizi","type":"cargo", "tags":["rusya_uzak_dogu","cin_ticaret"]},

    # ── AMERİKA ──────────────────────────────────────────────
    {"locode":"USNYC","name":"New York/New Jersey","lat":40.67,"lon":-74.07,"region":"abd_dogu_yakasi","type":"cargo","tags":["mega_port","abd_dogu"]},
    {"locode":"USLAX","name":"Los Angeles/Long Beach","lat":33.74,"lon":-118.27,"region":"abd_bati_yakasi","type":"cargo","tags":["mega_port","pasifik","cin_ticaret"]},
    {"locode":"USHOU","name":"Houston",           "lat":29.75,"lon":-95.36,"region":"meksika_korfezi","type":"tanker","tags":["abd_petrol","lng_ihracat"]},
    {"locode":"USSAV","name":"Savannah",          "lat":32.08,"lon":-81.09,"region":"abd_dogu_yakasi","type":"cargo","tags":["abd_lojistik_hub"]},
    {"locode":"CUBHV","name":"Havana",            "lat":23.15,"lon":-82.37,"region":"kuba_bogazi",  "type":"cargo",   "tags":["rusya_cin_koridoru","abd_karşısı"]},
    {"locode":"PABALB","name":"Balboa (Panama)",  "lat": 8.94,"lon":-79.57,"region":"panama_kanali","type":"cargo",  "tags":["kanal_girisi_pasifik"]},
    {"locode":"BRSAO","name":"Santos (Brezilya)", "lat":-23.97,"lon":-46.32,"region":"latin_amerika","type":"cargo",  "tags":["güney_amerika_ana_liman","brics"]},
    {"locode":"ARBA2","name":"Buenos Aires",      "lat":-34.59,"lon":-58.37,"region":"latin_amerika","type":"cargo",  "tags":["drake_alternatifi","güney_koni"]},
]


# ═══════════════════════════════════════════════════════════════
# YARDIMCI FONKSİYONLAR
# ═══════════════════════════════════════════════════════════════

def airports_by_region(region: str) -> list[dict]:
    return [a for a in AIRPORTS if a["region"] == region]


def ports_by_region(region: str) -> list[dict]:
    return [p for p in PORTS if p["region"] == region]


def straits() -> list[dict]:
    return [p for p in PORTS if "strait" in p.get("tags", [])]


def airports_by_tag(tag: str) -> list[dict]:
    return [a for a in AIRPORTS if tag in a.get("tags", [])]


def ports_by_tag(tag: str) -> list[dict]:
    return [p for p in PORTS if tag in p.get("tags", [])]


def choke_points() -> list[dict]:
    """Stratejik geçiş noktaları — dünya ticaretinin kritik darboğazları."""
    return [p for p in PORTS if "choke_point" in p.get("tags", []) or "critical" in p.get("tags", [])]


def print_summary():
    straits_list = straits()
    choke_list   = choke_points()
    print(f"\nGlobal Node Özeti:")
    print(f"  Havalimanı : {len(AIRPORTS)}")
    print(f"  Liman      : {len(PORTS)}")
    print(f"  Boğaz      : {len(straits_list)}")
    print(f"  Darboğaz   : {len(choke_list)}")
    print(f"  Bölge      : {len(REGIONS)}")
    print(f"\nStratejik Boğazlar:")
    for s in straits_list:
        print(f"  {s['locode']:10} {s['name']}")


if __name__ == "__main__":
    print_summary()
