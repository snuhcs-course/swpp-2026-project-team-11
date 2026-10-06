from ..catalog import CandidateCatalog


def candidate(food_id, name, group, beef, soupy):
    return {"food_id": food_id, "name": name, "display_name": name,
            "food_group": group, "features": {"beef": beef, "soupy": soupy},
            "offers": [{"restaurant": "Test hall", "meal": "LU", "price": 5000}]}


def small_catalog():
    return CandidateCatalog([
        candidate(1, "Beef noodles", "Noodles", .9, .9),
        candidate(2, "Chicken noodles", "Noodles", .1, .9),
        candidate(3, "Rice bowl", "Rice", .1, .1),
    ], [{"key": "beef"}, {"key": "soupy"}])
