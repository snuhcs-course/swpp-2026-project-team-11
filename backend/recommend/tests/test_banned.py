"""Dishes the user banned are never proposed, like dishes with one of their allergies."""
from menus.models import Food

from .helpers import DAY, post
from .test_edge_cases import SmallMenuTestCase


class BannedDishTests(SmallMenuTestCase):
    def test_a_banned_dish_is_never_proposed(self):
        rice = Food.objects.get(name="Rice bowl").id
        state, url = self.start(banned=[rice, 999999])
        self.assertEqual(state["candidate_count"], 2)
        proposed = []
        step = self.call(url + "recommend-now/")["step"]
        while step["type"] == "guess":
            proposed.append(step["food"]["food_id"])
            step = self.call(url + "feedback/", {"guess_id": step["guess_id"], "accepted": False})["step"]
        self.assertEqual(len(proposed), 2)
        self.assertNotIn(rice, proposed)
        self.assertEqual([d["display_name"] for d in self.client.get(url + "menu/", {"restaurant": "Test hall"})
                          .json()["dishes"]], ["Beef noodles", "Chicken noodles"])

    def test_banning_every_dish_leaves_an_empty_menu(self):
        state, _ = self.start(banned=list(Food.objects.values_list("id", flat=True)))
        self.assertEqual(state["step"]["reason"], "empty_candidates")

    def test_banned_must_be_a_list_of_food_ids(self):
        for banned in (1, "1", ["1"], [1.0], [True], {"id": 1}, [None]):
            response = post(self.client, "/api/sessions/", {"date": DAY, "banned": banned})
            self.assertEqual(response.status_code, 400, banned)
