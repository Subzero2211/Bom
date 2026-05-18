"""
logosint/reports/report_scheduler.py

Rapor zamanlayıcısı:
  - Saatlik   → Llama (otomatik, ücretsiz)
  - 4x günlük → Claude (06/12/18/00 UTC, son 4 saatin raporlarını sentezler)
  - Haftalık  → Claude (Pazartesi 06:00 UTC)
  - Aylık     → Claude (1. gün 06:00 UTC)

Tüm raporlar reports/ klasörüne yazılır:
  reports/
    hourly/   YYYY-MM-DD_HH00_hourly.pdf  (+ .txt özet)
    daily/    YYYY-MM-DD_HHMM_daily.pdf
    weekly/   YYYY-WXX_weekly.pdf
    monthly/  YYYY-MM_monthly.pdf
    index.json
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

log = logging.getLogger("ReportScheduler")

REPORTS_DIR = Path("reports")


# ═══════════════════════════════════════════════════════════
# DİZİN YAPISI
# ═══════════════════════════════════════════════════════════

def ensure_dirs():
    for sub in ("hourly", "daily", "weekly", "monthly"):
        (REPORTS_DIR / sub).mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════
# INDEX — raporların listesi
# ═══════════════════════════════════════════════════════════

def load_index() -> dict:
    idx_path = REPORTS_DIR / "index.json"
    if idx_path.exists():
        try:
            return json.loads(idx_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"reports": []}


def save_index(idx: dict):
    idx_path = REPORTS_DIR / "index.json"
    idx_path.write_text(json.dumps(idx, indent=2, ensure_ascii=False), encoding="utf-8")


def register_report(rtype: str, path: str, ts: datetime, meta: dict = None):
    idx = load_index()
    idx["reports"].append({
        "type":      rtype,
        "path":      str(path),
        "timestamp": ts.isoformat(),
        "meta":      meta or {},
    })
    # Son 500 kaydı tut
    idx["reports"] = idx["reports"][-500:]
    save_index(idx)


# ═══════════════════════════════════════════════════════════
# RAPOR İÇERİĞİ TOPLAMA
# ═══════════════════════════════════════════════════════════

def collect_scan_context(hours: int = 1) -> dict:
    """DB'den son N saatteki veriyi topla."""
    try:
        from logosint.repositories.feature_repo import (
            get_scores, get_heatmap, get_features,
            get_signals, get_predictions
        )
        return {
            "scores":      get_scores(hours=hours, min_score=15, limit=30),
            "heatmap":     get_heatmap(hours=hours),
            "features":    get_features(hours=hours, limit=10),
            "signals":     get_signals(hours=hours, limit=20),
            "predictions": get_predictions(hours=hours, limit=10),
        }
    except Exception as e:
        log.error("Context toplama hatası: %s", e)
        return {}


def read_recent_hourly_reports(n: int = 4) -> list[str]:
    """Son N saatlik rapor metnini oku (Llama özetleri)."""
    idx = load_index()
    hourly = [r for r in idx["reports"] if r["type"] == "hourly"]
    recent = sorted(hourly, key=lambda r: r["timestamp"], reverse=True)[:n]
    texts = []
    for r in recent:
        txt_path = Path(r["path"]).with_suffix(".txt")
        if txt_path.exists():
            texts.append(txt_path.read_text(encoding="utf-8"))
    return texts


# ═══════════════════════════════════════════════════════════
# LLAMA — SAATLIK RAPOR
# ═══════════════════════════════════════════════════════════

