"""
Run with:  python manage.py test
Covers the risk table, load rules, checkpoint spacing, ETA math, route
summaries and the 4-step recommendation. The plan-trip API test uses mock
providers so it runs offline.
"""
from datetime import datetime, timezone

from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient

from routes.services import risk
from routes.services.geo import build_checkpoints, checkpoint_miles, cumulative_miles
from routes.services.risk import HIGH, LOW, MODERATE, NO_TRAVEL, SEVERE


class RiskTableTests(SimpleTestCase):
    def test_wind_bands(self):
        cases = [(0, LOW), (24.9, LOW), (25, MODERATE), (34.9, MODERATE), (35, HIGH),
                 (44.9, HIGH), (45, SEVERE), (54.9, SEVERE), (55, NO_TRAVEL), (80, NO_TRAVEL)]
        for mph, expected in cases:
            self.assertEqual(risk.wind_level(mph), expected, mph)

    def test_rain_bands(self):
        cases = [(0.09, LOW), (0.10, MODERATE), (0.24, MODERATE), (0.25, HIGH), (0.49, HIGH),
                 (0.50, SEVERE), (1.00, SEVERE), (1.01, NO_TRAVEL)]
        for r, expected in cases:
            self.assertEqual(risk.rain_level(r), expected, r)

    def test_snow_bands(self):
        cases = [(0.4, LOW), (0.5, MODERATE), (0.9, MODERATE), (1.0, HIGH), (1.9, HIGH),
                 (2.0, SEVERE), (3.0, SEVERE), (3.1, NO_TRAVEL)]
        for s, expected in cases:
            self.assertEqual(risk.snow_level(s), expected, s)

    def test_max_of_conditions(self):
        # Moderate wind, High rain, Low snow -> High
        self.assertEqual(risk.risk_level(30, 0.3, 0.0, 0), HIGH)
        self.assertEqual(risk.risk_level(5, 0.0, 2.5, 0), SEVERE)


class LoadRuleTests(SimpleTestCase):
    def test_acceptance_45mph_35k_is_no_travel(self):
        self.assertEqual(risk.risk_level(45, 0, 0, 35_000), NO_TRAVEL)

    def test_55mph_no_travel_any_load(self):
        self.assertEqual(risk.risk_level(55, 0, 0, 0), NO_TRAVEL)

    def test_45_54_requires_over_30k(self):
        self.assertEqual(risk.risk_level(50, 0, 0, 30_000), SEVERE)
        self.assertEqual(risk.risk_level(50, 0, 0, 30_001), NO_TRAVEL)

    def test_35_44_over_40k_is_severe(self):
        self.assertEqual(risk.risk_level(40, 0, 0, 40_000), HIGH)
        self.assertEqual(risk.risk_level(40, 0, 0, 40_500), SEVERE)

    def test_load_rule_never_downgrades(self):
        # 40 mph + heavy load -> Severe, but 1.5 in/hr rain is already No Travel
        self.assertEqual(risk.risk_level(40, 1.5, 0, 45_000), NO_TRAVEL)

    def test_light_wind_heavy_load_unchanged(self):
        self.assertEqual(risk.risk_level(20, 0, 0, 80_000), LOW)

    def test_assess_flags_load_adjustment(self):
        a = risk.assess(45, 0, 0, 35_000)
        self.assertEqual(a["label"], "No Travel")
        self.assertTrue(a["load_adjusted"])
        self.assertEqual(a["factors"]["wind"], "Severe")


class CheckpointTests(SimpleTestCase):
    def test_marks_include_start_and_end(self):
        self.assertEqual(checkpoint_miles(60, 25), [0, 25, 50, 60])
        self.assertEqual(checkpoint_miles(50, 25), [0, 25, 50])

    def test_spacing_along_polyline(self):
        # Straight line north along a meridian: 1 deg lat ~= 69.09 mi
        coords = [[30 + i * 0.1, -100] for i in range(31)]  # ~207 mi
        total = cumulative_miles(coords)[-1]
        cps = build_checkpoints(coords, total, 25)
        self.assertEqual(cps[0]["mile"], 0)
        self.assertAlmostEqual(cps[-1]["mile"], round(total, 1), places=1)
        self.assertAlmostEqual(cps[-1]["lat"], 33.0, places=4)
        for a, b in zip(cps, cps[1:-1]):
            self.assertAlmostEqual(b["lat"] - a["lat"], 25 / 69.09, places=2)


