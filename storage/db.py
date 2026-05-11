"""
storage/db.py

SQLite tabanlı kalıcı depolama.
Tüm eventler, anomaliler ve raporlar burada tutulur.
30 günden eski kayıtlar otomatik temizlenir.
"""

import sqlite3
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from config import DATABASE

log = logging.getLogger("DB")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE["path"])
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # concurrent read/write
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Veritabanı tablolarını oluştur (yoksa)."""
    with get_conn() as conn:
        conn.executescript("""
        -- Ham olaylar
        CREATE TABLE IF NOT EXISTS raw_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id    TEXT NOT NULL,
            source      TEXT NOT NULL,
            domain      TEXT NOT NULL,
            title       TEXT,
            body        TEXT,
            url         TEXT,
            timestamp   TEXT NOT NULL,
            lat         REAL,
            lon         REAL,
            location_name TEXT,
            country     TEXT,
            region      TEXT,
            affected_regions TEXT,   -- JSON array
            keywords_matched TEXT,   -- JSON array
            entities    TEXT,        -- JSON array
            raw_data    TEXT,        -- JSON object
            inserted_at TEXT DEFAULT (datetime('now')),
            UNIQUE(source, event_id)
        );
        CREATE INDEX IF NOT EXISTS idx_raw_ts     ON raw_events(timestamp);
        CREATE INDEX IF NOT EXISTS idx_raw_src    ON raw_events(source);
        CREATE INDEX IF NOT EXISTS idx_raw_domain ON raw_events(domain);
        CREATE INDEX IF NOT EXISTS idx_raw_region ON raw_events(region);

        -- Anomali olayları
        CREATE TABLE IF NOT EXISTS anomaly_events (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            raw_event_id    INTEGER REFERENCES raw_events(id),
            source          TEXT NOT NULL,
            domain          TEXT NOT NULL,
            event_id        TEXT NOT NULL,
            severity        TEXT NOT NULL,
            current_value   REAL,
            baseline_value  REAL,
            zscore          REAL,
            delta_pct       REAL,
            description     TEXT,
            confidence      REAL,
            timestamp       TEXT NOT NULL,
            region          TEXT,
            lat             REAL,
            lon             REAL,
            correlated_ids  TEXT,    -- JSON array
            inserted_at     TEXT DEFAULT (datetime('now')),
            UNIQUE(source, event_id)
        );
        CREATE INDEX IF NOT EXISTS idx_anom_sev ON anomaly_events(severity);
        CREATE INDEX IF NOT EXISTS idx_anom_ts  ON anomaly_events(timestamp);

        -- Korelasyon kümeleri
        CREATE TABLE IF NOT EXISTS correlation_clusters (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            cluster_id      TEXT UNIQUE NOT NULL,
            severity        TEXT NOT NULL,
            event_ids       TEXT,    -- JSON array
            domains         TEXT,    -- JSON array
            regions         TEXT,    -- JSON array
            keywords        TEXT,    -- JSON array
            centroid_lat    REAL,
            centroid_lon    REAL,
            centroid_name   TEXT,
            first_seen      TEXT,
            last_seen       TEXT,
            corr_type       TEXT,
            summary         TEXT,
            confidence      REAL,
            inserted_at     TEXT DEFAULT (datetime('now'))
        );

        -- İstihbarat raporları
        CREATE TABLE IF NOT EXISTS intel_reports (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id       TEXT UNIQUE NOT NULL,
            generated_at    TEXT NOT NULL,
            system_status   TEXT,
            active_anomalies INTEGER,
            active_corrs    INTEGER,
            key_findings    TEXT,    -- JSON array
            watch_list      TEXT,    -- JSON array
            domain_summary  TEXT,    -- JSON object
            region_summary  TEXT,    -- JSON object
            source_stats    TEXT,    -- JSON object
            full_json       TEXT     -- tam rapor JSON
        );

        -- Zaman serisi — sayısal kaynaklar için rolling baseline
        CREATE TABLE IF NOT EXISTS timeseries (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            station_key TEXT NOT NULL,   -- "opensky_LTFM", "marine_TRISA", vb.
            value       REAL NOT NULL,
            timestamp   TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ts_key ON timeseries(station_key);
        CREATE INDEX IF NOT EXISTS idx_ts_ts  ON timeseries(timestamp);
        """)
        log.info("Veritabanı hazır: %s", DATABASE["path"])


# ── RAW EVENTS ──────────────────────────────────────────────

def insert_raw_event(event_dict: dict) -> Optional[int]:
    """Ham olayı ekle. Zaten varsa None döner."""
    sql = """
        INSERT OR IGNORE INTO raw_events
        (event_id, source, domain, title, body, url, timestamp,
         lat, lon, location_name, country, region,
         affected_regions, keywords_matched, entities, raw_data)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """
    try:
        with get_conn() as conn:
            cur = conn.execute(sql, (
                event_dict.get("event_id"),
                event_dict.get("source"),
                event_dict.get("domain"),
                event_dict.get("title"),
                event_dict.get("body"),
                event_dict.get("url"),
                event_dict.get("timestamp"),
                event_dict.get("lat"),
                event_dict.get("lon"),
                event_dict.get("location_name"),
                event_dict.get("country"),
                event_dict.get("region"),
                json.dumps(event_dict.get("affected_regions", [])),
                json.dumps(event_dict.get("keywords_matched", [])),
                json.dumps(event_dict.get("entities", [])),
                json.dumps(event_dict.get("raw_data", {})),
            ))
            return cur.lastrowid if cur.rowcount > 0 else None
    except Exception as e:
        log.error("insert_raw_event hata: %s", e)
        return None


def get_recent_raw_events(hours: int = 24, domain: str = None,
                          region: str = None, limit: int = 500) -> list[dict]:
    since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    conditions = ["timestamp >= ?"]
    params = [since]
    if domain:
        conditions.append("domain = ?")
        params.append(domain)
    if region:
        conditions.append("(region = ? OR affected_regions LIKE ?)")
        params.extend([region, f'%"{region}"%'])
    params.append(limit)
    sql = f"""
        SELECT * FROM raw_events
        WHERE {' AND '.join(conditions)}
        ORDER BY timestamp DESC LIMIT ?
    """
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


# ── ANOMALY EVENTS ──────────────────────────────────────────

def insert_anomaly(a: dict) -> Optional[int]:
    sql = """
        INSERT OR REPLACE INTO anomaly_events
        (source, domain, event_id, severity, current_value, baseline_value,
         zscore, delta_pct, description, confidence, timestamp, region, lat, lon, correlated_ids)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """
    try:
        with get_conn() as conn:
            cur = conn.execute(sql, (
                a.get("source"), a.get("domain"), a.get("event_id"),
                a.get("severity"), a.get("current_value"), a.get("baseline_value"),
                a.get("zscore"), a.get("delta_pct"), a.get("anomaly_description"),
                a.get("confidence"), a.get("timestamp"), a.get("region"),
                a.get("lat"), a.get("lon"),
                json.dumps(a.get("correlated_event_ids", [])),
            ))
            return cur.lastrowid
    except Exception as e:
        log.error("insert_anomaly hata: %s", e)
        return None


def get_active_anomalies(hours: int = 12) -> list[dict]:
    since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    sql = """
        SELECT * FROM anomaly_events
        WHERE timestamp >= ? AND severity IN ('warning', 'critical')
        ORDER BY severity DESC, timestamp DESC
    """
    with get_conn() as conn:
        rows = conn.execute(sql, (since,)).fetchall()
    return [dict(r) for r in rows]


# ── KORELASYON KÜMELERİ ─────────────────────────────────────

def insert_cluster(c: dict):
    sql = """
        INSERT OR REPLACE INTO correlation_clusters
        (cluster_id, severity, event_ids, domains, regions, keywords,
         centroid_lat, centroid_lon, centroid_name,
         first_seen, last_seen, corr_type, summary, confidence)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """
    with get_conn() as conn:
        conn.execute(sql, (
            c["cluster_id"], c["severity"],
            json.dumps(c.get("event_ids", [])),
            json.dumps(c.get("domains_involved", [])),
            json.dumps(c.get("regions_involved", [])),
            json.dumps(c.get("keywords_common", [])),
            c.get("centroid_lat"), c.get("centroid_lon"), c.get("centroid_name"),
            c.get("first_seen"), c.get("last_seen"),
            c.get("correlation_type"), c.get("summary"), c.get("confidence"),
        ))


def get_active_clusters(hours: int = 24) -> list[dict]:
    since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    sql = """
        SELECT * FROM correlation_clusters
        WHERE last_seen >= ?
        ORDER BY severity DESC, confidence DESC
    """
    with get_conn() as conn:
        rows = conn.execute(sql, (since,)).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        for f in ("event_ids","domains","regions","keywords"):
            try: d[f] = json.loads(d.get(f) or "[]")
            except: d[f] = []
        result.append(d)
    return result


# ── RAPORLAR ────────────────────────────────────────────────

def insert_report(report_dict: dict):
    sql = """
        INSERT OR REPLACE INTO intel_reports
        (report_id, generated_at, system_status, active_anomalies, active_corrs,
         key_findings, watch_list, domain_summary, region_summary, source_stats, full_json)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """
    with get_conn() as conn:
        conn.execute(sql, (
            report_dict["report_id"],
            report_dict["generated_at"],
            report_dict.get("system_status"),
            report_dict.get("active_anomalies", 0),
            report_dict.get("active_correlations", 0),
            json.dumps(report_dict.get("key_findings", [])),
            json.dumps(report_dict.get("watch_list", [])),
            json.dumps(report_dict.get("domain_summary", {})),
            json.dumps(report_dict.get("region_summary", {})),
            json.dumps(report_dict.get("source_stats", {})),
            json.dumps(report_dict),
        ))


def get_latest_report() -> Optional[dict]:
    sql = "SELECT full_json FROM intel_reports ORDER BY generated_at DESC LIMIT 1"
    with get_conn() as conn:
        row = conn.execute(sql).fetchone()
    if row:
        try: return json.loads(row["full_json"])
        except: return None
    return None


# ── ZAMAN SERİSİ ────────────────────────────────────────────

def push_timeseries(station_key: str, value: float):
    sql = "INSERT INTO timeseries (station_key, value, timestamp) VALUES (?,?,?)"
    with get_conn() as conn:
        conn.execute(sql, (station_key, value, datetime.utcnow().isoformat()))


def get_timeseries(station_key: str, limit: int = 48) -> list[float]:
    sql = """
        SELECT value FROM timeseries
        WHERE station_key = ?
        ORDER BY timestamp DESC LIMIT ?
    """
    with get_conn() as conn:
        rows = conn.execute(sql, (station_key, limit)).fetchall()
    return [r["value"] for r in reversed(rows)]


# ── TEMİZLİK ────────────────────────────────────────────────

def archive_old_records():
    """
    30 günden eski kayıtları silmez — aylık arşiv SQLite dosyasına taşır.
    archive/YYYY-MM/osint_archive_YYYY-MM.db formatında yerel diske yazar.
    """
    import shutil
    cutoff = (datetime.utcnow() - timedelta(days=DATABASE["keep_days"]))
    cutoff_str = cutoff.isoformat()
    archive_label = cutoff.strftime("%Y-%m")
    archive_dir = Path(DATABASE.get("archive_dir", "archive")) / archive_label
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / f"osint_archive_{archive_label}.db"

    # Arşiv DB'yi hazırla (aynı şema)
    archive_conn = sqlite3.connect(str(archive_path))
    archive_conn.row_factory = sqlite3.Row

    with get_conn() as src:
        # Tablo şemalarını kopyala
        schema_rows = src.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table'"
        ).fetchall()
        for row in schema_rows:
            if row["sql"]:
                try:
                    archive_conn.execute(row["sql"])
                except Exception:
                    pass
        archive_conn.commit()

        for table, ts_col in [
            ("raw_events",           "timestamp"),
            ("anomaly_events",       "timestamp"),
            ("timeseries",           "timestamp"),
            ("intel_reports",        "generated_at"),
            ("correlation_clusters", "last_seen"),
        ]:
            rows = src.execute(
                f"SELECT * FROM {table} WHERE {ts_col} < ?", (cutoff_str,)
            ).fetchall()
            if not rows:
                continue

            cols = [d[0] for d in rows[0].description] if hasattr(rows[0], "description") else []
            if not cols:
                cols = [description[0] for description in src.execute(
                    f"PRAGMA table_info({table})"
                ).fetchall()]
                # pragma returns: cid, name, type, notnull, dflt_value, pk
                cols = [r[1] for r in src.execute(f"PRAGMA table_info({table})").fetchall()]

            # Daha güvenli: rows'u dict'e çevir
            dicts = [dict(r) for r in rows]
            if not dicts:
                continue

            placeholders = ", ".join(["?" for _ in dicts[0]])
            col_names = ", ".join(dicts[0].keys())
            archive_conn.executemany(
                f"INSERT OR IGNORE INTO {table} ({col_names}) VALUES ({placeholders})",
                [list(d.values()) for d in dicts]
            )
            archive_conn.commit()

            # Arşivlendi — ana DB'den sil
            src.execute(f"DELETE FROM {table} WHERE {ts_col} < ?", (cutoff_str,))

        src.commit()

    archive_conn.close()
    log.info(
        "Arşivleme tamamlandı → %s | Cutoff: %s",
        archive_path, cutoff_str[:10]
    )


# Geriye dönük uyumluluk için alias
def cleanup_old_records():
    archive_old_records()
