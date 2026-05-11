import { useState, useEffect, useRef, useCallback } from "react";

// ─── Simulated FR24 data engine ───────────────────────────────────────────────
// Real implementation: fetch("https://data-live.flightradar24.com/zones/fcgi/feed.js?bounds=...")
// Burada gerçek veriyi simüle ediyoruz — production'da aşağıdaki endpoint'ler kullanılır:
// GET https://data-live.flightradar24.com/zones/fcgi/feed.js?bounds={lat_max},{lat_min},{lon_min},{lon_max}
// GET https://api.flightradar24.com/common/v1/airport.json?code={ICAO}&plugin[]=schedule

const AIRPORTS = [
  { icao: "LTFM", name: "İstanbul", country: "TR", lat: 41.27, lon: 28.74, normal: 420 },
  { icao: "LTAC", name: "Ankara", country: "TR", lat: 40.12, lon: 32.99, normal: 180 },
  { icao: "OMDB", name: "Dubai", country: "AE", lat: 25.25, lon: 55.36, normal: 680 },
  { icao: "UUEE", name: "Moskova", country: "RU", lat: 55.97, lon: 37.41, normal: 290 },
  { icao: "LLBG", name: "Tel Aviv", country: "IL", lat: 32.00, lon: 34.88, normal: 210 },
  { icao: "OJAM", name: "Amman", country: "JO", lat: 31.72, lon: 35.99, normal: 95 },
  { icao: "ORBI", name: "Bağdat", country: "IQ", lat: 33.26, lon: 44.23, normal: 55 },
  { icao: "OIII", name: "Tahran", country: "IR", lat: 35.69, lon: 51.31, normal: 120 },
  { icao: "HECA", name: "Kahire", country: "EG", lat: 30.12, lon: 31.40, normal: 185 },
  { icao: "EGLL", name: "Londra", country: "GB", lat: 51.47, lon: -0.46, normal: 720 },
  { icao: "EDDM", name: "Münih", country: "DE", lat: 48.35, lon: 11.79, normal: 380 },
  { icao: "UKBB", name: "Kyiv", country: "UA", lat: 50.34, lon: 30.89, normal: 15 },
  { icao: "URSS", name: "Soçi", country: "RU", lat: 43.44, lon: 39.94, normal: 88 },
  { icao: "LYBT", name: "Belgrad", country: "RS", lat: 44.82, lon: 20.31, normal: 120 },
];

const ROUTES = [
  { from: "LTFM", to: "OMDB", normal: 24 },
  { from: "LTFM", to: "LLBG", normal: 8 },
  { from: "LTFM", to: "UUEE", normal: 6 },
  { from: "LTFM", to: "OJAM", normal: 10 },
  { from: "OMDB", to: "ORBI", normal: 14 },
  { from: "UUEE", to: "LLBG", normal: 0 },
  { from: "OIII", to: "OMDB", normal: 12 },
  { from: "HECA", to: "LLBG", normal: 4 },
  { from: "LTFM", to: "UKBB", normal: 0 },
  { from: "EGLL", to: "UUEE", normal: 2 },
];

