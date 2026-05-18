"""
logosint/analysis/llm_analyzer.py

LLM Analiz — Anthropic + Ollama hibrit, doğru iş bölümü.

OLLAMA (Llama 3.1 — yerel, ücretsiz, sürekli):
  - Saatlik otomatik rutin özet
  - Anomali alert yorumu
  - Bilgisayar açık olmalı

ANTHROPIC (Claude — internet, talep üzerine):
  - Sadece "Derin Analiz" butonuna basıldığında
  - Tüm veri katmanlarını sentezler:
      senaryo skorları + cascade + aktör analizi +
      GDELT events + uydu + tarihsel emsal
  - Çıktı Substack'a uygun kalite
  - Maliyet: ~$0.003-0.01 per analiz
"""
from __future__ import annotations
import json, logging, time
from datetime import datetime, timezone
from typing import Optional
log = logging.getLogger("LLMAnalyzer")

OLLAMA_SYSTEM = """Sen LOGOSİNT jeopolitik erken uyarı sisteminin rutin analiz asistanısın.
Saatlik anomali özetleri ve hızlı bölge yorumları üretirsin.
Kısa, net, Türkçe. 2-3 paragraf. Spekülatif olma."""

ANTHROPIC_SYSTEM = """Sen LOGOSİNT'in derin sentez motorusun.

Sana çok katmanlı ham istihbarat verisi geliyor:
- Fiziksel trafik anomalileri (hava + deniz)
- Aktör bazlı davranış (kim kaçıyor, kim kalıyor, kim birikiyor)
- GDELT event tablosu (CAMEO kodları, Goldstein, aktör çiftleri)
- Uydu ısı anomalileri (SentinelHub)
- Senaryo puanlama motoru (1800 ağırlık matrisi)
- Cascade origin (hangi bölge önce, nasıl yayıldı)
- Tarihsel vaka eşleştirmesi

Görevin:
1. Tüm katmanları bütünleşik anlatıya dönüştür
2. Fiziksel + bilgi sinyallerini çapraz doğrula
3. Aktör davranışından niyet oku
4. Tarihsel emsalle karşılaştır
5. Analist ve okuyucunun anlayacağı dilde yaz

Kurallar:
- Türkçe yaz
- Veriye dayan, speküle etme ama bağlam ekle
- Güven seviyeni belirt (yüksek/orta/düşük + neden)
- Çıktı Substack makalesine dönüştürülebilir kalitede
- 4-6 paragraf: durum → aktörler → sinyallerin anlamı → tarihsel bağlam → sonraki 24-48 saat"""


def build_deep_prompt(region: str, scan_id: Optional[str], hours: int) -> str:
    sections = [
        f"BÖLGE: {region.upper()}",
        f"ANALİZ PENCERESİ: Son {hours} saat",
        f"ZAMAN: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
    ]
    try:
        from logosint.repositories.feature_repo import get_scores, get_features, get_signals
        scores = get_scores(region=region, hours=hours, min_score=15, limit=15)
        if scores:
            sections.append("── SENARYO SKORLARI ──")
            for s in sorted(scores, key=lambda x: -x["score"])[:8]:
                bar = "█" * int(s["score"] / 10)
                sections.append(
                    f"  {s['scenario_name']}: {s['score']:.1f}/100 "
                    f"(%{int(s.get('probability',0)*100)} olasılık, "
                    f"L{s.get('threshold_level',0)}) {bar}"
                )
            sections.append("")

        features = get_features(region=region, hours=hours, limit=10)
        if features:
            sections.append("── SİNYAL ÖZELLİKLERİ ──")
            for f in features:
                if f["value"] > 0.2:
                    sections.append(
                        f"  {f['feature_name']}: {f['value']*100:.0f}% "
                        f"(güven: {f['confidence']*100:.0f}%)"
                    )
            sections.append("")

        signals = get_signals(geography=region, hours=hours, limit=20)
        if signals:
            sections.append("── HAM SİNYALLER (En Güçlü) ──")
            for s in sorted(signals, key=lambda x: -(x.get("normalized_value") or 0))[:8]:
                try:
                    kw = ", ".join(json.loads(s.get("keywords", "[]"))[:3])
                except Exception:
                    kw = ""
                sections.append(
                    f"  [{s['source']}] {s['signal_type']} | "
                    f"normalize: {(s.get('normalized_value') or 0)*100:.0f}% | "
                    f"şiddet: {s.get('severity','?')} | {kw}"
                )
            sections.append("")
    except Exception as e:
        sections.append(f"[Veri yükleme hatası: {e}]")
        sections.append("")

    try:
        import os, json as _j
        trained_dir = "cases/trained"
        if os.path.exists(trained_dir):
            sections.append("── TARİHSEL EMSAL ──")
            for fname in list(os.listdir(trained_dir))[:3]:
                try:
                    with open(f"{trained_dir}/{fname}") as f:
                        case = _j.load(f)
                    sections.append(
                        f"  {case.get('name','?')} ({case.get('event_date','?')}): "
                        f"peak {case.get('peak_spike','?')}x, "
                        f"lead {case.get('lead_time_days','?')}g"
                    )
                except Exception:
                    pass
            sections.append("")
    except Exception:
        pass

    sections += [
        "── ANALİZ İSTEĞİ ──",
        f"Yukarıdaki tüm veri katmanlarını {region} bölgesi için sentezle. "
        "Fiziksel sinyaller, aktör davranışı ve bilgi sinyalleri birbirini "
        "nasıl doğruluyor veya çelişiyor? Tarihsel emsalle karşılaştır. "
        "Sonraki 24-48 saatte izlenmesi gereken kritik sinyalleri listele.",
    ]
    return "\n".join(sections)


