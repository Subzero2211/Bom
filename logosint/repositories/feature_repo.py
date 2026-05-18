"""
logosint/repositories/feature_repo.py

Feature store — normalized signals, scenario features, scoring outputs.
SQLite ile implement edildi (PostgreSQL'e migrate edilebilir).
"""

from __future__ import annotations
import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from logosint.models.signals import UnifiedSignal, ScenarioFeature
from logosint.models.scoring import ScoringOutput, Prediction, PredictionStatus

log = logging.getLogger("FeatureRepo")
DB_PATH = "logosint.db"


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    return c


def init_feature_store():
    """Tablo şemalarını oluştur."""
    with _conn() as db:
        db.executescript("""
        -- Normalize edilmiş sinyaller
        CREATE TABLE IF NOT EXISTS unified_signals (
            signal_id        TEXT PRIMARY KEY,
            timestamp        TEXT NOT NULL,
            source           TEXT NOT NULL,
            signal_type      TEXT NOT NULL,
            geography        TEXT NOT NULL,
            lat              REAL,
            lon              REAL,
            confidence       REAL,
            severity         TEXT,
            value            REAL,
            normalized_value REAL,
            keywords         TEXT,   -- JSON
            entities         TEXT,   -- JSON
            metadata         TEXT,   -- JSON
            scan_id          TEXT,
            inserted_at      TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_us_geo ON unified_signals(geography, timestamp);
        CREATE INDEX IF NOT EXISTS idx_us_src ON unified_signals(source, timestamp);
        CREATE INDEX IF NOT EXISTS idx_us_ts  ON unified_signals(timestamp);

        -- Senaryo feature'ları
        CREATE TABLE IF NOT EXISTS scenario_features (
            feature_id           TEXT PRIMARY KEY,
            feature_name         TEXT NOT NULL,
            region               TEXT NOT NULL,
            timestamp            TEXT NOT NULL,
            value                REAL NOT NULL,
            confidence           REAL NOT NULL,
            contributing_signals TEXT,   -- JSON
            scenario_relevance   TEXT,   -- JSON
            decay_factor         REAL,
            scan_id              TEXT,
            inserted_at          TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_sf_region ON scenario_features(region, timestamp);
        CREATE INDEX IF NOT EXISTS idx_sf_name   ON scenario_features(feature_name, timestamp);

        -- Scoring çıktıları
        CREATE TABLE IF NOT EXISTS scoring_outputs (
            output_id            TEXT PRIMARY KEY,
            scan_id              TEXT NOT NULL,
            timestamp            TEXT NOT NULL,
            scenario_id          INTEGER NOT NULL,
            scenario_name        TEXT,
            region               TEXT NOT NULL,
            score                REAL NOT NULL,
            probability          REAL NOT NULL,
            confidence           REAL NOT NULL,
            threshold_level      INTEGER,
            contributing_factors TEXT,   -- JSON
            edge_contributions   TEXT,   -- JSON
            inserted_at          TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_so_region   ON scoring_outputs(region, timestamp);
        CREATE INDEX IF NOT EXISTS idx_so_scenario ON scoring_outputs(scenario_id, timestamp);
        CREATE INDEX IF NOT EXISTS idx_so_scan     ON scoring_outputs(scan_id);

        -- Prediction registry
        CREATE TABLE IF NOT EXISTS predictions (
            prediction_id TEXT PRIMARY KEY,
            created_at    TEXT NOT NULL,
            scenario_id   INTEGER NOT NULL,
            scenario_name TEXT,
            region        TEXT NOT NULL,
            probability   REAL NOT NULL,
            confidence    REAL NOT NULL,
            horizon_hours INTEGER,
            status        TEXT DEFAULT 'pending',
            outcome       INTEGER,    -- 0/1/NULL
            brier_score   REAL,
            verified_at   TEXT,
            source_scan_id TEXT,
            inserted_at   TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_pred_region ON predictions(region, created_at);
        CREATE INDEX IF NOT EXISTS idx_pred_status ON predictions(status);
        """)
    log.info("Feature store hazır: %s", DB_PATH)


# ═══════════════════════════════════════════════════════════
# UNIFIED SIGNALS
# ═══════════════════════════════════════════════════════════

