"""A dish or group banned on the result screen is not proposed again in that session, even after undo."""
from menus.models import MenuItem
from menus.menu_registry import register_menu_ids

from .helpers import add_food
from .test_edge_cases import SmallMenuTestCase


class BannedDishTests(SmallMenuTestCase):
    def guess(self):
        state, url = self.start()
        guess = self.call(url + "recommend-now/")
        return guess, url, guess["step"]["food"]["food_id"]

    def test_the_dish_on_screen_stays_until_the_user_moves_on(self):
        guess, url, food_id = self.guess()
        self.assertEqual(self.call(url + "ban/", {"food_id": food_id, "banned": True}), guess)

    def test_back_skips_a_banned_dish_and_it_is_not_proposed_again(self):
        guess, url, food_id = self.guess()
        self.call(url + "ban/", {"food_id": food_id, "banned": True})
        self.call(url + "feedback/", {"guess_id": guess["step"]["guess_id"], "accepted": False})
        # Undoing the rejection would show the banned dish again, so it goes back to the question.
        back = self.call(url + "undo/")["step"]
        self.assertEqual((back["type"], back["question_count"]), ("question", 0))

        proposed = self.propose_until_exhausted(url, back)
        self.assertEqual(len(proposed), 2)
        self.assertNotIn(food_id, proposed)

    def test_a_banned_group_leaves_out_its_dishes(self):
        state, url = self.start()
        self.call(url + "ban/", {"food_group": "Noodles", "banned": True})
        proposed = self.propose_until_exhausted(url, state["step"])
        self.assertEqual(proposed, [MenuItem.objects.get(raw_name="Rice bowl").id])

    def test_a_banned_group_leaves_out_the_sets_holding_one_of_its_dishes(self):
        # A set dish has no group of its own; it takes that of its single variant.
        add_food("Beef noodles", is_set=True, price=8000)
        add_food("Dumplings", is_set=True, price=8000)
        MenuItem.objects.filter(food__is_set=True).update(raw_name="Beef noodles + Dumplings")
        register_menu_ids("cafeteria")
        state, url = self.start()
        self.assertEqual(state["candidate_count"], 4)
        self.call(url + "ban/", {"food_group": "Noodles", "banned": True})
        proposed = self.propose_until_exhausted(url, state["step"])
        self.assertEqual(proposed, [MenuItem.objects.get(raw_name="Rice bowl").id])

    def propose_until_exhausted(self, url, step):
        """The dishes proposed from `step` on, each turned down, until none is left."""
        proposed = []
        while step["type"] != "unavailable":
            if step["type"] == "question":
                step = self.call(url + "recommend-now/")["step"]
                continue
            proposed.append(step["food"]["food_id"])
            step = self.call(url + "feedback/", {"guess_id": step["guess_id"], "accepted": False})["step"]
        self.assertEqual(step["reason"], "candidates_exhausted")
        return proposed

    def test_a_lifted_ban_lets_the_dish_back(self):
        guess, url, food_id = self.guess()
        self.call(url + "ban/", {"food_id": food_id, "banned": True})
        self.call(url + "ban/", {"food_id": food_id, "banned": False})
        self.call(url + "feedback/", {"guess_id": guess["step"]["guess_id"], "accepted": False})
        self.assertEqual(self.call(url + "undo/"), guess)

    def test_a_new_session_has_no_bans(self):
        _, url, food_id = self.guess()
        self.call(url + "ban/", {"food_id": food_id, "banned": True})
        self.assertEqual(self.guess()[2], food_id)

    def test_the_ban_body_is_checked(self):
        guess, url, food_id = self.guess()
        for body in ({"food_id": str(food_id), "banned": True}, {"food_id": True, "banned": True},
                     {"food_id": None, "banned": True}, {"food_id": food_id, "banned": "yes"},
                     {"food_id": food_id, "banned": 1}, {"food_id": food_id}, {"banned": True},
                     {"food_group": "", "banned": True}, {"food_group": 1, "banned": True},
                     {"food_group": ["Noodles"], "banned": True},
                     {"food_id": food_id, "food_group": "Noodles", "banned": True}):
            self.assertEqual(self.call(url + "ban/", body, 400)["error"]["code"], "invalid_request", body)
        self.assertEqual(self.client.get(url).json(), guess)
