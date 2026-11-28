import json

from django.test import SimpleTestCase, TestCase

from recommend import sessions
from recommend.areas import STATIONS, distance_m, near_station

DAY = "2026-11-02"
STUDENT_CENTER = (37.45932, 126.95058)  # 학생회관식당 in the shared snapshot
SNU_STATION = STATIONS["snu_station"][1:3]


def candidate(*offers):
    return {"food_id": 1, "name": "Dish", "offers": [
        {"restaurant": name, "meal": "LU", "price": 5000, "lat": lat, "lng": lng}
        for name, lat, lng in offers]}


class AreaTests(SimpleTestCase):
    def test_haversine_in_whole_meters(self):
        self.assertEqual(distance_m(*STUDENT_CENTER, *STUDENT_CENTER), 0)
        self.assertEqual(distance_m(37.0, 127.0, 38.0, 127.0), 111195)  # one degree of latitude
        self.assertEqual(distance_m(*STUDENT_CENTER, 37.46451, 126.95424), 661)  # to 220동식당

    def test_a_station_keeps_offers_in_its_circle_and_dishes_left_with_one(self):
        inside = (SNU_STATION[0] + 0.005, SNU_STATION[1])  # 556 m north, radius 600 m
        outside = (SNU_STATION[0] + 0.0055, SNU_STATION[1])  # 612 m
        both = candidate(("Inside", *inside), ("Outside", *outside))
        only_outside = candidate(("Outside", *outside))
        unlocated = candidate(("No lat", None, SNU_STATION[1]), ("No lng", SNU_STATION[0], None))
        kept = near_station([both, only_outside, unlocated], "snu_station")
        self.assertEqual([[o["restaurant"] for o in c["offers"]] for c in kept], [["Inside"]])


class SessionAreaTests(TestCase):
    fixtures = ["menus_v3_contract"]

    def start(self, **body):
        return self.client.post("/api/sessions/", content_type="application/json",
                                data=json.dumps({"date": DAY, "meal": "LU", **body}))

    def test_campus_is_the_default_and_offers_carry_no_distance(self):
        state = self.start().json()
        self.assertEqual(state["candidate_count"], 103)
        self.assertEqual(sessions.get(state["session_id"]).area, "campus")
        url = f"/api/sessions/{state['session_id']}/recommend-now/"
        offers = self.client.post(url, content_type="application/json").json()["step"]["food"]["offers"]
        self.assertTrue(offers)
        self.assertTrue(all("distance_m" not in offer for offer in offers))

    def test_a_location_from_an_old_phone_changes_nothing(self):
        state = self.start(area="campus", location={"lat": 37.0, "lng": 127.0}).json()
        self.assertEqual(state["candidate_count"], 103)

    def test_an_unknown_area_is_400(self):
        for area in ("near", "any", "general", None, 1):
            response = self.start(area=area)
            self.assertEqual(response.status_code, 400, area)
            self.assertEqual(response.json()["error"]["code"], "invalid_request")

    def test_the_llm_engine_is_campus_only(self):
        for area in ("snu_station", "nakseongdae", "all"):
            response = self.start(area=area, engine="llm")
            self.assertEqual(response.status_code, 400, area)
            self.assertEqual(response.json()["error"]["code"], "area_llm_unsupported")
