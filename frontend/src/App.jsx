import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import RouteMap from "./components/RouteMap";
import RiskChart from "./components/RiskChart";
import RiskBar from "./components/RiskBar";
import WeatherChart from "./components/WeatherChart";
import SmartDeparture from "./components/SmartDeparture";
import BuddyChat from "./components/BuddyChat";
import Auth from "./components/Auth";
import History from "./components/History";
import {
  planRoutes, corridorData, saveTrip, getTrip, me,
  getToken, clearToken,
  RISK_COLORS, ROUTE_COLORS, normRecommended, rankingLabel,
} from "./api";
import "./App.css";

const LEVELS = ["Low", "Moderate", "High", "Severe", "No Travel"];

function fmtDur(s) {
  const h = Math.floor(s / 3600), m = Math.round((s % 3600) / 60);
  return `${h}h ${m}m`;
}
function fmtTime(iso) {
  return new Date(iso).toUTCString().slice(5, 22) + " UTC";
}
function pad(n) { return String(n).padStart(2, "0"); }
function fmtLocalInput(d) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
function toLocalInput(iso) {
  const d = new Date(iso);
  return isNaN(d) ? "" : fmtLocalInput(d);
}
function nextFullHour() {
  const d = new Date();
  d.setMinutes(0, 0, 0);
  d.setHours(d.getHours() + 1);
  return fmtLocalInput(d);
}
function forecastBounds() {
  const now = Date.now();
  return {
    min: fmtLocalInput(new Date(now - 3600e3)),
    max: fmtLocalInput(new Date(now + 48 * 3600e3)),
  };
}

/** Miles by level for a route — prefers the backend's risk_breakdown, falls back to checkpoints. */
function breakdownOf(route) {
  const b = route.risk_breakdown;
  if (b) {
    return {
      low: Number(b.low_miles || 0),
      moderate: Number(b.moderate_miles || 0),
      high: Number(b.high_miles || 0),
      severe: Number(b.severe_miles || 0),
      noTravel: Number(b.no_travel_miles || 0),
      avg: b.avg_score,
    };
  }
  const cps = route.checkpoints || [];
  const miles = { Low: 0, Moderate: 0, High: 0, Severe: 0, "No Travel": 0 };
  cps.forEach((cp, i) => {
    const seg = i + 1 < cps.length ? cps[i + 1].mile - cp.mile : 0;
    miles[cp.level] = (miles[cp.level] || 0) + seg;
  });
  return { low: miles.Low, moderate: miles.Moderate, high: miles.High, severe: miles.Severe, noTravel: miles["No Travel"] };
}

function routeStats(route) {
  const counts = {};
  (route.checkpoints || []).forEach((cp) => { counts[cp.level] = (counts[cp.level] || 0) + 1; });
  return { counts };
}

const BOUNDS = forecastBounds();

/* ---------- motion presets: smooth page + card transitions ---------- */
const pageVariants = {
  initial: { opacity: 0, y: 22, scale: 0.995 },
  animate: { opacity: 1, y: 0, scale: 1 },
  exit: { opacity: 0, y: -14, scale: 0.998 },
};
const pageTransition = { duration: 0.38, ease: [0.22, 1, 0.36, 1] };

const resultsVariants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.09, delayChildren: 0.05 } },
  exit: { opacity: 0, y: -10, transition: { duration: 0.22 } },
};
const panelVariants = {
  hidden: { opacity: 0, y: 26 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: [0.22, 1, 0.36, 1] } },
};
const cardVariants = {
  hidden: { opacity: 0, y: 22, scale: 0.97 },
  show: (i) => ({
    opacity: 1, y: 0, scale: 1,
    transition: { duration: 0.45, delay: 0.06 * i, ease: [0.22, 1, 0.36, 1] },
  }),
};

