"""
logosint/storage/db_writer.py

Tek yazıcı DB mimarisi.
Tüm SQLite write'ları bu queue üzerinden geçer.
Collectors ve scheduler'lar ASLA direkt write yapmaz.

Neden: SQLite concurrent write → "database is locked" hatası.
Çözüm: Tüm write'ları tek bir worker thread'e serialize et.
"""

from __future__ import annotations

import logging
import queue
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

log = logging.getLogger("DBWriter")

DB_PATH = "logosint.db"

# WAL mode + busy timeout — concurrent reader'lar için
PRAGMA_INIT = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA busy_timeout=5000;
PRAGMA foreign_keys=ON;
PRAGMA temp_store=MEMORY;
PRAGMA mmap_size=268435456;
"""


# ═══════════════════════════════════════════════════════════
# WRITE TASK
# ═══════════════════════════════════════════════════════════

@dataclass
class WriteTask:
    sql:        str
    params:     tuple = field(default_factory=tuple)
    result_q:   Optional[queue.Queue] = None   # None = fire-and-forget
    batch_id:   Optional[str] = None


@dataclass
class BatchTask:
    """Birden fazla SQL ifadesini atomik transaction içinde çalıştır."""
    operations: list[tuple[str, tuple]]  # [(sql, params), ...]
    result_q:   Optional[queue.Queue] = None
    scan_id:    Optional[str] = None


# ═══════════════════════════════════════════════════════════
# DB WRITER
# ═══════════════════════════════════════════════════════════

class DBWriter:
    """
    Tek yazıcı SQLite worker.
    Tüm INSERT/UPDATE/DELETE işlemleri bu sınıf üzerinden geçer.
    SELECT'ler direkt bağlantıyla yapılabilir (WAL = concurrent read OK).
    """

    def __init__(self, db_path: str = DB_PATH, queue_size: int = 10_000):
        self._db_path   = db_path
        self._queue: queue.Queue = queue.Queue(maxsize=queue_size)
        self._thread: Optional[threading.Thread] = None
        self._running   = False
        self._accepting = False              # yeni: shutdown sırasında False
        self._conn: Optional[sqlite3.Connection] = None
        self._write_count   = 0
        self._error_count   = 0
        self._dropped_count = 0              # yeni: queue dolduğunda artar
        self._batch_count   = 0              # yeni: batch sayacı
        self._last_write_at: Optional[float] = None
        self._lock = threading.Lock()

    # ── Başlat / Durdur ────────────────────────────────────

    def start(self):
        with self._lock:
            if self._running:
                return
            self._running   = True
            self._accepting = True
        self._thread = threading.Thread(
            target=self._worker, name="DBWriter", daemon=True
        )
        self._thread.start()
        log.info("DBWriter başladı: %s", self._db_path)

    def stop(self, timeout: float = 10.0):
        """
        Graceful shutdown:
        1) accepting_writes=False — yeni task kabul etme
        2) sentinel koy
        3) thread'in bitmesini bekle
        """
        with self._lock:
            self._accepting = False
        self._running = False
        try:
            self._queue.put(None, timeout=2.0)   # sentinel
        except queue.Full:
            log.warning("Shutdown sentinel queue dolu — zorla durduruluyor")

        if self._thread:
            self._thread.join(timeout=timeout)
        log.info(
            "DBWriter durdu. write=%d batch=%d error=%d dropped=%d",
            self._write_count, self._batch_count,
            self._error_count, self._dropped_count,
        )

    # ── Write API ──────────────────────────────────────────

    def execute(
        self,
        sql: str,
        params: tuple = (),
        wait: bool = False,
    ) -> Optional[bool]:
        """
        Tek SQL ifadesi yaz.
        wait=True → senkron
        wait=False → fire-and-forget
        Shutdown sırasında veya queue dolduğunda silent değil — drop sayılır.
        """
        if not self._accepting:
            self._inc_dropped("shutdown")
            return False

        result_q = queue.Queue(maxsize=1) if wait else None
        task = WriteTask(sql=sql, params=params, result_q=result_q)
        try:
            self._queue.put(task, timeout=2.0)
        except queue.Full:
            self._inc_dropped("queue_full")
            return False

        if wait and result_q:
            try:
                return result_q.get(timeout=10.0)
            except queue.Empty:
                log.error("DB write zaman aşımı: %s", sql[:60])
                return None
        return True

    def execute_batch(
        self,
        operations: list[tuple[str, tuple]],
        scan_id: str = None,
        wait: bool = True,
    ) -> Optional[bool]:
        """Atomik batch — ya hepsi commit ya rollback."""
        if not self._accepting:
            self._inc_dropped("shutdown", n=len(operations))
            return False
        if not operations:
            return True

        result_q = queue.Queue(maxsize=1) if wait else None
        task = BatchTask(operations=operations, result_q=result_q, scan_id=scan_id)
        try:
            self._queue.put(task, timeout=5.0)
        except queue.Full:
            self._inc_dropped("queue_full", n=len(operations))
            log.error(
                "Batch atlandı (queue dolu) — scan_id=%s op=%d",
                scan_id, len(operations),
            )
            return False

        if wait and result_q:
            try:
                return result_q.get(timeout=30.0)
            except queue.Empty:
                log.error("Batch write zaman aşımı (scan_id=%s)", scan_id)
                return None
        return True

    def _inc_dropped(self, reason: str, n: int = 1):
        """Drop sayacını artır + uyarı logla."""
        with self._lock:
            self._dropped_count += n
        # Her 10 drop'ta bir uyarı (spam'i engelle)
        if self._dropped_count % 10 == 1:
            log.error(
                "DB write DROP (%s) — toplam dropped: %d, queue: %d/%d",
                reason, self._dropped_count,
                self._queue.qsize(), self._queue.maxsize,
            )

    # ── Worker ─────────────────────────────────────────────

    def _worker(self):
        self._conn = sqlite3.connect(self._db_path)
        self._conn.executescript(PRAGMA_INIT)
        log.debug("DBWriter bağlantısı kuruldu")

        while True:
            try:
                task = self._queue.get(timeout=1.0)
            except queue.Empty:
                if not self._running:
                    break
                continue

            if task is None:   # sentinel
                break

            try:
                if isinstance(task, BatchTask):
                    self._handle_batch(task)
                elif isinstance(task, WriteTask):
                    self._handle_single(task)
            except Exception as e:
                log.error("Worker beklenmedik hata: %s", e, exc_info=True)
                self._error_count += 1

            self._queue.task_done()

        if self._conn:
            self._conn.close()
            self._conn = None

    def _handle_single(self, task: WriteTask):
        try:
            with self._conn:   # otomatik commit/rollback
                self._conn.execute(task.sql, task.params)
            self._write_count += 1
            if task.result_q:
                task.result_q.put(True)
        except Exception as e:
            log.error("Write hatası: %s | SQL: %s", e, task.sql[:80])
            self._error_count += 1
            if task.result_q:
                task.result_q.put(False)

    def _handle_batch(self, task: BatchTask):
        try:
            with self._conn:
                for sql, params in task.operations:
                    self._conn.execute(sql, params)
            self._write_count += len(task.operations)
            self._batch_count += 1
            self._last_write_at = time.time()
            log.debug(
                "Batch commit: %d op (scan_id=%s)",
                len(task.operations), task.scan_id,
            )
            if task.result_q:
                task.result_q.put(True)
        except Exception as e:
            log.error(
                "Batch rollback (scan_id=%s): %s",
                task.scan_id, e, exc_info=True,
            )
            self._error_count += 1
            if task.result_q:
                task.result_q.put(False)

    # ── Read (direkt bağlantı — WAL ile concurrent read OK) ─

    def query(
        self,
        sql: str,
        params: tuple = (),
    ) -> list[dict]:
        """
        SELECT sorguları worker thread'i atlar.
        WAL mode'da concurrent read güvenli.
        """
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── Stats ──────────────────────────────────────────────

    @property
    def stats(self) -> dict:
        with self._lock:
            qsize = self._queue.qsize()
            return {
                "running":          self._running,
                "accepting_writes": self._accepting,
                "queue_size":       qsize,
                "queue_max":        self._queue.maxsize,
                "queue_pct":        round(100 * qsize / self._queue.maxsize, 1),
                "write_count":      self._write_count,
                "batch_count":      self._batch_count,
                "error_count":      self._error_count,
                "dropped_count":    self._dropped_count,
                "last_write_at":    self._last_write_at,
                "seconds_since_last_write": (
                    round(time.time() - self._last_write_at, 1)
                    if self._last_write_at else None
                ),
            }


# ── Singleton ────────────────────────────────────────────

_writer: Optional[DBWriter] = None
_writer_lock = threading.Lock()


def get_writer() -> DBWriter:
    global _writer
    with _writer_lock:
        if _writer is None:
            _writer = DBWriter()
            _writer.start()
    return _writer


def shutdown_writer():
    global _writer
    with _writer_lock:
        if _writer:
            _writer.stop()
            _writer = None
