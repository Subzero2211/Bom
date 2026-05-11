"""
collectors/opensky_collector.py

OpenSky Network — gerçek zamanlı ADS-B uçuş verisi.
Tamamen ücretsiz, kayıt opsiyonel (kayıtlı = daha yüksek rate limit).
API Docs: https://opensky-network.org/apidoc/
"""

import time
import hashlib
import requests
import logging
from datetime import datetime
from models.event import RawEvent, Domain, GeoPoint
from models.event import AnomalyEvent
from collectors.base import BaseCollector
from analysis.anomaly import analyze_numeric
from storage.db import insert_anomaly
from config import OPENSKY, REGIONS

log = logging.getLogger("Collector.OpenSky")

# İzlenecek havalimanları
AIRPORTS = [
    {"icao": "LTFM", "name": "İstanbul",        "lat": 41.27, "lon": 28.74, "region": "marmara"},
    {"icao": "LTBA", "name": "İst. Sabiha",      "lat": 40.90, "lon": 29.31, "region": "marmara"},
    {"icao": "LTAI", "name": "Antalya",           "lat": 36.89, "lon": 30.79, "region": "akdeniz_tr"},
    {"icao": "LTBJ", "name": "İzmir",             "lat": 38.29, "lon": 27.15, "region": "ege"},
    {"icao": "OMDB", "name": "Dubai",             "lat": 25.25, "lon": 55.36, "region": "korfez"},
    {"icao": "OOMS", "name": "Maskat",            "lat": 23.59, "lon": 58.28, "region": "korfez"},
    {"icao": "UUEE", "name": "Moskova",           "lat": 55.97, "lon": 37.41, "region": "rusya_guney"},
    {"icao": "LLBG", "name": "Tel Aviv",          "lat": 32.00, "lon": 34.88, "region": "levant"},
    {"icao": "OJAM", "name": "Amman",             "lat": 31.72, "lon": 35.99, "region": "levant"},
    {"icao": "ORBI", "name": "Bağdat",            "lat": 33.26, "lon": 44.23, "region": "levant"},
    {"icao": "OIII", "name": "Tahran",            "lat": 35.69, "lon": 51.31, "region": "iran"},
    {"icao": "HECA", "name": "Kahire",            "lat": 30.12, "lon": 31.40, "region": "suez"},
    {"icao": "LGAV", "name": "Atina",             "lat": 37.94, "lon": 23.95, "region": "dogu_akdeniz"},
    {"icao": "LCPH", "name": "Lefkoşa",           "lat": 34.87, "lon": 33.62, "region": "dogu_akdeniz"},
    {"icao": "UKBB", "name": "Kyiv",              "lat": 50.34, "lon": 30.89, "region": "ukrayna"},
]


class OpenSkyCollector(BaseCollector):
    name = "opensky"
    domain = Domain.AIR
    BASE = "https://opensky-network.org/api"

    def _get(self, endpoint: str, params: dict = None) -> dict | None:
        auth = None
        if OPENSKY["user"] and OPENSKY["password"]:
            auth = (OPENSKY["user"], OPENSKY["password"])
        try:
            r = requests.get(
                self.BASE + endpoint, params=params, auth=auth, timeout=15
            )
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                self.log.warning("Rate limit — 20s bekliyor")
                time.sleep(20)
            return None
        except Exception as e:
            self.log.error("OpenSky bağlantı hatası: %s", e)
            return None

    def collect(self) -> list[RawEvent]:
        events = []
        for ap in AIRPORTS:
            count = self._count_flights_near(ap)
            station_key = f"opensky_{ap['icao']}"

            raw = RawEvent(
                source="opensky",
                domain=Domain.AIR,
                event_id=f"opensky_{ap['icao']}_{datetime.utcnow().strftime('%Y%m%d%H')}",
                title=f"{ap['icao']} / {ap['name']} — {count} aktif uçuş",
                timestamp=datetime.utcnow(),
                location=GeoPoint(
                    lat=ap["lat"], lon=ap["lon"],
                    name=ap["name"], region=ap["region"]
                ),
                affected_regions=[ap["region"]],
                keywords_matched=["aviation"],
                raw_data={"airport_icao": ap["icao"], "flight_count": count},
            )

            anomaly = analyze_numeric(
                station_key=station_key,
                current_value=float(count),
                source="opensky",
                event=raw,
            )

            # Anomali ise DB'ye kaydet
            if anomaly.severity.value in ("warning", "critical"):
                insert_anomaly(anomaly.to_dict())

            events.append(raw)
            time.sleep(0.5)   # Rate limit koruması

        return events

    def _count_flights_near(self, ap: dict, radius_deg: float = 0.8) -> int:
        """Havalimanı etrafındaki bbox'ta aktif uçuş say."""
        lat, lon = ap["lat"], ap["lon"]
        data = self._get("/states/all", {
            "lamin": lat - radius_deg, "lamax": lat + radius_deg,
            "lomin": lon - radius_deg, "lomax": lon + radius_deg,
        })
        if data and data.get("states"):
            return len(data["states"])
        return 0
