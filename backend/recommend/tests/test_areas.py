import json
from unittest import mock

from django.test import SimpleTestCase, TestCase

from menus.allergens import ALLERGEN_VERSION
from menus.models import Restaurant, StoreMenu
from menus.personal import offers
from recommend import sessions
from recommend.areas import AREAS, STATIONS, distance_m, near_stations

DAY = "2026-11-02"
STUDENT_CENTER = (37.45932, 126.95058)  # 학생회관식당 in the shared snapshot
SNU_STATION = STATIONS["snu_station"][1:3]
NAKSEONGDAE = STATIONS["nakseongdae"][1:3]


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
        kept = near_stations([both, only_outside, unlocated], ["snu_station"])
        self.assertEqual([[o["restaurant"] for o in c["offers"]] for c in kept], [["Inside"]])

    def test_several_stations_keep_the_offers_inside_any_of_their_circles(self):
        def offers():
            return candidate(("SNU", *SNU_STATION), ("Nakseongdae", *NAKSEONGDAE), ("Campus", *STUDENT_CENTER))
        kept = {tuple(areas): [o["restaurant"] for c in near_stations([offers()], areas) for o in c["offers"]]
                for areas in (["snu_station"], ["nakseongdae"], ["snu_station", "nakseongdae"])}
        self.assertEqual(kept, {("snu_station",): ["SNU"], ("nakseongdae",): ["Nakseongdae"],
                                ("snu_station", "nakseongdae"): ["SNU", "Nakseongdae"]})


class SessionAreaTests(TestCase):
    fixtures = ["menus_v3_contract"]

    def start(self, **body):
        return self.client.post("/api/sessions/", content_type="application/json",
                                data=json.dumps({"date": DAY, "meal": "LU", **body}))

    def test_campus_is_the_default_and_offers_carry_no_distance(self):
        state = self.start().json()
        self.assertEqual(state["candidate_count"], 103)
        self.assertEqual(sessions.get(state["session_id"]).areas, ("campus",))
        url = f"/api/sessions/{state['session_id']}/recommend-now/"
        offers = self.client.post(url, content_type="application/json").json()["step"]["food"]["offers"]
        self.assertTrue(offers)
        self.assertTrue(all("distance_m" not in offer for offer in offers))

    def test_a_location_from_an_old_phone_changes_nothing(self):
        state = self.start(area="campus", location={"lat": 37.0, "lng": 127.0}).json()
        self.assertEqual(state["candidate_count"], 103)

    def test_an_apk_from_before_areas_keeps_every_restaurant(self):
        for body, areas in (({"source": "all", "distance_scope": "near"}, AREAS), ({"source": "general"}, AREAS),
                            ({"source": "cafeteria"}, ("campus",)), ({"area": None}, ("campus",)),
                            ({"area": "snu_station", "source": "all"}, ("snu_station",))):
            state = self.start(**body).json()
            self.assertEqual(sessions.get(state["session_id"]).areas, areas, body)

    def test_an_apk_with_one_area_gets_it_and_all_is_every_area(self):
        for area, areas in (("campus", ("campus",)), ("nakseongdae", ("nakseongdae",)), ("all", AREAS)):
            state = self.start(area=area).json()
            self.assertEqual(sessions.get(state["session_id"]).areas, areas, area)

    def test_areas_come_in_order_and_win_over_an_old_area(self):
        state = self.start(areas=["nakseongdae", "campus", "nakseongdae"], area="snu_station").json()
        self.assertEqual(sessions.get(state["session_id"]).areas, ("campus", "nakseongdae"))

    def test_an_unknown_area_is_400(self):
        for body in ({"area": "near"}, {"area": "any"}, {"area": "general"}, {"area": 1},
                     {"areas": []}, {"areas": ["all"]}, {"areas": ["campus", "near"]}, {"areas": "campus"}):
            response = self.start(**body)
            self.assertEqual(response.status_code, 400, body)
            self.assertEqual(response.json()["error"]["code"], "invalid_request")

    def test_the_llm_engine_is_campus_only(self):
        for body in ({"area": "snu_station"}, {"area": "nakseongdae"}, {"area": "all"},
                     {"areas": ["campus", "snu_station"]}, {"areas": ["nakseongdae"]}):
            response = self.start(**body, engine="llm")
            self.assertEqual(response.status_code, 400, body)
            self.assertEqual(response.json()["error"]["code"], "area_llm_unsupported")


class AreaUnionTests(TestCase):
    """The candidates are the union of the picked areas; every area keeps every restaurant."""
    fixtures = ["menus_v3_contract"]

    def setUp(self):
        patch = mock.patch.object(offers, "resolve", return_value="food_009")  # 김치찌개
        patch.start()
        self.addCleanup(patch.stop)
        for code, name, lat, lng in (("A7S", "가게 S", *SNU_STATION), ("A7N", "가게 N", *NAKSEONGDAE),
                                     ("A7X", "가게 X", None, None)):
            place = Restaurant.objects.create(code=code, name=name, source="naver", lat=lat, lng=lng)
            StoreMenu.objects.create(restaurant=place, raw_name="김치찌개", description=f"{name} 김치찌개",
                                     price=9000, allergen_version=ALLERGEN_VERSION)

    def restaurants(self, **body):
        response = self.client.post("/api/sessions/", content_type="application/json",
                                    data=json.dumps({"date": DAY, "meal": "LU", "engine": "decision_tree", **body}))
        self.assertEqual(response.status_code, 201, response.content)
        names = set(sessions.get(response.json()["session_id"]).menus)
        return {"campus" if not name.startswith("가게") else name for name in names}

    def test_each_area_adds_its_own_restaurants(self):
        self.assertEqual(self.restaurants(areas=["campus"]), {"campus"})
        self.assertEqual(self.restaurants(areas=["snu_station"]), {"가게 S"})
        self.assertEqual(self.restaurants(areas=["campus", "nakseongdae"]), {"campus", "가게 N"})
        self.assertEqual(self.restaurants(areas=["snu_station", "nakseongdae"]), {"가게 S", "가게 N"})

    def test_every_area_is_everything_like_an_old_all(self):
        everything = {"campus", "가게 S", "가게 N", "가게 X"}
        self.assertEqual(self.restaurants(areas=list(AREAS)), everything)
        self.assertEqual(self.restaurants(area="all"), everything)
        self.assertEqual(self.restaurants(source="all"), everything)

    def test_prewarm_reads_the_areas_and_the_old_area(self):
        for body in ({"areas": ["campus", "snu_station"]}, {"area": "nakseongdae"}, {}):
            response = self.client.post("/api/sessions/prewarm/", content_type="application/json", data=json.dumps(body))
            self.assertEqual(response.status_code, 204, body)
        response = self.client.post("/api/sessions/prewarm/", content_type="application/json", data=json.dumps({"areas": []}))
        self.assertEqual(response.status_code, 400)
