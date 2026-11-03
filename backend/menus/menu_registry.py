"""Prepare durable recipe IDs during source writes, never catalogue reads."""
from collections import defaultdict

from .menu_profiles import recipe_key, title
from .models import MenuItem, SalesMenu, StoreMenu


def register_menu_ids(source, *, using="default", date=None, restaurant_ids=None, raw_name=None):
    if source not in {"cafeteria", "general"}:
        raise ValueError("Unknown menu source")
    model = MenuItem if source == "cafeteria" else StoreMenu
    fields = ["pk", "restaurant_id", "raw_name", "price", "food_id", "food__name", "food__is_set"]
    fields += ["date", "meal"] if source == "cafeteria" else ["description"]
    items = model.objects.using(using).select_related("food").only(*fields).order_by("pk")
    if date is not None and source == "cafeteria":
        items = items.filter(date=date)
    if restaurant_ids is not None:
        items = items.filter(restaurant_id__in=restaurant_ids)
    if raw_name is not None:
        items = items.filter(raw_name=raw_name)
    grouped = defaultdict(list)
    for item in items:
        grouped[(item.restaurant_id, getattr(item, "date", None), getattr(item, "meal", ""),
                 item.raw_name, getattr(item, "description", ""), item.price)].append(item)
    prepared = {}
    for rows in grouped.values():
        if any(not row.food_id for row in rows):
            continue
        parts = {row.food_id: row.food for row in rows}
        row = rows[0]
        key = recipe_key(source, row.raw_name, getattr(row, "description", ""), parts.values())
        prepared[key] = SalesMenu(key=key, source=source, name=title(row.raw_name))
    SalesMenu.objects.using(using).bulk_create(prepared.values(), ignore_conflicts=True, batch_size=500)
    return len(prepared)
