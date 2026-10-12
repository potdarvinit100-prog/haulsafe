import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { getTrips, deleteTrip, normRecommended, ROUTE_COLORS } from "../api";

function fmtDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d) ? iso : d.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

export default function History({ onOpen, onNew }) {
  const [trips, setTrips] = useState(null);
  const [error, setError] = useState("");
  const [deleting, setDeleting] = useState(null);

  useEffect(() => {
    let alive = true;
    getTrips()
      .then((data) => { if (alive) setTrips(Array.isArray(data) ? data : data.trips || []); })
      .catch((err) => { if (alive) setError(err.message); });
    return () => { alive = false; };
  }, []);

  async function onDelete(t) {
    if (!window.confirm(`Delete "${t.name || t.origin + " → " + t.destination}"? This can't be undone.`)) return;
    setDeleting(t.id);
    try {
      await deleteTrip(t.id);
      setTrips((prev) => prev.filter((x) => x.id !== t.id));
    } catch (err) {
      setError(err.message);
    } finally {
      setDeleting(null);
    }
  }

  return (
    <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }}>
      <div className="page-head">
        <div>
          <h2>Trip History</h2>
          <p>Every trip you've saved, ready to reload in one click.</p>
        </div>
        <button className="btn-primary" onClick={onNew}>+ New trip</button>
      </div>

      {error && <div className="banner error">{error}</div>}

      {trips === null && !error && (
        <div className="trip-list">
          {[0, 1, 2].map((i) => <div key={i} className="skeleton trip-skel" />)}
        </div>
      )}

      {trips && trips.length === 0 && (
        <div className="empty-state glass">
          <div className="empty-emoji">🗺️</div>
          <h3>No saved trips yet</h3>
          <p>Plan a route and hit <b>Save trip</b> — it'll show up here for instant reloads.</p>
          <button className="btn-primary" onClick={onNew}>Plan your first trip</button>
        </div>
      )}

      <AnimatePresence>
        {trips && trips.length > 0 && (
          <motion.div className="trip-list" layout>
            {trips.map((t) => {
              const rec = normRecommended(t.plan_result || {});
              const recIdx = typeof t.recommended_index === "number" ? t.recommended_index : rec.index;
              return (
                <motion.div key={t.id} className="trip-card glass" layout
                  initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, scale: 0.97 }}>
                  <button className="trip-main" onClick={() => onOpen(t)}>
                    <div className="trip-title">
                      {t.name || `${t.origin} → ${t.destination}`}
                      <span className="badge sm">Route {recIdx + 1} recommended</span>
                    </div>
                    <div className="trip-meta">
                      <span>🚚 {Number(t.load_weight_lb).toLocaleString()} lb</span>
                      <span>📅 {fmtDate(t.departure)}</span>
                      <span className="dot" style={{ background: ROUTE_COLORS[recIdx % ROUTE_COLORS.length] }} />
                      <span>Saved {fmtDate(t.created_at)}</span>
                    </div>
                  </button>
                  <button className="icon-btn danger" title="Delete trip"
                    onClick={() => onDelete(t)} disabled={deleting === t.id}>
                    {deleting === t.id ? "…" : "🗑"}
                  </button>
                </motion.div>
              );
            })}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
