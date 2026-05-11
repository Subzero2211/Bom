# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Multi-source geopolitical OSINT intelligence engine that aggregates real-time data from 9+ sources (news, aviation, maritime, conflict, economic, disaster), detects anomalies using statistical methods, finds cross-domain correlations, and synthesizes intelligence reports.

**Current State**: Core data collection, anomaly detection, and correlation engine complete. **In Development**: PDF report generation and data interpretation modules.

---

## Architecture

### Data Processing Pipeline

```
COLLECTORS (9 sources)
    ↓
RawEvent (unstructured data + metadata)
    ↓
ANOMALY DETECTION (analyze.anomaly)
    ├─ Z-score (numeric: OpenSky, Marine, FRED)
    └─ Frequency spike (text: RSS, Reddit, Telegram)
    ↓
AnomalyEvent (severity + baseline + confidence)
    ↓
CORRELATION (analysis.correlator)
    ├─ Geographic (Haversine ≤ 400 km)
    ├─ Temporal (±12 hours)
    └─ Thematic (keyword overlap)
    ↓
CorrelationCluster (parallel|divergent|cascade)
    ↓
SYNTHESIS (analysis.synthesizer)
    ↓
IntelligenceReport (key findings + watch list + summaries)
    ↓
DATABASE (storage.db) + API (api.server) + DASHBOARDS (frontend/)
```

### Key Data Models (`models/`)

**RawEvent**: Unstructured event from any source
- `source`: "opensky", "rss_bbc", "telegram_reuters", etc.
- `domain`: Domain.AIR, .SEA, .NEWS, .CONFLICT, .DISASTER, .ECONOMIC, .SOCIAL
- `location`: GeoPoint (lat, lon, region)
- `affected_regions`: List of geopolitical regions from config.REGIONS
- `keywords_matched`: From config.KEYWORDS groups
- `raw_data`: Source-specific extra fields

**AnomalyEvent**: Analyzed raw event
- `severity`: Severity.OK | .INFO | .WARNING | .CRITICAL
- `zscore`: For numeric data anomalies
- `delta_pct`: Percentage change from baseline
- `baseline_value`: Historical average
- `confidence`: Source weight (from config.SOURCE_WEIGHTS)

**CorrelationCluster**: Grouped anomalies with shared signals
- `correlation_type`: "parallel" (same direction), "divergent" (opposite), "cascade" (news→physical)
- `centroid`: Weighted geographic center
- `first_seen`/`last_seen`: Time window

**IntelligenceReport**: Final synthesis
- `key_findings`: Top 5 high-severity events/clusters
- `watch_list`: Regions/topics requiring monitoring
- `domain_summary`: Stats by domain (air, sea, etc.)
- `region_summary`: Stats by geopolitical region

### Collector Pattern

All collectors extend `BaseCollector` (collectors/base.py):

```python
class NewCollector(BaseCollector):
    name = "source_name"
    domain = Domain.NEWS  # Pick from Domain enum
    
    def collect(self) -> list[RawEvent]:
        # Fetch data
        # Return list of RawEvent objects
        pass
```

**Critical**: Must handle gracefully:
- Rate limits (sleep, return partial data)
- API downtime (log warning, return empty list)
- Missing credentials (log.info "skipping")
- Consecutive errors (backoff after 5 failures)

The `run()` wrapper (inherited) handles error counting, logging, and timing.

---

## Configuration & Thresholds

**config.py** is the single source of truth for:

1. **ANOMALY thresholds**:
   - `zscore_warn = 2.0`: Warning threshold
   - `zscore_crit = 3.0`: Critical threshold
   - `history_window = 48`: Rolling baseline lookback
   - `news_spike_mult = 2.5`: Article count multiplier for WARNING
   - `news_crit_mult = 5.0`: Article count multiplier for CRITICAL

2. **REGIONS**: Bounding boxes for geopolitical areas (lat_min, lat_max, lon_min, lon_max)
   - Used by `region_from_location(lat, lon)` in base.py
   - Maps any coordinate to affected regions

3. **SOURCE_WEIGHTS**: Confidence multipliers (0.0-1.0)
   - Higher = more trustworthy (GDACS: 0.95, ACLED: 0.90, Reddit: 0.45)
   - Used in anomaly synthesis and cluster confidence calculation

4. **SCAN_INTERVALS**: Frequency per collector (minutes)
   - Respects API rate limits and budget constraints
   - Telegram: 5 min (near real-time), FRED: 1440 (daily)

5. **KEYWORDS**: Group definitions for thematic matching
   - Groups: "military", "sanctions", "energy", "crisis", "maritime", "aviation", etc.
   - Used by `match_keywords(text)` to tag events

---

## Database Schema

SQLite (`osint_data.db`):

| Table | Purpose |
|-------|---------|
| `raw_events` | All ingested events (30-day retention) |
| `anomaly_events` | Analyzed anomalies (severity + metrics) |
| `correlation_clusters` | Grouped anomalies with correlation metadata |
| `intel_reports` | Final synthesis reports (one per hour typically) |
| `timeseries` | Rolling baselines for numeric sources |

**Key queries**:
- Last 12h anomalies: `SELECT * FROM anomaly_events WHERE timestamp >= datetime('now', '-12 hours') AND severity IN ('warning', 'critical')`
- Active clusters: `SELECT * FROM correlation_clusters WHERE last_seen >= datetime('now', '-24 hours')`

---

## Common Development Tasks

