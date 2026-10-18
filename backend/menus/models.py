from django.db import models


class Restaurant(models.Model):
    """A campus cafeteria, e.g. 학생회관식당."""

    code = models.CharField(max_length=100, unique=True)  # source's id, e.g. "220동식당"
    name = models.CharField(max_length=100)
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)
    source = models.CharField(max_length=20, default="siksha")

    def __str__(self):
        return self.name


class Food(models.Model):
    """A distinct dish - the unit the question engines recommend.

    One row per (cleaned name, set status), shared across days and restaurants.
    Both variants share name-based measurements; meal variety is deterministic.
    """

    name = models.CharField(max_length=300)  # normalize.clean_name()
    is_set = models.BooleanField(default=False)
    display_name = models.CharField(max_length=50, blank=True)
    is_food = models.BooleanField(null=True)  # preprocessing verdict; legacy rows may be null
    food_group = models.CharField(max_length=30, blank=True)  # 국밥, 덮밥, 돈까스, ...

    # v2: expected feature intensity; v1: legacy response score.
    features = models.JSONField(default=dict, blank=True)
    feature_std = models.JSONField(default=dict, blank=True)  # recipe variation; absent in v1
    feature_version = models.CharField(max_length=10, blank=True)
    extraction_model = models.CharField(max_length=50, blank=True)
    extracted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["name", "is_set"], name="unique_food_name_and_set",
        )]

    def __str__(self):
        return self.display_name or self.name


class MenuLine(models.Model):
    """A distinct menu line (by normalize.dish_key) and the dishes it stands for.

    This caches the preprocessing result, so a line seen on an earlier day is not
    sent to the LLM again. A combo line maps to several dishes; drinks, add-ons and
    notices map to none (is_meal=False).
    """

    class Source(models.TextChoices):
        RULE = "rule", "rule"  # no LLM answer yet: the whole line is one dish
        LLM = "llm", "llm"

    key = models.CharField(max_length=300, unique=True)
    name = models.CharField(max_length=300)  # cleaned name the first time the line was seen
    is_meal = models.BooleanField(default=True)
    dishes = models.JSONField(default=list, blank=True)  # canonical dish names (Food.name)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.RULE)
    version = models.CharField(max_length=10, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} -> {', '.join(self.dishes) or '(not a meal)'}"


class MenuItem(models.Model):
    """One dish served at one restaurant for one meal on one day."""

    class Meal(models.TextChoices):
        BREAKFAST = "BR", "아침"
        LUNCH = "LU", "점심"
        DINNER = "DN", "저녁"

    date = models.DateField(db_index=True)
    meal = models.CharField(max_length=2, choices=Meal.choices)
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name="menu_items")
    raw_name = models.CharField(max_length=500)
    food = models.ForeignKey(
        Food, null=True, blank=True, on_delete=models.SET_NULL, related_name="menu_items"
    )  # headers and notices are never stored, so this is null only if the Food was deleted
    price = models.IntegerField(null=True, blank=True)
    no_meat = models.BooleanField(default=False)

    class Meta:
        constraints = [
            # A combo line ("돈가스 카레우동") is stored once per dish it contains, so
            # each dish lists that cafeteria and the combo price among its offers.
            models.UniqueConstraint(
                fields=["date", "meal", "restaurant", "raw_name", "food"],
                name="unique_menu_item_per_dish",
            )
        ]
        ordering = ["date", "meal", "restaurant__name"]

    def __str__(self):
        return f"{self.date} {self.meal} {self.restaurant} - {self.raw_name}"
