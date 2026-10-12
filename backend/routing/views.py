"""API: plan, corridor, smart-departure, auth, trips."""
import math
from datetime import datetime, timedelta, timezone

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from rest_framework import status as http
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import geo, risk
from .models import Trip
from .weather import (
    geocode,
    get_hourly_weather,
    get_route_via_waypoint,
    get_routes,
)

MILES_PER_METER = 1 / 1609.344
FORECAST_HOURS = 49  # 0..48 inclusive
DEPARTURE_WINDOW = (timedelta(hours=1), timedelta(hours=48))  # past, future


# ---------------------------------------------------------------- helpers

def _parse_departure(value):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _validate_departure(departure):
    """Reject departures outside the forecast window instead of clamping."""
    now = datetime.now(timezone.utc)
    past, future = DEPARTURE_WINDOW
    if departure < now - past or departure > now + future:
        return Response(
            {"error": "Departure must be within the next 48 hours (forecast window)."},
            status=http.HTTP_400_BAD_REQUEST,
        )
    return None


def _nearest_hour(times, target):
    """Index of the hourly timestamp closest to target (both UTC)."""
    best, best_dt = 0, None
    for i, t in enumerate(times):
        ts = datetime.fromisoformat(t).replace(tzinfo=timezone.utc)
        delta = abs((ts - target).total_seconds())
        if best_dt is None or delta < best_dt:
            best, best_dt = i, delta
    return best


def _miles_of(raw_route):
    return raw_route["distance_m"] * MILES_PER_METER


def _perpendicular_waypoints(origin, destination):
    """Waypoints offset perpendicular to the straight origin->destination line.

    Offsets of ~0.7, ~1.4, ~2.1 and ~2.8 degrees force OSRM onto meaningfully
    different corridors when its built-in alternatives come up short; the
    ladder widens until a candidate clears the 3% distinctness rule.
    """
    (olat, olng), (dlat, dlng) = origin, destination
    mid_lat, mid_lng = (olat + dlat) / 2, (olng + dlng) / 2
    dx, dy = dlng - olng, dlat - olat
    length = math.hypot(dx, dy) or 1e-9
    perp_lat, perp_lng = -dx / length, dy / length
    return [
        (mid_lat + perp_lat * d, mid_lng + perp_lng * d)
        for d in (0.7, -0.7, 1.4, -1.4, 2.1, -2.1, 2.8, -2.8)
    ]


def _ensure_three_routes(origin, destination):
    """Guarantee exactly 3 distinct routes.

    OSRM's alternatives=true usually returns 2 routes for long hauls, so we
    top up with routes forced through waypoints offset perpendicular to the
    straight line. A candidate is rejected when its length is within 3% of an
    already-accepted route (i.e. it is not a real alternative). As a last
    resort the recommended route is repeated with an explicit note rather
    than returning fewer than 3.
    """
    accepted = list(get_routes(origin, destination))
    for waypoint in _perpendicular_waypoints(origin, destination):
        if len(accepted) >= 3:
            break
        try:
            detour = get_route_via_waypoint(origin, destination, waypoint)
        except Exception:
            continue
        miles = _miles_of(detour)
        if any(
            abs(miles - _miles_of(r)) / max(_miles_of(r), 1e-9) < 0.03
            for r in accepted
        ):
            continue
        detour["detour"] = True
        detour["note"] = "Alternate via offset waypoint"
        accepted.append(detour)
    while len(accepted) < 3:
        dup = dict(accepted[0])
        dup["detour"] = True
        dup["note"] = "No distinct alternate available; showing the recommended route again"
        accepted.append(dup)
    return accepted[:3]


def _round_stats(stats):
    out = {k: round(v, 1) for k, v in stats.items() if k != "avg_score"}
    out["avg_score"] = round(stats["avg_score"], 2)
    return out


def _classify_at_eta(weather_by_point, checkpoint, eta, load_lb):
    w = weather_by_point[(checkpoint["lat"], checkpoint["lng"])]
    i = _nearest_hour(w["time"], eta)
    verdict = risk.classify_checkpoint(w["wind"][i], w["rain"][i], w["snow"][i], load_lb)
    return {
        "lat": checkpoint["lat"],
        "lng": checkpoint["lng"],
        "mile": checkpoint["mile"],
        "eta": eta.isoformat(),
        "wind_mph": round(w["wind"][i], 1),
        "rain_inhr": round(w["rain"][i], 2),
        "snow_inhr": round(w["snow"][i], 2),
        **verdict,
    }


