"""
logosint/explain.py

Explainability engine.
Her skor için "neden bu skor verildi" sorusunu yanıtlar.
Black-box değil — analyst görüp denetleyebilir.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Optional

log = logging.getLogger("Explain")


def explain_scenario_score(
    scenario_id: int,
    region:      str,
    scan_id:     str = None,
    top_n:       int = 5,
) -> dict:
    """
    Belirli bir senaryo skoruna katkı sağlayan faktörleri analiz et.

    Returns:
      {
        "scenario_id":            int,
        "scenario_name":          str,
        "region":                 str,
        "score":                  float,
        "threshold_level":        int,
        "probability":            float,
        "confidence":             float,
        "top_edges":              [{"edge_id", "motor_a", "motor_b", "strength", "contribution"}],
        "top_motors":             [{"motor", "signal_value", "weight"}],
        "contributing_features":  [{"feature_name", "value", "confidence"}],
        "evidence_signals":       [{"source", "signal_type", "value", "timestamp"}],
        "anomaly":                {"type", "zscore", "std_floored"} | null,
        "explanation":            str,   # human-readable
      }
    """
    from logosint.scoring_engine import EDGE_WEIGHTS, EDGES, SCENARIOS
    from logosint.repositories.feature_repo import _conn

    with _conn() as db:
        # 1. Skor
        if scan_id:
            score_row = db.execute(
                """SELECT * FROM scoring_outputs
                   WHERE scenario_id=? AND region=? AND scan_id=?
                   ORDER BY timestamp DESC LIMIT 1""",
                (scenario_id, region, scan_id),
            ).fetchone()
        else:
            score_row = db.execute(
                """SELECT * FROM scoring_outputs
                   WHERE scenario_id=? AND region=?
                   ORDER BY timestamp DESC LIMIT 1""",
                (scenario_id, region),
            ).fetchone()

        if not score_row:
            return {"error": "Skor bulunamadı", "scenario_id": scenario_id, "region": region}

        score_d = dict(score_row)
        actual_scan_id = score_d["scan_id"]
        ts = score_d["timestamp"]

        # 2. Bu scan'deki edge skorları
        edge_rows = db.execute(
            """SELECT edge_id, signal_strength FROM edge_scores
               WHERE geography=? AND scan_id=?
               ORDER BY signal_strength DESC""",
            (region, actual_scan_id),
        ).fetchall()

        # 3. Feature'lar
        feature_rows = db.execute(
            """SELECT * FROM scenario_features
               WHERE region=? AND scan_id=?
               ORDER BY value DESC""",
            (region, actual_scan_id),
        ).fetchall()

        # 4. Sinyaller (son 1 saat, bu bölge)
        from logosint.utils.time_utils import hours_ago, iso
        signal_rows = db.execute(
            """SELECT source, signal_type, value, normalized_value, timestamp,
                      severity, keywords
               FROM unified_signals
               WHERE geography=? AND timestamp>=?
               ORDER BY normalized_value DESC LIMIT 30""",
            (region, iso(hours_ago(2))),
        ).fetchall()

        # 5. Anomali
        anomaly_row = db.execute(
            """SELECT anomaly_type, delta_rolling, delta_ref, zscore
               FROM alerts
               WHERE geography=? AND scenario_id=? AND scan_id=?
               ORDER BY timestamp DESC LIMIT 1""",
            (region, scenario_id, actual_scan_id),
        ).fetchone()

    # ── Top edges — bu senaryoya en çok katkı yapanlar ──
    edge_lookup = {eid: (ma, mb) for eid, ma, mb in EDGES}
    edge_contributions = []
    for row in edge_rows:
        eid      = row["edge_id"]
        strength = row["signal_strength"]
        weight   = EDGE_WEIGHTS.get(eid, {}).get(scenario_id, 0)
        if weight == 0:
            continue
        contribution = strength * weight
        ma, mb = edge_lookup.get(eid, ("?", "?"))
        edge_contributions.append({
            "edge_id":      eid,
            "motor_a":      ma,
            "motor_b":      mb,
            "strength":     round(strength, 4),
            "weight":       weight,
            "contribution": round(contribution, 3),
        })
    edge_contributions.sort(key=lambda x: -x["contribution"])
    top_edges = edge_contributions[:top_n]

    # ── Top motors — hangi motorlar en çok kullanıldı ──
    motor_totals: dict[str, float] = defaultdict(float)
    for ec in edge_contributions:
        motor_totals[ec["motor_a"]] += ec["contribution"] / 2
        motor_totals[ec["motor_b"]] += ec["contribution"] / 2
    top_motors = [
        {"motor": m, "contribution": round(c, 3)}
        for m, c in sorted(motor_totals.items(), key=lambda x: -x[1])[:top_n]
    ]

    # ── Contributing features ──
    features = []
    for r in feature_rows:
        features.append({
            "feature_name": r["feature_name"],
            "value":        r["value"],
            "confidence":   r["confidence"],
        })

    # ── Evidence signals ──
    evidence = []
    import json
    for r in signal_rows[:10]:
        kw_raw = r["keywords"] or "[]"
        try:
            kw = json.loads(kw_raw)
        except Exception:
            kw = []
        evidence.append({
            "source":      r["source"],
            "signal_type": r["signal_type"],
            "value":       r["value"],
            "normalized":  r["normalized_value"],
            "severity":    r["severity"],
            "timestamp":   r["timestamp"],
            "keywords":    kw,
        })

    # ── Anomaly ──
    anomaly = dict(anomaly_row) if anomaly_row else None

    # ── Human-readable açıklama ──
    explanation = _build_text_explanation(
        score_d, top_edges, top_motors, features, anomaly, region,
    )

    return {
        "scenario_id":           scenario_id,
        "scenario_name":         SCENARIOS.get(scenario_id, str(scenario_id)),
        "region":                region,
        "scan_id":               actual_scan_id,
        "timestamp":             ts,
        "score":                 score_d["score"],
        "threshold_level":       score_d.get("threshold_level"),
        "probability":           score_d.get("probability"),
        "confidence":            score_d.get("confidence"),
        "top_edges":             top_edges,
        "top_motors":            top_motors,
        "contributing_features": features,
        "evidence_signals":      evidence,
        "anomaly":               anomaly,
        "explanation":           explanation,
    }


def _build_text_explanation(
    score_d:    dict,
    top_edges:  list,
    top_motors: list,
    features:   list,
    anomaly:    Optional[dict],
    region:     str,
) -> str:
    """İnsan okunabilir açıklama metni üret."""
    lines = []

    score = score_d.get("score", 0)
    name  = score_d.get("scenario_name", "?")
    lines.append(
        f"{name} senaryosu {region} bölgesinde {score:.1f} skor aldı."
    )

    if score_d.get("threshold_level", 0) >= 3:
        lines.append("Bu kritik eşiği aşan bir seviye.")
    elif score_d.get("threshold_level", 0) >= 2:
        lines.append("Bu uyarı seviyesinde.")

    if anomaly:
        z = anomaly.get("zscore", 0)
        atype = anomaly.get("anomaly_type", "?")
        floored = anomaly.get("std_floored", False)
        lines.append(
            f"Anomali tespit edildi: tip={atype}, z-score={z:.2f}"
            + (" (std floor uygulandı)" if floored else "")
        )

    if top_motors:
        m_names = ", ".join(f"{m['motor']}" for m in top_motors[:3])
        lines.append(f"En çok katkı yapan motorlar: {m_names}")

    if top_edges:
        e_names = ", ".join(
            f"{e['motor_a']}↔{e['motor_b']}" for e in top_edges[:3]
        )
        lines.append(f"En güçlü kenar sinyalleri: {e_names}")

    if features:
        active_features = [f for f in features if f["value"] > 0.3]
        if active_features:
            f_names = ", ".join(f["feature_name"] for f in active_features[:3])
            lines.append(f"Aktif özellikler: {f_names}")

    if score_d.get("confidence", 0) < 0.5:
        lines.append(
            "DİKKAT: Güven düşük — sınırlı kaynaktan gelen sinyallere dayanıyor."
        )

    return " ".join(lines)


# ═══════════════════════════════════════════════════════════
# API ENTEGRASYONU
# ═══════════════════════════════════════════════════════════

def register_explain_routes(blueprint):
    """Flask blueprint'e /explain endpoint'i ekle."""
    from flask import request, jsonify

    @blueprint.route("/explain")
    def explain():
        scenario_id = request.args.get("scenario_id", type=int)
        region      = request.args.get("region")
        scan_id     = request.args.get("scan_id")

        if not scenario_id or not region:
            return jsonify({
                "status": "error",
                "message": "scenario_id ve region gerekli",
            }), 400

        try:
            data = explain_scenario_score(
                scenario_id=scenario_id,
                region=region,
                scan_id=scan_id,
            )
            return jsonify({"status": "ok", "data": data})
        except Exception as e:
            log.error("/explain hata: %s", e, exc_info=True)
            return jsonify({"status": "error", "message": str(e)}), 500
