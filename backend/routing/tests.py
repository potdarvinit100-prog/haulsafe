"""Tests for the HaulSafe routing backend: risk bands, load rules, ranking,
geo sampling, departure validation, the 3-route guarantee, auth, trips and
smart departure. External APIs are mocked; risk math is real."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from . import geo, risk

CHI_DENV = [(41.8781, -87.6298), (39.7392, -104.9903)]  # ~920 miles apart
DIST_M = 920 * 1609.344
DUR_S = 55200  # -> avg 60 mph


def midnight_utc():
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def weather_for(points, wind_by_hour=None, base_wind=10.0):
    """Build a fake get_hourly_weather result: 72 hourly slots from midnight."""
    base = midnight_utc()
    times = [(base + timedelta(hours=h)).isoformat() for h in range(72)]
    out = {}
    for pt in points:
        winds = [base_wind] * 72
        if wind_by_hour:
            for h, v in wind_by_hour.items():
                winds[h] = v
        out[pt] = {
            "time": times,
            "wind": winds,
            "rain": [0.0] * 72,
            "snow": [0.0] * 72,
        }
    return out


def calm_weather(points):
    return weather_for(points, wind_by_hour={})


def fake_route(i=0, dist=DIST_M, dur=DUR_S):
    return {"geometry": f"fake-{i}", "distance_m": dist, "duration_s": dur}


def mock_external(testcase, routes, weather_fn=calm_weather):
    """Patch geocode/routes/waypoint/polyline/weather for plan-like views."""
    p1 = patch("routing.views.geocode", return_value=CHI_DENV[0])
    p2 = patch("routing.views.get_routes", return_value=routes)
    p3 = patch("routing.views.get_route_via_waypoint")
    p4 = patch("routing.geo.decode_polyline", return_value=list(CHI_DENV))
    p5 = patch("routing.views.get_hourly_weather", side_effect=weather_fn)
    mocks = [p.start() for p in (p1, p2, p3, p4, p5)]
    testcase.addCleanup(lambda: [p.stop() for p in (p1, p2, p3, p4, p5)])
    return mocks


# ------------------------------------------------------------- thresholds

class ThresholdBandTests(TestCase):
    def test_wind_bands(self):
        cases = [
            (24.9, "Low"), (25, "Moderate"), (34, "Moderate"),
            (35, "High"), (44, "High"), (45, "Severe"),
            (54, "Severe"), (55, "No Travel"), (80, "No Travel"),
        ]
        for mph, expected in cases:
            with self.subTest(mph=mph):
                self.assertEqual(risk.wind_level(mph), expected)

    def test_rain_bands(self):
        cases = [
            (0.09, "Low"), (0.10, "Moderate"), (0.24, "Moderate"),
            (0.25, "High"), (0.49, "High"), (0.50, "Severe"),
            (0.99, "Severe"), (1.00, "No Travel"), (1.01, "No Travel"),
        ]
        for rate, expected in cases:
            with self.subTest(rate=rate):
                self.assertEqual(risk.rain_level(rate), expected)

    def test_snow_bands(self):
        cases = [
            (0.49, "Low"), (0.5, "Moderate"), (0.99, "Moderate"),
            (1.0, "High"), (1.99, "High"), (2.0, "Severe"),
            (2.99, "Severe"), (3.0, "No Travel"), (3.1, "No Travel"),
        ]
        for rate, expected in cases:
            with self.subTest(rate=rate):
                self.assertEqual(risk.snow_level(rate), expected)


class LoadRuleTests(TestCase):
    def check(self, wind, load):
        return risk.classify_checkpoint(wind, 0.0, 0.0, load)["level"]

    def test_wind_55_no_travel_any_load(self):
        self.assertEqual(self.check(60, 10_000), "No Travel")
        self.assertEqual(self.check(55, 80_000), "No Travel")

    def test_wind_45_54_heavy_load_no_travel(self):
        self.assertEqual(self.check(50, 35_000), "No Travel")
        self.assertEqual(self.check(50, 20_000), "Severe")  # light load: band only

    def test_wind_35_44_very_heavy_load_severe(self):
        self.assertEqual(self.check(40, 45_000), "Severe")
        self.assertEqual(self.check(40, 30_000), "High")  # band only

    def test_load_never_softens(self):
        self.assertEqual(self.check(30, 80_000), "Moderate")


# ------------------------------------------------------------- ranking

def mkroute(levels, duration=3600):
    return {
        "checkpoints": [{"mile": m, "level": lvl} for m, lvl in levels],
        "duration_s": duration,
    }


class RecommendOrderingTests(TestCase):
    def test_no_travel_ranks_before_severe(self):
        # 0 no-travel miles beats 5 no-travel miles even with more severe miles:
        # no_travel_miles is the first sort key.
        a = mkroute([(0, "Severe"), (20, "Low"), (40, "Low")])   # 20 severe mi
        b = mkroute([(0, "No Travel"), (5, "Low"), (40, "Low")])  # 5 no-travel mi
        self.assertEqual(risk.recommend([a, b]), 0)
        self.assertEqual(risk.recommend([b, a]), 1)

    def test_fewer_severe_miles_wins(self):
        a = mkroute([(0, "Severe"), (5, "Low"), (20, "Low")])
        b = mkroute([(0, "Severe"), (10, "Low"), (20, "Low")])
        self.assertEqual(risk.recommend([a, b]), 0)

    def test_fewer_high_miles_breaks_severe_tie(self):
        a = mkroute([(0, "Severe"), (5, "High"), (15, "Low"), (20, "Low")])
        b = mkroute([(0, "Severe"), (5, "High"), (7, "Low"), (20, "Low")])
        self.assertEqual(risk.recommend([a, b]), 1)

    def test_lower_avg_breaks_high_tie(self):
        a = mkroute([(0, "High"), (10, "Moderate"), (20, "Low")])
        b = mkroute([(0, "High"), (10, "Low"), (20, "Low")])
        self.assertEqual(risk.recommend([a, b]), 1)

    def test_shorter_time_breaks_full_tie(self):
        a = mkroute([(0, "Low"), (10, "Low")], duration=3600)
        b = mkroute([(0, "Low"), (10, "Low")], duration=7200)
        self.assertEqual(risk.recommend([a, b]), 0)

    def test_ranking_returns_full_order(self):
        mild = mkroute([(0, "Low"), (20, "Low")])
        rough = mkroute([(0, "Severe"), (20, "Low")])
        closed = mkroute([(0, "No Travel"), (20, "Low")])
        self.assertEqual(risk.rank_routes([rough, closed, mild]), [2, 0, 1])

    def test_route_stats_segments(self):
        route = mkroute([(0, "Low"), (10, "Severe"), (25, "High"), (30, "Low")])
        s = risk.route_stats(route)
        self.assertAlmostEqual(s["low_miles"], 10.0)
        self.assertAlmostEqual(s["severe_miles"], 15.0)
        self.assertAlmostEqual(s["high_miles"], 5.0)
        self.assertAlmostEqual(s["no_travel_miles"], 0.0)
        self.assertAlmostEqual(s["avg_score"], (0 + 3 + 2 + 0) / 4)  # Low0 Mod1 High2 Sev3 NT4


# ------------------------------------------------------------- geo

class GeoTests(TestCase):
    def test_sample_checkpoints_even_spacing(self):
        cps, total = geo.sample_checkpoints([(0.0, 0.0), (0.0, 1.0)], 25)
        self.assertEqual([c["mile"] for c in cps][:3], [0.0, 25, 50])
        self.assertAlmostEqual(cps[-1]["mile"], total, places=1)
        self.assertAlmostEqual(total, 69.1, delta=0.5)  # 1 deg lng at equator
        # interpolated point sits on the segment
        self.assertAlmostEqual(cps[1]["lat"], 0.0, places=4)
        self.assertGreater(cps[1]["lng"], 0.3)

    def test_haversine_known_distance(self):
        self.assertAlmostEqual(geo.haversine_miles(CHI_DENV[0], CHI_DENV[1]), 920, delta=15)


# ------------------------------------------------------------- departure validation

class DepartureValidationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        now = datetime.now(timezone.utc)
        self.ok_dep = (now + timedelta(hours=1)).isoformat()
        self.late_dep = (now + timedelta(hours=72)).isoformat()
        self.early_dep = (now - timedelta(hours=2)).isoformat()

    def test_plan_rejects_outside_window(self):
        for dep in (self.late_dep, self.early_dep):
            r = self.client.post("/api/plan/", {
                "origin": "Chicago, IL", "destination": "Denver, CO",
                "departure": dep, "load_weight_lb": 35000, "sample_miles": 25,
            }, format="json")
            self.assertEqual(r.status_code, 400)
            self.assertIn("48 hours", r.json()["error"])

    def test_corridor_rejects_outside_window(self):
        r = self.client.post("/api/corridor/", {
            "path": [[41.88, -87.63], [39.74, -104.99]],
            "departure": self.late_dep, "load_weight_lb": 35000,
        }, format="json")
        self.assertEqual(r.status_code, 400)

    def test_smart_departure_rejects_outside_window(self):
        r = self.client.post("/api/smart-departure/", {
            "origin": "Chicago, IL", "destination": "Denver, CO",
            "departure": self.late_dep, "load_weight_lb": 35000, "sample_miles": 25,
        }, format="json")
        self.assertEqual(r.status_code, 400)

    def test_plan_rejects_bad_location(self):
        with patch("routing.views.geocode", side_effect=ValueError("nope")):
            r = self.client.post("/api/plan/", {
                "origin": "Nowhere XX", "destination": "Denver, CO",
                "departure": self.ok_dep, "load_weight_lb": 35000, "sample_miles": 25,
            }, format="json")
            self.assertEqual(r.status_code, 422)


# ------------------------------------------------------------- 3-route guarantee

class ThreeRouteTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.dep = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        self.body = {
            "origin": "Chicago, IL", "destination": "Denver, CO",
            "departure": self.dep, "load_weight_lb": 35000, "sample_miles": 25,
        }

    def test_exactly_three_routes_with_waypoint_fallback(self):
        mocks = mock_external(self, [fake_route(0), fake_route(1)])
        mocks[2].return_value = fake_route(2, dist=DIST_M * 1.2)  # distinct detour
        r = self.client.post("/api/plan/", self.body, format="json")
        self.assertEqual(r.status_code, 200)
        routes = r.json()["routes"]
        self.assertEqual(len(routes), 3)
        self.assertTrue(routes[2]["detour"])
        self.assertIn("offset waypoint", routes[2]["note"])

    def test_near_duplicate_detour_rejected(self):
        mocks = mock_external(self, [fake_route(0), fake_route(1)])
        mocks[2].side_effect = [
            fake_route(9, dist=DIST_M * 1.01),   # within 3% -> rejected
            fake_route(8, dist=DIST_M * 1.25),   # distinct -> accepted
        ]
        r = self.client.post("/api/plan/", self.body, format="json")
        routes = r.json()["routes"]
        self.assertEqual(len(routes), 3)
        self.assertEqual(mocks[2].call_count, 2)  # near-dup rejected, next tried
        self.assertTrue(routes[2]["detour"])
        self.assertIn("offset waypoint", routes[2]["note"])

    def test_guarantee_when_osrm_fails(self):
        mocks = mock_external(self, [fake_route(0), fake_route(1)])
        mocks[2].side_effect = ValueError("no detour")
        r = self.client.post("/api/plan/", self.body, format="json")
        routes = r.json()["routes"]
        self.assertEqual(len(routes), 3)
        self.assertTrue(routes[2]["detour"])
        self.assertIn("No distinct alternate", routes[2]["note"])


class PlanResponseTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.dep = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

    def test_recommended_object_and_breakdown(self):
        mock_external(self, [fake_route(0), fake_route(1, dur=DUR_S + 600),
                             fake_route(2, dur=DUR_S + 1200)])
        r = self.client.post("/api/plan/", {
            "origin": "Chicago, IL", "destination": "Denver, CO",
            "departure": self.dep, "load_weight_lb": 35000, "sample_miles": 25,
        }, format="json")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        rec = data["recommended"]
        self.assertEqual(rec["index"], 0)  # all calm: shortest wins
        self.assertIn("Route 1", rec["reasoning"])
        self.assertEqual(sorted(rec["ranking"]), [0, 1, 2])
        self.assertEqual(rec["ranking"][0], 0)
        for route in data["routes"]:
            bd = route["risk_breakdown"]
            self.assertEqual(
                set(bd),
                {"severe_miles", "high_miles", "moderate_miles", "low_miles",
                 "no_travel_miles", "avg_score"},
            )
            self.assertAlmostEqual(bd["low_miles"], route["total_miles"], delta=1.0)
            self.assertIn("detour", route)


# ------------------------------------------------------------- corridor

class CorridorTests(TestCase):
    def test_49_hourly_scores(self):
        client = APIClient()
        dep = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        with patch("routing.views.get_hourly_weather", side_effect=calm_weather):
            r = client.post("/api/corridor/", {
                "path": [[41.88, -87.63], [39.74, -104.99]],
                "departure": dep, "load_weight_lb": 35000,
            }, format="json")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(len(data["hours"]), 49)
        self.assertTrue(all(len(p["hours"]) == 49 for p in data["points"]))
        self.assertTrue(all(s == 0 for p in data["points"] for s in p["hours"]))  # all Low


# ------------------------------------------------------------- auth + trips

class AuthTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_signup_login_me(self):
        r = self.client.post("/api/auth/signup/",
                             {"username": "driver1", "password": "secret1"}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertIn("token", r.json())
        r = self.client.post("/api/auth/login/",
                             {"username": "driver1", "password": "secret1"}, format="json")
        self.assertEqual(r.status_code, 200)
        token = r.json()["token"]
        r = self.client.get("/api/auth/me/", HTTP_AUTHORIZATION=f"Token {token}")
        self.assertEqual(r.json(), {"username": "driver1"})

    def test_signup_validations(self):
        self.client.post("/api/auth/signup/",
                         {"username": "dup", "password": "secret1"}, format="json")
        r = self.client.post("/api/auth/signup/",
                             {"username": "dup", "password": "secret1"}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/auth/signup/",
                             {"username": "short", "password": "123"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_login_bad_credentials(self):
        r = self.client.post("/api/auth/login/",
                             {"username": "nobody", "password": "wrong"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_me_requires_token(self):
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)


class TripTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.dep = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        self.plan_result = {"recommended": {"index": 1, "reasoning": "r", "ranking": [1, 0, 2]}}

    def auth_as(self, username):
        self.client.post("/api/auth/signup/",
                         {"username": username, "password": "secret1"}, format="json")
        token = self.client.post(
            "/api/auth/login/", {"username": username, "password": "secret1"},
            format="json").json()["token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")

    def test_crud_and_owner_isolation(self):
        self.auth_as("alice")
        r = self.client.post("/api/trips/", {
            "name": "Denver run", "origin": "Chicago, IL", "destination": "Denver, CO",
            "departure": self.dep, "load_weight_lb": 35000, "sample_miles": 25,
            "plan_result": self.plan_result,
        }, format="json")
        self.assertEqual(r.status_code, 201)
        trip_id = r.json()["id"]

        r = self.client.get("/api/trips/")
        items = r.json()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["recommended_index"], 1)
        self.assertNotIn("plan_result", items[0])  # summary shape

        r = self.client.get(f"/api/trips/{trip_id}/")
        self.assertEqual(r.json()["plan_result"], self.plan_result)

        # another driver sees nothing and cannot touch alice's trip
        self.auth_as("bob")
        self.assertEqual(self.client.get("/api/trips/").json(), [])
        self.assertEqual(self.client.get(f"/api/trips/{trip_id}/").status_code, 404)
        self.assertEqual(self.client.delete(f"/api/trips/{trip_id}/").status_code, 404)

        self.auth_as("alice")
        self.assertEqual(self.client.delete(f"/api/trips/{trip_id}/").status_code, 204)
        self.assertEqual(self.client.get(f"/api/trips/{trip_id}/").status_code, 404)

    def test_trips_require_token(self):
        self.assertEqual(self.client.get("/api/trips/").status_code, 401)

    def test_legacy_int_recommended_shape(self):
        self.auth_as("carol")
        r = self.client.post("/api/trips/", {
            "origin": "A", "destination": "B", "departure": self.dep,
            "load_weight_lb": 1000, "sample_miles": 25,
            "plan_result": {"recommended": 2},
        }, format="json")
        self.assertEqual(r.json()["recommended_index"], 2)


# ------------------------------------------------------------- smart departure

class SmartDepartureTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.now = datetime.now(timezone.utc)
        self.departure = self.now + timedelta(hours=1)
        self.body = {
            "origin": "Chicago, IL", "destination": "Denver, CO",
            "departure": self.departure.isoformat(),
            "load_weight_lb": 35000, "sample_miles": 25,
        }

    def test_finds_better_window(self):
        # Storm everywhere except a calm window +8h..+20h after departure:
        # shifting departure forward moves more of the drive into calm air.
        h0 = int((self.departure - midnight_utc()).total_seconds() // 3600)
        fn = lambda points: weather_for(  # noqa: E731
            points, wind_by_hour={h: 10.0 for h in range(h0 + 8, h0 + 21)},
            base_wind=40.0)
        mock_external(self, [fake_route(0), fake_route(1), fake_route(2)], weather_fn=fn)
        r = self.client.post("/api/smart-departure/", self.body, format="json")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("current", data)
        self.assertIn("alternatives", data)
        self.assertLessEqual(len(data["alternatives"]), 3)
        self.assertIsNotNone(data["best"])
        self.assertLess(data["best"]["high_miles"], data["current"]["high_miles"])
        # alternatives sorted best-first
        keys = [(a["no_travel_miles"], a["severe_miles"], a["high_miles"], a["avg_score"])
                for a in data["alternatives"]]
        self.assertEqual(keys, sorted(keys))

    def test_null_when_now_is_best(self):
        mock_external(self, [fake_route(0), fake_route(1), fake_route(2)],
                      weather_fn=calm_weather)
        r = self.client.post("/api/smart-departure/", self.body, format="json")
        data = r.json()
        self.assertEqual(data["alternatives"], [])
        self.assertIsNone(data["best"])