def generate_hourly_report(now: datetime) -> Optional[Path]:
    """
    Llama ile saatlik özet üret.
    Çıktı: TXT özet + PDF rapor.
    """
    from logosint.analysis.llm_analyzer import LLMAnalyzer
    from logosint.reports.pdf_builder import build_report_pdf

    try:
        from config import OLLAMA
        llm = LLMAnalyzer({"ollama_url": OLLAMA.get("url","http://localhost:11434"),
                           "ollama_model": OLLAMA.get("model","llama3.1:8b")})
    except ImportError:
        llm = LLMAnalyzer({})

    ctx = collect_scan_context(hours=1)
    scores = ctx.get("scores", [])
    top = scores[0] if scores else {}
    critC = sum(1 for s in scores if s.get("threshold_level",0) >= 3)
    warnC = sum(1 for s in scores if s.get("threshold_level",0) == 2)

    # Llama özet
    result = llm.routine_summary(
        region         = top.get("region", "global"),
        anomaly_count  = critC + warnC,
        top_scenario   = top.get("scenario_name", ""),
        top_score      = top.get("score", 0),
    )
    summary_text = result.get("text", "[Llama çevrimdışı]")

    # Dosya yolları
    ts_str   = now.strftime("%Y-%m-%d_%H%M")
    txt_path = REPORTS_DIR / "hourly" / f"{ts_str}_hourly.txt"
    pdf_path = REPORTS_DIR / "hourly" / f"{ts_str}_hourly.pdf"

    # TXT kaydet
    full_text = (
        f"LOGOSiNT SAATLIK RAPOR\n"
        f"Zaman: {now.strftime('%d %B %Y  %H:%M UTC')}\n"
        f"Backend: {result.get('backend','?')}\n"
        f"{'─'*60}\n\n"
        f"{summary_text}\n\n"
        f"{'─'*60}\n"
        f"Top senaryo: {top.get('scenario_name','-')} → {top.get('score',0):.1f}/100\n"
        f"Kritik: {critC}  Uyarı: {warnC}  İşlenen sinyal: {len(ctx.get('signals',[]))}\n"
    )
    txt_path.write_text(full_text, encoding="utf-8")

    # PDF üret
    try:
        build_report_pdf(
            out_path    = pdf_path,
            report_type = "hourly",
            timestamp   = now,
            context     = ctx,
            llm_text    = summary_text,
            backend     = result.get("backend","ollama"),
        )
    except Exception as e:
        log.error("Saatlik PDF hatası: %s", e)

    register_report("hourly", str(pdf_path), now, {
        "top_scenario": top.get("scenario_name",""),
        "top_score":    top.get("score",0),
        "critC": critC, "warnC": warnC,
    })
    log.info("Saatlik rapor: %s", pdf_path.name)
    return pdf_path


# ═══════════════════════════════════════════════════════════
# CLAUDE — GÜNLÜK KAPSAMLI RAPOR (4x)
# ═══════════════════════════════════════════════════════════

