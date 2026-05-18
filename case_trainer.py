"""
case_trainer.py — Senaryo Öğretme Mekanizması

GDELT'ten ham imza çeker, sana sorar, sen yorumlarsın.
Her onaylanan vaka interpreter.py'nin pattern matching'ine eklenir.

Workflow:
    python case_trainer.py

    1. Predefined vakalar için otomatik GDELT çekimi
    2. Her vakayı sana gösterir:
       - Ham haber sayıları (pencere bazlı)
       - Baskın temalar
       - Goldstein ton skoru
       - Örnek başlıklar
    3. Sen şunları girersin:
       - Doğru senaryo tipi (askeri mi, diplomatik mi, vs.)
       - Hangi sinyaller gerçekten öncüydü
       - Alternatif açıklamalar
       - Güven skoru
    4. İşlenmiş vaka cases/ klasörüne yazılır
    5. interpreter.py bir sonraki çalışmada bunu kullanır

WL = Weak Labeling: GDELT ham sinyal üretir, insan etiketi koyar.
Zamanla etiketli vaka sayısı arttıkça sistem daha isabetli hale gelir.
"""

import json
import time
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from textwrap import indent, wrap

from case_builder import CaseBuilder, PREDEFINED_CASES, _make_id, gdelt_query
from analysis.interpreter import SCENARIO_PATTERNS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("Trainer")

CASES_DIR = Path("cases")
TRAINED_DIR = Path("cases/trained")


# ═══════════════════════════════════════════════════════════════
# GÖRÜNTÜLEME YARDIMCILARI
# ═══════════════════════════════════════════════════════════════

def clear():
    os.system("cls" if os.name == "nt" else "clear")


def hr(char="═", width=70):
    print(char * width)


def section(title: str):
    hr()
    print(f"  {title}")
    hr()


def wrap_print(text: str, width=68, indent_str="  "):
    for line in wrap(text, width):
        print(indent_str + line)


def color(text: str, code: str) -> str:
    """Terminal renk kodu — Windows'ta çalışmayabilir."""
    codes = {
        "red": "\033[91m", "green": "\033[92m", "yellow": "\033[93m",
        "blue": "\033[94m", "cyan": "\033[96m", "bold": "\033[1m",
        "reset": "\033[0m",
    }
    return f"{codes.get(code, '')}{text}{codes['reset']}"


# ═══════════════════════════════════════════════════════════════
# VAKA GÖSTERİMİ
# ═══════════════════════════════════════════════════════════════

def display_case_summary(case: dict):
    """Vakayı terminal'de okunabilir şekilde göster."""
    clear()
    section(f"VAKA: {case['name']}  ({case['event_date']})")

    print(f"\n  Ülkeler  : {', '.join(case.get('countries', []))}")
    print(f"  Bölgeler : {', '.join(case.get('regions', []))}")
    print(f"  Notlar   : {case.get('notes', '—')}\n")

    # Pencere sayıları
    hr("-")
    print("  HABER YOĞUNLUĞU (pencere bazlı)")
    hr("-")
    counts = case.get("window_counts", {})
    spikes = case.get("spikes", {})
    baseline = counts.get("30_gun_once", 1)

    for label, count in counts.items():
        spike = spikes.get(label, 0)
        bar   = "█" * min(40, int(spike * 5))
        spike_str = f"{spike:.1f}x"
        flag  = ""
        if label in ("3_gun_once", "1_gun_once", "olay_gunu"):
            flag = color(" ◄ KRİTİK PENCERE", "yellow")
        c = "red" if spike >= 5 else "yellow" if spike >= 2.5 else "green"
        print(f"  {label:20} {count:4d}  {color(spike_str, c):8}  {bar}{flag}")

    print(f"\n  Baseline (30 gün öncesi): {baseline} haber")
    print(f"  Peak spike: {case.get('peak_window','?')} → {case.get('peak_spike',0):.1f}x\n")

    # Ton
    hr("-")
    print("  TON ANALİZİ (Goldstein Skalası: -10 şiddet ↔ +10 işbirliği)")
    hr("-")
    pre  = case.get("pre_tone", 0)
    post = case.get("post_tone", 0)
    tone_shift = case.get("tone_shift", 0)
    tone_c = "red" if tone_shift < -1 else "green" if tone_shift > 1 else "yellow"
    print(f"  Olay öncesi : {pre:+.2f}")
    print(f"  Olay sonrası: {post:+.2f}")
    print(f"  Değişim     : {color(f'{tone_shift:+.2f}', tone_c)}\n")

    # Öncü temalar
    hr("-")
    print("  ÖNE ÇIKAN TEMALAR (olay öncesi 7 gün)")
    hr("-")
    for i, t in enumerate(case.get("pre_event_themes", [])[:10], 1):
        print(f"  {i:2}. {t}")

    # Yeni post temalar
    new_themes = case.get("new_post_themes", [])
    if new_themes:
        print(f"\n  OLAY SONRASI YENİ TEMALAR:")
        for t in new_themes[:5]:
            print(f"       + {color(t, 'cyan')}")

    # Örnek başlıklar
    details = case.get("window_details", {})
    peak_w  = case.get("peak_window", "3_gun_once")
    samples = details.get(peak_w, {}).get("sample_titles", [])
    if samples:
        print(f"\n  ÖRNEK BAŞLIKLAR ({peak_w}):")
        for s in samples[:5]:
            print(f"  • {s[:90]}")

    # Otomatik tahmin
    sig = case.get("signal_signature", {})
    print(f"\n  OTOMATİK TAHMİN:")
    print(f"  Pattern : {color(sig.get('inferred_pattern','?'), 'cyan')}")
    print(f"  Yoğunluk: {color(sig.get('intensity','?'), 'yellow')}")
    print(f"  Erken uyarı: {'✓ VAR' if sig.get('early_warning') else '✗ YOK'}\n")


