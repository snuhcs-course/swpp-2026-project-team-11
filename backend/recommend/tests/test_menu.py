"""The other dishes of a restaurant, for the result screen's menu list."""
from menus.allergens import ALLERGEN_VERSION
from menus.models import Food, MenuItem, SalesMenu
from menus.menu_registry import register_menu_ids

from .helpers import add_food
from .test_edge_cases import SmallMenuTestCase


class RestaurantMenuTests(SmallMenuTestCase):
    def menu(self, url, restaurant, status=200):
        response = self.client.get(url + "menu/", {"restaurant": restaurant})
        self.assertEqual(response.status_code, status, response.content)
        return response.json()

    def test_lists_the_restaurants_dishes_by_meal(self):
        add_food("Toast", restaurant="Test hall", meal="BR", price=2000)
        add_food("Curry", restaurant="Other hall", price=4500)
        SalesMenu.objects.filter(source="cafeteria", name="Toast").update(id=4000)
        _, url = self.start(meal=None)
        # Transport IDs come from the prepared registry, not the source rows.
        self.assertEqual(self.menu(url, "Test hall"), {"restaurant": "Test hall", "dishes": [
            {"food_id": SalesMenu.objects.get(source="cafeteria", name=name).id, "display_name": name, "meal": meal, "price": price}
            for name, meal, price in [("Toast", "BR", 2000), ("Beef noodles", "LU", 6000),
                                      ("Chicken noodles", "LU", None), ("Rice bowl", "LU", 5000)]]})
        self.assertEqual([d["display_name"] for d in self.menu(url, "Other hall")["dishes"]], ["Curry"])

    def test_a_set_is_listed_once_at_its_whole_price(self):
        add_food("Pork cutlet", price=7000)
        add_food("Curry udon", price=7000)
        MenuItem.objects.filter(food__name__in=["Pork cutlet", "Curry udon"]).update(raw_name="Pork cutlet curry udon")
        register_menu_ids("cafeteria")
        _, url = self.start()
        dishes = [(d["display_name"], d["price"]) for d in self.menu(url, "Test hall")["dishes"]]
        self.assertIn(("Pork cutlet curry udon", 7000), dishes)
        self.assertEqual(len(dishes), 4)

    def test_lists_only_the_sessions_dishes(self):
        add_food("Toast", restaurant="Test hall", meal="BR", price=2000)
        Food.objects.filter(name="Rice bowl").update(allergens=["egg"], allergen_version=ALLERGEN_VERSION)
        Food.objects.exclude(name="Rice bowl").update(allergens=[], allergen_version=ALLERGEN_VERSION)
        _, url = self.start(allergies=["egg"])
        self.assertEqual([d["display_name"] for d in self.menu(url, "Test hall")["dishes"]],
                         ["Beef noodles", "Chicken noodles"])

    def test_an_unknown_restaurant_has_no_dishes(self):
        _, url = self.start()
        self.assertEqual(self.menu(url, "Nowhere"), {"restaurant": "Nowhere", "dishes": []})

    def test_restaurant_is_required_and_the_session_must_exist(self):
        _, url = self.start()
        self.assertEqual(self.menu(url, "", 400)["error"]["code"], "invalid_request")
        self.assertEqual(self.client.get(url + "menu/").status_code, 400)
        self.assertEqual(self.menu("/api/sessions/unknown/", "Test hall", 404)["error"]["code"],
                         "session_not_found")