def insert_signals(signals: list[UnifiedSignal], scan_id: str = "") -> int:
    count = 0
    with _conn() as db:
        for s in signals:
            try:
                db.execute("""
                    INSERT OR IGNORE INTO unified_signals
                    (signal_id, timestamp, source, signal_type, geography,
                     lat, lon, confidence, severity, value, normalized_value,
                     keywords, entities, metadata, scan_id)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    s.signal_id,
                    s.timestamp.isoformat(),
                    s.source,
                    s.signal_type.value,
                    s.geography,
                    s.coordinates.lat if s.coordinates else None,
                    s.coordinates.lon if s.coordinates else None,
                    s.confidence,
                    s.severity.value,
                    s.value,
                    s.normalized_value,
                    json.dumps(s.keywords),
                    json.dumps(s.entities),
                    json.dumps(s.metadata),
                    scan_id,
                ))
                count += 1
            except Exception as e:
                log.debug("Signal insert hata: %s", e)
    return count


def get_signals(
    geography: str = None,
    source: str = None,
    hours: int = 6,
    limit: int = 500,
) -> list[dict]:
    since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    conditions = ["timestamp >= ?"]
    params: list = [since]
    if geography:
        conditions.append("geography = ?")
        params.append(geography)
    if source:
        conditions.append("source = ?")
        params.append(source)
    params.append(limit)

    with _conn() as db:
        rows = db.execute(
            f"SELECT * FROM unified_signals WHERE {' AND '.join(conditions)} ORDER BY timestamp DESC LIMIT ?",
            params
        ).fetchall()
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════
# SCENARIO FEATURES
# ═══════════════════════════════════════════════════════════

def insert_features(features: list[ScenarioFeature], scan_id: str = "") -> int:
    count = 0
    with _conn() as db:
        for f in features:
            try:
                db.execute("""
                    INSERT OR IGNORE INTO scenario_features
                    (feature_id, feature_name, region, timestamp, value,
                     confidence, contributing_signals, scenario_relevance,
                     decay_factor, scan_id)
                    VALUES (?,?,?,?,?,?,?,?,?,?)
                """, (
                    f.feature_id,
                    f.feature_name,
                    f.region,
                    f.timestamp.isoformat(),
                    f.value,
                    f.confidence,
                    json.dumps(f.contributing_signals),
                    json.dumps({str(k): v for k, v in f.scenario_relevance.items()}),
                    f.decay_factor,
                    scan_id,
                ))
                count += 1
            except Exception as e:
                log.debug("Feature insert hata: %s", e)
    return count


def get_features(
    region: str = None,
    feature_name: str = None,
    hours: int = 6,
    limit: int = 200,
) -> list[dict]:
    since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    conditions = ["timestamp >= ?"]
    params: list = [since]
    if region:
        conditions.append("region = ?")
        params.append(region)
    if feature_name:
        conditions.append("feature_name = ?")
        params.append(feature_name)
    params.append(limit)

    with _conn() as db:
        rows = db.execute(
            f"SELECT * FROM scenario_features WHERE {' AND '.join(conditions)} ORDER BY timestamp DESC LIMIT ?",
            params
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        for field in ("contributing_signals", "scenario_relevance"):
            try:
                d[field] = json.loads(d.get(field) or "[]")
            except Exception:
                d[field] = []
        result.append(d)
    return result


# ═══════════════════════════════════════════════════════════
# SCORING OUTPUTS
# ═══════════════════════════════════════════════════════════

def insert_scoring_output(output: ScoringOutput) -> bool:
    try:
        with _conn() as db:
            db.execute("""
                INSERT OR REPLACE INTO scoring_outputs
                (output_id, scan_id, timestamp, scenario_id, scenario_name,
                 region, score, probability, confidence, threshold_level,
                 contributing_factors, edge_contributions)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                output.output_id,
                output.scan_id,
                output.timestamp.isoformat(),
                output.scenario_id,
                output.scenario_name,
                output.region,
                output.score,
                output.probability,
                output.confidence,
                output.threshold_level,
                json.dumps(output.contributing_factors),
                json.dumps(output.edge_contributions),
            ))
        return True
    except Exception as e:
        log.error("Scoring output insert hata: %s", e)
        return False


