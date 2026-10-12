# HaulSafe — Loom walkthrough script (5–10 min)

Narration script for the submission video. Read these lines as you record —
the demo example below is the one verified live in QA: Chicago → Denver.

## Scene 1 — Hook (hero screen)
**Show:** HaulSafe landing, logged out.
**Say:** "HaulSafe is a weather-aware routing app for heavy-haul truck drivers.
A driver enters an origin, a destination, a departure time, and the load weight —
and HaulSafe returns three route options, scores each one against live weather
forecasts, and recommends the safest route. Let me show you how."

## Scene 2 — Plan a trip
**Show:** Fill in origin Chicago, destination Denver, depart now, load 40,000 lb. Hit Plan.
**Say:** "I'm planning Chicago to Denver, departing now, with a 40,000-pound load.
The app geocodes both places, fetches driving routes, and drops checkpoints every
10, 25, and 50 miles along each route."

## Scene 3 — The map and checkpoints
**Show:** Map with 3 routes; click a checkpoint popup (wind/rain/snow, ETA, verdict reason).
**Say:** "Here are the three routes. Every checkpoint is color-coded by risk. For
each checkpoint, HaulSafe estimates when the truck will actually arrive there and
pulls the hourly forecast for that exact moment. Clicking any checkpoint shows the
wind, rain, and snow behind its verdict — nothing is a black box."

## Scene 4 — Risk breakdown + recommendation
**Show:** Risk breakdown bars per route + the recommendation with reasoning text.
**Say:** "Each route gets a risk breakdown — how many miles fall into each risk
level. Checkpoints are classified on a five-level scale: Low, Moderate, High,
Severe, and No Travel. The load rules are baked in: wind over 55 mph is No Travel
for any load, 45 to 54 mph with over 30,000 pounds is No Travel, and 35 to 44 mph
with over 40,000 pounds is Severe. Routes are ranked by fewest No Travel miles
first — a route you must not drive can never win on time. In this run, Route 2
caught a real No Travel weather cell and was ranked last, exactly as designed.
The recommendation comes with plain-English reasoning."

## Scene 5 — Heatmap and departure advisor
**Show:** Drag the 0–48h heatmap slider; open the smart departure panel.
**Say:** "The heatmap shows the weather risk along the route across the next
48 hours. And the smart departure advisor re-scores the recommended route's
already-fetched 49-hour forecasts across departures from plus-3 to plus-48 hours —
zero extra API calls — and suggests a safer window when one exists."

## Scene 6 — Driver accounts and trip history
**Show:** Sign up / log in, save the trip, reload it from history, delete one.
**Say:** "Drivers can sign up and log in, save trips, reload them later, or delete
them. Saved trips are isolated per driver."

## Scene 7 — Under the hood
**Show:** Quick scroll of the repo README (architecture section), test run output.
**Say:** "Under the hood: React with Vite and Leaflet on the frontend, Django with
Django REST Framework on the backend. Routing data comes from free, keyless APIs —
geocoding, driving routes, and hourly forecasts — batched so each plan needs only
one weather call. Thirty-four backend tests pass, and the repo ships with
production deploy configs. Dark and light mode, and an animated drive-through of
the truck along the route, round it out."

## Scene 8 — Close
**Show:** Hero screen again.
**Say:** "That's HaulSafe — three genuinely different routes, live weather scored
at the moment the truck arrives, honest ranking, and a recommendation a driver can
trust. Thanks for watching."

---
Fill before submitting: repo link, hosted app link. Total runtime target: 7–9 min.
