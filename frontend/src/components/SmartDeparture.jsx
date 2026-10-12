import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { smartDeparture } from "../api";

function fmtLocal(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  return d.toLocaleString([], { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function StatRow({ data, title }) {
  if (!data) return null;
  return (
    <div className="sd-stats">
      <span className="sd-title">{title}</span>
      <span>No Travel <b>{Math.round(data.no_travel_miles || 0)}</b> mi</span>
      <span>Severe <b>{Math.round(data.severe_miles || 0)}</b> mi</span>
      <span>High <b>{Math.round(data.high_miles || 0)}</b> mi</span>
      <span>avg <b>{Number(data.avg_score || 0).toFixed(2)}</b></span>
    </div>
  );
}

/**
 * Smart departure advisor: scans alternative departure windows and
 * recommends the safest one. Props: inputs (plan payload), onUseDeparture(iso).
 */
export default function SmartDeparture({ inputs, onUseDeparture }) {
  const [state, setState] = useState("idle"); // idle | loading | error | done
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  async function analyze() {
    setState("loading"); setError("");
    try {
      const r = await smartDeparture(inputs);
      setResult(r);
      setState("done");
    } catch (err) {
      setError(err.message);
      setState("error");
    }
  }

  const cur = result && result.current;
  const best = result && result.best;
  const alts = (result && result.alternatives) || [];

  return (
    <div className="smart glass">
      <div className="smart-head">
        <div>
          <h3>🧠 Smart departure</h3>
          <p>Scan nearby departure windows for a safer trip — same route, better timing.</p>
        </div>
        {state !== "loading" && (
          <button className="btn-primary" onClick={analyze}>
            {state === "done" ? "Re-analyze" : "Analyze departures"}
          </button>
        )}
      </div>

      {state === "loading" && (
        <div className="sd-loading">
          <div className="spinner" />
          <span>Scanning departure windows…</span>
        </div>
      )}

      <AnimatePresence>
        {state === "error" && <motion.div className="banner error" initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}}>{error}</motion.div>}
        {state === "done" && (
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
            <StatRow data={cur} title={`Current — ${cur && cur.departure ? fmtLocal(cur.departure) : ""}`} />

            {best ? (
              <div className="sd-best">
                <div className="sd-best-text">
                  <span className="badge">BEST WINDOW</span>
                  <p>
                    Leave at <b>{fmtLocal(best.departure)}</b> instead —{" "}
                    <b>{Math.max(0, Math.round((cur.severe_miles || 0) - (best.severe_miles || 0)))}</b> fewer severe miles,{" "}
                    <b>{Math.max(0, Math.round((cur.high_miles || 0) - (best.high_miles || 0)))}</b> fewer high miles.
                  </p>
                  <StatRow data={best} title="Projected" />
                </div>
                <button className="btn-primary" onClick={() => onUseDeparture(best.departure)}>
                  Use this departure
                </button>
              </div>
            ) : (
              <div className="sd-optimal">✅ Your departure already looks optimal for the next 48 hours.</div>
            )}

            {alts.length > 0 && (
              <details className="sd-alts">
                <summary>Other windows checked ({alts.length})</summary>
                {alts.map((a, i) => (
                  <StatRow key={i} data={a} title={a.departure ? fmtLocal(a.departure) : `Window ${i + 1}`} />
                ))}
              </details>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