def generate_daily_report(now: datetime) -> Optional[Path]:
    """
    Claude ile günlük derin rapor.
    Son 4 saatlik Llama özetlerini + son 4 saatin verisini alır, sentezler.
    """
    from logosint.analysis.llm_analyzer import LLMAnalyzer
    from logosint.reports.pdf_builder import build_report_pdf

    try:
        from config import ANTHROPIC, OLLAMA
        llm = LLMAnalyzer({
            "anthropic_api_key": ANTHROPIC.get("api_key",""),
            "anthropic_model":   ANTHROPIC.get("model","claude-sonnet-4-20250514"),
            "ollama_url":        OLLAMA.get("url","http://localhost:11434"),
            "ollama_model":      OLLAMA.get("model","llama3.1:8b"),
        })
    except ImportError:
        llm = LLMAnalyzer({})

    ctx = collect_scan_context(hours=4)
    recent_texts = read_recent_hourly_reports(n=4)

    # Claude prompt'una son 4 saatlik Llama özetlerini ekle
    hourly_summaries = "\n\n".join([
        f"[{i+1}. SAAT ÖZETİ]\n{t}" for i, t in enumerate(recent_texts)
    ]) if recent_texts else "Llama özeti mevcut değil."

    # Derin analiz
    from logosint.analysis.llm_analyzer import build_deep_prompt, ANTHROPIC_SYSTEM
    base_prompt = build_deep_prompt("global", None, 4)
    full_prompt = (
        f"{base_prompt}\n\n"
        f"── SON 4 SAATLIK LLAMA ÖZETLERİ ──\n{hourly_summaries}\n\n"
        "Yukarıdaki saatlik özetleri ve verileri entegre ederek 4 saatlik kapsamlı analiz yaz."
    )

    if llm.anthropic_key:
        text = llm._call_anthropic(full_prompt)
        backend = "anthropic"
    elif llm._ollama_available():
        text = llm._call_ollama(ANTHROPIC_SYSTEM, full_prompt)
        backend = "ollama_fallback"
    else:
        text = "[LLM yok — analiz üretilemiyor]"
        backend = "none"

    ts_str   = now.strftime("%Y-%m-%d_%H%M")
    txt_path = REPORTS_DIR / "daily" / f"{ts_str}_daily.txt"
    pdf_path = REPORTS_DIR / "daily" / f"{ts_str}_daily.pdf"

    txt_path.write_text(
        f"LOGOSiNT GÜNLÜK RAPOR ({now.strftime('%H:%M UTC')})\n"
        f"Zaman: {now.strftime('%d %B %Y %H:%M UTC')}\n"
        f"Backend: {backend}\n{'─'*60}\n\n{text}\n",
        encoding="utf-8"
    )

    try:
        build_report_pdf(
            out_path    = pdf_path,
            report_type = "daily",
            timestamp   = now,
            context     = ctx,
            llm_text    = text,
            backend     = backend,
        )
    except Exception as e:
        log.error("Günlük PDF hatası: %s", e)

    register_report("daily", str(pdf_path), now, {"backend": backend})
    log.info("Günlük rapor: %s", pdf_path.name)
    return pdf_path


# ═══════════════════════════════════════════════════════════
# CLAUDE — HAFTALIK RAPOR
# ═══════════════════════════════════════════════════════════

def generate_weekly_report(now: datetime) -> Optional[Path]:
    """Pazartesi 06:00 UTC — 7 günlük Substack taslağı."""
    from logosint.analysis.llm_analyzer import LLMAnalyzer
    from logosint.reports.pdf_builder import build_report_pdf

    try:
        from config import ANTHROPIC, OLLAMA
        llm = LLMAnalyzer({
            "anthropic_api_key": ANTHROPIC.get("api_key",""),
            "ollama_url": OLLAMA.get("url","http://localhost:11434"),
        })
    except ImportError:
        llm = LLMAnalyzer({})

    ctx = collect_scan_context(hours=168)   # 7 gün

    # Son 4 günlük raporları da topla
    idx = load_index()
    daily_reports = [r for r in idx["reports"] if r["type"]=="daily"]
    recent_daily  = sorted(daily_reports, key=lambda r: r["timestamp"], reverse=True)[:8]
    daily_texts   = []
    for r in recent_daily:
        p = Path(r["path"]).with_suffix(".txt")
        if p.exists():
            daily_texts.append(p.read_text(encoding="utf-8")[:800])

    result = llm.weekly_substack(days=7)
    weekly_text = result.get("text","[Haftalık analiz üretilemedi]")

    if daily_texts:
        weekly_text = (
            weekly_text +
            "\n\n── HAFTALIK VERİ ALTYAPISI ──\n" +
            "\n---\n".join(daily_texts[:4])
        )

    week_str = now.strftime("%Y-W%W")
    txt_path = REPORTS_DIR / "weekly" / f"{week_str}_weekly.txt"
    pdf_path = REPORTS_DIR / "weekly" / f"{week_str}_weekly.pdf"

    txt_path.write_text(
        f"LOGOSiNT HAFTALIK RAPOR — {week_str}\n"
        f"Üretildi: {now.strftime('%d %B %Y %H:%M UTC')}\n{'─'*60}\n\n{weekly_text}\n",
        encoding="utf-8"
    )

    try:
        build_report_pdf(
            out_path    = pdf_path,
            report_type = "weekly",
            timestamp   = now,
            context     = ctx,
            llm_text    = weekly_text,
            backend     = result.get("backend","?"),
        )
    except Exception as e:
        log.error("Haftalık PDF hatası: %s", e)

    register_report("weekly", str(pdf_path), now, {"week": week_str})
    log.info("Haftalık rapor: %s", pdf_path.name)
    return pdf_path


