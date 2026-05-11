"""
collectors/rss_collector.py

BBC, Reuters, Al Jazeera, AP ve diğer kaynaklardan RSS çeker.
API key gerekmez. Her feed için ayrı event üretir.
"""

import hashlib
import feedparser
import logging
from datetime import datetime
from email.utils import parsedate_to_datetime
from models.event import RawEvent, Domain, GeoPoint
from collectors.base import BaseCollector
from config import RSS_FEEDS

log = logging.getLogger("Collector.RSS")


class RSSCollector(BaseCollector):
    name = "rss"
    domain = Domain.NEWS

    def collect(self) -> list[RawEvent]:
        events = []
        for feed_name, feed_url in RSS_FEEDS.items():
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries[:20]:  # Her feed'den max 20 haber
                    event = self._parse_entry(feed_name, entry)
                    if event:
                        events.append(event)
                self.log.debug("%s: %d haber", feed_name, len(feed.entries[:20]))
            except Exception as e:
                self.log.warning("%s parse hatası: %s", feed_name, e)

        self.log.info("Toplam %d RSS haberi", len(events))
        return events

    def _parse_entry(self, feed_name: str, entry) -> RawEvent | None:
        try:
            title = entry.get("title", "").strip()
            link = entry.get("link", "")
            summary = entry.get("summary", entry.get("description", ""))

            if not title:
                return None

            # Zaman
            published = entry.get("published") or entry.get("updated")
            if published:
                try:
                    ts = parsedate_to_datetime(published).replace(tzinfo=None)
                except Exception:
                    ts = datetime.utcnow()
            else:
                ts = datetime.utcnow()

            full_text = f"{title} {summary}"
            keywords = self.match_keywords(full_text)
            entities = self.extract_entities(full_text)

            # Haber önemliyse (keyword eşleşmesi varsa) işle, yoksa da ekle
            # ama severity analizi anomaly.py'de yapılacak

            event_id = hashlib.md5(link.encode() or title.encode()).hexdigest()[:16]

            return RawEvent(
                source=f"rss_{feed_name.lower().replace(' ', '_')}",
                domain=Domain.NEWS,
                event_id=event_id,
                title=title,
                body=summary[:500] if summary else None,
                url=link,
                timestamp=ts,
                keywords_matched=keywords,
                entities=entities,
                raw_data={
                    "feed_name": feed_name,
                    "author": entry.get("author", ""),
                    "tags": [t.get("term", "") for t in entry.get("tags", [])],
                },
            )
        except Exception as e:
            self.log.debug("Entry parse hatası: %s", e)
            return None
