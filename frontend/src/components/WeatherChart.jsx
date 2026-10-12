import { useState } from "react";

/** Weather conditions across the trip: wind (mph), rain & snow (in/hr) vs miles. */
export default function WeatherChart({ route }) {
  const [hover, setHover] = useState(null);
  const W = 720, H = 170, PAD = 30;
  const cps = route.checkpoints;
  const maxMile = Math.max(...cps.map((c) => c.mile), 1);
  const maxWind = Math.max(...cps.map((c) => c.wind_mph), 10);
  const maxPrecip = Math.max(...cps.map((c) => Math.max(c.rain_inhr, c.snow_inhr)), 0.5);

  const x = (m) => PAD + (m / maxMile) * (W - PAD * 2);
  const yw = (v) => H - PAD - (v / maxWind) * (H - PAD * 2);
  const yp = (v) => H - PAD - (v / maxPrecip) * (H - PAD * 2);

  const line = (fn) => cps.map((cp, i) => `${i === 0 ? "M" : "L"} ${x(cp.mile).toFixed(1)} ${fn(cp).toFixed(1)}`).join(" ");
  const windD = line((cp) => yw(cp.wind_mph));
  const rainD = line((cp) => yp(cp.rain_inhr));
  const snowD = line((cp) => yp(cp.snow_inhr));

  return (
    <div className="weatherchart">
      <h3>Conditions — wind, rain &amp; snow along the route</h3>
      <svg viewBox={`0 0 ${W} ${H}`} onMouseLeave={() => setHover(null)}>
        {[0.25, 0.5, 0.75].map((f) => (
          <line key={f} x1={PAD} x2={W - PAD} y1={H - PAD - f * (H - PAD * 2)} y2={H - PAD - f * (H - PAD * 2)}
            stroke="currentColor" strokeOpacity="0.1" strokeDasharray="4 4" />
        ))}
        <path d={`${windD} L ${x(maxMile)} ${H - PAD} L ${x(0)} ${H - PAD} Z`} fill="#38bdf822" />
        <path d={windD} fill="none" stroke="#38bdf8" strokeWidth="2.5" />
        <path d={rainD} fill="none" stroke="#3b82f6" strokeWidth="2" strokeDasharray="6 3" />
        <path d={snowD} fill="none" stroke="#c084fc" strokeWidth="2" strokeDasharray="2 3" />
        {cps.map((cp, i) => (
          <circle key={i} cx={x(cp.mile)} cy={yw(cp.wind_mph)} r={hover === i ? 5.5 : 3}
            fill="#38bdf8" stroke="#0b1220" strokeWidth="1.2"
            onMouseEnter={() => setHover(i)} style={{ cursor: "pointer" }} />
        ))}
        {hover !== null && (
          <g>
            <rect x={Math.min(x(cps[hover].mile) + 10, W - 230)} y={8} width="220" height="56" rx="8" className="chart-tip" />
            <text x={Math.min(x(cps[hover].mile) + 20, W - 220)} y={28} fontSize="12" fontWeight="700" fill="currentColor">
              Mile {cps[hover].mile}
            </text>
            <text x={Math.min(x(cps[hover].mile) + 20, W - 220)} y={46} fontSize="11" fill="currentColor" opacity="0.75">
              Wind {cps[hover].wind_mph} mph · Rain {cps[hover].rain_inhr} in/hr · Snow {cps[hover].snow_inhr} in/hr
            </text>
          </g>
        )}
        <text x={4} y={16} fontSize="10" fill="#38bdf8" opacity="0.8">wind mph (max {Math.round(maxWind)})</text>
        <text x={4} y={H - 6} fontSize="10" fill="#3b82f6" opacity="0.8">rain/snow in/hr</text>
      </svg>
      <div className="wc-legend">
        <span><span className="dot" style={{ background: "#38bdf8" }} />Wind (mph)</span>
        <span><span className="dot" style={{ background: "#3b82f6" }} />Rain (in/hr)</span>
        <span><span className="dot" style={{ background: "#c084fc" }} />Snow (in/hr)</span>
      </div>
      <div className="chart-x">0 mi <span>{Math.round(maxMile)} mi</span></div>
    </div>
  );
}
