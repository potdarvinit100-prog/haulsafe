"""External API clients: Nominatim (geocoding), OSRM (routing), Open-Meteo (weather).

All three are free and need no API key, which keeps the assessment
self-contained and deployable anywhere.
"""
import requests
import time

HEADERS = {"User-Agent": "HaulSafe/1.0 (candidate project)"}
TIMEOUT = 25


def _get_with_retry(url, params):
    """GET with one retry and backoff — external APIs hiccup."""
    last = None
    for wait in (0, 2):
        if wait:
            time.sleep(wait)
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
            r.raise_for_status()
            return r
        except (requests.Timeout, requests.ConnectionError) as e:
            last = e
    raise last


def geocode(place: str):
    """Turn a place name into (lat, lng). Raises ValueError if not found."""
    r = _get_with_retry(
        "https://nominatim.openstreetmap.org/search",
        {"q": place, "format": "json", "limit": 1},
    )
    hits = r.json()
    if not hits:
        raise ValueError(f"Could not find a location for '{place}'")
    return float(hits[0]["lat"]), float(hits[0]["lon"])


def get_routes(origin, destination):
    """Ask OSRM for up to 3 alternative driving routes.

    Returns a list of {"geometry": polyline, "distance_m": ..., "duration_s": ...}.
    """
    (olat, olng), (dlat, dlng) = origin, destination
    r = _get_with_retry(
        f"https://router.project-osrm.org/route/v1/driving/{olng},{olat};{dlng},{dlat}",
        {"overview": "full", "geometries": "polyline", "alternatives": "3"},
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
    r = _get_with_retry(
        f"https://router.project-osrm.org/route/v1/driving/"
        f"{olng},{olat};{wlng},{wlat};{dlng},{dlat}",
        {"overview": "full", "geometries": "polyline"},
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
    """Fetch hourly weather for many points in ONE Open-Meteo call.

    points: list of (lat, lng). Returns dict keyed by (lat, lng) ->
    {"time": [...ISO...], "wind": [...mph...], "rain": [...in/hr...], "snow": [...in/hr...]}.
    forecast_days=3 (72 hourly slots from 00:00 UTC today) guarantees the
    hour +48 offset exists for the 0-48h corridor slider and smart departure.
    """
    lats = ",".join(f"{p[0]:.4f}" for p in points)
    lngs = ",".join(f"{p[1]:.4f}" for p in points)
    r = _get_with_retry(
        "https://api.open-meteo.com/v1/forecast",
        {
            "latitude": lats,
            "longitude": lngs,
            "hourly": "wind_speed_10m,precipitation,snowfall",
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "temperature_unit": "fahrenheit",
            "forecast_days": 3,
            "timezone": "UTC",
        },
    )
    payload = r.json()
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
