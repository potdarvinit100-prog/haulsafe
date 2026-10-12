"""Geospatial helpers: polyline decoding, distances, checkpoint sampling."""
import math

EARTH_MILES = 3958.8


def decode_polyline(polyline: str):
    """Decode an OSRM/GMaps polyline string into [(lat, lng), ...]."""
    coords = []
    index = lat = lng = 0
    while index < len(polyline):
        for coord in ("lat", "lng"):
            shift = result = 0
            while True:
                b = ord(polyline[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            delta = ~(result >> 1) if (result & 1) else (result >> 1)
            if coord == "lat":
                lat += delta
            else:
                lng += delta
        coords.append((lat / 1e5, lng / 1e5))
    return coords


def haversine_miles(a, b):
    """Great-circle distance in miles between (lat, lng) points."""
    lat1, lng1 = math.radians(a[0]), math.radians(a[1])
    lat2, lng2 = math.radians(b[0]), math.radians(b[1])
    dlat, dlng = lat2 - lat1, lng2 - lng1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * EARTH_MILES * math.asin(math.sqrt(h))


def cumulative_miles(coords):
    """Cumulative distance in miles at each coordinate."""
    cum = [0.0]
    for i in range(1, len(coords)):
        cum.append(cum[-1] + haversine_miles(coords[i - 1], coords[i]))
    return cum


def sample_checkpoints(coords, every_miles):
    """Return checkpoints every `every_miles` along the path.

    Each checkpoint: {"lat", "lng", "mile"} where mile is distance from origin.
    Always includes the origin (mile 0) and the destination.
    """
    cum = cumulative_miles(coords)
    total = cum[-1]
    checkpoints = [{"lat": coords[0][0], "lng": coords[0][1], "mile": 0.0}]
    target = every_miles
    i = 1
    while target < total and i < len(coords):
        while i < len(coords) and cum[i] < target:
            i += 1
        if i >= len(coords):
            break
        # interpolate between coords[i-1] and coords[i]
        prev_cum, next_cum = cum[i - 1], cum[i]
        frac = (target - prev_cum) / (next_cum - prev_cum) if next_cum > prev_cum else 0
        lat = coords[i - 1][0] + frac * (coords[i][0] - coords[i - 1][0])
        lng = coords[i - 1][1] + frac * (coords[i][1] - coords[i - 1][1])
        checkpoints.append({"lat": lat, "lng": lng, "mile": round(target, 2)})
        target += every_miles
    checkpoints.append({"lat": coords[-1][0], "lng": coords[-1][1], "mile": round(total, 2)})
    return checkpoints, round(total, 2)
