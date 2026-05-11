"""
collectors/marine_collector.py

AISHub + MarineTraffic — gemi trafik verisi.
AISHub: https://www.aishub.net (ücretsiz, AIS paylaşımı istenir)
MarineTraffic: https://marinetraffic.com (free tier: 100 istek/gün)
"""

import time
import requests
from datetime import datetime
from models.event import RawEvent, Domain, GeoPoint
from collectors.base import BaseCollector
from analysis.anomaly import analyze_numeric
from storage.db import insert_anomaly
from config import AISHUB, MARINETRAFFIC

PORTS = [
    {"locode": "TRISA", "name": "İstanbul Ambarlı", "lat": 40.97, "lon": 28.68, "region": "marmara"},
    {"locode": "TRALI", "name": "Aliağa/Nemrut",    "lat": 38.83, "lon": 26.96, "region": "ege"},
    {"locode": "TRIZM", "name": "İzmir",             "lat": 38.43, "lon": 27.13, "region": "ege"},
    {"locode": "TRMRN", "name": "Mersin",            "lat": 36.79, "lon": 34.63, "region": "akdeniz_tr"},
    {"locode": "TRAYT", "name": "Antalya",           "lat": 36.84, "lon": 30.62, "region": "akdeniz_tr"},
    {"locode": "AEJEA", "name": "Jebel Ali",         "lat": 24.97, "lon": 55.06, "region": "korfez"},
    {"locode": "AEFJR", "name": "Fujairah",          "lat": 25.11, "lon": 56.34, "region": "korfez"},
    {"locode": "IRBND", "name": "Bandar Abbas",      "lat": 27.17, "lon": 56.28, "region": "iran"},
    {"locode": "IRKHK", "name": "Kharg Term.",       "lat": 29.24, "lon": 50.32, "region": "iran"},
    {"locode": "ILASH", "name": "Aşdod",             "lat": 31.82, "lon": 34.65, "region": "levant"},
    {"locode": "EGSOU", "name": "Süveyş",            "lat": 29.96, "lon": 32.55, "region": "suez"},
    {"locode": "EGALY", "name": "İskenderiye",       "lat": 31.19, "lon": 29.88, "region": "suez"},
    {"locode": "GRPIR", "name": "Pire",              "lat": 37.94, "lon": 23.63, "region": "dogu_akdeniz"},
    {"locode": "CYLEM", "name": "Limasol",           "lat": 34.66, "lon": 33.04, "region": "dogu_akdeniz"},
    {"locode": "RULIM", "name": "Novorossiysk",      "lat": 44.72, "lon": 37.79, "region": "rusya_guney"},
    {"locode": "RUULE", "name": "Ust-Luga",          "lat": 59.68, "lon": 28.42, "region": "karadeniz"},
]


class MarineCollector(BaseCollector):
    name = "marine"
    domain = Domain.SEA

    def collect(self) -> list[RawEvent]:
        events = []
        for pt in PORTS:
            count = self._count_vessels(pt)
            station_key = f"marine_{pt['locode']}"

            raw = RawEvent(
                source="marine",
                domain=Domain.SEA,
                event_id=f"marine_{pt['locode']}_{datetime.utcnow().strftime('%Y%m%d%H')}",
                title=f"{pt['locode']} / {pt['name']} — {count} gemi",
                timestamp=datetime.utcnow(),
                location=GeoPoint(
                    lat=pt["lat"], lon=pt["lon"],
                    name=pt["name"], region=pt["region"]
                ),
                affected_regions=[pt["region"]],
                keywords_matched=["maritime"],
                raw_data={"port_locode": pt["locode"], "vessel_count": count},
            )

            anomaly = analyze_numeric(
                station_key=station_key,
                current_value=float(count),
                source="marine",
                event=raw,
            )
            if anomaly.severity.value in ("warning", "critical"):
                insert_anomaly(anomaly.to_dict())

            events.append(raw)
            time.sleep(0.3)

        return events

    def _count_vessels(self, pt: dict, radius_deg: float = 0.3) -> int:
        if AISHUB["user"]:
            lat, lon = pt["lat"], pt["lon"]
            try:
                r = requests.get("https://data.aishub.net/ws.php", params={
                    "username": AISHUB["user"], "format": "1",
                    "output": "json", "compress": "0",
                    "latmin": lat - radius_deg, "latmax": lat + radius_deg,
                    "lonmin": lon - radius_deg, "lonmax": lon + radius_deg,
                }, timeout=15)
                if r.status_code == 200:
                    data = r.json()
                    if isinstance(data, list) and len(data) > 1:
                        return len(data[1]) if isinstance(data[1], list) else 0
            except Exception:
                pass

        if MARINETRAFFIC["api_key"]:
            try:
                r = requests.get(
                    f"https://services.marinetraffic.com/api/getvessel/v:3/{MARINETRAFFIC['api_key']}/",
                    params={
                        "minlat": pt["lat"] - radius_deg, "maxlat": pt["lat"] + radius_deg,
                        "minlon": pt["lon"] - radius_deg, "maxlon": pt["lon"] + radius_deg,
                        "protocol": "jsono",
                    },
                    timeout=15,
                )
                if r.status_code == 200:
                    data = r.json()
                    return len(data) if isinstance(data, list) else 0
            except Exception:
                pass

        return 0