def get_scores(
    region: str = None,
    scenario_id: int = None,
    hours: int = 24,
    min_score: float = 0.0,
    limit: int = 200,
    offset: int = 0,
) -> list[dict]:
    since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    conditions = ["timestamp >= ?", "score >= ?"]
    params: list = [since, min_score]
    if region:
        conditions.append("region = ?")
        params.append(region)
    if scenario_id:
        conditions.append("scenario_id = ?")
        params.append(scenario_id)
    params.extend([limit, offset])

    with _conn() as db:
        rows = db.execute(
            f"SELECT * FROM scoring_outputs WHERE {' AND '.join(conditions)} ORDER BY score DESC LIMIT ? OFFSET ?",
            params
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        for field in ("contributing_factors", "edge_contributions"):
            try:
                d[field] = json.loads(d.get(field) or "[]")
            except Exception:
                d[field] = {}
        result.append(d)
    return result


def get_heatmap(hours: int = 24) -> list[dict]:
    """Her bölge için max skor."""
    since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    with _conn() as db:
        rows = db.execute("""
            SELECT region,
                   MAX(score) as max_score,
                   AVG(score) as avg_score,
                   COUNT(CASE WHEN threshold_level >= 3 THEN 1 END) as critical_count
            FROM scoring_outputs
            WHERE timestamp >= ?
            GROUP BY region
            ORDER BY max_score DESC
        """, (since,)).fetchall()
    return [dict(r) for r in rows]


def get_trend(
    region: str,
    scenario_id: int,
    days: int = 7,
) -> list[dict]:
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    with _conn() as db:
        rows = db.execute("""
            SELECT strftime('%Y-%m-%d %H:00', timestamp) as hour,
                   AVG(score) as avg_score,
                   MAX(score) as max_score
            FROM scoring_outputs
            WHERE region=? AND scenario_id=? AND timestamp>=?
            GROUP BY hour
            ORDER BY hour
        """, (region, scenario_id, since)).fetchall()
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════
# PREDICTIONS
# ═══════════════════════════════════════════════════════════

def insert_prediction(pred: Prediction) -> bool:
    try:
        with _conn() as db:
            db.execute("""
                INSERT OR IGNORE INTO predictions
                (prediction_id, created_at, scenario_id, scenario_name,
                 region, probability, confidence, horizon_hours,
                 status, source_scan_id)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (
                pred.prediction_id,
                pred.created_at.isoformat(),
                pred.scenario_id,
                pred.scenario_name,
                pred.region,
                pred.probability,
                pred.confidence,
                pred.horizon_hours,
                pred.status.value,
                pred.source_scan_id,
            ))
        return True
    except Exception as e:
        log.error("Prediction insert hata: %s", e)
        return False


def get_predictions(
    region: str = None,
    status: str = None,
    hours: int = 168,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    conditions = ["created_at >= ?"]
    params: list = [since]
    if region:
        conditions.append("region = ?")
        params.append(region)
    if status:
        conditions.append("status = ?")
        params.append(status)
    params.extend([limit, offset])

    with _conn() as db:
        rows = db.execute(
            f"SELECT * FROM predictions WHERE {' AND '.join(conditions)} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params
        ).fetchall()
    return [dict(r) for r in rows]


def compute_calibration_stats() -> dict:
    """Tüm verified prediction'lar için Brier skoru ve doğruluk."""
    with _conn() as db:
        rows = db.execute(
            "SELECT probability, outcome FROM predictions WHERE status='verified' AND outcome IS NOT NULL"
        ).fetchall()
    if not rows:
        return {"count": 0}
    brier_scores = [(r["probability"] - r["outcome"]) ** 2 for r in rows]
    correct = sum(
        1 for r in rows
        if (r["probability"] >= 0.5 and r["outcome"] == 1)
        or (r["probability"] < 0.5 and r["outcome"] == 0)
    )
    return {
        "count":       len(rows),
        "brier_score": round(sum(brier_scores) / len(brier_scores), 4),
        "accuracy":    round(correct / len(rows), 3),
    }
