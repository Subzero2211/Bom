"""
collectors/acled_collector.py

ACLED — Armed Conflict Location & Event Data.
Ücretsiz akademik erişim: https://acleddata.com/register
"""

import requests
from datetime import datetime, timedelta
from models.event import RawEvent, Domain, GeoPoint
from collectors.base import BaseCollector
from analysis.anomaly import analyze_event_severity
from storage.db import insert_anomaly
from config import ACLED


class ACLEDCollector(BaseCollector):
    name = "acled"
    domain = Domain.CONFLICT
    BASE = "https://api.acleddata.com/acled/read"

    EVENT_SEVERITY = {
        "Battles": "high",
        "Explosions/Remote violence": "high",
        "Violence against civilians": "high",
        "Protests": "medium",
        "Riots": "medium",
        "Strategic developments": "low",
    }

    COUNTRIES = [
        "Turkey", "Syria", "Iraq", "Iran", "Israel", "Palestine",
        "Lebanon", "Jordan", "Saudi Arabia", "Yemen", "Libya",
        "Egypt", "Ukraine", "Russia", "Azerbaijan", "Armenia",
        "Georgia", "Sudan", "Ethiopia", "Somalia",
    ]

    def collect(self) -> list[RawEvent]:
        if not ACLED["api_key"] or not ACLED["email"]:
            self.log.info("ACLED API key yok — atlanıyor")
            return []

        events = []
        since = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")

        for country in self.COUNTRIES:
            try:
                r = requests.get(self.BASE, params={
                    "key": ACLED["api_key"],
                    "email": ACLED["email"],
                    "country": country,
                    "event_date": since,
                    "event_date_where": ">=",
                    "limit": 20,
                    "fields": (
                        "event_id_cnty|event_date|event_type|sub_event_type"
                        "|country|admin1|location|latitude|longitude|fatalities|notes"
                    ),
                }, timeout=20)

                if r.status_code != 200:
                    continue

                for item in r.json().get("data", []):
                    ev = self._parse(item)
                    if ev:
                        events.append(ev)

            except Exception as e:
                self.log.warning("ACLED %s hata: %s", country, e)

        return events

    def _parse(self, item: dict) -> RawEvent | None:
        try:
            lat = float(item.get("latitude", 0) or 0)
            lon = float(item.get("longitude", 0) or 0)
            regions = self.region_from_location(lat, lon) if lat and lon else []

            event_type = item.get("event_type", "")
            fatalities = int(item.get("fatalities", 0) or 0)
            location_name = item.get("location", "")
            country = item.get("country", "")
            notes = item.get("notes", "")

            title = f"{event_type} — {location_name}, {country}"
            if fatalities > 0:
                title += f" ({fatalities} kayıp)"

            keywords = self.match_keywords(f"{title} {notes} {event_type}")
            keywords.append("conflict")
            if "explos" in event_type.lower() or "battle" in event_type.lower():
                keywords.append("military")

            raw = RawEvent(
                source="acled",
                domain=Domain.CONFLICT,
                event_id=f"acled_{item.get('event_id_cnty', '')}",
                title=title,
                body=notes[:500] if notes else None,
                timestamp=datetime.strptime(item["event_date"], "%Y-%m-%d"),
                location=GeoPoint(
                    lat=lat, lon=lon,
                    name=location_name, country=country,
                    region=regions[0] if regions else None,
                ) if lat and lon else None,
                affected_regions=regions,
                keywords_matched=list(set(keywords)),
                entities=[country],
                raw_data={
                    "event_type": event_type,
                    "sub_event_type": item.get("sub_event_type", ""),
                    "fatalities": fatalities,
                    "admin1": item.get("admin1", ""),
                },
            )

            sev_str = self.EVENT_SEVERITY.get(event_type, "low")
            anomaly = analyze_event_severity(
                event=raw, source="acled",
                fatalities=fatalities,
                event_type_severity=sev_str,
            )
            if anomaly.severity.value in ("warning", "critical"):
                insert_anomaly(anomaly.to_dict())

            return raw

        except Exception as e:
            self.log.debug("ACLED parse hata: %s", e)
            return None