def _run_pipeline(origin_ll, dest_ll, departure, load_lb, sample_miles):
    """Shared plan pipeline: routes -> checkpoints -> ONE weather call -> levels.

    Returns (routes, weather_by_point). Each route has "checkpoints" (with
    "level"/"mile"), "duration_s", "avg_mph", "risk_stats" (unrounded),
    "detour" and optional "note".
    """
    route_infos = []
    for raw in _ensure_three_routes(origin_ll, dest_ll):
        coords = geo.decode_polyline(raw["geometry"])
        checkpoints, total_miles = geo.sample_checkpoints(coords, sample_miles)
        avg_mph = (raw["distance_m"] * MILES_PER_METER) / max(raw["duration_s"] / 3600, 0.01)
        route_infos.append(
            {
                "coords": coords,
                "checkpoints": checkpoints,
                "total_miles": total_miles,
                "duration_s": raw["duration_s"],
                "avg_mph": avg_mph,
                "detour": bool(raw.get("detour")),
                "note": raw.get("note"),
            }
        )

    points = [(c["lat"], c["lng"]) for info in route_infos for c in info["checkpoints"]]
    weather = get_hourly_weather(points)

    routes = []
    for info in route_infos:
        cps_out = [
            _classify_at_eta(
                weather, c, departure + timedelta(hours=c["mile"] / info["avg_mph"]), load_lb
            )
            for c in info["checkpoints"]
        ]
        routes.append(
            {
                "path": [[lat, lng] for lat, lng in info["coords"]],
                "total_miles": info["total_miles"],
                "duration_s": info["duration_s"],
                "avg_mph": info["avg_mph"],
                "detour": info["detour"],
                "note": info["note"],
                "checkpoints": cps_out,
                "risk_stats": risk.route_stats(
                    {"checkpoints": cps_out, "duration_s": info["duration_s"]}
                ),
            }
        )
    return routes, weather


def _serialize_route(route):
    out = {
        "path": route["path"],
        "total_miles": route["total_miles"],
        "duration_s": round(route["duration_s"]),
        "avg_mph": round(route["avg_mph"], 1),
        "detour": route["detour"],
        "checkpoints": route["checkpoints"],
        "risk_breakdown": _round_stats(route["risk_stats"]),
    }
    if route["note"]:
        out["note"] = route["note"]
    return out


def _recommendation_reasoning(index, breakdown):
    n = index + 1
    return (
        f"Route {n} has the fewest no-travel miles ({breakdown['no_travel_miles']:.1f}) "
        f"and severe miles ({breakdown['severe_miles']:.1f}), "
        f"with the lowest average risk score ({breakdown['avg_score']:.2f})."
    )


def _tuple_of(stats):
    return (
        stats["no_travel_miles"],
        stats["severe_miles"],
        stats["high_miles"],
        stats["avg_score"],
    )


# ---------------------------------------------------------------- plan

@api_view(["POST"])
def plan(request):
    """Plan weather-aware routes.

    Body: {origin, destination, departure (ISO), load_weight_lb, sample_miles}
    Always returns exactly 3 routes. `recommended` is
    {index, reasoning, ranking} with ranking ordered best-first.
    """
    try:
        origin = request.data["origin"]
        destination = request.data["destination"]
        departure = _parse_departure(request.data["departure"])
        load_lb = float(request.data.get("load_weight_lb", 0))
        sample_miles = float(request.data.get("sample_miles", 25))
    except (KeyError, ValueError, TypeError) as e:
        return Response({"error": f"Invalid input: {e}"}, status=http.HTTP_400_BAD_REQUEST)

    bad = _validate_departure(departure)
    if bad:
        return bad

    try:
        o_ll = geocode(origin)
        d_ll = geocode(destination)
    except ValueError as e:
        return Response({"error": str(e)}, status=http.HTTP_422_UNPROCESSABLE_ENTITY)
    except Exception as e:
        return Response({"error": f"Routing service error: {e}"}, status=http.HTTP_502_BAD_GATEWAY)

    try:
        routes, _weather = _run_pipeline(o_ll, d_ll, departure, load_lb, sample_miles)
    except ValueError as e:
        return Response({"error": str(e)}, status=http.HTTP_422_UNPROCESSABLE_ENTITY)
    except Exception as e:
        return Response({"error": f"Routing/weather service error: {e}"},
                        status=http.HTTP_502_BAD_GATEWAY)

    ranking = risk.rank_routes(routes)
    best = ranking[0]
    best_breakdown = _round_stats(routes[best]["risk_stats"])

    return Response({
        "origin": {"lat": o_ll[0], "lng": o_ll[1]},
        "destination": {"lat": d_ll[0], "lng": d_ll[1]},
        "departure": departure.isoformat(),
        "load_weight_lb": load_lb,
        "routes": [_serialize_route(r) for r in routes],
        "recommended": {
            "index": best,
            "reasoning": _recommendation_reasoning(best, best_breakdown),
            "ranking": ranking,
        },
    })