function generateFlightData(seed = 0) {
  // Senaryolar: bazı havalimanlarında anomali üret
  const scenarios = {
    0: { airports: {}, routes: {} }, // normal
    1: { // Orta Doğu gerilimi
      airports: { LLBG: -0.72, OJAM: +0.45, HECA: -0.30 },
      routes: { "HECA-LLBG": -1.0, "LTFM-LLBG": -0.8 },
    },
    2: { // Rusya trafiği anomalisi
      airports: { UUEE: -0.55, URSS: +0.80, LYBT: +0.35 },
      routes: { "EGLL-UUEE": -1.0, "LTFM-UUEE": -0.4 },
    },
    3: { // Körfez diplomatik kriz
      airports: { OMDB: -0.60, ORBI: +0.40, OIII: +0.25 },
      routes: { "OMDB-ORBI": +0.90, "LTFM-OMDB": -0.30 },
    },
  };

  const scenario = scenarios[seed % 4];
  const now = Date.now();

  const airports = AIRPORTS.map((ap) => {
    const factor = scenario.airports[ap.icao] || (Math.random() * 0.1 - 0.05);
    const current = Math.round(ap.normal * (1 + factor));
    const delta = ((current - ap.normal) / ap.normal) * 100;
    const anomaly = Math.abs(delta) > 25;
    return {
      ...ap,
      current,
      delta: delta.toFixed(1),
      anomaly,
      severity: Math.abs(delta) > 50 ? "critical" : Math.abs(delta) > 25 ? "warning" : "normal",
      history: Array.from({ length: 12 }, (_, i) => {
        const jitter = Math.random() * 0.08 - 0.04;
        return Math.round(ap.normal * (1 + factor * (i / 12) + jitter));
      }),
    };
  });

  const routes = ROUTES.map((r) => {
    const key = `${r.from}-${r.to}`;
    const factor = scenario.routes[key] || (Math.random() * 0.12 - 0.06);
    const current = Math.max(0, Math.round(r.normal * (1 + factor)));
    const delta = r.normal === 0 ? 0 : ((current - r.normal) / r.normal) * 100;
    const anomaly = Math.abs(delta) > 40 || (r.normal === 0 && current > 0);
    return { ...r, current, delta: delta.toFixed(1), anomaly };
  });

  const alerts = [];
  airports.filter((a) => a.anomaly).forEach((a) => {
    alerts.push({
      id: `ap-${a.icao}`,
      type: a.severity,
      icon: parseFloat(a.delta) < 0 ? "▼" : "▲",
      msg: `${a.icao} / ${a.name}: ${a.delta > 0 ? "+" : ""}${a.delta}% trafik ${parseFloat(a.delta) < 0 ? "düşüşü" : "artışı"} (${a.normal}→${a.current} uçuş/gün)`,
      ts: new Date(now - Math.random() * 3600000).toISOString(),
    });
  });
  routes.filter((r) => r.anomaly).forEach((r) => {
    const fromAp = AIRPORTS.find((a) => a.icao === r.from);
    const toAp = AIRPORTS.find((a) => a.icao === r.to);
    alerts.push({
      id: `rt-${r.from}-${r.to}`,
      type: "warning",
      icon: "⚡",
      msg: `ROTA ANOMALİSİ: ${r.from}→${r.to} (${fromAp?.name}→${toAp?.name}): ${r.normal === 0 ? "Daha önce sıfır olan rotada trafik başladı" : `${r.delta > 0 ? "+" : ""}${r.delta}% değişim`}`,
      ts: new Date(now - Math.random() * 1800000).toISOString(),
    });
  });

  return { airports, routes, alerts, scenario: seed % 4, timestamp: now };
}

// ─── Mini sparkline ───────────────────────────────────────────────────────────
function Sparkline({ data, color }) {
  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;
  const w = 80, h = 28;
  const pts = data
    .map((v, i) => `${(i / (data.length - 1)) * w},${h - ((v - min) / range) * h}`)
    .join(" ");
  return (
    <svg width={w} height={h} style={{ display: "block" }}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" opacity="0.85" />
      <circle
        cx={(w)}
        cy={h - ((data[data.length - 1] - min) / range) * h}
        r="2.5"
        fill={color}
      />
    </svg>
  );
}

// ─── Radar sweep animation ─────────────────────────────────────────────────────
function RadarBlip({ x, y, severity }) {
  const colors = { critical: "#ff2d55", warning: "#ffd60a", normal: "#30d158" };
  const c = colors[severity] || "#30d158";
  return (
    <g>
      <circle cx={x} cy={y} r="4" fill={c} opacity="0.9" />
      <circle cx={x} cy={y} r="4" fill="none" stroke={c} strokeWidth="1" opacity="0.5">
        <animate attributeName="r" from="4" to="14" dur="2s" repeatCount="indefinite" />
        <animate attributeName="opacity" from="0.5" to="0" dur="2s" repeatCount="indefinite" />
      </circle>
    </g>
  );
}

