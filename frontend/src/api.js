const API = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";
const TOKEN_KEY = "haulsafe_token";

export function getToken() {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}
export function setToken(t) {
  try { localStorage.setItem(TOKEN_KEY, t); } catch { /* storage unavailable */ }
}
export function clearToken() {
  try { localStorage.removeItem(TOKEN_KEY); } catch { /* storage unavailable */ }
}

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request(path, { method = "GET", body } = {}) {
  const headers = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers["Authorization"] = `Token ${token}`;
  let res;
  try {
    res = await fetch(`${API}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError("Couldn't reach the backend — check that the server is running.", 0);
  }
  let data = null;
  try { data = await res.json(); } catch { data = null; }
  if (res.status === 401) {
    clearToken();
    throw new ApiError("Your session expired — please log in again.", 401);
  }
  if (!res.ok) {
    throw new ApiError((data && data.error) || `Request failed (HTTP ${res.status})`, res.status);
  }
  return data;
}

// ---- core planning ----
export const planRoutes = (p) => request("/api/plan/", { method: "POST", body: p });
export const corridorData = (p) => request("/api/corridor/", { method: "POST", body: p });
export const smartDeparture = (p) => request("/api/smart-departure/", { method: "POST", body: p });

// ---- auth (optional enhancement; failures must never break planning) ----
export const signup = (username, password) =>
  request("/api/auth/signup/", { method: "POST", body: { username, password } });
export const login = (username, password) =>
  request("/api/auth/login/", { method: "POST", body: { username, password } });
export const me = () => request("/api/auth/me/");

// ---- trip history ----
export const getTrips = () => request("/api/trips/");
export const saveTrip = (t) => request("/api/trips/", { method: "POST", body: t });
export const getTrip = (id) => request(`/api/trips/${id}/`);
export const deleteTrip = (id) => request(`/api/trips/${id}/`, { method: "DELETE" });

/**
 * Normalize the recommendation field.
 * New contract: {index, reasoning, ranking}. Tolerates the legacy bare-index shape.
 */
export function normRecommended(plan) {
  const r = plan && plan.recommended;
  if (typeof r === "number") return { index: r, reasoning: "", ranking: [] };
  return {
    index: (r && typeof r.index === "number") ? r.index : 0,
    reasoning: (r && r.reasoning) || "",
    ranking: (r && r.ranking) || [],
  };
}

export function rankingLabel(ranking) {
  if (Array.isArray(ranking) && ranking.length) {
    return ranking.map((i) => `Route ${i + 1}`).join(" › ");
  }
  if (typeof ranking === "string" && ranking) return ranking;
  return "";
}

export const RISK_COLORS = {
  "Low": "#22c55e",
  "Moderate": "#eab308",
  "High": "#f97316",
  "Severe": "#ef4444",
  "No Travel": "#7f1d1d",
};

export const ROUTE_COLORS = ["#2563eb", "#7c3aed", "#0d9488"];
