import { RISK_COLORS } from "../api";

const SEGMENTS = [
  { key: "low", label: "Low", color: RISK_COLORS["Low"] },
  { key: "moderate", label: "Moderate", color: RISK_COLORS["Moderate"] },
  { key: "high", label: "High", color: RISK_COLORS["High"] },
  { key: "severe", label: "Severe", color: RISK_COLORS["Severe"] },
  { key: "noTravel", label: "No Travel", color: RISK_COLORS["No Travel"] },
];

/**
 * Stacked horizontal bar of route miles by risk level.
 * breakdown: {low, moderate, high, severe, noTravel} in miles (+ optional avg).
 */
export default function RiskBar({ breakdown }) {
  if (!breakdown) return null;
  const total = SEGMENTS.reduce((s, g) => s + (Number(breakdown[g.key]) || 0), 0);
  const safeTotal = total > 0 ? total : 1;
  return (
    <div className="riskbar">
      <div className="riskbar-track">
        {SEGMENTS.map((g) => {
          const v = Number(breakdown[g.key]) || 0;
          if (v <= 0) return null;
          return (
            <div key={g.key} className="riskbar-seg" title={`${g.label}: ${Math.round(v)} mi`}
              style={{ width: `${(v / safeTotal) * 100}%`, background: g.color }} />
          );
        })}
      </div>
      <div className="riskbar-nums">
        {SEGMENTS.map((g) => (
          <span key={g.key} className="riskbar-num">
            <span className="dot" style={{ background: g.color }} />
            {g.label} {Math.round(Number(breakdown[g.key]) || 0)} mi
          </span>
        ))}
        {breakdown.avg !== undefined && breakdown.avg !== null && (
          <span className="riskbar-num avg">avg risk {Number(breakdown.avg).toFixed(2)}</span>
        )}
      </div>
    </div>
  );
}
