"""External API clients: Nominatim (geocoding), OSRM (routing), weather.

Weather goes through our tiny Vercel proxy (see ../weather-proxy/) which
forwards to Open-Meteo and returns its JSON untouched. Render's free-tier
shared egress IPs get 429s from Open-Meteo; the proxy runs on clean
egress. All three upstream APIs are free and need no key.
"""
import os
import requests
import time

HEADERS = {"User-Agent": "HaulSafe/1.0 (candidate project)"}
TIMEOUT = 25
WEATHER_PROXY_URL = os.environ.get(
    "WEATHER_PROXY_URL", "https://haulsafe-weather.vercel.app/api/weather"
)
GEOCODE_PROXY_URL = os.environ.get(
    "GEOCODE_PROXY_URL", "https://haulsafe-weather.vercel.app/api/geocode"
)
ROUTE_PROXY_URL = os.environ.get(
    "ROUTE_PROXY_URL", "https://haulsafe-weather.vercel.app/api/route"
)


def _post_with_retry(url, payload):
    """POST with retries incl. 429 backoff — weather is the critical path."""
    last = None
    for wait in (0, 5, 15):
        if wait:
            time.sleep(wait)
        try:
            r = requests.post(url, json=payload, headers=HEADERS, timeout=TIMEOUT)
            if r.status_code == 429:
                last = requests.HTTPError("429 from weather proxy")
                continue
            r.raise_for_status()
            return r
        except (requests.Timeout, requests.ConnectionError) as e:
            last = e
    raise last


def geocode(place: str):
    """Turn a place name into (lat, lng). Raises ValueError if not found."""
    r = _post_with_retry(GEOCODE_PROXY_URL, {"q": place})
    hits = r.json()
    if not hits:
        raise ValueError(f"Could not find a location for '{place}'")
    return float(hits[0]["lat"]), float(hits[0]["lon"])


def get_routes(origin, destination):
    """Ask OSRM (via proxy) for up to 3 alternative driving routes.

    Returns a list of {"geometry": polyline, "distance_m": ..., "duration_s": ...}.
    """
    (olat, olng), (dlat, dlng) = origin, destination
    r = _post_with_retry(
        ROUTE_PROXY_URL,
        {"coords": f"{olng},{olat};{dlng},{dlat}", "alternatives": True},
    )
    data = r.json()
    if data.get("code") != "Ok" or not data.get("routes"):
        raise ValueError("No driving route found between those points")
    return [
        {
            "geometry": route["geometry"],
            "distance_m": route["distance"],
            "duration_s": route["duration"],
        }
        for route in data["routes"][:3]
    ]


def get_route_via_waypoint(origin, destination, waypoint):
    """Force a single OSRM route through an intermediate waypoint.

    Used as a fallback when OSRM's alternatives=true returns fewer than 3
    distinct routes. Returns one {"geometry", "distance_m", "duration_s"} dict.
    """
    (olat, olng), (dlat, dlng) = origin, destination
    wlat, wlng = waypoint
    r = _post_with_retry(
        ROUTE_PROXY_URL,
        {"coords": f"{olng},{olat};{wlng},{wlat};{dlng},{dlat}"},
    )
    data = r.json()
    if data.get("code") != "Ok" or not data.get("routes"):
        raise ValueError("No detour route found via waypoint")
    route = data["routes"][0]
    return {
        "geometry": route["geometry"],
        "distance_m": route["distance"],
        "duration_s": route["duration"],
    }


def get_hourly_weather(points):
    """Fetch hourly weather for many points in ONE proxied Open-Meteo call.

    points: list of (lat, lng). Returns dict keyed by (lat, lng) ->
    {"time": [...ISO...], "wind": [...mph...], "rain": [...in/hr...], "snow": [...in/hr...]}.
    forecast_days=3 (72 hourly slots from 00:00 UTC today) guarantees the
    hour +48 offset exists for the 0-48h corridor slider and smart departure.
    """
    lats = ",".join(f"{p[0]:.4f}" for p in points)
    lngs = ",".join(f"{p[1]:.4f}" for p in points)
    r = _post_with_retry(WEATHER_PROXY_URL, {"latitude": lats, "longitude": lngs})
    payload = r.json()
    if isinstance(payload, dict) and "error" in payload and "hourly" not in payload:
        raise requests.HTTPError(f"weather proxy error: {payload['error']}")
    # Open-Meteo returns a list when multiple locations are requested,
    # a single object when only one is requested.
    items = payload if isinstance(payload, list) else [payload]
    out = {}
    for pt, item in zip(points, items):
        h = item["hourly"]
        out[pt] = {
            "time": h["time"],
            "wind": h["wind_speed_10m"],
            "rain": h["precipitation"],
            "snow": h["snowfall"],
        }
    return out