export default function App() {
  const [dark, setDark] = useState(true);
  const [view, setView] = useState("planner"); // planner | history | auth
  const [user, setUser] = useState(null);
  const [authMode, setAuthMode] = useState("login");
  const [authNotice, setAuthNotice] = useState("");

  const [form, setForm] = useState({
    origin: "Chicago, IL",
    destination: "Denver, CO",
    departure: nextFullHour(),
    load_weight_lb: 35000,
    sample_miles: 25,
  });
  const [plan, setPlan] = useState(null);
  const [payload, setPayload] = useState(null);
  const [selected, setSelected] = useState(0);
  const [corridor, setCorridor] = useState(null);
  const [heatHour, setHeatHour] = useState(0);
  const [showHeat, setShowHeat] = useState(false);
  const [loading, setLoading] = useState(false);
  const [heatLoading, setHeatLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [truckMile, setTruckMile] = useState(null);
  const [driving, setDriving] = useState(false);
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveName, setSaveName] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");
  const [mapStyle, setMapStyle] = useState("streets"); // streets | terrain | satellite
  const driveRef = useRef(null);

  const rec = plan ? normRecommended(plan) : { index: 0, reasoning: "", ranking: [] };

  // live telemetry: nearest checkpoint at/below the truck's current mile
  const teleCp = plan && truckMile !== null
    ? [...plan.routes[selected].checkpoints].reverse().find((c) => c.mile <= truckMile)
      || plan.routes[selected].checkpoints[0]
    : null;

  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
  }, [dark]);

  // restore session — auth is an optional enhancement, never blocks planning
  useEffect(() => {
    if (!getToken()) return;
    me().then((d) => setUser({ username: d.username })).catch(() => {});
  }, []);

  // truck animation loop
  const mileRef = useRef(0);
  useEffect(() => {
    if (!driving || !plan) return;
    const total = plan.routes[selected].total_miles;
    driveRef.current = setInterval(() => {
      mileRef.current += total / 120;
      if (mileRef.current >= total) {
        mileRef.current = total;
        setDriving(false);
      }
      setTruckMile(mileRef.current);
    }, 100);
    return () => clearInterval(driveRef.current);
  }, [driving, plan, selected]);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  function resetResults() {
    setPlan(null); setPayload(null); setCorridor(null);
    setShowHeat(false); setTruckMile(null); setDriving(false);
    mileRef.current = 0; setSaveOpen(false); setSaveMsg(""); setError(""); setNotice("");
  }

  async function onPlan(e, formOverride) {
    if (e) e.preventDefault();
    const f = formOverride || form;
    setLoading(true); setError(""); setNotice("");
    setPlan(null); setPayload(null); setCorridor(null);
    setShowHeat(false); setTruckMile(null); setDriving(false);
    mileRef.current = 0; setSaveOpen(false); setSaveMsg("");
    try {
      const p = {
        origin: f.origin,
        destination: f.destination,
        departure: new Date(f.departure).toISOString(),
        load_weight_lb: Number(f.load_weight_lb),
        sample_miles: Number(f.sample_miles),
      };
      const res = await planRoutes(p);
      setPlan(res);
      setPayload(p);
      setSelected(normRecommended(res).index);
    } catch (err) {
      if (err.status === 401) setUser(null);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function onHeat() {
    if (!plan) return;
    setHeatLoading(true); setError("");
    try {
      const route = plan.routes[selected];
      const c = await corridorData({
        path: route.path,
        departure: payload.departure,
        load_weight_lb: payload.load_weight_lb,
      });
      setCorridor(c); setHeatHour(0); setShowHeat(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setHeatLoading(false);
    }
  }

  function toggleDrive() {
    if (!plan) return;
    if (driving) { setDriving(false); return; }
    const total = plan.routes[selected].total_miles;
    if (truckMile === null || truckMile >= total) {
      mileRef.current = 0;
      setTruckMile(0);
    } else {
      mileRef.current = truckMile;
    }
    setDriving(true);
  }

  function onSelect(i) {
    setSelected(i); setCorridor(null); setShowHeat(false);
    setTruckMile(null); setDriving(false); mileRef.current = 0;
  }

  function useSmartDeparture(iso) {
    const f = { ...form, departure: toLocalInput(iso) };
    setForm(f);
    setNotice(`Departure updated to ${new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })} — re-planning…`);
    onPlan(null, f);
  }

  async function onSaveTrip() {
    if (!user) {
      setAuthNotice("Log in or create an account to save trips to your history.");
      setAuthMode("login");
      setView("auth");
      return;
    }
    setSaving(true); setError("");
    try {
      await saveTrip({
        name: saveName.trim() || `${form.origin} → ${form.destination}`,
        origin: form.origin,
        destination: form.destination,
        departure: payload.departure,
        load_weight_lb: payload.load_weight_lb,
        sample_miles: payload.sample_miles,
        plan_result: plan,
      });
      setSaveMsg("Trip saved ✓ — find it under Trip History.");
      setSaveOpen(false);
      setSaveName("");
    } catch (err) {
      if (err.status === 401) { setUser(null); setView("auth"); }
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function openTrip(t) {
    setLoading(true); setError(""); setNotice("");
    try {
      const full = await getTrip(t.id);
      const pr = full.plan_result || full;
      setForm({
        origin: t.origin,
        destination: t.destination,
        departure: toLocalInput(t.departure),
        load_weight_lb: t.load_weight_lb,
        sample_miles: t.sample_miles,
      });
      setPayload({
        origin: t.origin, destination: t.destination, departure: t.departure,
        load_weight_lb: Number(t.load_weight_lb), sample_miles: Number(t.sample_miles),
      });
      setPlan(pr);
      const idx = typeof t.recommended_index === "number" ? t.recommended_index : normRecommended(pr).index;
      setSelected(idx);
      setCorridor(null); setShowHeat(false); setTruckMile(null); setDriving(false);
      setSaveOpen(false); setSaveMsg("");
      setView("planner");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function logout() {
    clearToken();
    setUser(null);
    setView("planner");
    setNotice("Logged out.");
  }

  function goPlanner() { resetResults(); setView("planner"); }

  const heatMax = corridor && corridor.hours ? corridor.hours.length - 1 : 48;

  return (
    <div className="app">
      <div className="bg-glow" />

      <motion.header className="topbar" initial={{ opacity: 0, y: -18 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>
        <button className="brand" onClick={() => setView("planner")} title="HaulSafe home">
          <span className="brand-mark">🚚</span>
          <span className="brand-text">
            <span className="brand-name">HaulSafe</span>
            <span className="brand-tag">Weather-aware routing for heavy hauls.</span>
          </span>
        </button>
        <nav className="nav">
          <button className={`nav-btn ${view === "planner" ? "active" : ""}`} onClick={goPlanner}>New Trip</button>
          <button className={`nav-btn ${view === "history" ? "active" : ""}`}
            onClick={() => { if (!user) { setAuthNotice("Log in to view your trip history."); setAuthMode("login"); setView("auth"); } else setView("history"); }}>
            Trip History
          </button>
          {user ? (
            <>
              <span className="nav-user">👤 {user.username}</span>
              <button className="nav-btn ghost-btn" onClick={logout}>Logout</button>
            </>
          ) : (
            <button className="nav-btn ghost-btn" onClick={() => { setAuthNotice(""); setAuthMode("login"); setView("auth"); }}>Log in</button>
          )}
          <button className="theme-toggle" onClick={() => setDark(!dark)} title="Toggle dark / light mode">
            {dark ? "☀️" : "🌙"}
          </button>
        </nav>
      </motion.header>

      <AnimatePresence>{error && <motion.div className="banner error" initial={{ opacity: 0, y: -12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}>{error}</motion.div>}</AnimatePresence>
      <AnimatePresence>{notice && <motion.div className="banner notice" initial={{ opacity: 0, y: -12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}>{notice}</motion.div>}</AnimatePresence>

      <AnimatePresence mode="wait">
      {view === "auth" && (
        <motion.div key="auth" variants={pageVariants} initial="initial" animate="animate" exit="exit" transition={pageTransition}>
          <Auth mode={authMode} setMode={setAuthMode} notice={authNotice}
            onAuth={(u) => { setUser(u); setAuthNotice(""); setNotice(`Welcome, ${u.username}!`); setView("planner"); }} />
        </motion.div>
      )}

      {view === "history" && user && (
        <motion.div key="history" variants={pageVariants} initial="initial" animate="animate" exit="exit" transition={pageTransition}>
          <History onOpen={openTrip} onNew={goPlanner} />
        </motion.div>
      )}

      {view === "planner" && (
        <motion.div key="planner" variants={pageVariants} initial="initial" animate="animate" exit="exit" transition={pageTransition}>
          <motion.section className="hero" initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45 }}>
            <h2>Find the safest road for your load.</h2>
            <p>HaulSafe compares route options against live weather forecasts at every checkpoint —
              wind, rain and snow scored for your exact load weight — and recommends the safest departure.</p>
          </motion.section>

          <motion.form className="controls glass" onSubmit={onPlan}
            initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45, delay: 0.08 }}>
            <label>Origin<input value={form.origin} onChange={set("origin")} required placeholder="e.g. Chicago, IL" /></label>
            <label>Destination<input value={form.destination} onChange={set("destination")} required placeholder="e.g. Denver, CO" /></label>
            <label>Departure (local)
              <input type="datetime-local" value={form.departure} onChange={set("departure")}
                min={BOUNDS.min} max={BOUNDS.max} required />
            </label>
            <label>Load weight (lb)<input type="number" value={form.load_weight_lb} onChange={set("load_weight_lb")} min="0" /></label>
            <label>Sample every
              <select value={form.sample_miles} onChange={set("sample_miles")}>
                <option value="10">10 miles</option>
                <option value="25">25 miles</option>
                <option value="50">50 miles</option>
              </select>
            </label>
            <button type="submit" disabled={loading}>{loading ? "Planning…" : "Plan routes"}</button>
          </motion.form>
          <p className="hint">Forecast window: departures between {BOUNDS.min.replace("T", " ")} and {BOUNDS.max.replace("T", " ")} local.</p>

          {loading && (
            <div className="routes">
              {[0, 1, 2].map((i) => <div key={i} className="skeleton card-skel" />)}
            </div>
          )}

          <AnimatePresence mode="wait">
            {plan && (
              <motion.div key="results" variants={resultsVariants} initial="hidden" animate="show" exit="exit">
                <motion.div className="rec-panel glass" variants={panelVariants}>
                  <div className="rec-head">
                    <span className="badge">RECOMMENDED</span>
                    <b>Route {rec.index + 1}</b>
                    {rankingLabel(rec.ranking) && <span className="ranking">Ranking: {rankingLabel(rec.ranking)}</span>}
                  </div>
                  {rec.reasoning && <p className="rec-reason">{rec.reasoning}</p>}
                  {!rec.reasoning && (
                    <p className="rec-reason">Ranked by: fewest No Travel miles → fewest Severe miles → fewest High miles → lowest average risk → shortest travel time.</p>
                  )}
                  <div className="save-trip">
                    {!saveOpen ? (
                      <button className="btn-secondary" onClick={() => setSaveOpen(true)}>💾 Save trip</button>
                    ) : (
                      <div className="save-inline">
                        <input value={saveName} onChange={(e) => setSaveName(e.target.value)}
                          placeholder={`${form.origin} → ${form.destination}`} maxLength="80" />
                        <button className="btn-primary" onClick={onSaveTrip} disabled={saving}>
                          {saving ? "Saving…" : "Save"}
                        </button>
                        <button className="btn-secondary" onClick={() => setSaveOpen(false)}>Cancel</button>
                      </div>
                    )}
                    {saveMsg && <span className="save-msg">{saveMsg}</span>}
                  </div>
                </motion.div>

                <motion.div className="routes" variants={panelVariants}>
                  {plan.routes.map((r, i) => {
                    const s = routeStats(r);
                    const bd = breakdownOf(r);
                    const isRec = i === rec.index;
                    return (
                      <motion.button key={i} className={`card glass ${i === selected ? "active" : ""} ${isRec ? "rec" : ""}`}
                        onClick={() => onSelect(i)}
                        variants={cardVariants} custom={i} layout
                        whileHover={{ y: -5, transition: { duration: 0.18 } }}
                        whileTap={{ scale: 0.97 }}>
                        <div className="card-head">
                          <span className="dot" style={{ background: ROUTE_COLORS[i % ROUTE_COLORS.length] }} />
                          <b>Route {i + 1}</b>
                          {isRec && <span className="badge">RECOMMENDED</span>}
                          {r.detour && <span className="tag">detour</span>}
                        </div>
                        <div className="card-stats">
                          <span>{r.total_miles.toLocaleString()} mi</span>
                          <span>{fmtDur(r.duration_s)}</span>
                          <span>{(r.checkpoints || []).length} checkpoints</span>
                        </div>
                        <RiskBar breakdown={bd} />
                        <div className="card-risk">
                          {LEVELS.map((l) => s.counts[l] ? (
                            <span key={l} className="pill" style={{ background: RISK_COLORS[l] }}>{l}: {s.counts[l]}</span>
                          ) : null)}
                        </div>
                      </motion.button>
                    );
                  })}
                </motion.div>

                <motion.div className="toolbar glass" variants={panelVariants}>
                  <button onClick={onHeat} disabled={heatLoading}>
                    {heatLoading ? "Loading heatmap…" : showHeat ? "Reload heatmap" : "🌡️ 49h heatmap"}
                  </button>
                  <button onClick={toggleDrive} className={driving ? "warn" : ""}>
                    {driving ? "⏸ Pause trip" : truckMile ? "▶ Resume trip" : "▶ Drive the route"}
                  </button>
                  {truckMile !== null && (
                    <span className="trip-progress">Truck at mile {Math.round(truckMile)} / {Math.round(plan.routes[selected].total_miles)}</span>
                  )}
                  {showHeat && corridor && (
                    <label className="slider">
                      +{heatHour}h <span className="ts">{fmtTime(corridor.hours[heatHour])}</span>
                      <input type="range" min="0" max={heatMax} value={heatHour} onChange={(e) => setHeatHour(Number(e.target.value))} />
                    </label>
                  )}
                  {showHeat && <button className="ghost" onClick={() => setShowHeat(false)}>Hide heatmap</button>}
                  <span className="mapstyle">
                    {[["streets", "Streets"], ["terrain", "Terrain"], ["satellite", "Satellite"]].map(([k, label]) => (
                      <button key={k} className={mapStyle === k ? "on" : ""} onClick={() => setMapStyle(k)}>{label}</button>
                    ))}
                  </span>
                </motion.div>

                <AnimatePresence>
                  {teleCp && (
                    <motion.div className="telemetry glass" key="telemetry"
                      initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                      transition={{ duration: 0.3 }}>
                      <span className="tele-mile">🚚 Mile {Math.round(truckMile)}</span>
                      <AnimatePresence mode="wait">
                        <motion.span key={teleCp.level} className="tele-badge"
                          style={{ background: RISK_COLORS[teleCp.level] }}
                          initial={{ opacity: 0, scale: 0.85 }} animate={{ opacity: 1, scale: 1 }}
                          exit={{ opacity: 0, scale: 0.85 }} transition={{ duration: 0.2 }}>
                          {teleCp.level}
                        </motion.span>
                      </AnimatePresence>
                      <span className="tele-conds">
                        Wind <b>{teleCp.wind_mph} mph</b> · Rain <b>{teleCp.rain_inhr} in/hr</b> · Snow <b>{teleCp.snow_inhr} in/hr</b>
                      </span>
                      <span className="tele-conds">Checkpoint mile {teleCp.mile}</span>
                    </motion.div>
                  )}
                </AnimatePresence>

                <motion.div className="mapwrap" variants={panelVariants}>
                  <RouteMap plan={plan} corridor={corridor} selectedRoute={selected}
                    recommendedIndex={rec.index} heatHour={heatHour} showHeat={showHeat}
                    dark={dark} truckMile={truckMile} mapStyle={mapStyle} />
                </motion.div>

                <motion.div variants={panelVariants}>
                  <RiskChart route={plan.routes[selected]} />
                </motion.div>

                <motion.div variants={panelVariants}>
                  <WeatherChart route={plan.routes[selected]} />
                </motion.div>

                <motion.div variants={panelVariants}>
                  <SmartDeparture inputs={payload} onUseDeparture={useSmartDeparture} />
                </motion.div>

                <motion.div className="legend" variants={panelVariants}>
                  {LEVELS.map((l) => <span key={l}><span className="dot" style={{ background: RISK_COLORS[l] }} />{l}</span>)}
                  <span className="note">Times in UTC · Weather: Open-Meteo · Routing: OSRM · Click a checkpoint for details</span>
                </motion.div>
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>
      )}
      </AnimatePresence>

      <footer>HaulSafe — weather-aware routing for heavy hauls.</footer>

      <BuddyChat plan={plan} rec={rec} selected={selected} />
    </div>
  );
}
