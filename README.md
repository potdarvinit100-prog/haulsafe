# HaulSafe — Weather-Aware Truck Routing

A React + Django web app that helps a truck driver pick the safest route for a
heavy haul. The driver enters **origin**, **destination**, **departure time**,
and **load weight**; the app generates **3 route options**, samples the weather
forecast at every 10 / 25 / 50-mile checkpoint at the truck's estimated arrival
time, scores each checkpoint against wind / rain / snow thresholds plus
load-weight rules, and recommends the safest route — with a live map, a 48-hour
weather heatmap, a risk-profile chart, an animated drive-through, driver
accounts with saved trip history, and a smart departure advisor.

## How it works

1. The backend geocodes both places (Nominatim), fetches driving routes (OSRM),
   and drops **checkpoints every 10 / 25 / 50 miles** along each route.
2. For every checkpoint it estimates the truck's **arrival time** from the
   route's average speed, pulls the **hourly forecast** for that moment
   (Open-Meteo, one batched call for all checkpoints), and classifies risk:

   | Condition | Low | Moderate | High | Severe | No Travel |
   |---|---|---|---|---|---|
   | Wind | <25 mph | 25–34 | 35–44 | 45–54 | ≥55 mph |
   | Rain | <0.10 in/hr | 0.10–0.25 | 0.25–0.50 | 0.50–1.00 | >1.00 |
   | Snow | <0.5 in/hr | 0.5–1.0 | 1.0–2.0 | 2.0–3.0 | >3.0 |

   Load rules (escalate only, never soften): wind ≥55 mph → No Travel for any
   load; 45–54 mph with >30,000 lb → No Travel; 35–44 mph with >40,000 lb →
   Severe. A checkpoint's level is the worst of its wind/rain/snow verdicts.
3. Each route gets a **risk breakdown** (miles per level + average score).
   Routes are ranked by **fewest No Travel miles → fewest Severe miles →
   fewest High miles → lowest average risk → shortest travel time**, and the
   winner is recommended with a one-sentence reasoning.
4. The map shows all routes, color-coded checkpoints (click any for
   wind/rain/snow, ETA, and the reasons behind its verdict), a **48-hour
   weather heatmap** (offsets 0–48 inclusive) with an hour slider, a
   **risk-profile chart**, and an animated **truck drive-through**.
5. **Smart departure** re-scores the recommended route's already-fetched
   49-hour checkpoint forecasts at +3h…+48h departures — zero extra weather
   API calls — and suggests a safer window when one exists.
6. Drivers can **sign up / log in** (token auth) and **save trips** to reload
   or delete them later.

All times are UTC. All three data providers (Nominatim, OSRM, Open-Meteo) are
free and need no API key.

### Design notes

- **3-route guarantee.** OSRM's `alternatives=true` usually returns 2 routes on
  long hauls. When it comes up short, the backend forces extra routes through
  waypoints offset perpendicular to the straight line (±0.7°, ±1.4°),
  rejecting any candidate within 3% of an existing route's length so every
  option is a genuinely different corridor. Fallbacks are tagged
  `"detour": true` with an explanatory note. As a last resort the recommended
  route is repeated with an explicit note rather than returning fewer than 3.
- **No Travel ranks before Severe.** A stretch the truck must not drive at all
  is worse than one it can drive with caution, so `no_travel_miles` is the
  first sort key: a route with any no-travel miles can never win on time or
  averages.
- **Departure window.** Departures outside [now−1h, now+48h] are rejected with
  HTTP 400 instead of silently clamping to the forecast edge.

## Project layout

```
backend/               Django 6 + Django REST Framework
  config/              settings (env-driven), root URLs
  routing/
    geo.py             polyline decoding, haversine distance, checkpoint sampling
    weather.py         Nominatim / OSRM / Open-Meteo clients
    risk.py            risk classification + route ranking (brief's exact rules)
    views.py           plan / corridor / smart-departure / auth / trips
    models.py          Trip (saved route plans)
    tests.py           34 unit + API tests
  requirements.txt
  .env.example
frontend/              React + Vite + Leaflet
render.yaml            Render.com deployment (backend)
Procfile               gunicorn start command
```

## Run locally

```bash
# backend
cd backend
python -m venv venv && ./venv/bin/pip install -r requirements.txt
./venv/bin/python manage.py migrate
./venv/bin/python manage.py runserver 127.0.0.1:8000

# frontend (second terminal)
cd frontend
npm install
npm run dev            # http://127.0.0.1:5173, talks to the backend above
```

