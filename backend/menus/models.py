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

    One row per cleaned menu name, shared across days and restaurants, so the
    LLM feature extraction runs once per dish and is reused when it comes back.
    """

    name = models.CharField(max_length=300, unique=True)  # normalize.clean_name()
    display_name = models.CharField(max_length=50, blank=True)  # short name from the LLM
    is_food = models.BooleanField(null=True)  # LLM verdict; False for notices/headers
    food_group = models.CharField(max_length=30, blank=True)  # 국밥, 덮밥, 돈까스, ...

    # {feature_key: P(user answers "yes" to that feature's question | wants this food)}
    features = models.JSONField(default=dict, blank=True)
    feature_version = models.CharField(max_length=10, blank=True)
    extraction_model = models.CharField(max_length=50, blank=True)
    extracted_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.display_name or self.name


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
            models.UniqueConstraint(
                fields=["date", "meal", "restaurant", "raw_name"],
                name="unique_menu_item_per_meal",
            )
        ]
        ordering = ["date", "meal", "restaurant__name"]

    def __str__(self):
        return f"{self.date} {self.meal} {self.restaurant} - {self.raw_name}"
