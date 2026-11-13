import numpy as np
import pytest

from question_engines.group import GroupConfig, GroupEngine
from question_engines.decision_tree.catalog import CandidateCatalog
from question_engines.group.engine import PICKS, closest, fit, picks, place, restaurants

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


def banned(*food_ids, menus=MENUS):
    """Every offer of these menus: what a member who cannot eat them excludes."""
    return {(m["food_id"], place(o)) for m in menus if m["food_id"] in food_ids for o in m["offers"]}


def play(engine, wants=WANTS):
    while not engine.finished:
        for member, step in engine.questions().items():
            engine.answer(member, step["question_id"], wants[member].get(step["question_id"], "any"))
    return engine.recommendation()["picks"]


def test_first_round_asks_everyone_the_same_informative_question():
    engine = GroupEngine(MENUS, SCHEMA, [set(), set()])
    steps = engine.questions()
    assert set(steps) == {0, 1}
    assert steps[0]["question_id"] == steps[1]["question_id"] != "q:noodle"
    assert [o["id"] for o in steps[0]["options"]][0] == "yes"


def test_recommends_the_restaurant_that_serves_each_member_their_own_menu():
    engine = GroupEngine(MENUS, SCHEMA, [set(), set()])
    first, *others = play(engine)
    assert first["kind"] == "balanced" and first["restaurant"] == "Both hall"
    assert [m["food_id"] for m in first["menus"]] == [1, 2]
    assert len({p["restaurant"] for p in [first, *others]}) == 2
    assert 1 <= engine.recommendation()["rounds"] <= GroupConfig().max_rounds


def test_each_pick_scores_the_members_satisfaction_differently():
    satisfaction = np.array([[.9, .45], [.3, .45]])  # S_i(r) per member and restaurant
    assert picks(satisfaction) == list(zip(PICKS, [0, 1]))
    assert picks(np.array([[.9, .1], [.9, .1]])) == list(zip(PICKS, [0, 1]))


def test_a_spread_belief_gets_the_menu_in_the_middle_not_a_likeliest_one():
    features = np.array([[0.], [.5], [1.]])
    assert closest(features, np.array([.4, .2, .4]), np.arange(3)) == 1
    assert closest(features, np.array([.4, .2, .4]), np.array([0, 2])) == 0


def test_a_member_is_never_offered_a_menu_they_cannot_eat():
    result = play(GroupEngine(MENUS, SCHEMA, [set(), banned(2)]))
    assert result[0]["restaurant"] != "Both hall"
    assert all(p["menus"][1]["food_id"] != 2 for p in result)


def test_every_pick_has_a_menu_for_every_member():
    result = play(GroupEngine(MENUS, SCHEMA, [set(), banned(1, 2, 4)]))  # member 1 eats only at Mixed hall
    assert [p["restaurant"] for p in result] == ["Mixed hall"]
    assert picks(np.array([[.5, .25, .25], [1, 0, 0]])) == [("balanced", 0)]


def test_a_similar_menu_counts_for_most_of_a_match():
    catalog = CandidateCatalog(MENUS, SCHEMA)
    _, serves = restaurants(catalog)
    spicy_hall, spicy_soup = 3, 2  # restaurants and menus in sorted order
    assert fit(catalog, serves)[spicy_hall, spicy_soup] == pytest.approx(1 - .9 / 3)
    assert fit(catalog, serves)[spicy_hall, 0] == 1
    without_stir_fry = serves.copy()
    without_stir_fry[:, 0] = False
    assert not fit(catalog, without_stir_fry)[spicy_hall].any()
    assert fit(catalog, without_stir_fry)[0, 0] < 1 == fit(catalog, serves)[0, 0]  # Both hall still has the soup


def test_the_shared_fit_table_cannot_be_changed_in_place():
    catalog = CandidateCatalog(MENUS, SCHEMA)
    with pytest.raises(ValueError):
        fit(catalog, restaurants(catalog)[1])[0, 0] = 0