Set `VITE_API_URL` to point the frontend at a deployed backend.

Run the test suite:

```bash
cd backend && ./venv/bin/python manage.py test
```

## Environment variables

| Variable | Default (dev) | Purpose |
|---|---|---|
| `SECRET_KEY` | insecure dev key | Django secret key — set in prod |
| `DEBUG` | `True` | Set `False` in prod |
| `ALLOWED_HOSTS` | localhost only (when DEBUG) | Comma-separated hosts |
| `CORS_ALLOWED_ORIGINS` | allow-all (dev) | Comma-separated frontend origins |

Copy `backend/.env.example` to `backend/.env` for local overrides.

## Deploy

- **Render:** `render.yaml` at the repo root deploys `backend/` with
  `pip install -r requirements.txt` and
  `python manage.py migrate && gunicorn config.wsgi:application`. Set
  `ALLOWED_HOSTS` / `CORS_ALLOWED_ORIGINS` / `DEBUG=False` in the dashboard.
- **Procfile** (Heroku/Dokku-style): runs migrations then gunicorn.

## API reference

Base path: `/api/`. Departures must be ISO-8601 and within [now−1h, now+48h],
otherwise the endpoint returns `400 {"error": "Departure must be within the
next 48 hours (forecast window)."}`.

### POST /api/plan/

```json
{ "origin": "Chicago, IL", "destination": "Denver, CO",
  "departure": "2026-10-13T08:00:00Z", "load_weight_lb": 35000, "sample_miles": 25 }
```

Always returns exactly 3 routes. Response:

```json
{
  "origin": {"lat": 41.88, "lng": -87.62},
  "destination": {"lat": 39.74, "lng": -104.99},
  "departure": "2026-10-13T08:00:00+00:00",
  "load_weight_lb": 35000,
  "routes": [{
    "path": [[41.88, -87.62], "..."],
    "total_miles": 1002.4, "duration_s": 64140, "avg_mph": 56.2,
    "detour": false,
    "risk_breakdown": {"severe_miles": 0.0, "high_miles": 12.5,
      "moderate_miles": 40.0, "low_miles": 949.9, "no_travel_miles": 0.0,
      "avg_score": 0.18},
    "checkpoints": [{"lat": 41.88, "lng": -87.62, "mile": 0.0,
      "eta": "2026-10-13T08:00:00+00:00", "wind_mph": 12.0,
      "rain_inhr": 0.0, "snow_inhr": 0.0,
      "level": "Low", "reasons": ["conditions within safe limits"]}]
  }],
  "recommended": {
    "index": 0,
    "reasoning": "Route 1 has the fewest no-travel miles (0.0) and severe miles (0.0), with the lowest average risk score (0.18).",
    "ranking": [0, 2, 1]
  }
}
```

### POST /api/corridor/

```json
{ "path": [[41.88, -87.62], "..."], "departure": "2026-10-13T08:00:00Z",
  "load_weight_lb": 35000 }
```

→ `{points: [{lat, lng, mile, hours: [49 risk scores 0–4]}], hours: [49 ISO timestamps], total_miles}`.
Points are sampled ~every 10 miles; `hours` covers forecast offsets 0–48 inclusive.

### POST /api/smart-departure/

Same body as `/api/plan/`. Reuses the plan pipeline's already-fetched
checkpoint forecasts to score departures at +3h…+48h (step 3h) with no extra
weather calls. An alternative qualifies only if its
(no_travel, severe, high, avg) tuple is strictly better than now.

```json
{
  "current": {"departure": "...", "no_travel_miles": 0.0, "severe_miles": 25.0,
              "high_miles": 60.0, "avg_score": 1.42},
  "alternatives": [{"departure": "...", "no_travel_miles": 0.0, ...}],
  "best": {"departure": "...", ...}   // or null when now is already optimal
}
```

### Auth (token)

- `POST /api/auth/signup/` `{username, password}` → `201 {token, username}`
  (username unique, password ≥ 6 chars)
- `POST /api/auth/login/` `{username, password}` → `200 {token, username}`
- `GET /api/auth/me/` (header `Authorization: Token <token>`) → `{username}`

### Trips (token required, owner-scoped)

- `GET /api/trips/` → `[{id, name, origin, destination, departure,
  load_weight_lb, sample_miles, recommended_index, created_at}]`
- `POST /api/trips/` `{name?, origin, destination, departure,
  load_weight_lb, sample_miles, plan_result}` → `201` full object
- `GET /api/trips/<id>/` → full object including `plan_result`
- `DELETE /api/trips/<id>/` → `204`
