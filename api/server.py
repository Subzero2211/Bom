"""
api/server.py

Flask REST API — dashboard ve dış araçlar için.
"""

import json
import threading
import logging
from datetime import datetime, timedelta
from flask import Flask, jsonify, request
from flask_cors import CORS
from storage.db import (
    get_active_anomalies, get_active_clusters,
    get_latest_report, get_recent_raw_events,
)
from config import API

log = logging.getLogger("API")
app = Flask(__name__)
CORS(app)

# main.py tarafından doldurulur
_scan_trigger = None


def set_scan_trigger(fn):
    global _scan_trigger
    _scan_trigger = fn


# ── ENDPOINTS ─────────────────────────────────────────────────

@app.route("/api/status")
def status():
    """Sistem durumu + son rapor özeti."""
    report = get_latest_report()
    anomalies = get_active_anomalies(hours=12)
    clusters = get_active_clusters(hours=24)
    return jsonify({
        "status": report.get("system_status", "unknown") if report else "no_report",
        "last_report": report.get("generated_at") if report else None,
        "active_anomalies": len(anomalies),
        "active_clusters": len(clusters),
        "key_findings": report.get("key_findings", []) if report else [],
        "watch_list": report.get("watch_list", []) if report else [],
    })


@app.route("/api/report")
def report():
    """Son tam istihbarat raporu."""
    r = get_latest_report()
    if not r:
        return jsonify({"error": "Henüz rapor yok — ilk tarama bekleniyor"}), 404
    return jsonify(r)


@app.route("/api/anomalies")
def anomalies():
    """Aktif anomaliler."""
    hours = int(request.args.get("hours", 12))
    domain = request.args.get("domain")
    data = get_active_anomalies(hours=hours)
    if domain:
        data = [a for a in data if a.get("domain") == domain]
    return jsonify({"data": data, "count": len(data)})


@app.route("/api/clusters")
def clusters():
    """Aktif korelasyon kümeleri."""
    hours = int(request.args.get("hours", 24))
    data = get_active_clusters(hours=hours)
    return jsonify({"data": data, "count": len(data)})


@app.route("/api/events")
def events():
    """Ham olaylar — filtrelenebilir."""
    hours = int(request.args.get("hours", 6))
    domain = request.args.get("domain")
    region = request.args.get("region")
    limit = int(request.args.get("limit", 100))
    data = get_recent_raw_events(hours=hours, domain=domain, region=region, limit=limit)
    return jsonify({"data": data, "count": len(data)})


@app.route("/api/scan", methods=["POST"])
def manual_scan():
    """Manuel tarama tetikle."""
    if _scan_trigger:
        t = threading.Thread(target=_scan_trigger, daemon=True)
        t.start()
        return jsonify({"status": "scan_started", "time": datetime.utcnow().isoformat()})
    return jsonify({"error": "Scan trigger tanımlı değil"}), 500


@app.route("/api/sources")
def sources():
    """Kaynak konfigürasyonu ve durumu."""
    from config import RSS_FEEDS, REDDIT_SUBS, TELEGRAM, SCAN_INTERVALS
    return jsonify({
        "rss_feeds": list(RSS_FEEDS.keys()),
        "reddit_subs": REDDIT_SUBS,
        "telegram_channels": TELEGRAM["channels"],
        "scan_intervals": SCAN_INTERVALS,
    })


def run_server():
    log.info("API sunucusu başlatılıyor: http://localhost:%d", API["port"])
    app.run(host=API["host"], port=API["port"], debug=API["debug"], use_reloader=False)
