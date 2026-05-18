"""
logosint/monitoring/health_monitor.py

Sistem sağlık monitörü.
Her collector'ın durumunu, ingestion lag'ini, hata sayısını izler.
"""

from __future__ import annotations
import logging
import sqlite3
import time
import uuid
from datetime import datetime, timedelta
from threading import Lock
from typing import Optional

from logosint.models.health import (
    CollectorHealth, CollectorStatus, HealthSnapshot
)

log = logging.getLogger("HealthMonitor")
DB_PATH = "logosint.db"

_lock = Lock()
_collector_state: dict[str, dict] = {}  # {collector_name: state_dict}


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def _init_health_table():
    with _conn() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS health_snapshots (
            snapshot_id         TEXT PRIMARY KEY,
            timestamp           TEXT NOT NULL,
            system_ok           INTEGER,
            scoring_latency_ms  REAL,
            last_scan_id        TEXT,
            alerts_last_hour    INTEGER,
            snapshot_json       TEXT,
            inserted_at         TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS collector_heartbeats (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            collector           TEXT NOT NULL,
            timestamp           TEXT NOT NULL,
            status              TEXT NOT NULL,
            signals_count       INTEGER DEFAULT 0,
            error_message       TEXT,
            duration_ms         REAL
        );
        CREATE INDEX IF NOT EXISTS idx_hb_collector ON collector_heartbeats(collector, timestamp);
        """)


def record_heartbeat(
    collector: str,
    status: CollectorStatus,
    signals_count: int = 0,
    error_message: str = None,
    duration_ms: float = None,
):
    """Collector her çalıştığında bu fonksiyonu çağır."""
    now = datetime.utcnow().isoformat()
    with _lock:
        state = _collector_state.setdefault(collector, {
            "consecutive_errors": 0,
            "last_run": None,
            "last_success": None,
            "signals_last_hour": 0,
            "total_signals": 0,
        })
        state["last_run"] = now
        if status == CollectorStatus.OK:
            state["consecutive_errors"] = 0
            state["last_success"] = now
            state["signals_last_hour"] = signals_count
        else:
            state["consecutive_errors"] += 1

    try:
        with _conn() as db:
            db.execute("""
                INSERT INTO collector_heartbeats
                (collector, timestamp, status, signals_count, error_message, duration_ms)
                VALUES (?,?,?,?,?,?)
            """, (collector, now, status.value, signals_count, error_message, duration_ms))
    except Exception as e:
        log.error("Heartbeat kayıt hatası: %s", e)


def get_collector_health(
    collector: str,
    api_key_present: bool = False,
) -> CollectorHealth:
    """Bir collector'ın mevcut sağlık durumunu döndür."""
    with _lock:
        state = _collector_state.get(collector, {})

    last_run_str    = state.get("last_run")
    last_success_str= state.get("last_success")
    errors          = state.get("consecutive_errors", 0)
    signals_hr      = state.get("signals_last_hour", 0)

    last_run = datetime.fromisoformat(last_run_str) if last_run_str else None
    last_success = datetime.fromisoformat(last_success_str) if last_success_str else None

    # Durum belirleme
    if not api_key_present and collector not in ("opensky", "gdelt", "gdacs", "rss"):
        status = CollectorStatus.NO_KEY
    elif errors >= 5:
        status = CollectorStatus.FAILED
    elif errors >= 2:
        status = CollectorStatus.DEGRADED
    elif last_run and (datetime.utcnow() - last_run).seconds > 7200:
        status = CollectorStatus.STALE
    else:
        status = CollectorStatus.OK

    # Ingestion lag
    lag = None
    if last_run:
        lag = (datetime.utcnow() - last_run).total_seconds()

    return CollectorHealth(
        name               = collector,
        status             = status,
        last_run           = last_run,
        last_success       = last_success,
        consecutive_errors = errors,
        ingestion_lag_s    = lag,
        signals_last_hour  = signals_hr,
        api_key_present    = api_key_present,
    )


def take_snapshot(
    api_key_status: dict[str, bool] = None,
    scoring_latency_ms: float = None,
    last_scan_id: str = None,
) -> HealthSnapshot:
    """Anlık sistem sağlık snapshot'ı al."""
    import json

    api_key_status = api_key_status or {}

    COLLECTORS = [
        "opensky", "marine", "gdelt", "telegram", "acled",
        "fred", "gdacs", "sentinelhub", "comtrade", "telecom", "rss"
    ]

    collector_healths = [
        get_collector_health(c, api_key_status.get(c, False))
        for c in COLLECTORS
    ]

    # Son 1 saatteki uyarı sayısı
    alerts_hr = 0
    try:
        since = (datetime.utcnow() - timedelta(hours=1)).isoformat()
        with _conn() as db:
            row = db.execute(
                "SELECT COUNT(*) as cnt FROM alerts WHERE timestamp >= ? AND acknowledged=0",
                (since,)
            ).fetchone()
            alerts_hr = row["cnt"] if row else 0
    except Exception:
        pass

    system_ok = all(
        c.status in (CollectorStatus.OK, CollectorStatus.NO_KEY)
        for c in collector_healths
    )

    snapshot = HealthSnapshot(
        snapshot_id         = str(uuid.uuid4()),
        timestamp           = datetime.utcnow(),
        collectors          = collector_healths,
        scoring_latency_ms  = scoring_latency_ms,
        last_scan_id        = last_scan_id,
        last_scan_at        = None,
        alerts_last_hour    = alerts_hr,
        system_ok           = system_ok,
    )

    # DB'ye kaydet
    try:
        with _conn() as db:
            db.execute("""
                INSERT INTO health_snapshots
                (snapshot_id, timestamp, system_ok, scoring_latency_ms,
                 last_scan_id, alerts_last_hour, snapshot_json)
                VALUES (?,?,?,?,?,?,?)
            """, (
                snapshot.snapshot_id,
                snapshot.timestamp.isoformat(),
                int(system_ok),
                scoring_latency_ms,
                last_scan_id,
                alerts_hr,
                snapshot.model_dump_json(),
            ))
    except Exception as e:
        log.error("Snapshot kayıt hatası: %s", e)

    return snapshot


def get_latest_snapshot() -> Optional[HealthSnapshot]:
    """Son snapshot'ı döndür."""
    import json
    try:
        with _conn() as db:
            row = db.execute(
                "SELECT snapshot_json FROM health_snapshots ORDER BY timestamp DESC LIMIT 1"
            ).fetchone()
        if row:
            return HealthSnapshot.model_validate_json(row["snapshot_json"])
    except Exception as e:
        log.error("Snapshot yükleme hatası: %s", e)
    return None


# Init
_init_health_table()