# ═══════════════════════════════════════════════════════════════
# ETİKETLEME DİYALOĞU
# ═══════════════════════════════════════════════════════════════

def ask_labeling(case: dict) -> dict | None:
    """
    Kullanıcıdan etiket al.
    Döndürür: güncellenmiş vaka dict'i veya None (atla).
    """
    hr("─")
    print("\n  ETIKETLEME — Bu vakayı yorumla\n")

    # 1. Doğru pattern seç
    print("  Mevcut senaryo tipleri:")
    for i, p in enumerate(SCENARIO_PATTERNS, 1):
        print(f"  {i:2}. {p['id']:35} {p['name']}")
    print(f"  {len(SCENARIO_PATTERNS)+1:2}. Hiçbiri / Bilinmiyor")
    print(f"   0. Bu vakayı atla\n")

    auto_pattern = case.get("signal_signature", {}).get("inferred_pattern", "")
    auto_idx = next(
        (i+1 for i, p in enumerate(SCENARIO_PATTERNS) if p["id"] == auto_pattern),
        None,
    )
    hint = f"[otomatik tahmin: {auto_idx} — {auto_pattern}]" if auto_idx else ""
    choice_str = input(f"  Senaryo seç (1-{len(SCENARIO_PATTERNS)+1}, 0=atla) {hint}: ").strip()

    if choice_str == "0":
        print("  → Atlandı.")
        return None

    try:
        choice = int(choice_str)
    except ValueError:
        choice = auto_idx or (len(SCENARIO_PATTERNS) + 1)

    if 1 <= choice <= len(SCENARIO_PATTERNS):
        pattern_id   = SCENARIO_PATTERNS[choice - 1]["id"]
        pattern_name = SCENARIO_PATTERNS[choice - 1]["name"]
    else:
        pattern_id   = "unknown"
        pattern_name = "Bilinmiyor"

    print(f"\n  Seçilen: {color(pattern_name, 'cyan')}\n")

    # 2. Öncü sinyaller
    print("  HANGİ SINYALLER GERCEKTEN ÖNCÜYDÜ?")
    print("  (Virgülle ayır, boş bırakabilirsin)")
    print("  Örnek: 'haber spike 7 gün öncesi, ton düşüşü 3 gün öncesi, uçuş azalması'")
    precursor_raw = input("  Öncü sinyaller: ").strip()
    precursors = [p.strip() for p in precursor_raw.split(",") if p.strip()]

    # 3. Öncü süre
    lead_time_str = input("  Kaç gün öncesinden sinyal verdi? (boş = otomatik): ").strip()
    try:
        lead_time = int(lead_time_str)
    except ValueError:
        lead_time = case.get("lead_time_days", 7)

    # 4. Yanıltıcı sinyaller
    print("\n  YANILTICI/GÜRÜLTÜLÜ SİNYALLER VAR MI?")
    print("  (Bu dönemde başka olaylar haber spike'ını etkiledi mi?)")
    noise_raw = input("  Gürültü kaynakları (boş=yok): ").strip()
    noise = [n.strip() for n in noise_raw.split(",") if n.strip()]

    # 5. Alternatif açıklamalar
    print("\n  ALTERNATİF AÇIKLAMALAR?")
    print("  Bu imzanın başka bir nedeni olabilir miydi?")
    alt_raw = input("  Alternatif (boş=yok): ").strip()
    alternatives = [{"scenario": a.strip(), "confidence": 0.20} for a in alt_raw.split(",") if a.strip()]

    # 6. Fiziksel veri (opsiyonel)
    print("\n  FİZİKSEL VERİ (opsiyonel — biliyorsan gir)")
    print("  Örnek hava: LTFM:-0.15,LLBG:+0.40")
    air_raw  = input("  Hava trafiği değişimleri: ").strip()
    sea_raw  = input("  Deniz trafiği değişimleri: ").strip()

    def parse_delta(raw: str) -> dict:
        result = {}
        for item in raw.split(","):
            if ":" in item:
                k, v = item.split(":", 1)
                try:
                    result[k.strip()] = float(v.strip())
                except ValueError:
                    pass
        return result

    # 7. Sonuç
    outcome = input("\n  Olayın sonucu neydi? (kısa): ").strip()

    # 8. Güven skoru
    conf_str = input("  Bu etiketin güven skoru (0.0-1.0, boş=0.75): ").strip()
    try:
        confidence = float(conf_str)
    except ValueError:
        confidence = 0.75

    # 9. Ek not
    extra_note = input("\n  Ek not (boş=yok): ").strip()

    # Vakayı güncelle
    label = {
        "pattern_type":          pattern_id,
        "pattern_name":          pattern_name,
        "labeled_by":            "human",
        "labeled_at":            datetime.utcnow().isoformat(),
        "true_precursor_signals": precursors,
        "lead_time_days":        lead_time,
        "noise_sources":         noise,
        "alternatives":          alternatives,
        "physical_signals": {
            "air": parse_delta(air_raw),
            "sea": parse_delta(sea_raw),
        },
        "outcome":               outcome,
        "confidence_in_label":   confidence,
        "extra_note":            extra_note,
    }

    # Eşleştirme eşiklerini güncelle
    matching = {
        "pattern_type":        pattern_id,
        "min_spike_ratio":     max(1.5, case.get("peak_spike", 0) * 0.6),
        "lead_time_days":      lead_time,
        "required_themes":     case.get("pre_event_themes", [])[:3],
        "noise_sources":       noise,
        "true_precursors":     precursors,
        "confidence":          confidence,
    }

    case["label"]                 = label
    case["pattern_type"]          = pattern_id
    case["lead_time_days"]        = lead_time
    case["outcome"]               = outcome
    case["alternatives"]          = alternatives
    case["matching_thresholds"]   = matching
    case["confidence_in_signature"] = confidence
    if extra_note:
        case["notes"] = (case.get("notes", "") + " | " + extra_note).strip(" | ")

    return case


