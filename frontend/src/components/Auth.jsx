import { useState } from "react";
import { motion } from "framer-motion";
import { signup, login, setToken } from "../api";

export default function Auth({ mode, setMode, notice, onAuth }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setError("");
    if (!username.trim() || !password) {
      setError("Enter a username and password.");
      return;
    }
    setLoading(true);
    try {
      const fn = mode === "signup" ? signup : login;
      const data = await fn(username.trim(), password);
      if (!data || !data.token) throw new Error("Unexpected response from the server.");
      setToken(data.token);
      onAuth({ username: data.username || username.trim() });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <motion.div className="auth-wrap" initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }}>
      <div className="auth-card glass">
        <div className="auth-brand">
          <span className="brand-mark lg">🚚</span>
          <h2>{mode === "signup" ? "Create your HaulSafe account" : "Welcome back, driver"}</h2>
          <p>{mode === "signup"
            ? "Save trips, reload past plans, and keep your history in one place."
            : "Log in to see your saved trips and plan history."}</p>
        </div>
        {notice && <div className="banner notice">{notice}</div>}
        {error && <div className="banner error">{error}</div>}
        <form onSubmit={submit}>
          <label>Username
            <input value={username} onChange={(e) => setUsername(e.target.value)}
              autoComplete="username" placeholder="e.g. roadwarrior_99" />
          </label>
          <label>Password
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === "signup" ? "new-password" : "current-password"} placeholder="••••••••" />
          </label>
          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? (mode === "signup" ? "Creating account…" : "Logging in…")
                     : (mode === "signup" ? "Sign up" : "Log in")}
          </button>
        </form>
        <div className="auth-switch">
          {mode === "signup" ? (
            <>Already have an account? <button className="link" onClick={() => setMode("login")}>Log in</button></>
          ) : (
            <>New to HaulSafe? <button className="link" onClick={() => setMode("signup")}>Create an account</button></>
          )}
        </div>
      </div>
    </motion.div>
  );
}
