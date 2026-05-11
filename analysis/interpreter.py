"""
analysis/interpreter.py

Veri Yorumlama & Context Engine
Anomalilere bağlam, nedenleri ve öngörüleri ekler.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from models.event import AnomalyEvent, RawEvent, Severity, Domain
from models.intelligence import CorrelationCluster
from storage.db import get_conn

log = logging.getLogger("Interpreter")


class DataInterpreter:
    """Anomalileri contextualize et ve interpret et."""

    def __init__(self):
        self.historical_window = 30  # gün
        self.similarity_threshold = 0.6

    def interpret_anomaly(self, anomaly: AnomalyEvent) -> Dict:
        """
        Anomaliyi yorumla — context, nedenleri, öngörüler ekle.

        Returns: {
            'anomaly_id': str,
            'interpretation': str,
            'context': {...},
            'likely_causes': [...],
            'predictions': [...],
            'similar_historical_events': [...]
        }
        """
        return {
            "anomaly_id": anomaly.event_id,
            "interpretation": self._interpret_text(anomaly),
            "context": self._get_context(anomaly),
            "likely_causes": self._identify_causes(anomaly),
            "predictions": self._predict_next(anomaly),
            "similar_historical_events": self._find_similar_events(anomaly),
            "confidence": self._calculate_confidence(anomaly),
            "recommendation": self._recommend_action(anomaly),
        }

    def _interpret_text(self, anomaly: AnomalyEvent) -> str:
        """İnsan okunabilir yorum."""
        domain = anomaly.raw.domain.value
        severity = anomaly.severity.value
        delta = anomaly.delta_pct or 0
        title = anomaly.raw.title

        if severity == Severity.CRITICAL.value:
            action = "CRİTİK SEVİYEDE MÜDAHALE GEREKLIDIR"
        elif severity == Severity.WARNING.value:
            action = "yakından izlenmesi gerekiyor"
        else:
            action = "izlenmelidir"

        direction = "artış" if delta > 0 else "düşüş" if delta < 0 else "değişim"

        interpretation = f"""
        {domain.upper()} domaininde {abs(delta):.1f}% {direction} tespit edilmiştir.

        {title}

        Bu anomali {severity.upper()} seviyesinde sınıflandırılmış ve {action}.

        Baseline'dan %{abs(delta):.1f} sapma vardır. Z-score değeri {anomaly.zscore:.2f} olup,
        istatistiksel olarak anlamlıdır.
        """

        return interpretation.strip()

    def _get_context(self, anomaly: AnomalyEvent) -> Dict:
        """Anomali konteksti — tarihsel arka plan."""
        context = {
            "current_status": {
                "value": anomaly.current_value,
                "baseline": anomaly.baseline_value,
                "delta_pct": anomaly.delta_pct,
                "zscore": anomaly.zscore,
            },
            "temporal": {
                "detected_at": anomaly.timestamp.isoformat(),
                "days_ago": (datetime.utcnow() - anomaly.timestamp).days,
            },
            "geographic": {
                "region": anomaly.region,
                "lat": anomaly.lat,
                "lon": anomaly.lon,
            },
            "source_info": {
                "source": anomaly.raw.source,
                "domain": anomaly.raw.domain.value,
                "keywords": anomaly.raw.keywords_matched,
                "entities": anomaly.raw.entities,
            }
        }

        # Geçmiş trendi ekle
        context["trend"] = self._get_historical_trend(anomaly)
        return context

    def _get_historical_trend(self, anomaly: AnomalyEvent) -> Dict:
        """Tarihsel trend analizi."""
        try:
            conn = get_conn()
            query = """
            SELECT timestamp, severity FROM anomaly_events
            WHERE source = ? AND event_id LIKE ?
            ORDER BY timestamp DESC LIMIT 10
            """
            rows = conn.execute(
                query,
                (anomaly.raw.source, f"{anomaly.raw.event_id.split('_')[0]}%")
            ).fetchall()
            conn.close()

            if rows:
                severities = [r[1] for r in rows]
                return {
                    "history_count": len(rows),
                    "recent_severities": severities[:3],
                    "escalating": len(rows) > 1 and self._is_escalating(severities),
                }
        except Exception as e:
            log.debug(f"Trend analizi hatası: {e}")

        return {"history_count": 0, "recent_severities": [], "escalating": False}

    def _is_escalating(self, severities: List[str]) -> bool:
        """Escalation kontrolü."""
        severity_rank = {"ok": 0, "info": 1, "warning": 2, "critical": 3}
        if len(severities) < 2:
            return False
        return severity_rank.get(severities[0], 0) > severity_rank.get(severities[1], 0)

    def _identify_causes(self, anomaly: AnomalyEvent) -> List[str]:
        """Olası nedenleri belirle."""
        causes = []
        domain = anomaly.raw.domain.value
        keywords = anomaly.raw.keywords_matched
        delta = anomaly.delta_pct or 0

        # Domain-spesifik causation logic
        if domain == "air":
            if delta < -30:
                causes.append("✈ Hava sahasında kapatılma/yasak")
                causes.append("✈ Havacılık krizesi (çatışma, tehdit)")
            elif delta > 30:
                causes.append("✈ Yeni rota açılışı")
                causes.append("✈ Bölgesel hava trafiği yönlendirmesi")

        elif domain == "sea":
            if delta < -30:
                causes.append("⚓ Liman blokaması/abluka")
                causes.append("⚓ Deniz trafiği kısıtlaması (çatışma)")
            elif delta > 30:
                causes.append("⚓ Rota değişimi (yakında kapanma beklentisi)")
                causes.append("⚓ Alternatif liman kullanımı")

        elif domain == "news":
            if "military" in keywords:
                causes.append("🎖 Askeri aktivite artışı")
                causes.append("🎖 Çatışma riskinde tırmanma")
            if "sanctions" in keywords:
                causes.append("🚫 Yaptırım genişlemesi")
                causes.append("🚫 Ticaret kısıtlamaları")

        elif domain == "economic":
            if delta < -20:
                causes.append("📉 Piyasa düşüşü")
                causes.append("📉 Para politikası sıkılaştırması")
            elif delta > 20:
                causes.append("📈 Piyasa euforia")
                causes.append("📈 Likidite artışı")

        # Genel patterns
        if "crisis" in keywords:
            causes.append("🔴 Kriz/gerilim artışı (multi-domain)")
        if "embargo" in keywords or "blockade" in keywords:
            causes.append("⛔ İktisadi ambargo/abluka uygulanması")

        return causes if causes else ["Nedeni belirsiz — daha fazla veri gerekli"]

    def _predict_next(self, anomaly: AnomalyEvent) -> List[str]:
        """Sırada ne olabilir?"""
        predictions = []
        domain = anomaly.raw.domain.value
        severity = anomaly.severity.value
        delta = anomaly.delta_pct or 0

        # High severity anomalilere güçlü öngörüler
        if severity == "critical":
            if domain == "air":
                predictions.append("◆ Deniz trafiğinde de düşüş bekleniyor (bölgesel kapanma)")
                predictions.append("◆ Gazete/haber spike'ı yakında")
            elif domain == "sea":
                predictions.append("◆ Enerji ürünlerinde fiyat artışı")
                predictions.append("◆ Finans piyasalarında volatilite")

        # Escalation kontrol
        if anomaly.raw.location and anomaly.raw.location.region:
            region = anomaly.raw.location.region
            if severity in ["warning", "critical"]:
                predictions.append(f"◆ {region} bölgesinde diğer domain'lerde anomali olasılığı yüksek")

        # Trend-based
        trend = self._get_historical_trend(anomaly)
        if trend.get("escalating"):
            predictions.append("◆ Anomali şiddeti artma eğilimindedir")
            predictions.append("◆ Müdahale/açıklama bekleniyor")

        # Default
        if not predictions:
            predictions.append("◆ Durum normalleşmesi için 24-72 saat bekleme")
            predictions.append("◆ Korelasyon kümelerine dahil olup olmadığını kontrol et")

        return predictions

    def _find_similar_events(self, anomaly: AnomalyEvent) -> List[Dict]:
        """Geçmiş benzer olayları bul."""
        similar = []
        try:
            conn = get_conn()
            query = """
            SELECT event_id, timestamp, severity, delta_pct, description
            FROM anomaly_events
            WHERE source = ?
                AND domain = ?
                AND timestamp >= datetime('now', '-30 days')
                AND event_id != ?
            ORDER BY timestamp DESC
            LIMIT 5
            """
            rows = conn.execute(
                query,
                (anomaly.raw.source, anomaly.raw.domain.value, anomaly.event_id)
            ).fetchall()
            conn.close()

            for row in rows:
                similar.append({
                    "event_id": row[0],
                    "when": row[1],
                    "severity": row[2],
                    "delta_pct": row[3],
                    "description": row[4],
                })

        except Exception as e:
            log.debug(f"Benzer olay bulma hatası: {e}")

        return similar

    def _calculate_confidence(self, anomaly: AnomalyEvent) -> float:
        """Yorum güvenilirliği (0-1)."""
        confidence = anomaly.confidence or 0.5

        # Boost for high Z-score
        if anomaly.zscore and abs(anomaly.zscore) > 3:
            confidence = min(1.0, confidence + 0.2)

        # Boost for correlated events
        if anomaly.correlated_event_ids:
            confidence = min(1.0, confidence + 0.15)

        return round(confidence, 2)

    def _recommend_action(self, anomaly: AnomalyEvent) -> str:
        """Aksiyona geçilmesi gereken tavsiye."""
        severity = anomaly.severity.value

        if severity == "critical":
            return (
                "🔴 ACIL: İlgili bölüm/ülkede 2 saat içinde eskalasyon kontrol toplantısı yapınız. "
                "Diplomatik kanalları ve istihbarat ortaklarını haberdar ediniz."
            )
        elif severity == "warning":
            return (
                "🟡 ÖNEMLİ: Durum 6 saatlik aralıklarla kontrol edilmeli. "
                "Korelasyon kümelerine dahil olup olmadığını izleyin. "
                "Yakın sorumlulara bilgi verin."
            )
        else:
            return (
                "🟢 İZLEME: Düzenli gözetim altında tutun. "
                "Diğer anomaliler ile korelasyon kontrol edin. "
                "Normalleşme takip ediniz."
            )

    def interpret_cluster(self, cluster: CorrelationCluster) -> Dict:
        """Korelasyon kümesini yorumla."""
        return {
            "cluster_id": cluster.cluster_id,
            "interpretation": self._interpret_cluster_text(cluster),
            "implications": self._cluster_implications(cluster),
            "escalation_risk": self._assess_escalation_risk(cluster),
            "recommended_monitoring": self._monitoring_points(cluster),
        }

    def _interpret_cluster_text(self, cluster: CorrelationCluster) -> str:
        """Kümenin insan okunabilir açıklaması."""
        type_desc = {
            "parallel": "eş zamanlı",
            "divergent": "ters yönlü trafik",
            "cascade": "haber → fiziksel zincir"
        }.get(cluster.correlation_type, "karışık")

        return f"""
        {len(cluster.event_ids)} olaydan oluşan {type_desc} korelasyon kümesi.

        Domain: {', '.join(cluster.domains_involved)}
        Bölge: {', '.join(cluster.regions_involved)}

        Özet: {cluster.summary}

        Güven seviyesi: {cluster.confidence:.0%}
        """

    def _cluster_implications(self, cluster: CorrelationCluster) -> List[str]:
        """Kümenin gerçek dünya anlamı."""
        implications = []

        if cluster.correlation_type == "cascade":
            implications.append("⚠️ Haber sinyali fiziksel olaylara dönüşüyor — durum tırmanıyor")

        elif cluster.correlation_type == "divergent":
            implications.append("↔️ Trafik yönlendirmesi/kayması — alternatif güzergah kullanımı")

        elif cluster.correlation_type == "parallel":
            implications.append("📍 Bölgesel kapatılma/açılım — eş zamanlı multi-domain etki")

        # Severity-based
        if cluster.severity.value == "critical":
            implications.append("🔴 CRİTİK: Jeopolitik krizin net göstergesi")
        elif cluster.severity.value == "warning":
            implications.append("🟡 UYARI: Bölgesel gerilim yükseliş eğilimi")

        return implications

    def _assess_escalation_risk(self, cluster: CorrelationCluster) -> Dict:
        """Tırmanma riski değerlendirmesi."""
        risk_level = cluster.severity.value

        return {
            "risk_level": risk_level,
            "confidence": cluster.confidence,
            "hours_to_escalation": "6-24" if risk_level == "critical" else "24-72" if risk_level == "warning" else "72+",
            "monitoring_frequency": "30 min" if risk_level == "critical" else "2 saat" if risk_level == "warning" else "6 saat",
        }

    def _monitoring_points(self, cluster: CorrelationCluster) -> List[str]:
        """Ne izlenmesi gerek?"""
        points = []

        for domain in cluster.domains_involved:
            if domain == "air":
                points.append("✈ Havalimanı trafik trendi")
            elif domain == "sea":
                points.append("⚓ Liman trafik trendi")
            elif domain == "news":
                points.append("📰 Haber frekansı (spike)")
            elif domain == "conflict":
                points.append("🎖 Çatışma aktivitesi")

        points.append(f"📍 {', '.join(cluster.regions_involved)} bölgelerindeki yeni anomaliler")

        return points