# ═══════════════════════════════════════════════════════════════
# KAYDETME
# ═══════════════════════════════════════════════════════════════

def save_trained_case(case: dict):
    """Etiketlenmiş vakayı cases/trained/ klasörüne kaydet."""
    TRAINED_DIR.mkdir(parents=True, exist_ok=True)
    filename = TRAINED_DIR / f"{case['id']}_trained.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(case, f, ensure_ascii=False, indent=2)
    print(f"\n  {color('✓', 'green')} Kaydedildi: {filename}")
    return filename


# ═══════════════════════════════════════════════════════════════
# STATS & ÖZET
# ═══════════════════════════════════════════════════════════════

def show_training_stats():
    """Eğitim veri tabanının mevcut durumunu göster."""
    all_cases   = list(CASES_DIR.glob("*.json"))
    trained     = list(TRAINED_DIR.glob("*_trained.json")) if TRAINED_DIR.exists() else []

    section("EĞİTİM VERİ TABANI DURUMU")
    print(f"  Toplam vaka dosyası : {len(all_cases)}")
    print(f"  Etiketlenmiş vaka   : {len(trained)}")
    print(f"  Etiketlenmemiş      : {len(all_cases) - len(trained)}\n")

    if trained:
        pattern_counts: dict[str, int] = {}
        for f in trained:
            try:
                with open(f) as fh:
                    c = json.load(fh)
                pt = c.get("pattern_type", "unknown")
                pattern_counts[pt] = pattern_counts.get(pt, 0) + 1
            except Exception:
                pass

        print("  Pattern dağılımı:")
        for pt, cnt in sorted(pattern_counts.items(), key=lambda x: -x[1]):
            bar = "█" * cnt
            print(f"    {pt:40} {cnt:3}  {bar}")
    print()


