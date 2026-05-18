"""
logosint/reports/report_routes.py

Rapor API endpoint'leri.
Flask blueprint olarak routes.py'ye eklenir.

GET /api/reports/list              → arşiv listesi
GET /api/reports/latest?type=daily → son rapor bilgisi
GET /api/reports/trigger?type=hourly → manuel tetikleme
GET /reports/<path>                → PDF dosyasını sun

Ayrıca tarayıcıdan açılabilir arşiv sayfası:
GET /reports/archive               → HTML arşiv arayüzü
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, jsonify, request, send_file, render_template_string

from logosint.reports.report_scheduler import get_report_scheduler, load_index, REPORTS_DIR

rb = Blueprint("reports", __name__)

ARCHIVE_HTML = """<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8"/>
<title>LOGOSiNT — Rapor Arşivi</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#060c10;color:#c8dde8;font-family:'Segoe UI',sans-serif;font-size:13px}
header{padding:14px 24px;background:#040a0e;border-bottom:1px solid #1a3a4a;
  display:flex;align-items:center;gap:12px}
.logo{font-size:20px;font-weight:700;color:#fff}.logo b{color:#00c8e8}
.tabs{display:flex;gap:4px;margin:12px 24px 0}
.tab{padding:6px 18px;background:transparent;border:1px solid #1a3a4a;color:#2a5a6a;
  cursor:pointer;border-radius:4px 4px 0 0;font-size:11px}
.tab:hover,.tab.on{border-color:#00c8e8;color:#00c8e8;background:rgba(0,200,232,.06)}
#content{padding:0 24px 24px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:10px;margin-top:14px}
.card{background:#0a1520;border:1px solid #1a3a4a;border-radius:6px;padding:14px;
  display:flex;flex-direction:column;gap:6px}
.card:hover{border-color:#1e4a5e}
.card-type{font-size:9px;font-weight:600;letter-spacing:.12em;color:#2a5a6a}
.card-date{font-size:12px;font-weight:600;color:#c8dde8}
.card-meta{font-size:10px;color:#2a5a6a}
.card-link{margin-top:6px;display:flex;gap:8px}
.pdf-btn{padding:5px 14px;background:rgba(0,200,232,.08);border:1px solid #00c8e8;
  color:#00c8e8;border-radius:4px;text-decoration:none;font-size:10px}
.pdf-btn:hover{background:rgba(0,200,232,.18)}
.txt-btn{padding:5px 14px;background:rgba(42,90,106,.15);border:1px solid #1a3a4a;
  color:#5a8a9a;border-radius:4px;text-decoration:none;font-size:10px}
.score-badge{padding:2px 7px;border-radius:3px;font-size:9px;font-weight:600}
.badge-crit{background:#1a0008;border:1px solid #ff2244;color:#ff2244}
.badge-warn{background:#1a0e00;border:1px solid #ffaa00;color:#ffaa00}
.badge-ok{background:#001a08;border:1px solid #00cc66;color:#00cc66}
.empty{color:#2a5a6a;padding:24px 0;font-size:12px}
</style>
</head>
<body>
<header>
  <div class="logo">LOGOS<b>iNT</b></div>
  <span style="color:#2a5a6a;font-size:11px">Rapor Arşivi</span>
</header>

<div class="tabs">
  <button class="tab on" onclick="show('all')">Tümü</button>
  <button class="tab" onclick="show('hourly')">Saatlik</button>
  <button class="tab" onclick="show('daily')">Günlük</button>
  <button class="tab" onclick="show('weekly')">Haftalık</button>
  <button class="tab" onclick="show('monthly')">Aylık</button>
</div>

<div id="content">
  <div class="grid" id="grid"></div>
</div>

<script>
const reports = {{ reports|tojson }};
let current = 'all';

const LABELS = {
  hourly:'Saatlik',daily:'Günlük',weekly:'Haftalık',monthly:'Aylık'
};

function show(type){
  current=type;
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('on'));
  event.target.classList.add('on');
  render();
}

function render(){
  const filtered = current==='all' ? reports : reports.filter(r=>r.type===current);
  const sorted   = filtered.sort((a,b)=>b.timestamp.localeCompare(a.timestamp));
  const grid     = document.getElementById('grid');
  if(!sorted.length){grid.innerHTML='<div class="empty">Bu kategoride rapor bulunamadı.</div>';return;}
  grid.innerHTML = sorted.map(r=>{
    const d   = new Date(r.timestamp);
    const ts  = d.toLocaleString('tr-TR',{day:'2-digit',month:'long',year:'numeric',hour:'2-digit',minute:'2-digit'});
    const meta= r.meta||{};
    const score = meta.top_score ? parseFloat(meta.top_score) : null;
    const bclass= score>=75?'badge-crit':score>=55?'badge-warn':'badge-ok';
    const pdfUrl= '/reports/file?path='+encodeURIComponent(r.path);
    const txtUrl= pdfUrl.replace('.pdf','.txt');
    const crit  = meta.critC||0, warn=meta.warnC||0;
    return \`<div class="card">
      <div class="card-type">\${LABELS[r.type]||r.type}</div>
      <div class="card-date">\${ts}</div>
      <div class="card-meta">
        \${crit?'<span style="color:#ff2244">● '+crit+' kritik</span>&nbsp;':''}
        \${warn?'<span style="color:#ffaa00">▲ '+warn+' uyarı</span>&nbsp;':''}
        \${meta.top_scenario?'Top: '+meta.top_scenario:''}
      </div>
      \${score?'<div><span class="score-badge '+bclass+'">'+score.toFixed(1)+'</span></div>':''}
      <div class="card-link">
        <a class="pdf-btn" href="\${pdfUrl}" target="_blank">PDF Aç</a>
        <a class="txt-btn" href="\${txtUrl}" target="_blank">TXT</a>
      </div>
    </div>\`;
  }).join('');
}

render();
</script>
</body>
</html>"""


@rb.route("/reports/archive")
def archive_page():
    idx = load_index()
    reports = idx.get("reports", [])
    return render_template_string(ARCHIVE_HTML, reports=reports)


@rb.route("/reports/file")
def serve_report():
    """PDF veya TXT dosyasını sun."""
    path = request.args.get("path", "")
    if not path:
        return "path gerekli", 400
    p = Path(path)
    if not p.exists():
        return "Dosya bulunamadı", 404
    # Güvenlik: sadece reports/ dizini altındaki dosyalar
    try:
        p.resolve().relative_to(REPORTS_DIR.resolve())
    except ValueError:
        return "Erişim reddedildi", 403
    return send_file(str(p.absolute()),
                     as_attachment=False,
                     mimetype="application/pdf" if p.suffix == ".pdf" else "text/plain")


@rb.route("/api/reports/list")
def list_reports():
    rtype  = request.args.get("type")
    limit  = int(request.args.get("limit", 50))
    idx    = load_index()
    reports = idx.get("reports", [])
    if rtype:
        reports = [r for r in reports if r["type"] == rtype]
    reports = sorted(reports, key=lambda r: r["timestamp"], reverse=True)[:limit]
    return jsonify({"status": "ok", "count": len(reports), "data": reports})


@rb.route("/api/reports/latest")
def latest_report():
    rtype = request.args.get("type", "daily")
    idx   = load_index()
    filtered = [r for r in idx.get("reports", []) if r["type"] == rtype]
    if not filtered:
        return jsonify({"status": "ok", "data": None})
    latest = sorted(filtered, key=lambda r: r["timestamp"], reverse=True)[0]
    return jsonify({"status": "ok", "data": latest})


@rb.route("/api/reports/trigger", methods=["POST", "GET"])
def trigger_report():
    rtype     = request.args.get("type", "hourly")
    scheduler = get_report_scheduler()
    msg       = scheduler.trigger(rtype)
    return jsonify({"status": "ok", "message": msg, "type": rtype})


@rb.route("/api/reports/status")
def report_status():
    scheduler = get_report_scheduler()
    return jsonify({"status": "ok", "data": scheduler.status})
