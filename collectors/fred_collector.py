"""
collectors/fred_collector.py

FRED — Federal Reserve Economic Data.
Binlerce ekonomik gösterge, tamamen ücretsiz.
API key: https://fred.stlouisfed.org/docs/api/api_key.html
"""

import requests
from datetime import datetime, timedelta
from models.event import RawEvent, Domain
from collectors.base import BaseCollector
from analysis.anomaly import analyze_numeric
from storage.db import insert_anomaly
from config import FRED

FRED_SERIES = {
    # Enerji
    "DCOILWTICO":           ("WTI Ham Petrol ($/varil)",          "energy"),
    "DCOILBRENTEU":         ("Brent Ham Petrol ($/varil)",         "energy"),
    "DHHNGSP":              ("Doğalgaz Henry Hub ($/MMBtu)",       "energy"),
    # Döviz / risk
    "DEXUSEU":              ("EUR/USD",                            "economy"),
    "DEXJPUS":              ("USD/JPY",                            "economy"),
    "DEXTRUS":              ("USD/TRY",                            "economy"),
    "DEXSZUS":              ("USD/CHF — güvenli liman",            "economy"),
    # Kredi riski
    "BAMLH0A0HYM2":         ("High Yield Spread (risk iştahı)",    "economy"),
    "T10Y2Y":               ("ABD 10y-2y Getiri Eğrisi",          "economy"),
    # Emtia / güvenli liman
    "GOLDAMGBD228NLBM":     ("Altın ($/ons)",                      "economy"),
    # EM stres
    "DEXBZUS":              ("USD/BRL — EM stres",                 "economy"),
    "DEXCHUS":              ("USD/CNY",                            "economy"),
}


class FREDCollector(BaseCollector):
    name = "fred"
    domain = Domain.ECONOMIC
    BASE = "https://api.stlouisfed.org/fred/series/observations"

    def collect(self) -> list[RawEvent]:
        if not FRED["api_key"]:
            self.log.info("FRED API key yok — atlanıyor")
            return []

        events = []
        since = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")

        for series_id, (desc, kw_group) in FRED_SERIES.items():
            try:
                r = requests.get(self.BASE, params={
                    "series_id": series_id,
                    "api_key": FRED["api_key"],
                    "file_type": "json",
                    "observation_start": since,
                    "sort_order": "desc",
                    "limit": 10,
                }, timeout=15)

                if r.status_code != 200:
                    continue

                observations = r.json().get("observations", [])
                latest = next(
                    (o for o in observations if o.get("value") not in (".", "")), None
                )
                if not latest:
                    continue

                value = float(latest["value"])
                ts = datetime.strptime(latest["date"], "%Y-%m-%d")

                raw = RawEvent(
                    source="fred",
                    domain=Domain.ECONOMIC,
                    event_id=f"fred_{series_id}_{latest['date']}",
                    title=f"{desc}: {value:.5g}",
                    timestamp=ts,
                    keywords_matched=[kw_group, "economy"],
                    raw_data={"series_id": series_id, "value": value, "desc": desc},
                )

                anomaly = analyze_numeric(
                    station_key=f"fred_{series_id}",
                    current_value=value,
                    source="fred",
                    event=raw,
                )

                if anomaly.severity.value in ("warning", "critical"):
                    insert_anomaly(anomaly.to_dict())
                    self.log.warning(
                        "FRED anomali: [%s] %s → %s",
                        series_id, desc, anomaly.anomaly_description
                    )

                events.append(raw)

            except Exception as e:
                self.log.warning("FRED %s hata: %s", series_id, e)

        return events
