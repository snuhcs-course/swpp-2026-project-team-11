import numpy as np
import pytest

from question_engines.group import GroupConfig, GroupEngine
from question_engines.group.engine import closest

SCHEMA = [{"key": "spicy"}, {"key": "soupy"}, {"key": "noodle"}]


def menu(food_id, name, spicy, soupy, *restaurants, profile="rms-v1"):
    return {"food_id": food_id, "name": name, "menu_profile": profile,
            "features": {"spicy": spicy, "soupy": soupy, "noodle": .5},
            "offers": [{"restaurant": r, "meal": "LU", "price": 5000} for r in restaurants]}


MENUS = [
    menu(1, "Spicy stir-fry", .95, .05, "Both hall", "Spicy hall"),
    menu(2, "Mild soup", .05, .95, "Both hall", "Soup hall"),
    menu(3, "Spicy soup", .95, .95, "Mixed hall"),
    menu(4, "Plain rice", .05, .05, "Mixed hall"),
]
# Member 0 wants spicy and dry food; member 1 wants mild soup.
WANTS = [{"q:spicy": "yes", "q:soupy": "no"}, {"q:spicy": "no", "q:soupy": "yes"}]


def play(engine, wants=WANTS):
    while not engine.finished:
        for member, step in engine.questions().items():
            engine.answer(member, step["question_id"], wants[member].get(step["question_id"], "any"))
    return engine.recommendation()


def test_first_round_asks_everyone_the_same_informative_question():
    engine = GroupEngine(MENUS, SCHEMA, [set(), set()])
    steps = engine.questions()
    assert set(steps) == {0, 1}
    assert steps[0]["question_id"] == steps[1]["question_id"] != "q:noodle"
    assert [o["id"] for o in steps[0]["options"]][0] == "yes"


def test_recommends_the_restaurant_that_serves_each_member_their_own_menu():
    result = play(GroupEngine(MENUS, SCHEMA, [set(), set()]))
    assert result["restaurant"] == "Both hall"
    assert [m["food_id"] for m in result["menus"]] == [1, 2]
    assert 1 <= result["rounds"] <= GroupConfig().max_rounds


def test_a_spread_belief_gets_the_menu_in_the_middle_not_a_likeliest_one():
    features = np.array([[0.], [.5], [1.]])
    assert closest(features, np.array([.4, .2, .4]), np.arange(3)) == 1
    assert closest(features, np.array([.4, .2, .4]), np.array([0, 2])) == 0


def test_a_member_is_never_offered_a_menu_they_cannot_eat():
    result = play(GroupEngine(MENUS, SCHEMA, [set(), {2}]))
    assert result["restaurant"] != "Both hall"
    assert all(m is None or m["food_id"] != 2 for m in result["menus"][1:])


def test_more_menus_mean_more_chances_not_a_name_order_tie():
    menus = [menu(1, "Dish", .5, .5, "Alpha hall")] + [menu(i, f"Dish {i}", .5, .5, "Zeta hall") for i in (2, 3, 4)]
    engine = GroupEngine(menus, SCHEMA, [set(), set()], config={"max_rounds": 1})
    assert play(engine, [{}, {}])["restaurant"] == "Zeta hall"


def test_stops_after_the_round_limit():
    engine = GroupEngine(MENUS, SCHEMA, [set(), set()], config={"max_rounds": 1})
    with pytest.raises(ValueError):
        engine.recommendation()
    assert play(engine)["rounds"] == 1


def test_one_restaurant_needs_no_question():
    engine = GroupEngine(MENUS[2:], SCHEMA, [set(), set()])
    assert engine.finished and engine.questions() == {}
    assert engine.recommendation()["restaurant"] == "Mixed hall"


def test_rejects_invalid_groups_and_answers():
    with pytest.raises(ValueError):
        GroupEngine(MENUS, SCHEMA, [set()])
    with pytest.raises(ValueError):
        GroupEngine(MENUS, SCHEMA, [set(), {1, 2, 3, 4}])
    with pytest.raises(ValueError):
        GroupEngine([menu(1, "Dish", .5, .5, "Hall", profile=None)], SCHEMA, [set(), set()])
    engine = GroupEngine(MENUS, SCHEMA, [set(), set()])
    with pytest.raises(ValueError):
        engine.answer(0, "q:noodle", "yes")
    with pytest.raises(ValueError):
        engine.answer(0, engine.questions()[0]["question_id"], "maybe")


def test_korean_questions():
    engine = GroupEngine(MENUS, SCHEMA, [set(), set()], config={"language": "ko"})
    assert engine.questions()[0]["options"][0]["label"] == "좋아요"
