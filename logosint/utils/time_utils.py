"""
logosint/utils/time_utils.py

Timezone-safe datetime yardımcıları.

Neden: Naive datetime + timezone-aware datetime karıştırılınca
       trend sorguları yanlış sonuç verir.
Çözüm: Her yerde UTC-aware datetime kullan.
       Collector timestamp'leri normalize et.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional, Union
import re


def utcnow() -> datetime:
    """Her zaman UTC-aware datetime döndür."""
    return datetime.now(timezone.utc)


def to_utc(dt: Union[datetime, str, None]) -> Optional[datetime]:
    """
    Herhangi bir datetime veya string'i UTC-aware'e dönüştür.
    None gelirse None döner.
    """
    if dt is None:
        return None

    if isinstance(dt, str):
        dt = _parse_str(dt)

    if dt is None:
        return None

    if dt.tzinfo is None:
        # Naive → UTC kabul et (collector'lar UTC üretmeli)
        return dt.replace(tzinfo=timezone.utc)

    # Aware ama farklı timezone → UTC'ye çevir
    return dt.astimezone(timezone.utc)


def _parse_str(s: str) -> Optional[datetime]:
    """Çeşitli string formatlarını parse et."""
    s = s.strip()

    # GDELT formatı: 20240115T143000
    if re.match(r"^\d{8}T\d{6}$", s):
        try:
            return datetime.strptime(s, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    # ISO 8601 varyantları
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue

    return None


def hours_ago(hours: int) -> datetime:
    """N saat önceki UTC-aware datetime."""
    return utcnow() - timedelta(hours=hours)


def days_ago(days: int) -> datetime:
    """N gün önceki UTC-aware datetime."""
    return utcnow() - timedelta(days=days)


def iso(dt: Optional[datetime]) -> Optional[str]:
    """UTC-aware datetime → ISO string."""
    if dt is None:
        return None
    return to_utc(dt).isoformat()
