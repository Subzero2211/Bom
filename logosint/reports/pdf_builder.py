"""
logosint/reports/pdf_builder.py

Tüm rapor tipleri için birleşik PDF üretici.
report_scheduler.py buraya çağrı yapar.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, Flowable, KeepTogether
)

# ── RENKLER ───────────────────────────────────────────────
C = {
    "bg":     colors.HexColor("#060c10"),
    "panel":  colors.HexColor("#0a1520"),
    "dark":   colors.HexColor("#040a0e"),
    "border": colors.HexColor("#1a3a4a"),
    "crit":   colors.HexColor("#ff2244"),
    "warn":   colors.HexColor("#ffaa00"),
    "ok":     colors.HexColor("#00cc66"),
    "blue":   colors.HexColor("#00c8e8"),
    "purple": colors.HexColor("#cc88ff"),
    "dim":    colors.HexColor("#2a5a6a"),
    "text":   colors.HexColor("#c8dde8"),
    "red_bg": colors.HexColor("#1a0008"),
    "amb_bg": colors.HexColor("#1a0e00"),
    "white":  colors.white,
}

W, H = A4
W_body = W - 28*mm

TYPE_LABELS = {
    "hourly":  "Saatlik Rapor",
    "daily":   "Günlük Kapsamlı Rapor",
    "weekly":  "Haftalık Rapor",
    "monthly": "Aylık Değerlendirme",
}
TYPE_COLORS = {
    "hourly":  "#00c8e8",
    "daily":   "#00c8e8",
    "weekly":  "#cc88ff",
    "monthly": "#ffaa00",
}
BACKEND_LABELS = {
    "ollama":          "Llama 3.1 (Yerel)",
    "anthropic":       "Claude (Anthropic API)",
    "ollama_fallback": "Llama Fallback",
    "none":            "LLM Yok",
}


# ── STİL FONKSİYONU ───────────────────────────────────────
def S(name, **kw):
    base = dict(fontName="Helvetica", fontSize=9, textColor=C["text"],
                leading=14, spaceBefore=0, spaceAfter=0)
    base.update(kw)
    return ParagraphStyle(name, **base)


# ── CUSTOM FLOWABLES ──────────────────────────────────────

class SectionBar(Flowable):
    def __init__(self, text, color_hex="#00c8e8", w=None):
        self.text = text
        self.color = colors.HexColor(color_hex)
        self.w = w or W_body
        self.height = 20

    def wrap(self, *args): return self.w, self.height

    def draw(self):
        c = self.canv
        c.setFillColor(C["panel"])
        c.roundRect(0, 2, self.w, 16, 2, fill=1, stroke=0)
        c.setFillColor(self.color)
        c.rect(0, 2, 3, 16, fill=1, stroke=0)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(10, 7, self.text.upper())


class AlertBlock(Flowable):
    def __init__(self, level, title, detail, w=None):
        self.level  = level
        self.title  = title[:90]
        self.detail = detail[:120]
        self.w = w or W_body
        self.height = 50

    def wrap(self, *args): return self.w, self.height

    def draw(self):
        c = self.canv
        col = C["crit"] if self.level == "critical" else C["warn"] if self.level == "warning" else C["blue"]
        bg  = C["red_bg"] if self.level == "critical" else C["amb_bg"] if self.level == "warning" else C["panel"]
        c.setFillColor(bg)
        c.roundRect(0, 0, self.w, self.height, 3, fill=1, stroke=0)
        c.setFillColor(col)
        c.rect(0, 0, 3, self.height, fill=1, stroke=0)
        c.setFont("Helvetica-Bold", 7)
        c.setFillColor(col)
        c.drawString(10, self.height - 13, self.level.upper())
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(C["white"])
        c.drawString(10, self.height - 25, self.title)
        c.setFont("Helvetica", 8)
        c.setFillColor(C["text"])
        c.drawString(10, self.height - 37, self.detail)


# ── YARDIMCI ──────────────────────────────────────────────

def _thr_color(thr):
    return C["crit"] if thr >= 3 else C["warn"] if thr >= 2 else C["blue"] if thr >= 1 else C["dim"]


def _sev_color(sev):
    return C["crit"] if sev == "critical" else C["warn"] if sev == "warning" else C["ok"]


def _prob(score):
    import math
    return int(1 / (1 + math.exp(-(score - 50) / 15)) * 100)


# ── HEADER ────────────────────────────────────────────────

def _header(report_type, timestamp, backend, story):
    type_label  = TYPE_LABELS.get(report_type, report_type)
    type_color  = colors.HexColor(TYPE_COLORS.get(report_type, "#00c8e8"))
    back_label  = BACKEND_LABELS.get(backend, backend)

    hdata = [[
        Paragraph(
            '<font color="#00c8e8"><b>LOGOS</b></font><font color="white"><b>iNT</b></font>',
            S("lh", fontSize=22, fontName="Helvetica-Bold", leading=26)
        ),
        Paragraph(
            f'<font color="#2a5a6a">{type_label}</font><br/>'
            f'<font color="#1a4a5a">{timestamp.strftime("%d %B %Y  %H:%M UTC")}</font><br/>'
            f'<font color="#1a3a4a">Analiz: {back_label}</font>',
            S("rh", fontSize=8, textColor=C["dim"], leading=13, alignment=TA_RIGHT)
        ),
    ]]
    ht = Table(hdata, colWidths=[W_body * 0.4, W_body * 0.6])
    ht.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), C["dark"]),
        ("TOPPADDING",   (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 10),
        ("LEFTPADDING",  (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    story.append(ht)
    story.append(Spacer(1, 3 * mm))


def _status_bar(ctx, story):
    scores = ctx.get("scores", [])
    signals = ctx.get("signals", [])
    top    = scores[0] if scores else {}
    critC  = sum(1 for s in scores if s.get("threshold_level", 0) >= 3)
    warnC  = sum(1 for s in scores if s.get("threshold_level", 0) == 2)

    sdata = [[
        Paragraph(f'<b>{"● KRİTİK" if critC else "▲ UYARI" if warnC else "○ OK"}</b>',
                  S("ss", fontSize=11, fontName="Helvetica-Bold",
                    textColor=C["crit"] if critC else C["warn"] if warnC else C["ok"], leading=14)),
        Paragraph(f'<b>{critC}</b> Kritik  <b>{warnC}</b> Uyarı',
                  S("ss2", fontSize=9, textColor=C["warn"], leading=13)),
        Paragraph(f'<b>{len(scores)}</b> Senaryo',
                  S("ss3", fontSize=9, textColor=C["text"], leading=13)),
        Paragraph(f'<b>{len(signals)}</b> Sinyal',
                  S("ss4", fontSize=9, textColor=C["text"], leading=13)),
        Paragraph(f'Top: <b>{top.get("score", 0):.1f}</b>',
                  S("ss5", fontSize=9, textColor=C["purple"], fontName="Helvetica-Bold", leading=13)),
    ]]
    st = Table(sdata, colWidths=[W_body * 0.22, W_body * 0.22, W_body * 0.18,
                                   W_body * 0.18, W_body * 0.20])
    st.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), C["panel"]),
        ("TOPPADDING",   (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 7),
        ("LEFTPADDING",  (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("LINEAFTER",    (0, 0), (3, 0), 0.4, C["border"]),
    ]))
    story.append(st)
    story.append(Spacer(1, 4 * mm))


# ── BÖLÜMLER ──────────────────────────────────────────────

def _section_scores(ctx, story):
    scores = ctx.get("scores", [])
    if not scores:
        return
    story.append(SectionBar("Senaryo Skorları", TYPE_COLORS.get("daily", "#00c8e8")))
    story.append(Spacer(1, 3 * mm))

    header = [
        Paragraph("SENARYO",    S("th", fontSize=7, textColor=C["dim"], fontName="Helvetica-Bold", leading=10)),
        Paragraph("SKOR",       S("th2", fontSize=7, textColor=C["dim"], fontName="Helvetica-Bold", leading=10, alignment=TA_RIGHT)),
        Paragraph("BÖLGE",      S("th3", fontSize=7, textColor=C["dim"], fontName="Helvetica-Bold", leading=10)),
        Paragraph("EŞİK",       S("th4", fontSize=7, textColor=C["dim"], fontName="Helvetica-Bold", leading=10, alignment=TA_CENTER)),
        Paragraph("OLASILIK",   S("th5", fontSize=7, textColor=C["dim"], fontName="Helvetica-Bold", leading=10, alignment=TA_RIGHT)),
    ]
    rows = [header]
    for s in scores[:10]:
        col = _thr_color(s.get("threshold_level", 0))
        rows.append([
            Paragraph(s.get("scenario_name", "-"), S("sn", fontSize=9, textColor=col, leading=12)),
            Paragraph(f'{s.get("score", 0):.1f}', S("sv", fontSize=10, textColor=col, fontName="Helvetica-Bold", leading=12, alignment=TA_RIGHT)),
            Paragraph(s.get("region", "-"), S("sr", fontSize=8, textColor=C["dim"], leading=12)),
            Paragraph(f'L{s.get("threshold_level", 0)}', S("sl", fontSize=8, textColor=col, fontName="Helvetica-Bold", leading=12, alignment=TA_CENTER)),
            Paragraph(f'%{_prob(s.get("score", 0))}', S("sp", fontSize=8, textColor=C["dim"], leading=12, alignment=TA_RIGHT)),
        ])

    t = Table(rows, colWidths=[W_body * 0.38, W_body * 0.11, W_body * 0.22, W_body * 0.10, W_body * 0.19])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  colors.HexColor("#0a1a24")),
        ("BACKGROUND",    (0, 1), (-1, -1), C["panel"]),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [C["panel"], colors.HexColor("#081218")]),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 7),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 7),
        ("LINEBELOW",     (0, 0), (-1, 0),  0.5, C["border"]),
        ("LINEBELOW",     (0, 1), (-1, -2), 0.2, colors.HexColor("#0e2030")),
    ]))
    story.append(t)
    story.append(Spacer(1, 4 * mm))


def _section_signals(ctx, story):
    signals = ctx.get("signals", [])
    if not signals:
        return
    story.append(SectionBar("Ham Sinyal Verileri"))
    story.append(Spacer(1, 3 * mm))

    header = [
        Paragraph("KAYNAK",  S("th", fontSize=7, textColor=C["dim"], fontName="Helvetica-Bold", leading=10)),
        Paragraph("TİP",     S("th2", fontSize=7, textColor=C["dim"], fontName="Helvetica-Bold", leading=10)),
        Paragraph("BÖLGE",   S("th3", fontSize=7, textColor=C["dim"], fontName="Helvetica-Bold", leading=10)),
        Paragraph("DEĞER",   S("th4", fontSize=7, textColor=C["dim"], fontName="Helvetica-Bold", leading=10, alignment=TA_RIGHT)),
        Paragraph("ŞİDDET",  S("th5", fontSize=7, textColor=C["dim"], fontName="Helvetica-Bold", leading=10, alignment=TA_CENTER)),
    ]
    rows = [header]
    for s in signals[:12]:
        sev = s.get("severity", "low")
        col = _sev_color(sev)
        norm = s.get("normalized_value") or 0
        rows.append([
            Paragraph(s.get("source", "-"), S("src", fontSize=8, textColor=C["blue"], fontName="Courier", leading=11)),
            Paragraph(s.get("signal_type", "-"), S("sty", fontSize=8, textColor=C["text"], leading=11)),
            Paragraph(s.get("geography", "-"), S("sgeo", fontSize=8, textColor=C["dim"], leading=11)),
            Paragraph(f'{norm * 100:.0f}%', S("snv", fontSize=9, textColor=col, fontName="Helvetica-Bold", leading=12, alignment=TA_RIGHT)),
            Paragraph("●" if sev == "critical" else "▲" if sev == "warning" else "○",
                      S("ssev", fontSize=10, textColor=col, leading=12, alignment=TA_CENTER)),
        ])

    t = Table(rows, colWidths=[W_body * 0.20, W_body * 0.22, W_body * 0.28, W_body * 0.15, W_body * 0.15])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  colors.HexColor("#0a1a24")),
        ("BACKGROUND",    (0, 1), (-1, -1), C["panel"]),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [C["panel"], colors.HexColor("#081218")]),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 7),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 7),
        ("LINEBELOW",     (0, 0), (-1, 0),  0.5, C["border"]),
        ("LINEBELOW",     (0, 1), (-1, -2), 0.2, colors.HexColor("#0e2030")),
    ]))
    story.append(t)
    story.append(Spacer(1, 4 * mm))


def _section_features(ctx, story):
    features = ctx.get("features", [])
    if not features:
        return
    story.append(SectionBar("Sinyal Özellik Katmanı"))
    story.append(Spacer(1, 3 * mm))

    rows = []
    for f in features:
        val  = f.get("value", 0)
        conf = f.get("confidence", 0)
        col  = C["crit"] if val > 0.65 else C["warn"] if val > 0.45 else C["blue"]
        rows.append([
            Paragraph(f.get("feature_name", "-"), S("fn", fontSize=9, textColor=C["text"], leading=12)),
            Paragraph(f'{val * 100:.0f}%', S("fv", fontSize=10, textColor=col, fontName="Helvetica-Bold", leading=12, alignment=TA_RIGHT)),
            Paragraph(f'güven: {conf * 100:.0f}%', S("fc", fontSize=8, textColor=C["dim"], leading=12, alignment=TA_RIGHT)),
        ])

    t = Table(rows, colWidths=[W_body * 0.60, W_body * 0.18, W_body * 0.22])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), C["panel"]),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("LINEBELOW",     (0, 0), (-1, -2), 0.2, colors.HexColor("#0e2030")),
    ]))
    story.append(t)
    story.append(Spacer(1, 4 * mm))


def _section_predictions(ctx, story):
    preds = ctx.get("predictions", [])
    if not preds:
        return
    story.append(SectionBar("Tahmin Kaydı (Brier Takibi)"))
    story.append(Spacer(1, 3 * mm))

    header = [
        Paragraph("SENARYO / BÖLGE",  S("ph", fontSize=7, textColor=C["dim"], fontName="Helvetica-Bold", leading=10)),
        Paragraph("OLASILIK",         S("ph2", fontSize=7, textColor=C["dim"], fontName="Helvetica-Bold", leading=10, alignment=TA_CENTER)),
        Paragraph("UFUK",             S("ph3", fontSize=7, textColor=C["dim"], fontName="Helvetica-Bold", leading=10, alignment=TA_CENTER)),
        Paragraph("DURUM",            S("ph4", fontSize=7, textColor=C["dim"], fontName="Helvetica-Bold", leading=10, alignment=TA_CENTER)),
    ]
    rows = [header]
    for p in preds[:8]:
        prob  = p.get("probability", 0)
        pcol  = C["crit"] if prob > 0.75 else C["warn"] if prob > 0.55 else C["blue"]
        stat  = p.get("status", "pending")
        scol  = C["ok"] if stat == "verified" else C["warn"] if stat == "pending" else C["dim"]
        rows.append([
            Paragraph(f'{p.get("scenario_name","-")} / {p.get("region","-")}',
                      S("pn", fontSize=9, textColor=C["text"], leading=12)),
            Paragraph(f'%{int(prob * 100)}', S("pp", fontSize=10, textColor=pcol, fontName="Helvetica-Bold", leading=12, alignment=TA_CENTER)),
            Paragraph(f'{p.get("horizon_hours", 24)}s', S("ph5", fontSize=9, textColor=C["dim"], leading=12, alignment=TA_CENTER)),
            Paragraph(stat.upper(), S("ps", fontSize=8, textColor=scol, fontName="Helvetica-Bold", leading=12, alignment=TA_CENTER)),
        ])

    t = Table(rows, colWidths=[W_body * 0.52, W_body * 0.16, W_body * 0.12, W_body * 0.20])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  colors.HexColor("#0a1a24")),
        ("BACKGROUND",    (0, 1), (-1, -1), C["panel"]),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 7),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 7),
        ("LINEBELOW",     (0, 0), (-1, 0),  0.5, C["border"]),
        ("LINEBELOW",     (0, 1), (-1, -2), 0.2, colors.HexColor("#0e2030")),
    ]))
    story.append(t)
    story.append(Spacer(1, 4 * mm))


def _section_llm(llm_text, backend, report_type, story):
    if not llm_text or llm_text.startswith("["):
        return
    story.append(PageBreak())
    story.append(SectionBar(
        f"Analiz — {BACKEND_LABELS.get(backend, backend)}",
        TYPE_COLORS.get(report_type, "#00c8e8")
    ))
    story.append(Spacer(1, 3 * mm))

    llm_rows = []
    for para in llm_text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        llm_rows.append([Paragraph(para, S("llp", fontSize=9, textColor=C["text"], leading=15))])
        llm_rows.append([Spacer(1, 2 * mm)])

    t = Table(llm_rows, colWidths=[W_body])
    t.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), C["panel"]),
        ("TOPPADDING",   (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
        ("LEFTPADDING",  (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("LINEAFTER",    (0, 0), (0, -1),  2, colors.HexColor(TYPE_COLORS.get(report_type, "#00c8e8"))),
    ]))
    story.append(t)


def _footer(report_type, timestamp, story):
    story.append(Spacer(1, 4 * mm))
    story.append(HRFlowable(width=W_body, thickness=0.3, color=C["border"]))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(
        f'LOGOSiNT v2.0  ·  {TYPE_LABELS.get(report_type,"")}  ·  '
        f'{timestamp.strftime("%d %B %Y %H:%M UTC")}  ·  '
        f'Bu rapor otomatik üretilmiştir — nihai karar insana aittir.',
        S("ft", fontSize=7, textColor=C["dim"], alignment=TA_CENTER, leading=10)
    ))


# ── ANA FONKSİYON ─────────────────────────────────────────

def build_report_pdf(
    out_path:    Path,
    report_type: str,
    timestamp:   datetime,
    context:     dict,
    llm_text:    str   = "",
    backend:     str   = "ollama",
    extra:       dict  = None,
) -> Path:
    """
    Birleşik PDF rapor üretici.
    Tüm rapor tipleri (hourly/daily/weekly/monthly) aynı builder'ı kullanır.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=14*mm, rightMargin=14*mm,
        topMargin=12*mm,  bottomMargin=12*mm,
    )

    story = []

    _header(report_type, timestamp, backend, story)
    _status_bar(context, story)

    # Tipine göre içerik
    if report_type == "hourly":
        # Kısa: sadece top senaryolar + özellikler + LLM özet
        _section_scores(context, story)
        _section_features(context, story)
        _section_llm(llm_text, backend, report_type, story)

    elif report_type == "daily":
        # Kapsamlı: her şey
        _section_scores(context, story)
        _section_features(context, story)
        story.append(PageBreak())
        _section_signals(context, story)
        _section_predictions(context, story)
        _section_llm(llm_text, backend, report_type, story)

    elif report_type == "weekly":
        # Haftalık: trend + Substack taslağı
        _section_scores(context, story)
        _section_predictions(context, story)
        _section_llm(llm_text, backend, report_type, story)

    elif report_type == "monthly":
        # Aylık: her şey + kalibrasyon
        _section_scores(context, story)
        _section_features(context, story)
        _section_predictions(context, story)

        # Kalibrasyon kutusu
        if extra and "calibration" in extra:
            calib = extra["calibration"]
            story.append(SectionBar("Kalibrasyon İstatistikleri", "#cc88ff"))
            story.append(Spacer(1, 3*mm))
            cdata = [[
                Paragraph(f'Brier Skoru: <b>{calib.get("brier_score","—")}</b>',
                          S("cb", fontSize=10, textColor=C["text"], fontName="Helvetica-Bold", leading=14)),
                Paragraph(f'Doğruluk: <b>%{int((calib.get("accuracy",0))*100)}</b>',
                          S("ca", fontSize=10, textColor=C["ok"], fontName="Helvetica-Bold", leading=14, alignment=TA_CENTER)),
                Paragraph(f'Tahmin Sayısı: <b>{calib.get("count","—")}</b>',
                          S("cc", fontSize=10, textColor=C["dim"], leading=14, alignment=TA_RIGHT)),
            ]]
            ct = Table(cdata, colWidths=[W_body/3]*3)
            ct.setStyle(TableStyle([
                ("BACKGROUND",   (0,0),(-1,-1), C["panel"]),
                ("TOPPADDING",   (0,0),(-1,-1), 10),
                ("BOTTOMPADDING",(0,0),(-1,-1), 10),
                ("LEFTPADDING",  (0,0),(-1,-1), 12),
            ]))
            story.append(ct)
            story.append(Spacer(1, 4*mm))

        _section_llm(llm_text, backend, report_type, story)

    _footer(report_type, timestamp, story)

    doc.build(story)
    return out_path
