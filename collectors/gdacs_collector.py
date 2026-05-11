"""
collectors/gdacs_collector.py

GDACS — Global Disaster Alert and Coordination System.
BM'nin resmi doğal afet uyarı sistemi. Tamamen ücretsiz, API key yok.
https://www.gdacs.org/xml/rss.xml
"""

import hashlib
import feedparser
from datetime import datetime
from models.event import RawEvent, Domain, GeoPoint
from collectors.base import BaseCollector
from analysis.anomaly import analyze_event_severity
from storage.db import insert_anomaly

GDACS_FEEDS = {
    "all":        "https://www.gdacs.org/xml/rss.xml",
    "earthquakes":"https://www.gdacs.org/xml/rss_eq.xml",
    "cyclones":   "https://www.gdacs.org/xml/rss_tc.xml",
    "floods":     "https://www.gdacs.org/xml/rss_fl.xml",
}

GDACS_ALERT_MAP = {
    "Red":    "critical",
    "Orange": "high",
    "Green":  "low",
}

# Jeopolitik açıdan kritik bölgelerde afet → ekstra önem
CRITICAL_REGIONS_BBOX = [
    (35, 45, 25, 45),    # Türkiye + Doğu Akdeniz
    (22, 40, 44, 65),    # Körfez + İran
    (10, 32, 32, 44),    # Kızıldeniz + Yemen
    (44, 52, 22, 40),    # Ukrayna
]


class GDACSCollector(BaseCollector):
    name = "gdacs"
    domain = Domain.DISASTER

    def collect(self) -> list[RawEvent]:
        events = []
        seen_ids = set()

        for feed_name, url in GDACS_FEEDS.items():
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:20]:
                    ev = self._parse_entry(entry)
                    if ev and ev.event_id not in seen_ids:
                        seen_ids.add(ev.event_id)
                        events.append(ev)
            except Exception as e:
                self.log.warning("GDACS feed '%s' hata: %s", feed_name, e)

        self.log.info("%d GDACS uyarısı işlendi", len(events))
        return events

    def _parse_entry(self, entry) -> RawEvent | None:
        try:
            title = entry.get("title", "").strip()
            link  = entry.get("link", "")
            summary = entry.get("summary", "")

            alert_level = (
                entry.get("gdacs_alertlevel")
                or entry.get("cap_severity", "Green")
            )
            event_type = entry.get("gdacs_eventtype", "")
            country    = entry.get("gdacs_country", "")

            # Koordinat — birden fazla olası alan
            lat = lon = 0.0
            for lat_key in ("geo_lat", "gdacs_latitude", "cap_point"):
                val = entry.get(lat_key)
                if val:
                    try:
                        lat = float(str(val).split()[0])
                        break
                    except Exception:
                        pass
            for lon_key in ("geo_long", "gdacs_longitude"):
                val = entry.get(lon_key)
                if val:
                    try:
                        lon = float(str(val).split()[-1])
                        break
                    except Exception:
                        pass

            regions = self.region_from_location(lat, lon) if lat and lon else []

            # Jeopolitik bölgede mi?
            in_critical = False
            if lat and lon:
                for (lat_min, lat_max, lon_min, lon_max) in CRITICAL_REGIONS_BBOX:
                    if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
                        in_critical = True
                        break

            keywords = ["disaster"]
            if in_critical:
                keywords.append("crisis")
            if event_type in ("EQ", "TS"):
                keywords.extend(["military", "energy"])  # altyapı riski

            event_id = hashlib.md5((link or title).encode()).hexdigest()[:16]

            raw = RawEvent(
                source="gdacs",
                domain=Domain.DISASTER,
                event_id=f"gdacs_{event_id}",
                title=title,
                body=summary[:400] if summary else None,
                url=link,
                timestamp=datetime.utcnow(),
                location=GeoPoint(
                    lat=lat, lon=lon,
                    name=country, country=country,
                    region=regions[0] if regions else None,
                ) if lat and lon else None,
                affected_regions=regions,
                keywords_matched=keywords,
                entities=[country] if country else [],
                raw_data={
                    "alert_level": alert_level,
                    "event_type": event_type,
                    "country": country,
                    "in_critical_region": in_critical,
                },
            )

            sev_str = GDACS_ALERT_MAP.get(alert_level, "low")
            # Kritik bölgede orta seviye afet → bir adım yukarı
            if in_critical and sev_str == "low":
                sev_str = "medium"

            anomaly = analyze_event_severity(
                event=raw,
                source="gdacs",
                event_type_severity=sev_str,
            )
            if anomaly.severity.value in ("warning", "critical"):
                insert_anomaly(anomaly.to_dict())
                self.log.warning(
                    "GDACS [%s] %s — %s", alert_level, title[:60], country
                )

            return raw

        except Exception as e:
            self.log.debug("GDACS entry hata: %s", e)
            return None