# ═══════════════════════════════════════════════════════════
# CLAUDE — AYLIK RAPOR
# ═══════════════════════════════════════════════════════════

def generate_monthly_report(now: datetime) -> Optional[Path]:
    """Ayın 1'i 06:00 UTC — trend analizi + kalibrasyon."""
    from logosint.analysis.llm_analyzer import LLMAnalyzer
    from logosint.reports.pdf_builder import build_report_pdf
    from logosint.repositories.feature_repo import compute_calibration_stats

    try:
        from config import ANTHROPIC, OLLAMA
        llm = LLMAnalyzer({
            "anthropic_api_key": ANTHROPIC.get("api_key",""),
            "ollama_url": OLLAMA.get("url","http://localhost:11434"),
        })
    except ImportError:
        llm = LLMAnalyzer({})

    ctx   = collect_scan_context(hours=720)  # 30 gün
    calib = compute_calibration_stats()

    # Haftalık raporları topla
    idx = load_index()
    weekly_reps = [r for r in idx["reports"] if r["type"]=="weekly"]
    recent_weekly = sorted(weekly_reps, key=lambda r: r["timestamp"], reverse=True)[:4]
    weekly_texts = []
    for r in recent_weekly:
        p = Path(r["path"]).with_suffix(".txt")
        if p.exists():
            weekly_texts.append(p.read_text(encoding="utf-8")[:1000])

    prompt = (
        f"LOGOSiNT {now.strftime('%B %Y')} aylık değerlendirmesi:\n\n"
        f"Kalibrasyon: {json.dumps(calib, ensure_ascii=False)}\n\n"
        f"Son haftalık raporlar:\n" +
        "\n---\n".join(weekly_texts[:4]) +
        "\n\nAylık jeopolitik trend raporu yaz. Hangi senaryolar yükseldi? "
        "Sistem ne kadar doğru tahmin etti? Önümüzdeki ay ne izlenmeli?"
    )

    if llm.anthropic_key:
        monthly_text = llm._call_anthropic(prompt)
        backend = "anthropic"
    else:
        monthly_text = "[Anthropic key gerekli — aylık rapor üretilemedi]"
        backend = "none"

    month_str = now.strftime("%Y-%m")
    txt_path = REPORTS_DIR / "monthly" / f"{month_str}_monthly.txt"
    pdf_path = REPORTS_DIR / "monthly" / f"{month_str}_monthly.pdf"

    txt_path.write_text(
        f"LOGOSiNT AYLIK RAPOR — {month_str}\n"
        f"Üretildi: {now.strftime('%d %B %Y %H:%M UTC')}\n"
        f"Kalibrasyon: {calib}\n{'─'*60}\n\n{monthly_text}\n",
        encoding="utf-8"
    )

    try:
        build_report_pdf(
            out_path    = pdf_path,
            report_type = "monthly",
            timestamp   = now,
            context     = ctx,
            llm_text    = monthly_text,
            backend     = backend,
            extra        = {"calibration": calib},
        )
    except Exception as e:
        log.error("Aylık PDF hatası: %s", e)

    register_report("monthly", str(pdf_path), now, {"month": month_str, "calibration": calib})
    log.info("Aylık rapor: %s", pdf_path.name)
    return pdf_path


# ═══════════════════════════════════════════════════════════
# ZAMANLAYICI
# ═══════════════════════════════════════════════════════════

