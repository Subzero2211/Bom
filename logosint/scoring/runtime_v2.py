"""
logosint/scoring/runtime_v2.py

Production-hardened scoring runtime.

Entegre edilen düzeltmeler:
- Atomik ScanTransaction (partial scan yok)
- ScanLock (concurrent scan yok)
- UTC-aware timestamps
- Double decay fix (adapter_v2 kullanır)
- Survivorship bias fix (tüm predictions kaydedilir)
- DBWriter üzerinden tüm yazma işlemleri
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import timezone
from typing import Any

from logosint.models.signals import UnifiedSignal
from logosint.models.scoring import ScoringOutput, Prediction, PredictionStatus
from logosint.normalizers.base import NORMALIZER_REGISTRY
from logosint.adapters.signal_adapter_v2 import get_adapter
from logosint.storage.scan_transaction import ScanTransaction
from logosint.schedulers.scan_lock import get_scan_status
from logosint.utils.time_utils import utcnow, to_utc

log = logging.getLogger("ScoringRuntime")

try:
    from logosint.scoring_engine import (
        compute_scoring_cycle,    # pure computation — DB'ye yazmaz
        GEOGRAPHIES,
        SCENARIOS,
        EDGES,
        get_threshold_level,
        update_rolling_baseline,
        init_db as init_scoring_db,
    )
    SCORING_ENGINE_AVAILABLE = True
except ImportError:
    log.warning("scoring_engine import edilemedi")
    SCORING_ENGINE_AVAILABLE = False
    GEOGRAPHIES = {}
    SCENARIOS   = {}
    EDGES       = []


# ═══════════════════════════════════════════════════════════
# NORMALIZE
# ═══════════════════════════════════════════════════════════

def normalize_all(
    collector_outputs: dict[str, list[dict[str, Any]]],
) -> list[UnifiedSignal]:
    all_signals = []
    for source, items in collector_outputs.items():
        normalizer = NORMALIZER_REGISTRY.get(source)
        if not normalizer:
            log.debug("Normalizer yok: %s", source)
            continue
        for item in items:
            # Timestamp timezone normalize
            if "timestamp" in item and isinstance(item["timestamp"], str):
                ts = to_utc(item["timestamp"])
                if ts:
                    item["timestamp"] = ts.isoformat()
            try:
                sigs = normalizer.normalize(item)
                all_signals.extend(sigs)
            except Exception as e:
                log.debug("[%s] normalize hata: %s", source, e)
    log.info("%d sinyal normalize edildi", len(all_signals))
    return all_signals


# ═══════════════════════════════════════════════════════════
# FULL CYCLE
# ═══════════════════════════════════════════════════════════

def run_full_cycle(
    collector_outputs: dict[str, list[dict[str, Any]]],
    scan_id: str = None,
) -> dict:
    """
    Tam döngü — atomik, lock'lu, timezone-safe.
    """
    if scan_id is None:
        scan_id = f"SCAN-{utcnow().strftime('%Y%m%d-%H%M')}-{uuid.uuid4().hex[:6].upper()}"

    # ── Scan lock ─────────────────────────────────────────
    scan_status = get_scan_status()
    if not scan_status.try_acquire(scan_id):
        # Meşgul → manuel isteği sıraya al
        scan_status.queue_manual()
        return {
            "scan_id": scan_id,
            "status":  "skipped_busy",
            "message": "Scan zaten çalışıyor",
        }

    now     = utcnow()
    t_start = time.time()
    success = False

    log.info("═" * 60)
    log.info("FULL CYCLE: %s", scan_id)

    try:
        # 1. Normalize
        signals = normalize_all(collector_outputs)

        # 2. Adapt → features
        adapter  = get_adapter()
        regions  = list(GEOGRAPHIES.keys()) if SCORING_ENGINE_AVAILABLE else []
        features_by_region = adapter.adapt_all_regions(signals, regions, now)

        # 3. Motor signals
        motor_signals = adapter.to_motor_signals(features_by_region)

        # 4. PURE COMPUTATION — scoring engine artık DB'ye yazmıyor
        scoring_outputs: list[ScoringOutput] = []
        total_alerts = 0
        compute_result = {}

        if SCORING_ENGINE_AVAILABLE:
            compute_result = compute_scoring_cycle(motor_signals)
            scoring_outputs = _build_outputs_from_compute(
                compute_result, features_by_region, scan_id, now,
            )
            total_alerts = len(compute_result.get("anomalies", []))

        # 5. Predictions — threshold ≥ 1 olan tümü
        predictions = _generate_predictions(scoring_outputs, scan_id)

        # 6. TEK ATOMİK BATCH — signals + features + scoring + scans + alerts
        all_features = []
        for feats in features_by_region.values():
            all_features.extend(feats)

        with ScanTransaction(scan_id) as tx:
            tx.add_signals(signals)
            tx.add_features(all_features)
            tx.add_scores(scoring_outputs)
            tx.add_predictions(predictions)
            # Edge scores, scenario scores, alerts ve baseline güncellemeleri
            # de aynı transaction'a ekle
            _add_scoring_engine_writes(tx, compute_result, scan_id, now)

        success = True
        elapsed = time.time() - t_start

        log.info(
            "CYCLE TAMAM: %s | %.1fs | %d sig | %d feat | %d score | %d pred | %d alert",
            scan_id, elapsed,
            len(signals), len(all_features),
            len(scoring_outputs), len(predictions), total_alerts,
        )

        result = {
            "scan_id":     scan_id,
            "status":      "completed",
            "timestamp":   now.isoformat(),
            "signals":     len(signals),
            "features":    len(all_features),
            "scores":      len(scoring_outputs),
            "alerts":      total_alerts,
            "predictions": len(predictions),
            "elapsed_s":   round(elapsed, 2),
        }

    except Exception as e:
        log.error("CYCLE HATA %s: %s", scan_id, e, exc_info=True)
        result = {
            "scan_id": scan_id,
            "status":  "error",
            "message": str(e),
        }
    finally:
        scan_status.release(scan_id, success=success)

    log.info("═" * 60)

    # Bekleyen manuel scan var mı? — bounded queue (max 5)
    if scan_status.pop_queued():
        log.info("Sıradaki manuel scan tetikleniyor...")
        import threading
        # Direkt yeni thread'de çalıştır — kuyruktan çek
        threading.Thread(
            target=run_full_cycle,
            args=(collector_outputs, None),
            daemon=True,
            name="ManualScanFollowup",
        ).start()

    return result


# ═══════════════════════════════════════════════════════════
# OUTPUT BUILDER — pure compute result'tan ScoringOutput üretir
# ═══════════════════════════════════════════════════════════

def _build_outputs_from_compute(
    compute_result:     dict,
    features_by_region: dict,
    scan_id:            str,
    now,
) -> list[ScoringOutput]:
    """
    compute_scoring_cycle çıktısından ScoringOutput modelleri üret.
    DB'ye dokunmaz — tüm veri zaten dict içinde.
    """
    import math
    import uuid

    outputs = []
    scores_by_region = compute_result.get("scores", {})
    thresholds_by_region = compute_result.get("thresholds", {})

    for region, scenarios in scores_by_region.items():
        features = features_by_region.get(region, [])
        if features:
            conf = min(0.95, sum(f.confidence for f in features) / len(features))
        else:
            conf = 0.3

        factor_names = [f.feature_name for f in features if f.value > 0.3]

        for scenario_id, score in scenarios.items():
            prob      = 1 / (1 + math.exp(-(score - 50) / 15))
            threshold = thresholds_by_region.get(region, {}).get(scenario_id, 0)

            outputs.append(ScoringOutput(
                output_id            = str(uuid.uuid4()),
                scan_id              = scan_id,
                timestamp            = now,
                scenario_id          = scenario_id,
                scenario_name        = SCENARIOS.get(scenario_id, str(scenario_id)),
                region               = region,
                score                = score,
                probability          = round(prob, 4),
                confidence           = round(conf, 3),
                threshold_level      = threshold,
                contributing_factors = factor_names,
            ))

    return outputs


def _add_scoring_engine_writes(tx, compute_result: dict, scan_id: str, now):
    """
    Edge scores, scenario scores ve alerts'i ScanTransaction'a ekle.
    Tüm scoring engine yazıları artık tek transaction içinde.
    """
    from logosint.utils.time_utils import iso
    ts = iso(now)

    # Edge scores
    for geo, edges in compute_result.get("edge_strengths", {}).items():
        for edge_id, strength in edges.items():
            tx._ops.append((
                "INSERT INTO edge_scores (edge_id, geography, signal_strength, timestamp, scan_id) "
                "VALUES (?,?,?,?,?)",
                (edge_id, geo, strength, ts, scan_id),
            ))

    # Scenario scores
    for geo, scenarios in compute_result.get("scores", {}).items():
        thresholds = compute_result.get("thresholds", {}).get(geo, {})
        for scenario_id, score in scenarios.items():
            threshold = thresholds.get(scenario_id, 0)
            tx._ops.append((
                "INSERT INTO scenario_scores "
                "(scenario_id, scenario_name, geography, score, threshold, timestamp, scan_id) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    scenario_id, SCENARIOS.get(scenario_id, str(scenario_id)),
                    geo, score, threshold, ts, scan_id,
                ),
            ))

    # Alerts
    for anomaly in compute_result.get("anomalies", []):
        tx._ops.append((
            "INSERT INTO alerts "
            "(geography, scenario_id, scenario_name, score, threshold, "
            " anomaly_type, delta_rolling, delta_ref, timestamp, scan_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                anomaly["geography"], anomaly["scenario_id"],
                anomaly["scenario_name"], anomaly["score"],
                anomaly["threshold"], anomaly["anomaly_type"],
                anomaly["delta_rolling"], anomaly["delta_ref"],
                ts, scan_id,
            ),
        ))


# ═══════════════════════════════════════════════════════════
# PREDICTION GENERATOR — survivorship bias yok
# ═══════════════════════════════════════════════════════════

def _generate_predictions(
    outputs: list[ScoringOutput],
    scan_id: str,
) -> list[Prediction]:
    """
    Threshold ≥ 1 olan TÜM output'lardan prediction üret.
    Düşük güvenli olanlar da kaydedilir — calibration için gerekli.
    Sadece yüksek güvenli olanları kaydetmek survivorship bias yaratır.
    """
    predictions = []
    seen: set[tuple] = set()

    for o in outputs:
        if o.threshold_level < 1:
            continue
        key = (o.scenario_id, o.region)
        if key in seen:
            continue
        seen.add(key)

        predictions.append(Prediction(
            created_at     = o.timestamp,
            scenario_id    = o.scenario_id,
            scenario_name  = o.scenario_name,
            region         = o.region,
            probability    = o.probability,
            confidence     = o.confidence,
            horizon_hours  = 24,
            status         = PredictionStatus.PENDING,
            source_scan_id = scan_id,
        ))

    return predictions


# ═══════════════════════════════════════════════════════════
# INIT
# ═══════════════════════════════════════════════════════════

def init_runtime():
    from logosint.repositories.feature_repo import init_feature_store
    from logosint.storage.db_writer import get_writer
    init_feature_store()
    if SCORING_ENGINE_AVAILABLE:
        init_scoring_db()
    get_writer()   # writer'ı başlat
    log.info("Runtime v2 başlatıldı")
