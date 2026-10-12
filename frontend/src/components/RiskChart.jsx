import { useState } from "react";
import { RISK_COLORS } from "../api";

const LEVELS = ["Low", "Moderate", "High", "Severe", "No Travel"];

/** Risk profile: risk score vs miles for the selected route. */
export default function RiskChart({ route }) {
  const [hover, setHover] = useState(null);
  const W = 720, H = 150, PAD = 28;
  const cps = route.checkpoints;
  const maxMile = Math.max(...cps.map((c) => c.mile), 1);

  const x = (m) => PAD + (m / maxMile) * (W - PAD * 2);
  const y = (lvl) => H - PAD - (LEVELS.indexOf(lvl) / 4) * (H - PAD * 2);

  // stepped area path
  let d = `M ${x(0)} ${y(cps[0].level)}`;
  cps.forEach((cp, i) => {
    const nx = i + 1 < cps.length ? x(cps[i + 1].mile) : x(maxMile);
    d += ` L ${nx} ${y(cp.level)}`;
  });
  const area = `${d} L ${x(maxMile)} ${H - PAD} L ${x(0)} ${H - PAD} Z`;

  return (
    <div className="riskchart">
      <h3>Risk profile — Route risk across the trip</h3>
      <svg viewBox={`0 0 ${W} ${H}`} onMouseLeave={() => setHover(null)}>
        {[0, 1, 2, 3, 4].map((i) => (
          <g key={i}>
            <line x1={PAD} x2={W - PAD} y1={y(LEVELS[i])} y2={y(LEVELS[i])}
              stroke="currentColor" strokeOpacity="0.12" strokeDasharray="4 4" />
            <text x={4} y={y(LEVELS[i]) + 4} fontSize="10" fill="currentColor" opacity="0.55">{LEVELS[i]}</text>
          </g>
        ))}
        <path d={area} fill="url(#riskGrad)" opacity="0.85" />
        <path d={d} fill="none" stroke="#f97316" strokeWidth="2.5" />
        {cps.map((cp, i) => (
          <circle key={i} cx={x(cp.mile)} cy={y(cp.level)} r={hover === i ? 6 : 3.5}
            fill={RISK_COLORS[cp.level]} stroke="#0b1220" strokeWidth="1.5"
            onMouseEnter={() => setHover(i)} style={{ cursor: "pointer" }} />
        ))}
        {hover !== null && (
          <g>
            <rect x={Math.min(x(cps[hover].mile) + 10, W - 190)} y={10} width="180" height="54" rx="8" className="chart-tip" />
            <text x={Math.min(x(cps[hover].mile) + 20, W - 180)} y={30} fontSize="12" fontWeight="700" fill="currentColor">
              Mile {cps[hover].mile} — {cps[hover].level}
            </text>
            <text x={Math.min(x(cps[hover].mile) + 20, W - 180)} y={48} fontSize="11" fill="currentColor" opacity="0.7">
              Wind {cps[hover].wind_mph} mph · Rain {cps[hover].rain_inhr} in/hr
            </text>
          </g>
        )}
        <defs>
          <linearGradient id="riskGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#f97316" stopOpacity="0.55" />
            <stop offset="100%" stopColor="#22c55e" stopOpacity="0.15" />
          </linearGradient>
        </defs>
      </svg>
      <div className="chart-x">0 mi <span>{Math.round(maxMile)} mi</span></div>
    </div>
  );
}