def build_routine_prompt(region: str, anomaly_count: int, top_scenario: str, top_score: float) -> str:
    return (
        f"{region.upper()} bölgesinde saatlik tarama tamamlandı.\n"
        f"Aktif anomali: {anomaly_count}\n"
        f"En yüksek senaryo: {top_scenario} ({top_score:.1f}/100)\n\n"
        "2-3 cümleyle mevcut durumu özetle. Ne izlenmeli?"
    )


class LLMAnalyzer:

    def __init__(self, config: dict = None):
        self.config          = config or {}
        self.anthropic_key   = self.config.get("anthropic_api_key", "")
        self.anthropic_model = self.config.get("anthropic_model", "claude-sonnet-4-20250514")
        self.ollama_url      = self.config.get("ollama_url", "http://localhost:11434")
        self.ollama_model    = self.config.get("ollama_model", "llama3.1:8b")
        self.max_tokens      = self.config.get("max_tokens", 1200)
        self.timeout         = self.config.get("timeout", 90)
        self._ollama_ok: Optional[bool] = None

    def routine_summary(self, region: str, anomaly_count: int = 0,
                        top_scenario: str = "", top_score: float = 0) -> dict:
        """Saatlik rutin — Ollama."""
        if not self._ollama_available():
            return {"backend": "none", "text": "[Ollama çevrimdışı]", "region": region}
        prompt = build_routine_prompt(region, anomaly_count, top_scenario, top_score)
        return {
            "backend":   "ollama",
            "model":     self.ollama_model,
            "region":    region,
            "text":      self._call_ollama(OLLAMA_SYSTEM, prompt),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def deep_analysis(self, region: str, scan_id: str = None, hours: int = 24) -> dict:
        """Derin sentez — Anthropic. Sadece talep üzerine."""
        if not self.anthropic_key:
            if self._ollama_available():
                prompt = build_deep_prompt(region, scan_id, hours)
                return {
                    "backend": "ollama_fallback",
                    "warning": "Anthropic key yok — Ollama kullanıldı (kalite düşük)",
                    "region":  region,
                    "text":    self._call_ollama(ANTHROPIC_SYSTEM, prompt),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            return {"backend": "none", "error": "LLM yok", "region": region}

        t0     = time.time()
        prompt = build_deep_prompt(region, scan_id, hours)
        text   = self._call_anthropic(prompt)
        elapsed = time.time() - t0
        est_tok = (len(prompt.split()) + len(text.split())) * 1.3
        return {
            "backend":      "anthropic",
            "model":        self.anthropic_model,
            "region":       region,
            "scan_id":      scan_id,
            "text":         text,
            "elapsed_s":    round(elapsed, 1),
            "est_tokens":   int(est_tok),
            "est_cost_usd": round(est_tok / 1000 * 0.003, 4),
            "timestamp":    datetime.now(timezone.utc).isoformat(),
        }

    def weekly_substack(self, days: int = 7) -> dict:
        """Haftalık Substack taslağı — Anthropic."""
        if not self.anthropic_key:
            return {"error": "Anthropic key gerekli"}
        try:
            from logosint.repositories.feature_repo import get_heatmap, get_scores
            heatmap = get_heatmap(hours=days * 24)
            scores  = get_scores(hours=days * 24, min_score=40, limit=30)
        except Exception:
            heatmap, scores = [], []

        top_r = "\n".join(f"  - {r['region']}: max={r['max_score']:.1f}" for r in heatmap[:6]) or "  Veri yok"
        from collections import defaultdict
        sm: dict[str, float] = defaultdict(float)
        for s in scores:
            sm[s["scenario_name"]] = max(sm[s["scenario_name"]], s["score"])
        top_s = "\n".join(f"  - {n}: {v:.1f}" for n, v in sorted(sm.items(), key=lambda x: -x[1])[:5]) or "  Veri yok"

        prompt = (
            f"LOGOSİNT'in son {days} günlük verisi:\n\n"
            f"EN AKTİF BÖLGELER:\n{top_r}\n\n"
            f"EN YÜKSEK SENARYO SKORLARI:\n{top_s}\n\n"
            "Bu verilere dayanarak Substack için haftalık jeopolitik bülten yaz. "
            "Başlık, giriş, bölge bazlı analiz, öne çıkan riskler, sonuç. "
            "Okuyucu: jeopolitikle ilgilenen ama uzman olmayan. "
            "Türkçe, akıcı, 500-700 kelime."
        )
        return {
            "backend":   "anthropic",
            "days":      days,
            "text":      self._call_anthropic(prompt),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _call_anthropic(self, user_prompt: str) -> str:
        try:
            import requests
            r = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key":        self.anthropic_key,
                    "anthropic-version": "2023-06-01",
                    "content-type":      "application/json",
                },
                json={
                    "model":      self.anthropic_model,
                    "max_tokens": self.max_tokens,
                    "system":     ANTHROPIC_SYSTEM,
                    "messages":   [{"role": "user", "content": user_prompt}],
                },
                timeout=self.timeout,
            )
            r.raise_for_status()
            return r.json()["content"][0]["text"]
        except Exception as e:
            log.error("Anthropic: %s", e)
            return f"[Anthropic hata: {e}]"

    def _call_ollama(self, system: str, user_prompt: str) -> str:
        try:
            import requests
            r = requests.post(
                f"{self.ollama_url}/api/generate",
                json={"model": self.ollama_model,
                      "prompt": f"{system}\n\n{user_prompt}",
                      "stream": False, "options": {"num_predict": 600}},
                timeout=60,
            )
            r.raise_for_status()
            return r.json().get("response", "[Boş yanıt]")
        except Exception as e:
            log.error("Ollama: %s", e)
            return f"[Ollama hata: {e}]"

    def _ollama_available(self) -> bool:
        if self._ollama_ok is not None:
            return self._ollama_ok
        try:
            import requests
            self._ollama_ok = requests.get(f"{self.ollama_url}/api/tags", timeout=2).status_code == 200
        except Exception:
            self._ollama_ok = False
        return self._ollama_ok

    @property
    def status(self) -> dict:
        return {
            "anthropic_configured": bool(self.anthropic_key),
            "anthropic_model":      self.anthropic_model,
            "ollama_available":     self._ollama_available(),
            "ollama_model":         self.ollama_model,
            "mode": (
                "full"           if self.anthropic_key and self._ollama_available() else
                "anthropic_only" if self.anthropic_key else
                "ollama_only"    if self._ollama_available() else
                "none"
            ),
        }


def register_llm_routes(blueprint, config: dict = None):
    from flask import request, jsonify
    analyzer = LLMAnalyzer(config or {})

    @blueprint.route("/analyze/deep")
    def deep_analysis():
        region  = request.args.get("region")
        scan_id = request.args.get("scan_id")
        hours   = int(request.args.get("hours", 24))
        if not region:
            return jsonify({"status": "error", "message": "region gerekli"}), 400
        try:
            return jsonify({"status": "ok", "data": analyzer.deep_analysis(region, scan_id, hours)})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @blueprint.route("/analyze/routine")
    def routine():
        region = request.args.get("region", "global")
        try:
            from logosint.repositories.feature_repo import get_scores
            sc = get_scores(region=region, hours=2, min_score=20, limit=1)
            top = sc[0] if sc else {}
            return jsonify({"status": "ok", "data": analyzer.routine_summary(
                region=region, anomaly_count=len(sc),
                top_scenario=top.get("scenario_name",""),
                top_score=top.get("score",0),
            )})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @blueprint.route("/analyze/weekly")
    def weekly():
        try:
            return jsonify({"status": "ok", "data": analyzer.weekly_substack(
                int(request.args.get("days", 7))
            )})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @blueprint.route("/analyze/status")
    def llm_status():
        return jsonify({"status": "ok", "data": analyzer.status})