# ═══════════════════════════════════════════════════════════════
# ANA DÖNGÜ
# ═══════════════════════════════════════════════════════════════

def train_from_predefined(force_rebuild: bool = False):
    """
    Önceden tanımlı vakalar üzerinden eğitim döngüsü.
    Her vaka için:
      1. GDELT'ten imza çek (yoksa veya force_rebuild)
      2. Kullanıcıya göster
      3. Etiket al
      4. Kaydet
    """
    builder = CaseBuilder()
    CASES_DIR.mkdir(exist_ok=True)

    show_training_stats()
    hr()
    print(f"  {len(PREDEFINED_CASES)} önceden tanımlı vaka mevcut.")
    print("  Her vaka için GDELT imzası çekilecek, sen yorumlayacaksın.\n")
    print("  Komutlar: ENTER=devam, s=atla, q=çık, r=yeniden çek\n")
    hr()
    input("  Başlamak için ENTER...")

    for i, case_def in enumerate(PREDEFINED_CASES):
        case_id      = _make_id(case_def["name"], case_def["event_date"])
        raw_file     = CASES_DIR / f"{case_id}.json"
        trained_file = TRAINED_DIR / f"{case_id}_trained.json" if TRAINED_DIR.exists() else Path("x")

        # Zaten etiketlenmiş mi?
        if trained_file.exists() and not force_rebuild:
            clear()
            print(f"\n  [{i+1}/{len(PREDEFINED_CASES)}] {color('ATLA', 'green')} (etiketlenmiş): {case_def['name']}")
            time.sleep(0.5)
            continue

        # GDELT verisi var mı?
        if raw_file.exists() and not force_rebuild:
            with open(raw_file, encoding="utf-8") as f:
                case = json.load(f)
        else:
            clear()
            print(f"\n  [{i+1}/{len(PREDEFINED_CASES)}] GDELT çekiliyor: {case_def['name']}")
            print("  (Bu birkaç dakika sürebilir...)\n")
            case = builder.build(**{k: v for k, v in case_def.items()})
            if not case:
                print("  GDELT verisi alınamadı — atlanıyor.")
                time.sleep(2)
                continue

        # Göster
        display_case_summary(case)

        # Etiketle
        print(f"\n  [{i+1}/{len(PREDEFINED_CASES)}] {color(case['name'], 'bold')} — {case['event_date']}")
        cmd = input("\n  [ENTER=etiketle / s=atla / q=çık / r=yeniden çek]: ").strip().lower()

        if cmd == "q":
            print("\n  Çıkılıyor. İlerleme kaydedildi.")
            break
        elif cmd == "s":
            print("  → Atlandı.")
            continue
        elif cmd == "r":
            print("  → GDELT'ten yeniden çekiliyor...")
            case = builder.build(**{k: v for k, v in case_def.items()})
            if case:
                display_case_summary(case)
            else:
                print("  Veri alınamadı.")
                continue

        # Etiket al
        labeled = ask_labeling(case)
        if labeled is None:
            continue

        save_trained_case(labeled)

        print(f"\n  [{color('✓', 'green')}] {labeled['name']} etiketlendi → {labeled['pattern_type']}")
        input("\n  ENTER ile devam...")
        time.sleep(0.5)

    clear()
    hr()
    print("\n  EĞİTİM TAMAMLANDI\n")
    show_training_stats()


