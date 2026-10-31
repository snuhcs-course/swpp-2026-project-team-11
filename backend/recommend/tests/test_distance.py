import json

from django.test import SimpleTestCase, TestCase, override_settings

from menus.models import Restaurant
from recommend.distance import distance_m, with_distances

DAY = "2026-09-29"
STUDENT_CENTER = (37.45932, 126.95058)  # 학생회관식당 in the shared snapshot


def candidate(*offers):
    return {"food_id": 1, "name": "Dish", "offers": [
        {"restaurant": name, "meal": "LU", "price": 5000, "lat": lat, "lng": lng}
        for name, lat, lng in offers]}


class DistanceTests(SimpleTestCase):
    def test_haversine_in_whole_meters(self):
        self.assertEqual(distance_m(*STUDENT_CENTER, *STUDENT_CENTER), 0)
        self.assertEqual(distance_m(37.0, 127.0, 38.0, 127.0), 111195)  # one degree of latitude
        self.assertEqual(distance_m(*STUDENT_CENTER, 37.46451, 126.95424), 661)  # to 220동식당

    def test_without_a_location_distances_are_unknown_and_nothing_is_cut(self):
        [located] = with_distances([candidate(("Far", 37.0, 127.0))], None, max_distance_m=100)
        self.assertIsNone(located["offers"][0]["distance_m"])

    def test_the_cutoff_drops_far_offers_and_dishes_left_without_one(self):
        near_and_far = candidate(("Near", *STUDENT_CENTER), ("Far", 37.46451, 126.95424))
        only_far = candidate(("Far", 37.46451, 126.95424))
        unlocated = candidate(("Unknown", None, None))
        located = with_distances([near_and_far, only_far, unlocated], STUDENT_CENTER, max_distance_m=500)
        self.assertEqual([[(o["restaurant"], o["distance_m"]) for o in c["offers"]] for c in located],
                         [[("Near", 0)], [("Unknown", None)]])

    def test_a_cafeteria_missing_either_coordinate_has_no_distance(self):
        [located] = with_distances([candidate(("No lng", 37.46451, None), ("No lat", None, 126.95424))],
                                   STUDENT_CENTER, max_distance_m=100)
        self.assertEqual([o["distance_m"] for o in located["offers"]], [None, None])

    def test_without_a_cutoff_every_offer_stays(self):
        located = with_distances([candidate(("Far", 37.46451, 126.95424))], STUDENT_CENTER)
        self.assertEqual(located[0]["offers"][0]["distance_m"], 661)


class SessionDistanceTests(TestCase):
    fixtures = ["menus_2026-09-29"]

    def start(self, **body):
        return self.client.post("/api/sessions/", content_type="application/json",
                                data=json.dumps({"date": DAY, "meal": "LU", **body}))

    def offers(self, state):
        url = f"/api/sessions/{state['session_id']}/recommend-now/"
        return self.client.post(url, content_type="application/json").json()["step"]["food"]["offers"]

    def test_a_location_adds_distances_and_the_cutoff_is_off_by_default(self):
        state = self.start(location={"lat": 37.0, "lng": 127.0}).json()
        self.assertEqual(state["candidate_count"], 193)
        self.assertTrue(all(o["distance_m"] > 50_000 for o in self.offers(state) if o["lat"] is not None))

    def test_without_a_location_distances_are_null(self):
        self.assertTrue(all(o["distance_m"] is None for o in self.offers(self.start().json())))

    def test_a_cafeteria_with_half_a_location_does_not_break_the_session(self):
        Restaurant.objects.filter(name="학생회관식당").update(lng=None)
        response = self.start(location={"lat": STUDENT_CENTER[0], "lng": STUDENT_CENTER[1]})
        self.assertEqual(response.status_code, 201)

    @override_settings(RECOMMEND_MAX_DISTANCE_M=300)
    def test_the_cutoff_leaves_out_far_cafeterias(self):
        near = self.start(location={"lat": STUDENT_CENTER[0], "lng": STUDENT_CENTER[1]}).json()
        self.assertLess(near["candidate_count"], 193)
        self.assertTrue(all(o["distance_m"] is None or o["distance_m"] <= 300 for o in self.offers(near)))
        self.assertEqual(self.start().json()["candidate_count"], 193)  # no location: nothing to cut

    def test_a_malformed_location_is_400(self):
        for location in ({"lat": 37.4}, [37.4, 126.9], {"lat": "37.4", "lng": 126.9},
                         {"lat": True, "lng": 126.9}, {"lat": 91, "lng": 126.9}):
            response = self.start(location=location)
            self.assertEqual(response.status_code, 400, location)
            self.assertEqual(response.json()["error"]["code"], "invalid_request")