# ---------------------------------------------------------------- corridor

@api_view(["POST"])
def corridor(request):
    """Heatmap data for one route corridor.

    Body: {path: [[lat, lng], ...], departure (ISO), load_weight_lb}
    Returns points every ~10 miles, each with 49 hourly risk scores (0-4)
    for offsets 0..48 inclusive.
    """
    try:
        path = [(p[0], p[1]) for p in request.data["path"]]
        departure = _parse_departure(request.data["departure"])
        load_lb = float(request.data.get("load_weight_lb", 0))
    except (KeyError, ValueError, TypeError) as e:
        return Response({"error": f"Invalid input: {e}"}, status=http.HTTP_400_BAD_REQUEST)

    bad = _validate_departure(departure)
    if bad:
        return bad

    checkpoints, total_miles = geo.sample_checkpoints(path, 10)
    points = [(c["lat"], c["lng"]) for c in checkpoints]
    try:
        weather = get_hourly_weather(points)
    except Exception as e:
        return Response({"error": f"Weather service error: {e}"}, status=http.HTTP_502_BAD_GATEWAY)

    heat = []
    for c in checkpoints:
        w = weather[(c["lat"], c["lng"])]
        scores = []
        for h in range(FORECAST_HOURS):
            target = departure + timedelta(hours=h)
            i = _nearest_hour(w["time"], target)
            verdict = risk.classify_checkpoint(w["wind"][i], w["rain"][i], w["snow"][i], load_lb)
            scores.append(risk.score(verdict["level"]))
        heat.append({"lat": c["lat"], "lng": c["lng"], "mile": c["mile"], "hours": scores})

    hours = [(departure + timedelta(hours=h)).isoformat() for h in range(FORECAST_HOURS)]
    return Response({"points": heat, "hours": hours, "total_miles": total_miles})


# ---------------------------------------------------------------- smart departure

@api_view(["POST"])
def smart_departure(request):
    """Find a safer departure window without extra weather API calls.

    Body: {origin, destination, departure, load_weight_lb, sample_miles}
    Runs the plan pipeline once at the requested departure, then reuses the
    already-fetched 49-hour checkpoint forecasts to score candidate departures
    at +3h..+48h (step 3h). An alternative qualifies only if its
    (no_travel_miles, severe_miles, high_miles, avg_score) tuple is strictly
    better than the current one. Returns up to 3, best-first; best is null
    when leaving now is already optimal.
    """
    try:
        origin = request.data["origin"]
        destination = request.data["destination"]
        departure = _parse_departure(request.data["departure"])
        load_lb = float(request.data.get("load_weight_lb", 0))
        sample_miles = float(request.data.get("sample_miles", 25))
    except (KeyError, ValueError, TypeError) as e:
        return Response({"error": f"Invalid input: {e}"}, status=http.HTTP_400_BAD_REQUEST)

    bad = _validate_departure(departure)
    if bad:
        return bad

    try:
        o_ll = geocode(origin)
        d_ll = geocode(destination)
    except ValueError as e:
        return Response({"error": str(e)}, status=http.HTTP_422_UNPROCESSABLE_ENTITY)
    except Exception as e:
        return Response({"error": f"Routing service error: {e}"}, status=http.HTTP_502_BAD_GATEWAY)

    try:
        routes, weather = _run_pipeline(o_ll, d_ll, departure, load_lb, sample_miles)
    except ValueError as e:
        return Response({"error": str(e)}, status=http.HTTP_422_UNPROCESSABLE_ENTITY)
    except Exception as e:
        return Response({"error": f"Routing/weather service error: {e}"},
                        status=http.HTTP_502_BAD_GATEWAY)

    best_idx = risk.rank_routes(routes)[0]
    rec = routes[best_idx]
    base_cps = [{"lat": c["lat"], "lng": c["lng"], "mile": c["mile"]} for c in rec["checkpoints"]]
    current_stats = rec["risk_stats"]
    current_tuple = _tuple_of(current_stats)

    alternatives = []
    for offset in range(3, FORECAST_HOURS, 3):
        cand_dep = departure + timedelta(hours=offset)
        pseudo = []
        for c in base_cps:
            w = weather[(c["lat"], c["lng"])]
            eta = cand_dep + timedelta(hours=c["mile"] / rec["avg_mph"])
            i = _nearest_hour(w["time"], eta)
            verdict = risk.classify_checkpoint(w["wind"][i], w["rain"][i], w["snow"][i], load_lb)
            pseudo.append({"mile": c["mile"], "level": verdict["level"]})
        stats = risk.route_stats({"checkpoints": pseudo, "duration_s": rec["duration_s"]})
        if _tuple_of(stats) < current_tuple:
            alternatives.append(
                {"departure": cand_dep.isoformat(), **_round_stats(stats)}
            )

    alternatives.sort(
        key=lambda a: (
            a["no_travel_miles"], a["severe_miles"], a["high_miles"], a["avg_score"]
        )
    )
    alternatives = alternatives[:3]
    best = alternatives[0] if alternatives else None

    return Response({
        "current": {"departure": departure.isoformat(), **_round_stats(current_stats)},
        "alternatives": alternatives,
        "best": best,
    })