def add_custom_case():
    """
    Listede olmayan bir olay için özel vaka oluştur ve etiketle.
    """
    clear()
    section("ÖZEL VAKA EKLE")

    name    = input("  Olay adı: ").strip()
    date    = input("  Tarih (YYYY-MM-DD): ").strip()
    countries_raw = input("  Ülkeler (virgülle): ").strip()
    kw_raw  = input("  Anahtar kelimeler (virgülle): ").strip()
    regions_raw = input("  Bölgeler (nodes.py REGIONS key'leri, virgülle): ").strip()
    notes   = input("  Not: ").strip()

    case_def = {
        "name":       name,
        "event_date": date,
        "countries":  [c.strip() for c in countries_raw.split(",") if c.strip()],
        "keywords":   [k.strip() for k in kw_raw.split(",") if k.strip()],
        "regions":    [r.strip() for r in regions_raw.split(",") if r.strip()],
        "notes":      notes,
    }

    print("\n  GDELT çekiliyor...\n")
    builder = CaseBuilder()
    case = builder.build(**case_def)

    if not case:
        print("  Veri alınamadı.")
        return

    display_case_summary(case)
    labeled = ask_labeling(case)
    if labeled:
        save_trained_case(labeled)
        print(f"\n  {color('✓', 'green')} Vaka eklendi: {labeled['name']}")


# ═══════════════════════════════════════════════════════════════
# INTERPRETER ENTEGRASYONU
# Etiketlenmiş vakalar interpreter.py'ye dinamik pattern olarak eklenir
# ═══════════════════════════════════════════════════════════════

def load_trained_cases_as_patterns() -> list[dict]:
    """
    cases/trained/*.json dosyalarını yükle,
    interpreter.py formatına dönüştür.
    Bu fonksiyon interpreter.py tarafından çağrılır.
    """
    if not TRAINED_DIR.exists():
        return []

    patterns = []
    for f in TRAINED_DIR.glob("*_trained.json"):
        try:
            with open(f, encoding="utf-8") as fh:
                case = json.load(fh)

            label = case.get("label", {})
            if not label or label.get("pattern_type") == "unknown":
                continue

            mt = case.get("matching_thresholds", {})
            themes = mt.get("required_themes", [])

            # interpreter.py SCENARIO_PATTERNS formatına dönüştür
            pattern = {
                "id":          f"learned_{case['id']}",
                "name":        f"[Öğrenildi] {case['name']}",
                "description": (
                    f"{case.get('notes', '')} "
                    f"Emsal: {case['event_date']} — {', '.join(case.get('countries', []))}"
                ),
                "required_signals": [
                    {
                        "domain":    "news",
                        "direction": "up",
                        "keywords":  themes[:2] if themes else ["crisis"],
                    }
                ],
                "optional_signals": [],
                "base_confidence":  label.get("confidence_in_label", 0.60) * 0.85,
                "cascade_bonus":    0.10,
                "watch_message":    (
                    f"Emsal vaka: {case['name']} ({case['event_date']}). "
                    f"O vakada öncü sinyaller: {', '.join(label.get('true_precursor_signals', []))}"
                ),
                "alternatives":     [
                    (a["scenario"], a.get("confidence", 0.20))
                    for a in case.get("alternatives", [])
                ],
                "precedents":       [f"{case['name']} ({case['event_date']})"],
                # Ekstra — spike eşiği kontrolü için
                "_min_spike":       mt.get("min_spike_ratio", 2.0),
                "_lead_days":       case.get("lead_time_days", 7),
                "_learned":         True,
            }
            patterns.append(pattern)
        except Exception as e:
            log.debug("Trained case yüklenemedi %s: %s", f, e)

    log.info("%d öğrenilmiş pattern yüklendi", len(patterns))
    return patterns


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    clear()
    hr("═")
    print("""
   OSINT CASE TRAINER
   Senaryo Öğretme Mekanizması — WL (Weak Labeling)

   GDELT ham sinyal + sen etiket koyarsın
   → Sistem bir sonraki benzeri vakada daha isabetli yorum yapar
    """)
    hr("═")
    print("""
   1. Önceden tanımlı vakalar üzerinden eğit  (önerilen başlangıç)
   2. Özel vaka ekle (listede olmayanlar)
   3. Eğitim istatistiklerini göster
   4. Çık
    """)
    hr("─")

    choice = input("  Seçim (1-4): ").strip()

    if choice == "1":
        force = input("  Mevcut GDELT verisini yenile? (e/h, h=hız): ").strip().lower() == "e"
        train_from_predefined(force_rebuild=force)
    elif choice == "2":
        add_custom_case()
    elif choice == "3":
        show_training_stats()
    else:
        print("  Çıkılıyor.")