def _route(rid, severe=0, nt=0, high=0, avg=1.0, dur=600):
    return {
        "id": rid,
        "name": f"Route {rid}",
        "summary": {
            "severe_or_worse_miles": severe + nt, "severe_miles": severe, "no_travel_miles": nt,
            "high_miles": high, "avg_risk_score": avg, "total_duration_min": dur,
        },
    }


class RecommendationTests(SimpleTestCase):
    def test_step1_fewest_severe(self):
        routes = [_route(1, severe=12, dur=500), _route(2, severe=0, dur=700), _route(3, nt=25)]
        ranking, best, reason = risk.recommend(routes)
        self.assertEqual(best, 2)
        self.assertEqual(ranking, [2, 1, 3])
        self.assertIn("Severe", reason)

    def test_step2_high_miles(self):
        routes = [_route(1, high=30), _route(2, high=10), _route(3, high=20)]
        self.assertEqual(risk.recommend(routes)[1], 2)

    def test_step3_avg_risk(self):
        routes = [_route(1, avg=1.6), _route(2, avg=1.2, dur=900), _route(3, avg=1.4)]
        self.assertEqual(risk.recommend(routes)[1], 2)

    def test_step4_duration(self):
        routes = [_route(1, dur=700), _route(2, dur=650), _route(3, dur=800)]
        best = risk.recommend(routes)
        self.assertEqual(best[1], 2)
        self.assertIn("travel time", best[2])

    def test_summary_miles_add_up(self):
        def cp(mile, level):
            return {"mile": mile, "risk": {"level": level}}

        cps = [cp(0, LOW), cp(25, SEVERE), cp(50, LOW), cp(60, HIGH)]
        s = risk.summarize_route(cps, 60, 60)
        self.assertEqual(s["low_miles"] + s["severe_miles"] + s["high_miles"], 60)
        self.assertEqual(s["severe_miles"], 25)   # 12.5 before + 12.5 after
        self.assertEqual(s["high_miles"], 5)      # half of the final 10 mi segment
        self.assertAlmostEqual(s["avg_risk_score"], (30 * 1 + 25 * 4 + 5 * 3) / 60, places=2)


@override_settings(ROUTING_PROVIDER="mock", WEATHER_PROVIDER="mock")
class PlanTripApiTests(SimpleTestCase):
    def test_plan_trip_mock(self):
        resp = APIClient().post(
            "/api/plan-trip",
            {
                "origin_lat": 34.0522, "origin_lon": -118.2437,
                "dest_lat": 39.7392, "dest_lon": -104.9903,
                "departure_iso": datetime.now(timezone.utc).isoformat(),
                "load_weight_lb": 40500, "sample_miles": 25,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertEqual(len(data["routes"]), 3)
        self.assertIn(data["recommended_route_id"], [r["id"] for r in data["routes"]])
        for r in data["routes"]:
            cps = r["checkpoints"]
            self.assertEqual(cps[0]["mile"], 0)
            self.assertEqual(cps[-1]["mile"], r["total_miles"])
            for c in cps:
                self.assertIn("eta_iso", c)
                self.assertIn("wind_mph", c["weather"])
                self.assertIn(c["risk"]["label"], risk.LEVEL_LABELS.values())
            frames = data["corridor"]["routes"][str(r["id"])]
            self.assertEqual(len(frames), len(cps))
            self.assertEqual(len(frames[0]["risk"]), 49)

        corridor = APIClient().get(
            f"/api/corridor-weather?trip_id={data['trip_id']}&route_id=1"
        )
        self.assertEqual(corridor.status_code, 200)

    def test_validation(self):
        resp = APIClient().post("/api/plan-trip", {"origin_lat": 999}, format="json")
        self.assertEqual(resp.status_code, 400)
