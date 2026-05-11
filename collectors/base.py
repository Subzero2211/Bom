"""
collectors/base.py

Tüm collector'ların miras aldığı base class.
Her collector collect() metodunu implement eder,
RawEvent listesi döndürür.
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import Optional
from models.event import RawEvent, Domain
from config import KEYWORDS

log = logging.getLogger("Collector")


class BaseCollector(ABC):
    """
    Her kaynak için temel yapı.
    Subclass'lar sadece collect() metodunu implement eder.
    """

    name: str = "base"
    domain: Domain = Domain.NEWS

    def __init__(self):
        self.log = logging.getLogger(f"Collector.{self.name}")
        self._last_run: Optional[float] = None
        self._consecutive_errors: int = 0
        self._max_errors: int = 5

    def run(self) -> list[RawEvent]:
        """
        Güvenli çalıştırma wrapper'ı.
        Hata sayacı, backoff, loglama.
        """
        try:
            start = time.time()
            events = self.collect()
            elapsed = time.time() - start
            self._consecutive_errors = 0
            self._last_run = time.time()
            self.log.info("✓ %d event toplandı (%.1fs)", len(events), elapsed)
            return events
        except Exception as e:
            self._consecutive_errors += 1
            self.log.error("✗ Hata #%d: %s", self._consecutive_errors, e)
            if self._consecutive_errors >= self._max_errors:
                self.log.critical(
                    "Collector %s %d ardışık hata — devre dışı bırakıldı",
                    self.name, self._max_errors
                )
            return []

    @abstractmethod
    def collect(self) -> list[RawEvent]:
        """Veriyi çek, RawEvent listesi döndür."""
        raise NotImplementedError

    # ── Yardımcı metodlar ────────────────────────────────────

    def match_keywords(self, text: str) -> list[str]:
        """
        Metinde hangi keyword gruplarının eşleştiğini döndür.
        config.KEYWORDS'deki grupları kontrol eder.
        """
        text_lower = text.lower()
        matched = []
        for group, words in KEYWORDS.items():
            if any(w.lower() in text_lower for w in words):
                matched.append(group)
        return matched

    def extract_entities(self, text: str) -> list[str]:
        """
        Basit entity extraction — ülke isimleri.
        Production'da spaCy veya GeoNames ile değiştirilmeli.
        """
        COUNTRY_NAMES = [
            "Turkey", "Türkiye", "Russia", "Rusya", "Iran", "İran",
            "Israel", "İsrail", "Saudi Arabia", "Suudi Arabistan",
            "UAE", "Egypt", "Mısır", "Iraq", "Irak", "Syria", "Suriye",
            "Ukraine", "Ukrayna", "China", "Çin", "USA", "United States",
            "Germany", "France", "UK", "Britain", "Greece", "Yunanistan",
            "Lebanon", "Lübnan", "Jordan", "Ürdün", "Qatar", "Katar",
            "Kuwait", "Kuveyt", "Oman", "Umman", "Azerbaijan", "Azerbaycan",
            "Armenia", "Ermenistan", "Georgia", "Gürcistan",
        ]
        text_lower = text.lower()
        return [c for c in COUNTRY_NAMES if c.lower() in text_lower]

    def region_from_location(self, lat: float, lon: float) -> list[str]:
        """
        Koordinattan etkilenen bölgeleri döndür.
        config.REGIONS bounding box'larına göre.
        """
        from config import REGIONS
        matched = []
        for region_name, (lat_min, lat_max, lon_min, lon_max) in REGIONS.items():
            if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
                matched.append(region_name)
        return matched