### Adding a New Collector

1. **Create** `collectors/your_collector.py`
2. **Implement** `collect() -> list[RawEvent]` with error handling
3. **Register** in main.py: Add to COLLECTORS dict
4. **Configure**: Add to `config.SCAN_INTERVALS` (minutes)
5. **Test**: Run manually: `python -c "from collectors.your import YourCollector; print(len(YourCollector().run()))"`

### Modifying Anomaly Thresholds

- Edit `config.ANOMALY` dict
- Thresholds apply **immediately** to new anomalies
- Existing anomalies in DB are unchanged
- Re-synthesis produces new IntelligenceReport automatically

### Adding a Geopolitical Region

1. **Define bbox** in `config.REGIONS`: `"new_region": (lat_min, lat_max, lon_min, lon_max)`
2. **Update** collector region tags if hardcoded (e.g., AIRPORTS in opensky_collector.py)
3. **Verify** with: `python -c "from analysis.base import BaseCollector; bc=BaseCollector(); print(bc.region_from_location(lat, lon))"`

### Inspecting Pipeline Output

```bash
# See what raw events are collected
sqlite3 osint_data.db "SELECT source, title, timestamp FROM raw_events ORDER BY timestamp DESC LIMIT 5;"

# Check anomaly severity distribution
sqlite3 osint_data.db "SELECT severity, COUNT(*) FROM anomaly_events WHERE timestamp >= datetime('now', '-24 hours') GROUP BY severity;"

# Get latest synthesis report (JSON)
sqlite3 osint_data.db "SELECT full_json FROM intel_reports ORDER BY generated_at DESC LIMIT 1;" | python -m json.tool
```

---

## Upcoming: PDF Report & Data Interpretation

### PDF Report Generation (next phase)

Expected location: `analysis/report_generator.py`

Requirements:
- Input: IntelligenceReport object from synthesizer
- Output: PDF file with:
  - Executive summary (system status + key findings)
  - Domain-wise breakdown (air/sea/conflict/economic/disaster)
  - Region-wise summaries + map
  - Cluster details (types, confidence, interpretations)
  - Watch list with recommendations
  - Appendix: Raw anomaly data + sources

Use `reportlab` (already in requirements.txt) for PDF generation.

### Data Interpretation Enhancement

Expected location: `analysis/interpreter.py`

Should provide:
- **Context lookup**: Given an anomaly, fetch historical precedents
- **Causal inference**: Why did this anomaly happen? (check related events, news spikes, geopolitical events)
- **Predictive signals**: What might happen next based on correlation patterns?
- **Source credibility check**: Cross-validate against independent sources

---

## API Endpoints (Flask)

**Running**: `python main.py` starts server on `http://localhost:5055`

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/status` | System health + summary |
| GET | `/api/report` | Latest IntelligenceReport (JSON) |
| GET | `/api/anomalies` | Filtered anomalies (`?hours=12&domain=air&region=levant`) |
| GET | `/api/clusters` | Correlation clusters (`?hours=24`) |
| GET | `/api/events` | Raw events (`?domain=news&limit=100`) |
| POST | `/api/scan` | Trigger manual scan (async) |
| GET | `/api/sources` | Collector status & config |

---

## File Organization

```
osint_engine/
├── collectors/          # 9 data source collectors
│   ├── base.py         # BaseCollector abstract class
│   ├── opensky_collector.py, marine_collector.py, ... (9 collectors)
│   └── __init__.py
├── models/             # Data structures
│   ├── event.py        # RawEvent, AnomalyEvent, Domain, Severity, GeoPoint
│   ├── intelligence.py # CorrelationCluster, IntelligenceReport
│   └── __init__.py
├── analysis/           # Analysis pipeline
│   ├── anomaly.py      # Z-score & frequency spike detection
│   ├── correlator.py   # Geographic + temporal + thematic clustering
│   ├── synthesizer.py  # Report synthesis
│   └── __init__.py
├── storage/
│   ├── db.py           # SQLite initialization & queries
│   └── __init__.py
├── api/
│   ├── server.py       # Flask REST endpoints
│   └── __init__.py
├── frontend/
│   ├── html/           # Static dashboards
│   └── react/          # React components (optional future)
├── config.py           # Single source of truth
├── main.py             # Orchestration & scheduling
├── requirements.txt
└── README.md
```

---

## Key Decision Points

1. **Anomaly severity mapping**: Config thresholds vs. event-specific logic
   - Decision: Config-driven (ANOMALY dict) for consistency
   - Location: `analysis/anomaly.py:severity_from_zscore()`, `analyze_event_severity()`

2. **Correlation distance**: 400 km threshold vs. region-based
   - Decision: Haversine + region overlap (config.ANOMALY["corr_distance_km"])
   - Location: `analysis/correlator.py:_geo_close()`, `_thematic_overlap()`

3. **PDF report scope**: Per-region, per-domain, or unified?
   - Decision: Unified IntelligenceReport → multi-page PDF (executive summary + detailed breakdowns)

4. **Database archival**: Keep 30 days, auto-archive older records to monthly files
   - Location: `storage/db.py:archive_old_records()` (runs monthly)

---

## Testing Strategy

- **Unit**: Mock API responses in collectors
- **Integration**: Check pipeline transforms (RawEvent → AnomalyEvent → CorrelationCluster)
- **Manual**: `python main.py` → check `/api/report` endpoint
- **Database**: Verify schema with `sqlite3 osint_data.db ".schema"`
