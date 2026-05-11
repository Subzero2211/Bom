"""
collectors/gdelt_collector.py

GDELT Project — dünya geneli haber olayları, tamamen ücretsiz.
GKG (Global Knowledge Graph) ve Events tablosunu kullanır.

Endpoint: https://api.gdeltproject.org/api/v2/
Döküman:  https://blog.gdeltproject.org/gdelt-2-0-our-global-world-in-realtime/
"""

import hashlib
import requests
import logging
from datetime import datetime, timedelta
from models.event import RawEvent, Domain, GeoPoint
from collectors.base import BaseCollector

log = logging.getLogger("Collector.GDELT")

# İzlenecek ülke kodları (FIPS)
COUNTRIES_OF_INTEREST = {
    "TR": "Türkiye", "RS": "Rusya", "IR": "İran", "IS": "İsrail",
    "SA": "Suudi Arabistan", "AE": "BAE", "EG": "Mısır", "IZ": "Irak",
    "SY": "Suriye", "UP": "Ukrayna", "GG": "Gürcistan", "JO": "Ürdün",
    "LE": "Lübnan", "QA": "Katar", "KU": "Kuveyt", "OM": "Umman",
    "GR": "Yunanistan", "CY": "Kıbrıs", "AJ": "Azerbaycan",
}

# İlgilendiğimiz CAMEO olay kodları (ilk 2 rakam)
# https://www.gdeltproject.org/data/documentation/CAMEO.Manual.1.1b3.pdf
CAMEO_OF_INTEREST = {
    "14": "Protesto",
    "15": "Tehdit",
    "17": "Baskı / Yaptırım",
    "18": "Saldırı / Askeri eylem",
    "19": "Kitle şiddeti",
    "20": "Toplu şiddet",
}


class GDELTCollector(BaseCollector):
    name = "gdelt"
    domain = Domain.NEWS

    BASE_URL = "https://api.gdeltproject.org/api/v2"

    def collect(self) -> list[RawEvent]:
        events = []

        # 1. Son 15 dakikadaki olayları çek (GDELT 15 dakikada bir güncellenir)
        events += self._fetch_events()

        # 2. Bölgesel haber arama
        events += self._fetch_news_mentions()

        return events

    def _fetch_events(self) -> list[RawEvent]:
        """
        GDELT Events tablosu — son 15 dakika, ilgi alanı ülkeler + CAMEO kodları.
        """
        url = f"{self.BASE_URL}/events/search"
        params = {
            "query": " OR ".join(
                [f"countrycode:{c}" for c in list(COUNTRIES_OF_INTEREST.keys())[:8]]
            ),
            "mode": "artlist",
            "maxrecords": 50,
            "format": "json",
            "timespan": "15min",
            "sort": "GoldsteinScale",
        }
        try:
            r = requests.get(url, params=params, timeout=15)
            if r.status_code != 200:
                self.log.warning("GDELT events HTTP %d", r.status_code)
                return []
            data = r.json()
            articles = data.get("articles", [])
            result = []
            for art in articles:
                ev = self._parse_gdelt_article(art, "gdelt_events")
                if ev:
                    result.append(ev)
            return result
        except Exception as e:
            self.log.error("GDELT events hata: %s", e)
            return []

    def _fetch_news_mentions(self) -> list[RawEvent]:
        """
        GDELT GKG — jeopolitik + askeri + enerji konu araması.
        """
        queries = [
            "military strike attack missile",
            "sanctions embargo oil gas pipeline",
            "naval blockade strait tanker",
            "coup protest civil unrest",
        ]
        result = []
        for q in queries:
            url = f"{self.BASE_URL}/doc/search"
            params = {
                "query": q,
                "mode": "artlist",
                "maxrecords": 20,
                "format": "json",
                "timespan": "1h",
                "sort": "hybridrel",
            }
            try:
                r = requests.get(url, params=params, timeout=15)
                if r.status_code != 200:
                    continue
                data = r.json()
                for art in data.get("articles", []):
                    ev = self._parse_gdelt_article(art, f"gdelt_{q.split()[0]}")
                    if ev:
                        result.append(ev)
            except Exception as e:
                self.log.debug("GDELT mention hata (%s): %s", q, e)
        return result

    def _parse_gdelt_article(self, art: dict, source_tag: str) -> RawEvent | None:
        try:
            title = art.get("title", "").strip()
            url = art.get("url", "")
            if not title or not url:
                return None

            event_id = hashlib.md5(url.encode()).hexdigest()[:16]

            # Zaman
            seendate = art.get("seendate", "")
            try:
                ts = datetime.strptime(seendate[:14], "%Y%m%dT%H%M%S")
            except Exception:
                ts = datetime.utcnow()

            # Coğrafya
            location = None
            lat = art.get("geolat")
            lon = art.get("geolong")
            if lat and lon:
                try:
                    flat, flon = float(lat), float(lon)
                    regions = self.region_from_location(flat, flon)
                    location = GeoPoint(
                        lat=flat, lon=flon,
                        name=art.get("geofullname", ""),
                        country=art.get("sourcecountry", ""),
                        region=regions[0] if regions else None,
                    )
                except Exception:
                    pass

            full_text = f"{title} {art.get('domain', '')}"
            keywords = self.match_keywords(full_text)
            entities = self.extract_entities(full_text)

            # Goldstein Scale: -10 (şiddet) → +10 (işbirliği)
            goldstein = art.get("goldstein", 0)
            try:
                goldstein = float(goldstein)
            except Exception:
                goldstein = 0

            return RawEvent(
                source=source_tag,
                domain=Domain.NEWS,
                event_id=event_id,
                title=title,
                url=url,
                timestamp=ts,
                location=location,
                affected_regions=self.region_from_location(
                    location.lat, location.lon
                ) if location else [],
                keywords_matched=keywords,
                entities=entities,
                raw_data={
                    "goldstein": goldstein,
                    "domain": art.get("domain", ""),
                    "language": art.get("language", ""),
                    "sourcecountry": art.get("sourcecountry", ""),
                    "socialsharecount": art.get("socialsharecount", 0),
                },
            )
        except Exception as e:
            self.log.debug("GDELT parse hata: %s", e)
            return None
