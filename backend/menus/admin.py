# AI-generated: written with Claude (Anthropic) and reviewed by the team.
from django.contrib import admin

from .models import Food, MenuItem, Restaurant


@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "source"]
    search_fields = ["name", "code"]


@admin.register(Food)
class FoodAdmin(admin.ModelAdmin):
    list_display = ["name", "display_name", "is_food", "food_group", "feature_version"]
    list_filter = ["is_food", "feature_version", "food_group"]
    search_fields = ["name", "display_name"]


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ["date", "meal", "restaurant", "raw_name", "price", "food"]
    list_filter = ["date", "meal", "restaurant"]
    search_fields = ["raw_name", "food__name"]
    list_select_related = ["restaurant", "food"]