def test_an_allergen_at_one_restaurant_rules_out_only_that_offer():
    # One stir-fry served at A and B; A's has the member's allergen, B's does not.
    menus = [menu(1, "Stir-fry", .95, .05, "A hall", "B hall"), menu(2, "Soup", .05, .95, "A hall")]
    unsafe = {(1, ("A hall", None, None))}
    wants = [WANTS[0], WANTS[0]]
    assert play(GroupEngine(menus, SCHEMA, [set(), set()]), wants)[0]["restaurant"] == "A hall"
    result = play(GroupEngine(menus, SCHEMA, [unsafe, set()]), wants)
    assert result[0]["restaurant"] == "B hall" and result[0]["menus"][0]["food_id"] == 1
    assert all(p["menus"][0]["food_id"] != 1 for p in result if p["restaurant"] == "A hall")


def test_branches_with_one_name_are_different_restaurants():
    def at(lat):
        return {"restaurant": "Chain", "meal": "LU", "price": 5000, "lat": lat, "lng": 127.}

    menus = [dict(MENUS[0], offers=[at(37.1), {"restaurant": "Mixed hall", "meal": "LU", "price": 5000}]),
             dict(MENUS[1], offers=[at(37.2), {"restaurant": "Mixed hall", "meal": "LU", "price": 5000}])]
    first, *others = play(GroupEngine(menus, SCHEMA, [set(), set()]))
    assert first["restaurant"] == "Mixed hall"  # no single Chain branch serves both menus
    assert {(p["restaurant"], p["lat"]) for p in others} <= {("Chain", 37.1), ("Chain", 37.2)}


def test_stops_once_every_question_is_asked():
    engine = GroupEngine(MENUS, SCHEMA, [set(), set()], config={"max_rounds": 10})
    for member in engine.members:
        member.answers = dict.fromkeys(range(len(engine.model.questions)), 0)
    assert engine._plan() == {}


def test_eight_members_take_turns_until_the_group_is_decided():
    engine = GroupEngine(MENUS, SCHEMA, [set()] * 8)
    assert len(engine.questions()) == 8
    assert play(engine, WANTS * 4)[0]["restaurant"] == "Both hall"
    with pytest.raises(ValueError):
        GroupEngine(MENUS, SCHEMA, [set()] * 9)


def test_every_member_answers_the_same_new_question_each_round():
    engine = GroupEngine(MENUS, SCHEMA, [set(), banned(2), set()])  # member 1 cannot eat the mild soup
    wants = WANTS + [{"q:spicy": "no", "q:soupy": "no", "q:noodle": "yes"}]
    asked = []
    while not engine.finished:
        steps = engine.questions()
        assert set(steps) == {0, 1, 2} and len({s["question_id"] for s in steps.values()}) == 1
        asked.append(steps[0]["question_id"])
        for member, step in steps.items():
            engine.answer(member, step["question_id"], wants[member].get(step["question_id"], "any"))
    assert len(asked) == len(set(asked)) == engine.round > 1


def test_the_group_keeps_learning_tastes_while_the_restaurants_tie():
    tied = [dict(m, offers=[{"restaurant": r, "meal": "LU", "price": 5000} for r in ("A hall", "B hall")]) for m in MENUS]
    engine = GroupEngine(tied, SCHEMA, [set(), set()])
    play(engine)
    assert engine.round > 1
    assert all(len(m.answers) == engine.round for m in engine.members)


def test_stops_after_the_round_limit():
    engine = GroupEngine(MENUS, SCHEMA, [set(), set()], config={"max_rounds": 1})
    with pytest.raises(ValueError):
        engine.recommendation()
    play(engine)
    assert engine.recommendation()["rounds"] == 1


def test_one_restaurant_needs_no_question():
    engine = GroupEngine(MENUS[2:], SCHEMA, [set(), set()])
    assert engine.finished and engine.questions() == {}
    assert [p["restaurant"] for p in engine.recommendation()["picks"]] == ["Mixed hall"]


def test_rejects_invalid_groups_and_answers():
    with pytest.raises(ValueError):
        GroupEngine(MENUS, SCHEMA, [set()])
    with pytest.raises(ValueError):
        GroupEngine(MENUS, SCHEMA, [set(), banned(1, 2, 3, 4)])
    with pytest.raises(ValueError):
        GroupEngine(MENUS, SCHEMA, [banned(2, 3, 4), banned(1, 2, 4)])  # no restaurant serves both
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