function RadarMap({ airports }) {
  // Basit Mercator projeksiyon
  const W = 520, H = 300;
  const lonMin = -10, lonMax = 60, latMin = 25, latMax = 58;

  function project(lat, lon) {
    const x = ((lon - lonMin) / (lonMax - lonMin)) * W;
    const y = ((latMax - lat) / (latMax - latMin)) * H;
    return [x, y];
  }

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ background: "transparent" }}>
      {/* Grid */}
      {[...Array(8)].map((_, i) => (
        <line
          key={`v${i}`}
          x1={(i / 7) * W}
          y1={0}
          x2={(i / 7) * W}
          y2={H}
          stroke="#1a3a2a"
          strokeWidth="0.5"
        />
      ))}
      {[...Array(6)].map((_, i) => (
        <line
          key={`h${i}`}
          x1={0}
          y1={(i / 5) * H}
          x2={W}
          y2={(i / 5) * H}
          stroke="#1a3a2a"
          strokeWidth="0.5"
        />
      ))}

      {/* Routes */}
      {ROUTES.map((r) => {
        const from = airports.find((a) => a.icao === r.from);
        const to = airports.find((a) => a.icao === r.to);
        if (!from || !to) return null;
        const [x1, y1] = project(from.lat, from.lon);
        const [x2, y2] = project(to.lat, to.lon);
        const routeData = airports
          .find((a) => a.icao === r.from)
          ?.history; // placeholder
        return (
          <line
            key={`${r.from}-${r.to}`}
            x1={x1}
            y1={y1}
            x2={x2}
            y2={y2}
            stroke={r.anomaly ? "#ffd60a" : "#0d3320"}
            strokeWidth={r.anomaly ? 1.5 : 0.8}
            strokeDasharray={r.anomaly ? "4,3" : "none"}
            opacity={r.anomaly ? 0.9 : 0.4}
          />
        );
      })}

      {/* Blips */}
      {airports.map((ap) => {
        const [x, y] = project(ap.lat, ap.lon);
        return (
          <g key={ap.icao}>
            <RadarBlip x={x} y={y} severity={ap.severity} />
            <text
              x={x + 7}
              y={y + 4}
              fontSize="8"
              fill="#4ade80"
              fontFamily="'Courier New', monospace"
              opacity="0.8"
            >
              {ap.icao}
            </text>
          </g>
        );
      })}

      {/* Sweep line overlay */}
      <defs>
        <linearGradient id="sweep" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#00ff88" stopOpacity="0" />
          <stop offset="100%" stopColor="#00ff88" stopOpacity="0.06" />
        </linearGradient>
      </defs>
      <rect x={0} y={0} width={W} height={H} fill="url(#sweep)" opacity="0.3" />
    </svg>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────
