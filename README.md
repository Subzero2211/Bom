# OSINT Intelligence Engine

Çok kaynaklı açık kaynak istihbarat motoru.
Haber, uçuş, gemi, çatışma, ekonomi ve afet verilerini gerçek zamanlı birleştirir,
coğrafi + zamansal + tematik korelasyon yaparak istihbarat sentezi üretir.

---

## Kurulum

```bash
# 1. Klonla / klasörü aç
cd osint_engine

# 2. Sanal ortam oluştur (önerilir)
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Bağımlılıkları kur
pip install -r requirements.txt

# 4. config.py'yi düzenle — API keylerini gir
nano config.py

# 5. Başlat
python main.py
```

---

## API Keyleri

| Kaynak | Nereden | Ücret |
|--------|---------|-------|
| OpenSky Network | opensky-network.org/register | Ücretsiz |
| AISHub | aishub.net/register | Ücretsiz (AIS paylaşımı) |
| MarineTraffic | marinetraffic.com/en/ais-api-services | Free tier: 100/gün |
| ACLED | acleddata.com/register | Ücretsiz (akademik) |
| Reddit | reddit.com/prefs/apps → "script" | Ücretsiz |
| FRED | fred.stlouisfed.org/docs/api | Ücretsiz |
| Telegram | my.telegram.org | Ücretsiz |
| NewsAPI | newsapi.org/register | Free tier: 100/gün |
| GDELT | Yok (key gereksiz) | Tamamen ücretsiz |
| GDACS | Yok (key gereksiz) | Tamamen ücretsiz |
| RSS Feeds | Yok | Tamamen ücretsiz |

---

## Sistem Mimarisi

```
KAYNAKLAR              ANALİZ                  ÇIKTI
──────────             ──────                  ──────
RSS (BBC/Reuters) ──→                          
GDELT            ──→  anomaly.py              
OpenSky          ──→  Z-score /          ──→  correlator.py  ──→  synthesizer.py
MarineTraffic    ──→  frekans spike           Coğrafi +            İstihbarat
ACLED            ──→  analizi                 Zamansal +           Raporu
Reddit           ──→                          Tematik              (SQLite)
Telegram         ──→                          korelasyon
FRED             ──→
GDACS            ──→
```

### Korelasyon Tipleri

| Tip | Anlam | Örnek |
|-----|-------|-------|
| `parallel` | Aynı yön anomali | Tel Aviv ✈ ↓ + Aşdod ⚓ ↓ → bölgesel kapanma |
| `divergent` | Ters yön (pivot) | Moskova ✈ ↓ + Mersin ⚓ ↑ → trafik kayması |
| `cascade` | Haber → fiziksel | Haber spike → uçuş anomalisi → gemi anomalisi |

### Severity Seviyeleri

| Seviye | Z-score / Kriter |
|--------|-----------------|
| `ok` | \|z\| < 2.0 |
| `info` | Yeni veri / baseline oluşturuluyor |
| `warning` | \|z\| ≥ 2.0 veya haber 2.5x spike |
| `critical` | \|z\| ≥ 3.0 veya haber 5x spike |

---

## API Endpoints

Sistem başladıktan sonra `http://localhost:5055` üzerinden:

```
GET /api/status        → Sistem durumu + son rapor özeti
GET /api/report        → Tam istihbarat raporu (JSON)
GET /api/anomalies     → Aktif anomaliler (?hours=12&domain=air)
GET /api/clusters      → Korelasyon kümeleri (?hours=24)
GET /api/events        → Ham olaylar (?domain=news&region=levant&limit=100)
GET /api/sources       → Kaynak konfigürasyonu
POST /api/scan         → Manuel tarama tetikle
```

### Örnek: Son raporu çek

```bash
curl http://localhost:5055/api/report | python -m json.tool
```

### Örnek: Levant bölgesi anomalileri

```bash
curl "http://localhost:5055/api/anomalies?region=levant&hours=24"
```

---

## Tarama Aralıkları

| Kaynak | Aralık | Neden |
|--------|--------|-------|
| Telegram | 5 dk | Gerçek zamanlıya en yakın |
| RSS | 15 dk | Makul gecikme |
| OpenSky | 20 dk | 100/gün bütçe koruması |
| MarineTraffic | 20 dk | 100/gün bütçe koruması |
| GDELT | 30 dk | Yükü düşük tut |
| Reddit | 30 dk | Rate limit |
| GDACS | 60 dk | Afetler sık değişmez |
| ACLED | 360 dk | Günlük güncelleniyor |
| FRED | 1440 dk | Günlük ekonomik veri |

---

## Veritabanı

SQLite — `osint_data.db` (otomatik oluşturulur)

```bash
# Son 10 anomaliyi gör
sqlite3 osint_data.db "SELECT source, severity, description, timestamp FROM anomaly_events ORDER BY timestamp DESC LIMIT 10;"

# Aktif korelasyonları gör
sqlite3 osint_data.db "SELECT cluster_id, severity, summary FROM correlation_clusters ORDER BY last_seen DESC LIMIT 5;"

# Son raporu çek
sqlite3 osint_data.db "SELECT generated_at, system_status, active_anomalies FROM intel_reports ORDER BY generated_at DESC LIMIT 1;"
```

---

## Genişletme

Yeni kaynak eklemek için:

1. `collectors/` altına yeni collector dosyası oluştur
2. `BaseCollector`'ı miras al, `collect()` metodunu implement et
3. `RawEvent` listesi döndür
4. `main.py`'deki `COLLECTORS` dict'ine ekle
5. `config.py`'ye tarama aralığını ekle

```python
# collectors/yeni_collector.py
from collectors.base import BaseCollector
from models.event import RawEvent, Domain

class YeniCollector(BaseCollector):
    name = "yeni"
    domain = Domain.NEWS

    def collect(self) -> list[RawEvent]:
        # Veriyi çek
        # RawEvent listesi döndür
        return []
```

---

## Notlar

- **Gri alan kaynaklar** (Telegram, bazı scraping): Kendi sorumluluğunuzda kullanın.
- **ACLED**: Akademik kullanım için ücretsiz, ticari kullanım için lisans gerekebilir.
- **MarineTraffic free tier**: 100 istek/gün — 20 dakikalık tarama ile 72/gün = limitin içinde.
- **OpenSky kayıtsız kullanım**: Her 10 saniyede 1 istek. Kayıtlı: daha yüksek limit.
- Sistem ilk 5 taramada baseline oluşturur, bu sürede anomali üretmez.
