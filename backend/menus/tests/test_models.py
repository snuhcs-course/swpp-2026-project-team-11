# AI-generated: written with Claude (Anthropic) and reviewed by the team.
import datetime

from django.db import IntegrityError
from django.test import TestCase

from menus.models import Food, MenuItem, Restaurant


class MenuItemModelTests(TestCase):
    def setUp(self):
        self.restaurant = Restaurant.objects.create(code="학생회관식당", name="학생회관식당")
        self.food = Food.objects.create(name="육개장")

    def test_same_dish_twice_in_one_meal_is_rejected(self):
        kwargs = dict(date=datetime.date(2026, 9, 30), meal="LU",
                      restaurant=self.restaurant, raw_name="육개장")
        MenuItem.objects.create(food=self.food, price=3000, **kwargs)
        with self.assertRaises(IntegrityError):
            MenuItem.objects.create(food=self.food, price=3000, **kwargs)

    def test_one_food_is_shared_across_days(self):
        for day in (29, 30):
            MenuItem.objects.create(date=datetime.date(2026, 9, day), meal="LU",
                                    restaurant=self.restaurant, raw_name="육개장",
                                    food=self.food)
        self.assertEqual(self.food.menu_items.count(), 2)
        self.assertEqual(Food.objects.count(), 1)

    def test_deleting_food_keeps_menu_item(self):
        item = MenuItem.objects.create(date=datetime.date(2026, 9, 30), meal="DN",
                                       restaurant=self.restaurant, raw_name="육개장",
                                       food=self.food)
        self.food.delete()
        item.refresh_from_db()
        self.assertIsNone(item.food)
