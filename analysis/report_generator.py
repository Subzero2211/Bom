"""
analysis/report_generator.py

PDF İstihbarat Raporu Oluşturma — ReportLab ile profesyonel raporlar.
IntelligenceReport → PDF dönüştürme.
"""

import logging
from datetime import datetime
from io import BytesIO
from pathlib import Path
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
    PageBreak, Image, KeepTogether
)
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from models.intelligence import IntelligenceReport, CorrelationCluster
from models.event import Severity

log = logging.getLogger("ReportGenerator")


class ReportGenerator:
    """PDF rapor oluşturucusu."""

    def __init__(self, output_dir: str = "reports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        """Custom stilleri tanımla."""
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1a3a52'),
            spaceAfter=30,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        ))

        self.styles.add(ParagraphStyle(
            name='SectionHeading',
            parent=self.styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#2c5aa0'),
            spaceAfter=12,
            spaceBefore=12,
            fontName='Helvetica-Bold'
        ))

        self.styles.add(ParagraphStyle(
            name='BodyText',
            parent=self.styles['BodyText'],
            fontSize=10,
            alignment=TA_JUSTIFY,
            spaceAfter=12
        ))

    def generate(self, report: IntelligenceReport) -> str:
        """
        Raporu PDF'e dönüştür.

        Returns: PDF dosya yolu
        """
        filename = f"osint_report_{report.report_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
        filepath = self.output_dir / filename

        doc = SimpleDocTemplate(str(filepath), pagesize=A4)
        story = []

        # 1. Başlık
        story.extend(self._build_header(report))
        story.append(Spacer(1, 0.3 * inch))

        # 2. Executive Summary
        story.append(Paragraph("YÖNETIM ÖZETİ", self.styles['SectionHeading']))
        story.extend(self._build_executive_summary(report))
        story.append(Spacer(1, 0.2 * inch))

        # 3. System Status
        story.append(Paragraph("SİSTEM DURUMU", self.styles['SectionHeading']))
        story.extend(self._build_status_section(report))
        story.append(Spacer(1, 0.2 * inch))

        # 4. Domain Summary
        story.append(Paragraph("DOMAIN ÖZETI", self.styles['SectionHeading']))
        story.extend(self._build_domain_summary(report))
        story.append(PageBreak())

        # 5. Region Summary
        story.append(Paragraph("BÖLGE ANALİZİ", self.styles['SectionHeading']))
        story.extend(self._build_region_summary(report))
        story.append(Spacer(1, 0.2 * inch))

        # 6. Key Findings
        story.append(Paragraph("ÖNEMLİ BULGULAR", self.styles['SectionHeading']))
        story.extend(self._build_key_findings(report))
        story.append(PageBreak())

        # 7. Watch List
        story.append(Paragraph("UYARI LİSTESİ", self.styles['SectionHeading']))
        story.extend(self._build_watch_list(report))
        story.append(Spacer(1, 0.2 * inch))

        # 8. Correlation Clusters
        if report.clusters:
            story.append(Paragraph("KORELASYON KÜMELERİ", self.styles['SectionHeading']))
            story.extend(self._build_clusters(report.clusters))
            story.append(PageBreak())

        # 9. Source Statistics
        story.append(Paragraph("KAYNAK İSTATİSTİKLERİ", self.styles['SectionHeading']))
        story.extend(self._build_source_stats(report))

        # Build PDF
        try:
            doc.build(story)
            log.info(f"✓ PDF rapor oluşturuldu: {filepath}")
            return str(filepath)
        except Exception as e:
            log.error(f"PDF oluşturma hatası: {e}")
            raise

    def _build_header(self, report: IntelligenceReport):
        """Başlık bölümü."""
        story = []
        story.append(Paragraph("OSINT İSTİHBARAT RAPORU", self.styles['CustomTitle']))

        # Meta bilgisi
        meta_data = [
            [f"Rapor ID: {report.report_id}", f"Oluşturma: {report.generated_at.isoformat()}"],
            [f"Sistem Durumu: {report.system_status.value.upper()}",
             f"Aktif Anomali: {report.active_anomalies} | Korelasyon: {report.active_correlations}"]
        ]
        meta_table = Table(meta_data, colWidths=[3*inch, 3*inch])
        meta_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f0f0f0')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), TA_CENTER),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey)
        ]))
        story.append(meta_table)
        return story

    def _build_executive_summary(self, report: IntelligenceReport):
        """Yönetim özeti."""
        story = []

        status_color = {
            Severity.OK: colors.green,
            Severity.INFO: colors.blue,
            Severity.WARNING: colors.orange,
            Severity.CRITICAL: colors.red
        }.get(report.system_status, colors.black)

        summary_text = f"""
        <b>Sistem Durumu:</b> <font color="{status_color.hexval()}">{report.system_status.value.upper()}</font><br/>
        <b>Aktif Anomali:</b> {report.active_anomalies}<br/>
        <b>Korelasyon Kümesi:</b> {report.active_correlations}<br/>
        <b>Önemli Bulgular:</b> {len(report.key_findings)}<br/>
        <br/>
        Sistem son 24 saatte {report.active_anomalies} anomali tespit etmiş,
        {report.active_correlations} korelasyon kümesi oluşturmuştur.
        En kritik bulguları aşağıda görebilirsiniz.
        """
        story.append(Paragraph(summary_text, self.styles['BodyText']))
        return story

    def _build_status_section(self, report: IntelligenceReport):
        """Sistem durumu tablosu."""
        story = []

        status_text = f"""
        <b>Genel Durum:</b> {report.system_status.value.upper()}<br/>
        <b>Son Güncelleme:</b> {report.generated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}<br/>
        <b>Veri Kaynakları:</b> 9 (OpenSky, Marine, ACLED, Telegram, GDACS, Reddit, FRED, GDELT, RSS)<br/>
        <b>İçinde Tutulan Veri:</b> Son 30 gün<br/>
        """
        story.append(Paragraph(status_text, self.styles['BodyText']))
        return story

    def _build_domain_summary(self, report: IntelligenceReport):
        """Domain başına özet."""
        story = []

        if not report.domain_summary:
            story.append(Paragraph("Domain özeti mevcut değil.", self.styles['BodyText']))
            return story

        data = [['Domain', 'Toplam', 'Kritik', 'Uyarı', 'İyi']]
        for domain, stats in report.domain_summary.items():
            data.append([
                domain.upper(),
                str(stats.get('total', 0)),
                str(stats.get('critical', 0)),
                str(stats.get('warning', 0)),
                str(stats.get('info', 0))
            ])

        table = Table(data, colWidths=[1.5*inch, 1*inch, 1*inch, 1*inch, 1*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5aa0')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), TA_CENTER),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(table)
        return story

    def _build_region_summary(self, report: IntelligenceReport):
        """Bölge başına özet."""
        story = []

        if not report.region_summary:
            story.append(Paragraph("Bölge özeti mevcut değil.", self.styles['BodyText']))
            return story

        data = [['Bölge', 'Anomali', 'Korelasyon', 'Max Severity']]
        for region, stats in sorted(report.region_summary.items()):
            data.append([
                region.upper(),
                str(stats.get('anomalies', 0)),
                str(stats.get('clusters', 0)),
                stats.get('max_severity', 'ok').upper()
            ])

        table = Table(data, colWidths=[2*inch, 1.2*inch, 1.2*inch, 1.2*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5aa0')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), TA_CENTER),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.lightgrey),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(table)
        return story

    def _build_key_findings(self, report: IntelligenceReport):
        """Önemli bulgular."""
        story = []

        if not report.key_findings:
            story.append(Paragraph("Bulgu yok.", self.styles['BodyText']))
            return story

        for i, finding in enumerate(report.key_findings[:5], 1):
            story.append(Paragraph(f"<b>{i}.</b> {finding}", self.styles['BodyText']))
            story.append(Spacer(1, 0.1 * inch))

        return story

    def _build_watch_list(self, report: IntelligenceReport):
        """Uyarı listesi."""
        story = []

        if not report.watch_list:
            story.append(Paragraph("Izleme gereken konu yok.", self.styles['BodyText']))
            return story

        for item in report.watch_list[:5]:
            story.append(Paragraph(f"<b>▸</b> {item}", self.styles['BodyText']))
            story.append(Spacer(1, 0.1 * inch))

        return story

    def _build_clusters(self, clusters: list):
        """Korelasyon kümeleri."""
        story = []

        for cluster in clusters[:10]:
            cluster_text = f"""
            <b>ID:</b> {cluster.cluster_id} | <b>Tip:</b> {cluster.correlation_type} | <b>Güven:</b> {cluster.confidence:.0%}<br/>
            <b>Domain:</b> {', '.join(cluster.domains_involved)}<br/>
            <b>Bölge:</b> {', '.join(cluster.regions_involved)}<br/>
            <b>Özet:</b> {cluster.summary}<br/>
            """
            story.append(Paragraph(cluster_text, self.styles['BodyText']))
            story.append(Spacer(1, 0.15 * inch))

        return story

    def _build_source_stats(self, report: IntelligenceReport):
        """Kaynak istatistikleri."""
        story = []

        if not report.source_stats:
            story.append(Paragraph("Kaynak istatistikleri mevcut değil.", self.styles['BodyText']))
            return story

        data = [['Kaynak', 'Anomali Sayısı']]
        for source, count in sorted(report.source_stats.items(), key=lambda x: x[1], reverse=True):
            data.append([source, str(count)])

        table = Table(data, colWidths=[3*inch, 2*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5aa0')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), TA_CENTER),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.lightblue),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(table)
        return story
