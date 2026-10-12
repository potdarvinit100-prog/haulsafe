"""Weather risk classification straight from the assessment brief."""

LEVELS = ["Low", "Moderate", "High", "Severe", "No Travel"]
_SCORE = {level: i for i, level in enumerate(LEVELS)}


def _band(value, thresholds):
    """Classify value into a level using [(upper_bound, level), ...]."""
    for upper, level in thresholds:
        if value < upper:
            return level
    return thresholds[-1][1]


def wind_level(mph):
    return _band(mph, [(25, "Low"), (35, "Moderate"), (45, "High"), (55, "Severe"), (float("inf"), "No Travel")])


def rain_level(in_per_hr):
    return _band(
        in_per_hr,
        [(0.10, "Low"), (0.25, "Moderate"), (0.50, "High"), (1.00, "Severe"), (float("inf"), "No Travel")],
    )


def snow_level(in_per_hr):
    return _band(
        in_per_hr,
        [(0.5, "Low"), (1.0, "Moderate"), (2.0, "High"), (3.0, "Severe"), (float("inf"), "No Travel")],
    )


def classify_checkpoint(wind_mph, rain_inhr, snow_inhr, load_lb):
    """Combine the three weather conditions with the load rules.

    Returns {"level", "reasons": [...]} where reasons explain the verdict.
    """
    wind = wind_level(wind_mph)
    rain_lvl = rain_level(rain_inhr)
    snow_lvl = snow_level(snow_inhr)
    level = max([wind, rain_lvl, snow_lvl], key=lambda l: _SCORE[l])
    reasons = []
    if wind != "Low":
        reasons.append(f"wind {wind_mph:.0f} mph ({wind})")
    if rain_inhr >= 0.10:
        reasons.append(f"rain {rain_inhr:.2f} in/hr ({rain_lvl})")
    if snow_inhr >= 0.5:
        reasons.append(f"snow {snow_inhr:.2f} in/hr ({snow_lvl})")

    # Load rules from the brief (can only escalate, never soften).
    if wind_mph >= 55:
        level, note = "No Travel", "wind ≥55 mph: no travel for any load"
        reasons.append(note)
    elif 45 <= wind_mph < 55 and load_lb > 30_000:
        level, note = "No Travel", f"wind {wind_mph:.0f} mph with {load_lb:,.0f} lb load: no travel"
        reasons.append(note)
    elif 35 <= wind_mph < 45 and load_lb > 40_000:
        if _SCORE["Severe"] > _SCORE[level]:
            level = "Severe"
        reasons.append(f"wind {wind_mph:.0f} mph with {load_lb:,.0f} lb load: severe")

    return {"level": level, "reasons": reasons or ["conditions within safe limits"]}


def score(level):
    return _SCORE[level]


def route_stats(route):
    """Miles per risk level plus the average risk score for one route.

    Miles are attributed exactly like recommend(): each checkpoint owns the
    segment stretching to the next checkpoint (the level sampled at the
    segment's start applies to the whole segment). Values are unrounded;
    callers round for display.
    """
    miles = {level: 0.0 for level in LEVELS}
    total_score = 0.0
    cps = route["checkpoints"]
    for i, cp in enumerate(cps):
        seg = (cps[i + 1]["mile"] - cp["mile"]) if i + 1 < len(cps) else 0
        miles[cp["level"]] = miles.get(cp["level"], 0.0) + max(seg, 0)
        total_score += _SCORE[cp["level"]]
    return {
        "no_travel_miles": miles["No Travel"],
        "severe_miles": miles["Severe"],
        "high_miles": miles["High"],
        "moderate_miles": miles["Moderate"],
        "low_miles": miles["Low"],
        "avg_score": total_score / max(len(cps), 1),
    }


def _rank_key(route):
    s = route_stats(route)
    return (
        s["no_travel_miles"],
        s["severe_miles"],
        s["high_miles"],
        s["avg_score"],
        route["duration_s"],
    )


def rank_routes(routes):
    """Indices of routes sorted best-first.

    Priority: fewest No Travel miles -> fewest Severe miles -> fewest High
    miles -> lowest average risk -> shortest travel time.

    No Travel ranks before Severe on purpose: a stretch the truck must not
    drive at all is worse than a stretch it can drive with caution, so a
    route with any no-travel miles can never win on time or averages.
    """
    return sorted(range(len(routes)), key=lambda i: _rank_key(routes[i]))


def recommend(routes):
    """Pick the best route per the brief's priority order.

    routes: list of dicts with "checkpoints" (each has "level" + "mile")
    and "duration_s". Returns the index of the recommended route.
    """
    return rank_routes(routes)[0]
