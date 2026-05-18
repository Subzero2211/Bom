"""
logosint/api/routes.py

Flask API endpoints — production-hardened.
Tüm yazma işlemleri DBWriter üzerinden.
Tüm timestamp'ler UTC-aware.
"""

from __future__ import annotations
import logging
from flask import Blueprint, jsonify, request

from logosint.repositories.feature_repo import (
    get_scores, get_heatmap, get_trend,
    get_features, get_signals,
    get_predictions, compute_calibration_stats,
)
from logosint.monitoring.health_monitor import take_snapshot
from logosint.schedulers.scoring_scheduler import get_scheduler
from logosint.schedulers.scan_lock import get_scan_status
from logosint.utils.time_utils import utcnow

log = logging.getLogger("API")
bp = Blueprint("logosint", __name__, url_prefix="/api")

# Explain endpoint
from logosint.explain import register_explain_routes
register_explain_routes(bp)

# LLM analiz endpoint'leri
def _init_llm_routes():
    try:
        from logosint.analysis.llm_analyzer import register_llm_routes
        try:
            from config import ANTHROPIC, OLLAMA
            llm_config = {
                "anthropic_api_key": ANTHROPIC.get("api_key", ""),
                "anthropic_model":   ANTHROPIC.get("model", "claude-sonnet-4-20250514"),
                "ollama_url":        OLLAMA.get("url", "http://localhost:11434"),
                "ollama_model":      OLLAMA.get("model", "llama3.1:8b"),
            }
        except (ImportError, AttributeError):
            llm_config = {}
        register_llm_routes(bp, llm_config)
        log.info("LLM analiz endpoint'leri kaydedildi")
    except Exception as e:
        log.warning("LLM routes yüklenemedi: %s", e)

_init_llm_routes()


def _pagination(req) -> tuple[int, int]:
    limit  = min(int(req.args.get("limit",  100)), 500)
    offset = int(req.args.get("offset", 0))
    return limit, offset


def _hours(req, default: int = 24) -> int:
    return max(1, min(int(req.args.get("hours", default)), 720))


# ─── /api/scores ──────────────────────────────────────────

@bp.route("/scores")
def scores():
    try:
        limit, offset = _pagination(request)
        data = get_scores(
            region      = request.args.get("region"),
            scenario_id = request.args.get("scenario_id", type=int),
            hours       = _hours(request),
            min_score   = float(request.args.get("min_score", 0)),
            limit       = limit,
            offset      = offset,
        )
        return jsonify({"status": "ok", "count": len(data), "offset": offset, "data": data})
    except Exception as e:
        log.error("/api/scores: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500


# ─── /api/heatmap ─────────────────────────────────────────

@bp.route("/heatmap")
def heatmap():
    try:
        from logosint.scoring_engine import GEOGRAPHIES
        data = get_heatmap(hours=_hours(request))
        for row in data:
            geo = GEOGRAPHIES.get(row["region"], {})
            row["lat"] = geo.get("lat")
            row["lon"] = geo.get("lon")
        return jsonify({"status": "ok", "count": len(data), "data": data})
    except Exception as e:
        log.error("/api/heatmap: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500


# ─── /api/trends ──────────────────────────────────────────

@bp.route("/trends")
def trends():
    region      = request.args.get("region")
    scenario_id = request.args.get("scenario_id", type=int)
    days        = max(1, min(int(request.args.get("days", 7)), 90))

    if not region or not scenario_id:
        return jsonify({"status": "error", "message": "region ve scenario_id gerekli"}), 400
    try:
        data = get_trend(region, scenario_id, days)
        return jsonify({
            "status": "ok", "region": region,
            "scenario_id": scenario_id, "days": days, "data": data,
        })
    except Exception as e:
        log.error("/api/trends: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500


# ─── /api/features ────────────────────────────────────────

@bp.route("/features")
def features():
    try:
        limit, _ = _pagination(request)
        data = get_features(
            region       = request.args.get("region"),
            feature_name = request.args.get("feature_name"),
            hours        = _hours(request, 6),
            limit        = limit,
        )
        return jsonify({"status": "ok", "count": len(data), "data": data})
    except Exception as e:
        log.error("/api/features: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500


# ─── /api/signals ─────────────────────────────────────────

@bp.route("/signals")
def signals():
    try:
        limit, _ = _pagination(request)
        data = get_signals(
            geography = request.args.get("geography"),
            source    = request.args.get("source"),
            hours     = _hours(request, 6),
            limit     = limit,
        )
        return jsonify({"status": "ok", "count": len(data), "data": data})
    except Exception as e:
        log.error("/api/signals: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500


# ─── /api/predictions ─────────────────────────────────────

@bp.route("/predictions")
def predictions():
    try:
        limit, offset = _pagination(request)
        data = get_predictions(
            region  = request.args.get("region"),
            status  = request.args.get("status"),
            hours   = _hours(request, 168),
            limit   = limit,
            offset  = offset,
        )
        return jsonify({"status": "ok", "count": len(data), "offset": offset, "data": data})
    except Exception as e:
        log.error("/api/predictions: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route("/predictions/calibration")
def calibration():
    try:
        return jsonify({"status": "ok", "data": compute_calibration_stats()})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ─── /api/health ──────────────────────────────────────────

@bp.route("/health")
def health():
    try:
        from config import OPENSKY, AISHUB, MARINETRAFFIC, ACLED, REDDIT, FRED, TELEGRAM
        api_key_status = {
            "opensky":  bool(OPENSKY.get("user")),
            "marine":   bool(AISHUB.get("user") or MARINETRAFFIC.get("api_key")),
            "acled":    bool(ACLED.get("api_key")),
            "reddit":   bool(REDDIT.get("client_id")),
            "fred":     bool(FRED.get("api_key")),
            "telegram": bool(TELEGRAM.get("api_id")),
        }
    except ImportError:
        api_key_status = {}

    from logosint.storage.db_writer import get_writer
    writer_stats = get_writer().stats
    scheduler    = get_scheduler()
    snapshot     = take_snapshot(
        api_key_status = api_key_status,
        last_scan_id   = scheduler.status.get("last_scan_id"),
    )

    return jsonify({
        "status":          "ok",
        "system_ok":       snapshot.system_ok,
        "timestamp":       utcnow().isoformat(),
        "scheduler":       scheduler.status,
        "scan_lock":       get_scan_status().api_status,
        "db_writer":       writer_stats,
        "collectors":      [c.model_dump() for c in snapshot.collectors],
        "alerts_last_hour": snapshot.alerts_last_hour,
    })


# ─── /api/scan (POST) ─────────────────────────────────────

@bp.route("/scan", methods=["POST"])
def manual_scan():
    """Manuel scoring döngüsü."""
    import threading
    s = get_scan_status()

    if s.is_running:
        queued = s.queue_manual()
        if not queued:
            return jsonify({
                "status":    "dropped",
                "message":   "Manuel scan kuyruğu dolu, istek atıldı",
                "timestamp": utcnow().isoformat(),
            }), 503
        return jsonify({
            "status":    "queued",
            "message":   "Scan çalışıyor, sıraya alındı",
            "timestamp": utcnow().isoformat(),
        })

    scheduler = get_scheduler()
    t = threading.Thread(target=scheduler.trigger_now, daemon=True)
    t.start()
    return jsonify({
        "status":    "scan_started",
        "timestamp": utcnow().isoformat(),
    })


# ─── /api/scan/status ─────────────────────────────────────

@bp.route("/scan/status")
def scan_status():
    """Mevcut scan durumu."""
    return jsonify({
        "status": "ok",
        "data":   get_scan_status().api_status,
    })