export default function FlightOSINT() {
  const [data, setData] = useState(() => generateFlightData(0));
  const [scenario, setScenario] = useState(0);
  const [selected, setSelected] = useState(null);
  const [tab, setTab] = useState("airports");
  const [scanning, setScanning] = useState(false);
  const [tick, setTick] = useState(0);
  const intervalRef = useRef(null);

  const scan = useCallback((sc) => {
    setScanning(true);
    setTimeout(() => {
      setData(generateFlightData(sc));
      setScanning(false);
      setTick((t) => t + 1);
    }, 1200);
  }, []);

  useEffect(() => {
    intervalRef.current = setInterval(() => {
      setTick((t) => {
        const next = t + 1;
        setData(generateFlightData(scenario + next));
        return next;
      });
    }, 15000);
    return () => clearInterval(intervalRef.current);
  }, [scenario]);

  const selAp = data.airports.find((a) => a.icao === selected);
  const critCount = data.alerts.filter((a) => a.type === "critical").length;
  const warnCount = data.alerts.filter((a) => a.type === "warning").length;

  const scenarioLabels = ["Normal", "Orta Doğu Gerilimi", "Rusya Yaptırımları", "Körfez Krizi"];

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "#020d05",
        color: "#d1fae5",
        fontFamily: "'Courier New', 'Lucida Console', monospace",
        fontSize: "12px",
        padding: "0",
        overflow: "hidden",
      }}
    >
      {/* Scanline overlay */}
      <div
        style={{
          position: "fixed",
          inset: 0,
          backgroundImage:
            "repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,255,100,0.015) 2px, rgba(0,255,100,0.015) 4px)",
          pointerEvents: "none",
          zIndex: 999,
        }}
      />

      {/* Header */}
      <div
        style={{
          borderBottom: "1px solid #0d4a20",
          padding: "10px 18px",
          display: "flex",
          alignItems: "center",
          gap: "16px",
          background: "#020d05",
          position: "sticky",
          top: 0,
          zIndex: 100,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <div
            style={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: scanning ? "#ffd60a" : "#30d158",
              boxShadow: scanning ? "0 0 8px #ffd60a" : "0 0 8px #30d158",
              animation: "pulse 1.5s infinite",
            }}
          />
          <span style={{ color: "#4ade80", fontSize: "13px", letterSpacing: "0.15em", fontWeight: "bold" }}>
            FLIGHT-OSINT
          </span>
          <span style={{ color: "#1a5c30", fontSize: "10px" }}>v2.4.1</span>
        </div>

        <div style={{ flex: 1 }} />

        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          {critCount > 0 && (
            <span
              style={{
                background: "#3d0012",
                border: "1px solid #ff2d55",
                color: "#ff2d55",
                padding: "2px 8px",
                fontSize: "10px",
                letterSpacing: "0.1em",
              }}
            >
              ◉ KRİTİK: {critCount}
            </span>
          )}
          {warnCount > 0 && (
            <span
              style={{
                background: "#2d2000",
                border: "1px solid #ffd60a",
                color: "#ffd60a",
                padding: "2px 8px",
                fontSize: "10px",
                letterSpacing: "0.1em",
              }}
            >
              ⚠ UYARI: {warnCount}
            </span>
          )}
          <span style={{ color: "#1a5c30", fontSize: "9px" }}>
            {new Date(data.timestamp).toUTCString().replace("GMT", "UTC")}
          </span>
        </div>
      </div>

      <div style={{ display: "flex", height: "calc(100vh - 45px)" }}>
        {/* Left panel */}
        <div
          style={{
            width: "220px",
            borderRight: "1px solid #0d4a20",
            display: "flex",
            flexDirection: "column",
            flexShrink: 0,
          }}
        >
          <div style={{ padding: "10px 12px", borderBottom: "1px solid #0a2e14", color: "#1a7a38", fontSize: "9px", letterSpacing: "0.15em" }}>
            SENARYO MODU
          </div>
          <div style={{ padding: "8px" }}>
            {scenarioLabels.map((label, i) => (
              <button
                key={i}
                onClick={() => {
                  setScenario(i);
                  scan(i);
                }}
                style={{
                  display: "block",
                  width: "100%",
                  textAlign: "left",
                  background: scenario === i ? "#0a2e14" : "transparent",
                  border: scenario === i ? "1px solid #1a7a38" : "1px solid transparent",
                  color: scenario === i ? "#4ade80" : "#1a5c30",
                  padding: "6px 8px",
                  cursor: "pointer",
                  fontSize: "10px",
                  marginBottom: "2px",
                  letterSpacing: "0.05em",
                  transition: "all 0.15s",
                }}
              >
                {scenario === i ? "▶ " : "  "}
                {label}
              </button>
            ))}
          </div>

          <div style={{ padding: "10px 12px", borderTop: "1px solid #0a2e14", borderBottom: "1px solid #0a2e14", color: "#1a7a38", fontSize: "9px", letterSpacing: "0.15em" }}>
            PYTHON KOD YAPISИ
          </div>
          <div
            style={{
              padding: "10px 12px",
              fontSize: "9px",
              color: "#0d5c25",
              lineHeight: "1.8",
              flex: 1,
              overflowY: "auto",
            }}
          >
            <div style={{ color: "#1a7a38" }}>flightradar24-client</div>
            <div>└ FlightRadar24API()</div>
            <div style={{ color: "#1a7a38", marginTop: "6px" }}>Airports</div>
            <div>├ get_airports()</div>
            <div>└ get_airport_details()</div>
            <div style={{ color: "#1a7a38", marginTop: "6px" }}>Flights</div>
            <div>├ get_flights()</div>
            <div>├ get_flight_details()</div>
            <div>└ get_zones()</div>
            <div style={{ color: "#1a7a38", marginTop: "6px" }}>Anomaly</div>
            <div>├ z_score()</div>
            <div>├ route_delta()</div>
            <div>└ alert_engine()</div>
          </div>

          <div style={{ padding: "10px 12px", borderTop: "1px solid #0a2e14" }}>
            <button
              onClick={() => scan(scenario)}
              disabled={scanning}
              style={{
                width: "100%",
                background: scanning ? "#0a2e14" : "#0d4a20",
                border: "1px solid #1a7a38",
                color: scanning ? "#1a5c30" : "#4ade80",
                padding: "8px",
                cursor: scanning ? "not-allowed" : "pointer",
                fontSize: "10px",
                letterSpacing: "0.12em",
                transition: "all 0.2s",
              }}
            >
              {scanning ? "[ TARAMA... ]" : "[ YENİLE ]"}
            </button>
          </div>
        </div>

        {/* Main */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
          {/* Radar map */}
          <div
            style={{
              borderBottom: "1px solid #0d4a20",
              padding: "10px 14px 0",
              background: "#020d05",
            }}
          >
            <div style={{ fontSize: "9px", color: "#1a5c30", letterSpacing: "0.15em", marginBottom: "6px" }}>
              BÖLGESEL RADAR — AVRUPA / ORTA DOĞU / KAFKASYA
              {scanning && (
                <span style={{ color: "#ffd60a", marginLeft: "12px", animation: "blink 0.6s infinite" }}>
                  ◈ TARAMA DEVAM EDİYOR
                </span>
              )}
            </div>
            <RadarMap airports={data.airports} />
            <div style={{ fontSize: "8px", color: "#0d3320", padding: "4px 0", display: "flex", gap: "16px" }}>
              <span><span style={{ color: "#30d158" }}>●</span> Normal</span>
              <span><span style={{ color: "#ffd60a" }}>●</span> Uyarı (&gt;25%)</span>
              <span><span style={{ color: "#ff2d55" }}>●</span> Kritik (&gt;50%)</span>
              <span><span style={{ color: "#ffd60a" }}>---</span> Anomali rotası</span>
            </div>
          </div>

          {/* Tabs */}
          <div style={{ display: "flex", borderBottom: "1px solid #0d4a20" }}>
            {["airports", "routes", "alerts"].map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                style={{
                  padding: "7px 16px",
                  background: "transparent",
                  border: "none",
                  borderBottom: tab === t ? "2px solid #4ade80" : "2px solid transparent",
                  color: tab === t ? "#4ade80" : "#1a5c30",
                  cursor: "pointer",
                  fontSize: "9px",
                  letterSpacing: "0.12em",
                  textTransform: "uppercase",
                }}
              >
                {t === "airports" ? `HAVALİMANI (${data.airports.length})` : t === "routes" ? `ROTALAR (${data.routes.length})` : `UYARILAR (${data.alerts.length})`}
              </button>
            ))}
          </div>

          {/* Tab content */}
          <div style={{ flex: 1, overflowY: "auto", padding: "8px 12px" }}>
            {tab === "airports" && (
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ color: "#1a5c30", fontSize: "9px", letterSpacing: "0.12em" }}>
                    <th style={{ textAlign: "left", padding: "4px 6px", borderBottom: "1px solid #0a2e14" }}>ICAO</th>
                    <th style={{ textAlign: "left", padding: "4px 6px", borderBottom: "1px solid #0a2e14" }}>HAVALİMANI</th>
                    <th style={{ textAlign: "right", padding: "4px 6px", borderBottom: "1px solid #0a2e14" }}>NORMAL</th>
                    <th style={{ textAlign: "right", padding: "4px 6px", borderBottom: "1px solid #0a2e14" }}>GÜNCEL</th>
                    <th style={{ textAlign: "right", padding: "4px 6px", borderBottom: "1px solid #0a2e14" }}>Δ%</th>
                    <th style={{ textAlign: "center", padding: "4px 6px", borderBottom: "1px solid #0a2e14" }}>TREND</th>
                    <th style={{ textAlign: "center", padding: "4px 6px", borderBottom: "1px solid #0a2e14" }}>DURUM</th>
                  </tr>
                </thead>
                <tbody>
                  {data.airports.map((ap) => {
                    const delta = parseFloat(ap.delta);
                    const colors = { critical: "#ff2d55", warning: "#ffd60a", normal: "#4ade80" };
                    const c = colors[ap.severity];
                    return (
                      <tr
                        key={ap.icao}
                        onClick={() => setSelected(selected === ap.icao ? null : ap.icao)}
                        style={{
                          cursor: "pointer",
                          background: selected === ap.icao ? "#0a2e14" : ap.anomaly ? "#0d1a0a" : "transparent",
                          borderBottom: "1px solid #050e07",
                          transition: "background 0.1s",
                        }}
                      >
                        <td style={{ padding: "5px 6px", color: "#4ade80", fontWeight: "bold" }}>{ap.icao}</td>
                        <td style={{ padding: "5px 6px", color: "#d1fae5" }}>{ap.name}</td>
                        <td style={{ padding: "5px 6px", textAlign: "right", color: "#1a7a38" }}>{ap.normal}</td>
                        <td style={{ padding: "5px 6px", textAlign: "right", color: c, fontWeight: ap.anomaly ? "bold" : "normal" }}>{ap.current}</td>
                        <td style={{ padding: "5px 6px", textAlign: "right", color: delta > 0 ? "#30d158" : delta < 0 ? "#ff2d55" : "#1a5c30", fontWeight: "bold" }}>
                          {delta > 0 ? "+" : ""}{ap.delta}%
                        </td>
                        <td style={{ padding: "5px 6px", textAlign: "center" }}>
                          <Sparkline data={ap.history} color={c} />
                        </td>
                        <td style={{ padding: "5px 6px", textAlign: "center" }}>
                          {ap.anomaly ? (
                            <span style={{ color: c, fontSize: "9px", letterSpacing: "0.1em" }}>
                              {ap.severity === "critical" ? "◉ KRİTİK" : "⚠ UYARI"}
                            </span>
                          ) : (
                            <span style={{ color: "#0d5c25", fontSize: "9px" }}>● NORMAL</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}

            {tab === "routes" && (
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ color: "#1a5c30", fontSize: "9px", letterSpacing: "0.12em" }}>
                    <th style={{ textAlign: "left", padding: "4px 6px", borderBottom: "1px solid #0a2e14" }}>ROTA</th>
                    <th style={{ textAlign: "left", padding: "4px 6px", borderBottom: "1px solid #0a2e14" }}>GÜZERGAH</th>
                    <th style={{ textAlign: "right", padding: "4px 6px", borderBottom: "1px solid #0a2e14" }}>NORMAL</th>
                    <th style={{ textAlign: "right", padding: "4px 6px", borderBottom: "1px solid #0a2e14" }}>GÜNCEL</th>
                    <th style={{ textAlign: "right", padding: "4px 6px", borderBottom: "1px solid #0a2e14" }}>Δ%</th>
                    <th style={{ textAlign: "center", padding: "4px 6px", borderBottom: "1px solid #0a2e14" }}>ANOMALİ</th>
                  </tr>
                </thead>
                <tbody>
                  {data.routes.map((r) => {
                    const fromAp = AIRPORTS.find((a) => a.icao === r.from);
                    const toAp = AIRPORTS.find((a) => a.icao === r.to);
                    const delta = parseFloat(r.delta);
                    return (
                      <tr
                        key={`${r.from}-${r.to}`}
                        style={{
                          background: r.anomaly ? "#0d1a0a" : "transparent",
                          borderBottom: "1px solid #050e07",
                        }}
                      >
                        <td style={{ padding: "5px 6px", color: "#4ade80", fontWeight: "bold", fontFamily: "monospace" }}>
                          {r.from} → {r.to}
                        </td>
                        <td style={{ padding: "5px 6px", color: "#8ecda0", fontSize: "10px" }}>
                          {fromAp?.name} → {toAp?.name}
                        </td>
                        <td style={{ padding: "5px 6px", textAlign: "right", color: "#1a7a38" }}>{r.normal}</td>
                        <td style={{ padding: "5px 6px", textAlign: "right", color: r.anomaly ? "#ffd60a" : "#4ade80", fontWeight: r.anomaly ? "bold" : "normal" }}>
                          {r.current}
                        </td>
                        <td style={{ padding: "5px 6px", textAlign: "right", color: delta > 0 ? "#30d158" : delta < 0 ? "#ff2d55" : "#1a5c30" }}>
                          {r.normal === 0 && r.current > 0 ? "YENİ ROTA" : `${delta > 0 ? "+" : ""}${r.delta}%`}
                        </td>
                        <td style={{ padding: "5px 6px", textAlign: "center" }}>
                          {r.anomaly ? (
                            <span style={{ color: "#ffd60a", fontSize: "9px" }}>⚡ TESPİT EDİLDİ</span>
                          ) : (
                            <span style={{ color: "#0d5c25", fontSize: "9px" }}>—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}

            {tab === "alerts" && (
              <div>
                {data.alerts.length === 0 ? (
                  <div style={{ color: "#1a5c30", padding: "20px", textAlign: "center", letterSpacing: "0.1em" }}>
                    ✓ ANOMALİ TESPİT EDİLMEDİ — SİSTEM NORMAL
                  </div>
                ) : (
                  data.alerts.map((alert) => (
                    <div
                      key={alert.id}
                      style={{
                        borderLeft: `3px solid ${alert.type === "critical" ? "#ff2d55" : "#ffd60a"}`,
                        padding: "8px 12px",
                        marginBottom: "6px",
                        background: alert.type === "critical" ? "#1a0008" : "#1a1400",
                      }}
                    >
                      <div style={{ display: "flex", gap: "8px", alignItems: "flex-start" }}>
                        <span style={{ fontSize: "14px" }}>{alert.icon}</span>
                        <div style={{ flex: 1 }}>
                          <div style={{ color: alert.type === "critical" ? "#ff2d55" : "#ffd60a", lineHeight: "1.5" }}>
                            {alert.msg}
                          </div>
                          <div style={{ color: "#1a5c30", fontSize: "9px", marginTop: "3px" }}>
                            {new Date(alert.ts).toLocaleTimeString("tr-TR")} UTC | ID: {alert.id}
                          </div>
                        </div>
                      </div>
                    </div>
                  ))
                )}

                <div
                  style={{
                    marginTop: "16px",
                    padding: "12px",
                    border: "1px solid #0a2e14",
                    background: "#020d05",
                    fontSize: "9px",
                    color: "#1a5c30",
                    lineHeight: "1.8",
                  }}
                >
                  <div style={{ color: "#1a7a38", marginBottom: "6px", letterSpacing: "0.1em" }}>
                    ANOMALİ ALGILAMA METODOLOJİSİ
                  </div>
                  <div>▸ Z-Score eşiği: |z| &gt; 2.0 → uyarı, |z| &gt; 3.0 → kritik</div>
                  <div>▸ Rota bazlı: 7 günlük rolling average ile karşılaştırma</div>
                  <div>▸ Sıfırdan trafiğe geçen rotalar otomatik bayrak</div>
                  <div>▸ Çoklu havalimanı korelasyon analizi (bölgesel pattern)</div>
                  <div>▸ Zaman serisi: saatlik granülarite, 30 günlük baseline</div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Right panel — airport detail */}
        <div
          style={{
            width: selAp ? "220px" : "0",
            borderLeft: selAp ? "1px solid #0d4a20" : "none",
            overflow: "hidden",
            transition: "width 0.2s",
            flexShrink: 0,
          }}
        >
          {selAp && (
            <div style={{ padding: "12px", width: "220px" }}>
              <div style={{ color: "#4ade80", fontSize: "13px", fontWeight: "bold", marginBottom: "2px" }}>
                {selAp.icao}
              </div>
              <div style={{ color: "#8ecda0", marginBottom: "12px" }}>{selAp.name} / {selAp.country}</div>

              <div style={{ fontSize: "9px", color: "#1a5c30", marginBottom: "6px", letterSpacing: "0.1em" }}>
                TRAFIK ANALİZİ
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "4px" }}>
                <span style={{ color: "#0d5c25" }}>Baseline:</span>
                <span style={{ color: "#4ade80" }}>{selAp.normal} uçuş/gün</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "4px" }}>
                <span style={{ color: "#0d5c25" }}>Güncel:</span>
                <span style={{ color: selAp.anomaly ? "#ffd60a" : "#4ade80" }}>{selAp.current} uçuş/gün</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "12px" }}>
                <span style={{ color: "#0d5c25" }}>Δ:</span>
                <span
                  style={{
                    color: parseFloat(selAp.delta) > 0 ? "#30d158" : "#ff2d55",
                    fontWeight: "bold",
                  }}
                >
                  {parseFloat(selAp.delta) > 0 ? "+" : ""}
                  {selAp.delta}%
                </span>
              </div>

              <div style={{ fontSize: "9px", color: "#1a5c30", marginBottom: "6px", letterSpacing: "0.1em" }}>
                12 SAATLIK TREND
              </div>
              <Sparkline data={selAp.history} color={selAp.severity === "critical" ? "#ff2d55" : selAp.severity === "warning" ? "#ffd60a" : "#30d158"} />

              <div style={{ marginTop: "12px", fontSize: "9px", color: "#1a5c30", letterSpacing: "0.1em" }}>
                KOORDİNAT
              </div>
              <div style={{ color: "#0d5c25", marginTop: "3px" }}>
                {selAp.lat.toFixed(2)}°N {selAp.lon.toFixed(2)}°E
              </div>

              <div style={{ marginTop: "12px", fontSize: "9px", color: "#1a5c30", letterSpacing: "0.1em" }}>
                DURUM
              </div>
              <div
                style={{
                  marginTop: "4px",
                  padding: "4px 8px",
                  background: selAp.severity === "critical" ? "#1a0008" : selAp.severity === "warning" ? "#1a1400" : "#0a1a0a",
                  border: `1px solid ${selAp.severity === "critical" ? "#ff2d55" : selAp.severity === "warning" ? "#ffd60a" : "#1a7a38"}`,
                  color: selAp.severity === "critical" ? "#ff2d55" : selAp.severity === "warning" ? "#ffd60a" : "#4ade80",
                  fontSize: "10px",
                  letterSpacing: "0.1em",
                  textAlign: "center",
                }}
              >
                {selAp.severity === "critical" ? "◉ KRİTİK ANOMALİ" : selAp.severity === "warning" ? "⚠ UYARI SEVİYESİ" : "● NORMAL"}
              </div>
            </div>
          )}
        </div>
      </div>

      <style>{`
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
        @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-track { background: #020d05; }
        ::-webkit-scrollbar-thumb { background: #0d4a20; }
        tr:hover { background: #060f07 !important; }
      `}</style>
    </div>
  );
}
