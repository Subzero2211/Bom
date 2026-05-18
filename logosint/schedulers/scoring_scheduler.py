"""
logosint/schedulers/scoring_scheduler.py

Saatlik scoring döngüsü zamanlayıcısı.
main.py'deki scan döngüsüne entegre olur.
"""

from __future__ import annotations
import logging
import threading
import time
import uuid
from typing import Callable, Any

log = logging.getLogger("Scheduler")


class ScoringScheduler:
    """
    Thread-safe saatlik scoring zamanlayıcısı.
    Collector çıktılarını toplayıp run_full_cycle'a iletir.
    """

    def __init__(
        self,
        interval_seconds: int = 3600,
        collector_fn: Callable[[], dict[str, list[dict]]] = None,
    ):
        self.interval   = interval_seconds
        self._collector = collector_fn
        self._running   = False
        self._thread: threading.Thread | None = None
        self._last_scan_id: str | None = None
        self._last_run: datetime | None = None
        self._consecutive_failures = 0
        self._lock = threading.Lock()

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log.info("Scoring zamanlayıcısı başladı (interval: %ds)", self.interval)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
        log.info("Scoring zamanlayıcısı durduruldu")

    def trigger_now(self) -> dict:
        """Manuel tetikleme."""
        return self._run_cycle()

    def _loop(self):
        # İlk çalışma — 30 saniye bekle (collector'ların başlaması için)
        time.sleep(30)
        while self._running:
            self._run_cycle()
            # Interval boyunca küçük adımlarla bekle (stop'u hızlı yakala)
            for _ in range(self.interval):
                if not self._running:
                    break
                time.sleep(1)

    def _run_cycle(self) -> dict:
        from logosint.utils.time_utils import utcnow
        scan_id = f"SCAN-{utcnow().strftime('%Y%m%d-%H%M')}-{uuid.uuid4().hex[:6].upper()}"
        log.info("Scoring döngüsü başlıyor: %s", scan_id)
        t0 = time.time()

        try:
            collector_outputs = self._collector() if self._collector else {}

            # v2 runtime — atomik, lock'lu, timezone-safe
            from logosint.scoring.runtime_v2 import run_full_cycle
            result = run_full_cycle(collector_outputs, scan_id)

            with self._lock:
                self._last_scan_id = scan_id
                self._last_run     = utcnow()
                self._consecutive_failures = 0

            log.info("Döngü tamamlandı: %s (%.1fs)", scan_id, time.time() - t0)
            return result

        except Exception as e:
            self._consecutive_failures += 1
            log.error("Döngü hatası #%d: %s", self._consecutive_failures, e, exc_info=True)
            return {"scan_id": scan_id, "error": str(e)}

    @property
    def status(self) -> dict:
        with self._lock:
            return {
                "running":              self._running,
                "last_scan_id":         self._last_scan_id,
                "last_run":             self._last_run.isoformat() if self._last_run else None,
                "consecutive_failures": self._consecutive_failures,
                "interval_s":           self.interval,
            }


# Singleton
_scheduler: ScoringScheduler | None = None


def get_scheduler() -> ScoringScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = ScoringScheduler()
    return _scheduler