# ---------------------------------------------------------------- auth

@api_view(["POST"])
def signup(request):
    """Create a driver account. Body: {username, password}."""
    username = (request.data.get("username") or "").strip()
    password = request.data.get("password") or ""
    if not username:
        return Response({"error": "Username is required."}, status=http.HTTP_400_BAD_REQUEST)
    if User.objects.filter(username=username).exists():
        return Response({"error": "Username is already taken."}, status=http.HTTP_400_BAD_REQUEST)
    if len(password) < 6:
        return Response(
            {"error": "Password must be at least 6 characters."},
            status=http.HTTP_400_BAD_REQUEST,
        )
    user = User.objects.create_user(username=username, password=password)
    token = Token.objects.create(user=user)
    return Response({"token": token.key, "username": user.username}, status=http.HTTP_201_CREATED)


@api_view(["POST"])
def login(request):
    """Log in a driver. Body: {username, password}."""
    user = authenticate(
        username=request.data.get("username"), password=request.data.get("password")
    )
    if not user:
        return Response(
            {"error": "Invalid username or password."}, status=http.HTTP_400_BAD_REQUEST
        )
    token, _ = Token.objects.get_or_create(user=user)
    return Response({"token": token.key, "username": user.username})


@api_view(["GET"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def me(request):
    return Response({"username": request.user.username})


# ---------------------------------------------------------------- trips

def _recommended_index(plan_result):
    rec = plan_result.get("recommended") if isinstance(plan_result, dict) else None
    if isinstance(rec, dict):
        return rec.get("index")
    return rec if isinstance(rec, int) else None


def _trip_summary(t):
    return {
        "id": t.id,
        "name": t.name,
        "origin": t.origin,
        "destination": t.destination,
        "departure": t.departure.isoformat(),
        "load_weight_lb": t.load_weight_lb,
        "sample_miles": t.sample_miles,
        "recommended_index": _recommended_index(t.plan_result or {}),
        "created_at": t.created_at.isoformat(),
    }


@api_view(["GET", "POST"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def trips(request):
    if request.method == "GET":
        own = Trip.objects.filter(user=request.user)
        return Response([_trip_summary(t) for t in own])
    try:
        origin = request.data["origin"]
        destination = request.data["destination"]
        departure = _parse_departure(request.data["departure"])
        load_lb = float(request.data.get("load_weight_lb", 0))
        sample_miles = float(request.data.get("sample_miles", 25))
        plan_result = request.data.get("plan_result") or {}
    except (KeyError, ValueError, TypeError) as e:
        return Response({"error": f"Invalid input: {e}"}, status=http.HTTP_400_BAD_REQUEST)
    trip = Trip.objects.create(
        user=request.user,
        name=(request.data.get("name") or "").strip(),
        origin=origin,
        destination=destination,
        departure=departure,
        load_weight_lb=load_lb,
        sample_miles=sample_miles,
        plan_result=plan_result,
    )
    body = _trip_summary(trip)
    body["plan_result"] = trip.plan_result
    return Response(body, status=http.HTTP_201_CREATED)


@api_view(["GET", "DELETE"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def trip_detail(request, pk):
    trip = get_object_or_404(Trip, pk=pk, user=request.user)
    if request.method == "DELETE":
        trip.delete()
        return Response(status=http.HTTP_204_NO_CONTENT)
    body = _trip_summary(trip)
    body["plan_result"] = trip.plan_result
    return Response(body)
