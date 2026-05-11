"""
api/server.py

Flask REST API — dashboard ve dış araçlar için.
"""

import json
import threading
import logging
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from storage.db import (
    get_active_anomalies, get_active_clusters,
    get_latest_report, get_recent_raw_events, get_conn,
)
from config import API
from analysis.report_generator import ReportGenerator
from analysis.interpreter import DataInterpreter
from models.intelligence import IntelligenceReport
from models.event import AnomalyEvent

log = logging.getLogger("API")
app = Flask(__name__)
CORS(app)

# Generators
report_gen = ReportGenerator()
interpreter = DataInterpreter()

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


@app.route("/api/report/pdf")
def report_pdf():
    """Son raporu PDF olarak indir."""
    try:
        report_data = get_latest_report()
        if not report_data:
            return jsonify({"error": "Rapor bulunamadı"}), 404

        # Dict'i IntelligenceReport nesnesine dönüştür
        report = IntelligenceReport(**report_data)

        # PDF oluştur
        filepath = report_gen.generate(report)

        # İndir
        return send_file(filepath, as_attachment=True, download_name=f"osint_report_{report.report_id}.pdf")

    except Exception as e:
        log.error(f"PDF oluşturma hatası: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/interpret/anomaly/<anomaly_id>")
def interpret_anomaly(anomaly_id):
    """Anomaliyi yorumla."""
    try:
        conn = get_conn()
        row = conn.execute(
            "SELECT * FROM anomaly_events WHERE event_id = ? LIMIT 1",
            (anomaly_id,)
        ).fetchone()
        conn.close()

        if not row:
            return jsonify({"error": "Anomali bulunamadı"}), 404

        # Dict'e çevir
        anom_dict = dict(row)

        # AnomalyEvent nesnesine dönüştür (simplified)
        # Not: Burada tam conversion yapmak için raw event da gerekli olabilir
        interpretation = interpreter.interpret_anomaly(anom_dict)

        return jsonify(interpretation)

    except Exception as e:
        log.error(f"Yorumlama hatası: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/interpret/cluster/<cluster_id>")
def interpret_cluster(cluster_id):
    """Korelasyon kümesini yorumla."""
    try:
        conn = get_conn()
        row = conn.execute(
            "SELECT * FROM correlation_clusters WHERE cluster_id = ? LIMIT 1",
            (cluster_id,)
        ).fetchone()
        conn.close()

        if not row:
            return jsonify({"error": "Küme bulunamadı"}), 404

        cluster_dict = dict(row)
        interpretation = interpreter.interpret_cluster(cluster_dict)

        return jsonify(interpretation)

    except Exception as e:
        log.error(f"Küme yorumlama hatası: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/insights")
def insights():
    """Üst seviye insights — anomaliler + kümeler + öngörüler."""
    try:
        hours = int(request.args.get("hours", 24))

        anomalies = get_active_anomalies(hours=hours)
        clusters = get_active_clusters(hours=hours)

        # Kritik anomalileri yorumla
        interpretations = []
        for anom in anomalies[:5]:  # Top 5
            interp = interpreter.interpret_anomaly(anom)
            interpretations.append(interp)

        # Kritik kümeleri yorumla
        cluster_interps = []
        for clust in clusters[:3]:  # Top 3
            interp = interpreter.interpret_cluster(clust)
            cluster_interps.append(interp)

        return jsonify({
            "timestamp": datetime.utcnow().isoformat(),
            "anomaly_insights": interpretations,
            "cluster_insights": cluster_interps,
            "total_anomalies": len(anomalies),
            "total_clusters": len(clusters),
        })

    except Exception as e:
        log.error(f"Insights hatası: {e}")
        return jsonify({"error": str(e)}), 500


def run_server():
    log.info("API sunucusu başlatılıyor: http://localhost:%d", API["port"])
    app.run(host=API["host"], port=API["port"], debug=API["debug"], use_reloader=False)
