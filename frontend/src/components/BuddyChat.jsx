import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

/** Road Buddy — a friendly built-in assistant that answers questions from the trip data. */
function answer(q, ctx) {
  const t = q.toLowerCase().trim();
  const { plan, rec, selected } = ctx;
  if (!plan) return "Plan a trip first and I'll help you read it — ask me which route is safest, or about weather at any mile.";

  const routes = plan.routes;
  const r = routes[selected];
  const has = (...ws) => ws.some((w) => t.includes(w));

  if (has("safest", "best route", "recommend", "which route", "which one")) {
    return `Route ${rec.index + 1} is the recommendation. ${rec.reasoning || "It scored best on fewest severe miles, then high miles, then average risk."}`;
  }
  if (has("compare", "difference", "vs", "versus")) {
    return routes.map((x, i) =>
      `Route ${i + 1}: ${Math.round(x.total_miles)} mi, ${Math.round(x.duration_s / 3600)}h${Math.round((x.duration_s % 3600) / 60)}m, avg risk ${x.risk_breakdown ? x.risk_breakdown.avg_score.toFixed(2) : "?"}${i === rec.index ? " ⭐ recommended" : ""}`
    ).join("\n");
  }
  const mileMatch = t.match(/mile\s*(\d+)/);
  if (mileMatch || has("wind", "rain", "snow", "weather", "condition")) {
    let cp;
    if (mileMatch) {
      const m = Number(mileMatch[1]);
      cp = [...r.checkpoints].reverse().find((c) => c.mile <= m) || r.checkpoints[0];
    } else {
      const worst = [...r.checkpoints].sort((a, b) =>
        ["Low", "Moderate", "High", "Severe", "No Travel"].indexOf(b.level) - ["Low", "Moderate", "High", "Severe", "No Travel"].indexOf(a.level))[0];
      cp = worst;
      if (worst.level === "Low") return `Good news — every checkpoint on Route ${selected + 1} is Low risk. Calm trip ahead.`;
    }
    return `Mile ${cp.mile} on Route ${selected + 1}: ${cp.level} risk.\nWind ${cp.wind_mph} mph · Rain ${cp.rain_inhr} in/hr · Snow ${cp.snow_inhr} in/hr.\n${cp.reasons.join("; ")}`;
  }
  if (has("arrive", "eta", "reach", "how long", "duration", "time")) {
    const last = r.checkpoints[r.checkpoints.length - 1];
    const eta = last ? new Date(last.eta).toUTCString().slice(0, 22) + " UTC" : "?";
    return `Route ${selected + 1} covers ${Math.round(r.total_miles)} miles in about ${Math.round(r.duration_s / 3600)}h ${Math.round((r.duration_s % 3600) / 60)}m. Estimated arrival: ${eta}.`;
  }
  if (has("no travel")) {
    return `"No Travel" means conditions are too dangerous for a truck at your load weight — e.g. wind at/above 55 mph, or 45–54 mph winds with a load over 30,000 lb. The recommendation always avoids No Travel miles first.`;
  }
  if (has("load", "weight", "heavy")) {
    return `Load rules: at 45–54 mph winds with over 30,000 lb → No Travel. At 35–44 mph winds with over 40,000 lb → Severe. Heavier loads get stricter verdicts — that's why the same storm can be fine for one truck and a no-go for another.`;
  }
  if (has("departure", "leave", "when should", "delay")) {
    return "Try the Smart departure panel above — it scans every 3 hours over the next 48 and tells you if leaving later dodges the worst weather.";
  }
  if (has("hi", "hello", "hey", "yo") && t.length < 12) {
    return "Hey! I'm Road Buddy. Ask me which route is safest, compare the routes, check weather at a mile, or when you'll arrive.";
  }
  if (has("thank")) return "Anytime, driver. Stay safe out there.";
  return "I can help with: safest route, compare routes, weather at mile __, arrival time, load rules, or what No Travel means. What do you want to know?";
}

const CHIPS = ["Which route is safest?", "Compare routes", "Weather at mile 500", "When will I arrive?", "What does No Travel mean?"];

export default function BuddyChat({ plan, rec, selected }) {
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState([{ from: "bot", text: "Hey, I'm Road Buddy — your trip assistant. Ask me anything about these routes." }]);
  const [input, setInput] = useState("");
  const boxRef = useRef(null);

  useEffect(() => {
    if (boxRef.current) boxRef.current.scrollTop = boxRef.current.scrollHeight;
  }, [msgs, open]);

  function send(text) {
    const q = (text ?? input).trim();
    if (!q) return;
    const reply = answer(q, { plan, rec, selected });
    setMsgs((m) => [...m, { from: "user", text: q }, { from: "bot", text: reply }]);
    setInput("");
  }

  return (
    <>
      <motion.button className="buddy-fab" onClick={() => setOpen(!open)} title="Chat with Road Buddy"
        whileHover={{ scale: 1.06 }} whileTap={{ scale: 0.92 }}>
        {open ? "✕" : "💬"}
      </motion.button>
      <AnimatePresence>
        {open && (
          <motion.div className="buddy-panel"
            initial={{ opacity: 0, y: 24, scale: 0.96 }} animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 24, scale: 0.96 }} transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}>
            <div className="buddy-head">🚚 Road Buddy <button onClick={() => setOpen(false)}>✕</button></div>
            <div className="buddy-msgs" ref={boxRef}>
              {msgs.map((m, i) => (
                <motion.div key={i} className={`buddy-msg ${m.from}`}
                  initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.22 }}>
                  {m.text}
                </motion.div>
              ))}
            </div>
            <div className="buddy-chips">
              {CHIPS.map((c) => <button key={c} onClick={() => send(c)}>{c}</button>)}
            </div>
            <div className="buddy-input">
              <input value={input} onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && send()}
                placeholder="Ask about your trip…" maxLength="200" />
              <button onClick={() => send()}>Send</button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
