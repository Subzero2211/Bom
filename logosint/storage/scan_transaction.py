"""
logosint/storage/scan_transaction.py

Atomik scan transaction'ı.
insert_signals + insert_features + insert_scores
ya hepsi commit olur ya hiçbiri.

Neden: Partial scan → tutarsız veri → yanlış anomali tespiti.
Çözüm: Tüm scan operasyonlarını tek BatchTask içine topla.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from logosint.storage.db_writer import get_writer

if TYPE_CHECKING:
    from logosint.models.signals import UnifiedSignal, ScenarioFeature
    from logosint.models.scoring import ScoringOutput, Prediction

log = logging.getLogger("ScanTransaction")


class ScanTransaction:
    """
    Bir tarama döngüsünün tüm DB yazma operasyonlarını toplar,
    tek atomik batch olarak commit eder.

    Kullanım:
        with ScanTransaction(scan_id) as tx:
            tx.add_signals(signals)
            tx.add_features(features)
            tx.add_scores(scores)
        # __exit__ → commit veya rollback
    """

    def __init__(self, scan_id: str):
        self.scan_id    = scan_id
        self._ops: list[tuple[str, tuple]] = []
        self._committed = False

    def __enter__(self) -> "ScanTransaction":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            log.error(
                "ScanTransaction %s rollback (exception: %s)",
                self.scan_id, exc_val,
            )
            return False   # exception'ı yeniden fırlat

        if self._ops:
            writer = get_writer()
            success = writer.execute_batch(
                self._ops,
                scan_id=self.scan_id,
                wait=True,
            )
            if success:
                self._committed = True
                log.info(
                    "ScanTransaction %s commit: %d op",
                    self.scan_id, len(self._ops),
                )
            else:
                log.error(
                    "ScanTransaction %s commit başarısız",
                    self.scan_id,
                )
        return False

    # ── Sinyal ekleme ──────────────────────────────────────

    def add_signals(self, signals: list["UnifiedSignal"]):
        for s in signals:
            self._ops.append((
                """INSERT OR IGNORE INTO unified_signals
                   (signal_id, timestamp, source, signal_type, geography,
                    lat, lon, confidence, severity, value, normalized_value,
                    keywords, entities, metadata, scan_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    s.signal_id,
                    _ts(s.timestamp),
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
                    self.scan_id,
                ),
            ))

    # ── Feature ekleme ─────────────────────────────────────

    def add_features(self, features: list["ScenarioFeature"]):
        for f in features:
            self._ops.append((
                """INSERT OR IGNORE INTO scenario_features
                   (feature_id, feature_name, region, timestamp, value,
                    confidence, contributing_signals, scenario_relevance,
                    decay_factor, scan_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    f.feature_id,
                    f.feature_name,
                    f.region,
                    _ts(f.timestamp),
                    f.value,
                    f.confidence,
                    json.dumps(f.contributing_signals),
                    json.dumps({str(k): v for k, v in f.scenario_relevance.items()}),
                    f.decay_factor,
                    self.scan_id,
                ),
            ))

    # ── Scoring output ekleme ──────────────────────────────

    def add_scores(self, outputs: list["ScoringOutput"]):
        for o in outputs:
            self._ops.append((
                """INSERT OR REPLACE INTO scoring_outputs
                   (output_id, scan_id, timestamp, scenario_id, scenario_name,
                    region, score, probability, confidence, threshold_level,
                    contributing_factors, edge_contributions)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    o.output_id,
                    self.scan_id,
                    _ts(o.timestamp),
                    o.scenario_id,
                    o.scenario_name,
                    o.region,
                    o.score,
                    o.probability,
                    o.confidence,
                    o.threshold_level,
                    json.dumps(o.contributing_factors),
                    json.dumps(o.edge_contributions),
                ),
            ))

    # ── Prediction ekleme ──────────────────────────────────

    def add_predictions(self, predictions: list["Prediction"]):
        """
        Tüm prediction'lar kaydedilir — düşük güvenli olanlar dahil.
        Survivorship bias'ı önler: sadece yüksek güvenli olanları kaydetme.
        """
        for p in predictions:
            self._ops.append((
                """INSERT OR IGNORE INTO predictions
                   (prediction_id, created_at, scenario_id, scenario_name,
                    region, probability, confidence, horizon_hours,
                    status, source_scan_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    p.prediction_id,
                    _ts(p.created_at),
                    p.scenario_id,
                    p.scenario_name,
                    p.region,
                    p.probability,
                    p.confidence,
                    p.horizon_hours,
                    p.status.value,
                    p.source_scan_id,
                ),
            ))

    @property
    def op_count(self) -> int:
        return len(self._ops)


def _ts(dt: datetime) -> str:
    """
    Timezone-aware UTC datetime → ISO string.
    Naive datetime → UTC varsayımı ile düzelt.
    """
    if dt.tzinfo is None:
        # Naive → UTC kabul et
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()
