"""
logosint/schedulers/scan_lock.py

Scheduler kilidi — concurrent scan önleme.
Hem scheduled hem manual scan aynı anda çalışamaz.

Neden: İki scan aynı anda çalışırsa çift scoring, duplicate alerts.
Çözüm: Threading.Event + state machine.
"""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

log = logging.getLogger("ScanLock")


class ScanState(str, Enum):
    IDLE     = "idle"
    RUNNING  = "running"
    QUEUED   = "queued"   # manual scan bekliyorsa


class ScanStatus:
    """Thread-safe scan durumu + bounded manual scan queue."""

    MAX_QUEUED_MANUAL = 5   # üst sınır — recursive scan storm önleme

    def __init__(self):
        self._lock          = threading.Lock()
        self._state         = ScanState.IDLE
        self._current_scan  : Optional[str]      = None
        self._started_at    : Optional[datetime] = None
        self._last_scan_id  : Optional[str]      = None
        self._last_finished : Optional[datetime] = None
        self._queued_count  : int                = 0     # FIFO counter
        self._dropped_manual: int                = 0     # backpressure metrik
        self._scan_count    : int                = 0
        self._error_count   : int                = 0

    def try_acquire(self, scan_id: str) -> bool:
        with self._lock:
            if self._state == ScanState.RUNNING:
                log.warning(
                    "Scan zaten çalışıyor (%s) — %s atlandı",
                    self._current_scan, scan_id,
                )
                return False
            self._state        = ScanState.RUNNING
            self._current_scan = scan_id
            self._started_at   = datetime.now(timezone.utc)
            return True

    def release(self, scan_id: str, success: bool = True):
        with self._lock:
            if self._current_scan != scan_id:
                log.warning(
                    "Release mismatch: beklenen %s, gelen %s",
                    self._current_scan, scan_id,
                )
                return
            self._last_scan_id  = scan_id
            self._last_finished = datetime.now(timezone.utc)
            self._state         = ScanState.IDLE
            self._current_scan  = None
            self._scan_count   += 1
            if not success:
                self._error_count += 1

    def queue_manual(self) -> bool:
        """
        Manuel scan isteğini sıraya al.
        Üst sınıra ulaşılırsa drop et — recursive storm önleme.
        Returns: True = sıraya alındı, False = drop edildi.
        """
        with self._lock:
            if self._queued_count >= self.MAX_QUEUED_MANUAL:
                self._dropped_manual += 1
                log.error(
                    "Manuel scan queue dolu (%d/%d) — drop. Toplam drop: %d",
                    self._queued_count, self.MAX_QUEUED_MANUAL,
                    self._dropped_manual,
                )
                return False
            self._queued_count += 1
            return True

    def pop_queued(self) -> bool:
        """Bekleyen manuel scan varsa al."""
        with self._lock:
            if self._queued_count > 0:
                self._queued_count -= 1
                return True
            return False

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._state == ScanState.RUNNING

    @property
    def api_status(self) -> dict:
        with self._lock:
            return {
                "state":             self._state.value,
                "current_scan_id":   self._current_scan,
                "started_at":        self._started_at.isoformat() if self._started_at else None,
                "last_scan_id":      self._last_scan_id,
                "last_finished":     self._last_finished.isoformat() if self._last_finished else None,
                "scan_count":        self._scan_count,
                "error_count":       self._error_count,
                "queued_manual":     self._queued_count,
                "queued_max":        self.MAX_QUEUED_MANUAL,
                "dropped_manual":    self._dropped_manual,
            }


# Singleton
_scan_status = ScanStatus()


def get_scan_status() -> ScanStatus:
    return _scan_status