DAILY_REPORT_HOURS = {6, 12, 18, 0}   # UTC saat başlarında


class ReportScheduler:
    """
    Ana zamanlayıcı — her dakika kontrol eder, zamanı gelen raporu üretir.
    """

    def __init__(self):
        self._running   = False
        self._thread: Optional[threading.Thread] = None
        self._last_hourly:  Optional[str] = None   # "YYYY-MM-DD-HH"
        self._last_daily:   Optional[str] = None   # "YYYY-MM-DD-HH"
        self._last_weekly:  Optional[str] = None   # "YYYY-WXX"
        self._last_monthly: Optional[str] = None   # "YYYY-MM"

    def start(self):
        ensure_dirs()
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="ReportScheduler", daemon=True)
        self._thread.start()
        log.info("Rapor zamanlayıcısı başladı")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self):
        # İlk başlatmada 2 dakika bekle (sistem otursun)
        time.sleep(120)
        while self._running:
            try:
                self._check(datetime.now(timezone.utc))
            except Exception as e:
                log.error("Rapor döngüsü hata: %s", e)
            time.sleep(60)  # Her dakika kontrol

    def _check(self, now: datetime):
        hour_key   = now.strftime("%Y-%m-%d-%H")
        daily_key  = f"{now.strftime('%Y-%m-%d')}-{now.hour}"
        week_key   = now.strftime("%Y-W%W")
        month_key  = now.strftime("%Y-%m")

        # Saatlik — her saat başı
        if now.minute < 5 and self._last_hourly != hour_key:
            self._last_hourly = hour_key
            log.info("Saatlik rapor başlıyor: %s", hour_key)
            threading.Thread(target=generate_hourly_report, args=(now,), daemon=True).start()

        # Günlük — 06/12/18/00 UTC
        if now.hour in DAILY_REPORT_HOURS and now.minute < 5 and self._last_daily != daily_key:
            self._last_daily = daily_key
            log.info("Günlük rapor başlıyor: %s:00 UTC", now.hour)
            threading.Thread(target=generate_daily_report, args=(now,), daemon=True).start()

        # Haftalık — Pazartesi 06:00 UTC
        if now.weekday() == 0 and now.hour == 6 and now.minute < 5 and self._last_weekly != week_key:
            self._last_weekly = week_key
            log.info("Haftalık rapor başlıyor: %s", week_key)
            threading.Thread(target=generate_weekly_report, args=(now,), daemon=True).start()

        # Aylık — Ayın 1'i 06:00 UTC
        if now.day == 1 and now.hour == 6 and now.minute < 5 and self._last_monthly != month_key:
            self._last_monthly = month_key
            log.info("Aylık rapor başlıyor: %s", month_key)
            threading.Thread(target=generate_monthly_report, args=(now,), daemon=True).start()

    def trigger(self, rtype: str = "hourly") -> str:
        """Manuel tetikleme."""
        now = datetime.now(timezone.utc)
        fns = {
            "hourly":  generate_hourly_report,
            "daily":   generate_daily_report,
            "weekly":  generate_weekly_report,
            "monthly": generate_monthly_report,
        }
        fn = fns.get(rtype)
        if not fn:
            return f"Bilinmeyen rapor tipi: {rtype}"
        t = threading.Thread(target=fn, args=(now,), daemon=True)
        t.start()
        return f"{rtype} raporu başlatıldı"

    @property
    def status(self) -> dict:
        return {
            "running":        self._running,
            "last_hourly":    self._last_hourly,
            "last_daily":     self._last_daily,
            "last_weekly":    self._last_weekly,
            "last_monthly":   self._last_monthly,
            "reports_dir":    str(REPORTS_DIR.absolute()),
        }


# Singleton
_scheduler = ReportScheduler()

def get_report_scheduler() -> ReportScheduler:
    return _scheduler
