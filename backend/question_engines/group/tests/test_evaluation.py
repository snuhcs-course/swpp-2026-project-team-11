from question_engines.decision_tree.catalog import CandidateCatalog
from question_engines.group.engine import PICKS
from question_engines.group.evaluation import (ALLERGIES, ARMS, SITUATIONS, SIZES, build_cases, compare,
                                               oracle, summarize)

SCHEMA = [{"key": "spicy"}, {"key": "soupy"}, {"key": "noodle"}]
FEATURES = [(.9, .1, .1), (.1, .9, .1), (.9, .9, .9), (.1, .1, .9),
            (.5, .5, .1), (.8, .2, .6), (.2, .7, .3), (.6, .6, .5)]
CANDIDATES = [{"food_id": i + 1, "name": f"Menu {i + 1}", "menu_profile": "rms-v1",
               "features": dict(zip(("spicy", "soupy", "noodle"), values)),
               "offers": [{"restaurant": f"Hall {i % 3}", "meal": "LU", "price": 5000}]}
              for i, values in enumerate(FEATURES)]
CATALOG = CandidateCatalog(CANDIDATES, SCHEMA)


def offers(*food_ids):
    return {(f, (f"Hall {(f - 1) % 3}", None, None)) for f in food_ids}


SAFE = {key: offers(1, 2, 3, 4, 5) for key in ALLERGIES} | {"wheat": set()}  # no menu is free of wheat


def test_cases_are_deterministic_and_cover_every_situation_and_size():
    cases = build_cases(CATALOG, SAFE, groups=2, seed=7)
    assert cases == build_cases(CATALOG, SAFE, groups=2, seed=7)
    assert {(c["situation"], c["size"]) for c in cases} == {(s, n) for s in SITUATIONS for n in SIZES}
    assert all(len(c["members"]) == c["size"] for c in cases)
    restricted = [c["members"][0] for c in cases if c["situation"] == "restricted"]
    assert all(m["allergy"] != "wheat" and (m["target"], hall) in SAFE[m["allergy"]]
               for m in restricted for hall in [(f"Hall {(m['target'] - 1) % 3}", None, None)])


def test_a_similar_group_never_wants_one_menu_twice():
    twins = CANDIDATES + [dict(c, food_id=c["food_id"] + 100) for c in CANDIDATES]  # identical features
    cases = build_cases(CandidateCatalog(twins, SCHEMA), SAFE, groups=6, seed=7)
    similar = [[m["target"] for m in c["members"]] for c in cases if c["situation"] == "similar"]
    assert all(len(set(targets)) == len(targets) for targets in similar)


def test_compare_reports_every_arm_per_situation_and_size():
    cases = build_cases(CATALOG, SAFE, groups=1, seed=7)
    report = compare(CANDIDATES, SCHEMA, SAFE, cases, oracle(CATALOG, 7), config={"max_rounds": 2})
    assert set(report["summary"]) == set(SITUATIONS)
    assert all(set(row["by_size"]) == set(SIZES) for row in report["summary"].values())
    for case in report["cases"]:
        group, matched = case["group"], case["separate_matched"]
        assert 1 <= group["rounds"] <= 2
        assert matched["rounds"] <= group["rounds"]
        for arm in ARMS:
            outcome = case[arm]
            assert outcome["regret_per_member"] >= 0 and 0 < outcome["menu_satisfaction"] <= 1
            assert list(outcome["picks"]) == list(PICKS)
            assert outcome["picks"]["balanced"]["restaurant"] == outcome["restaurant"]
            assert outcome["best_pick_regret_per_member"] <= outcome["regret_per_member"]


def test_parallel_cases_give_the_same_report():
    cases = build_cases(CATALOG, SAFE, groups=1, seed=3)
    one, many = (compare(CANDIDATES, SCHEMA, SAFE, cases, oracle(CATALOG, 3), workers=w) for w in (1, 4))
    assert one == many


def test_pass_needs_half_the_questions_and_little_regret_in_every_check():
    def row(questions, regret, menu=.9):
        pick = {"restaurant": "Hall", "regret_per_member": regret, "mean_satisfaction": .9, "min_satisfaction": .9}
        return {"best": True, "regret_per_member": regret, "best_pick_regret_per_member": regret,
                "min_satisfaction": .9, "menu_satisfaction": menu, "picks": dict.fromkeys(PICKS, pick),
                "questions": questions, "rounds": 1}

    def verdict(group, separate, matched, most=row(0, .1, .8)):
        case = {"situation": "similar", "size": 2, "group": group, "separate": separate,
                "separate_matched": matched, "most_menus": most}
        return summarize([case])["similar"]["checks"]

    assert all(verdict(row(5, .03), row(10, .02), row(5, .05)).values())
    assert verdict(row(6, .03), row(10, .02), row(5, .05)) == {
        "questions": False, "regret_vs_separate": True, "regret_vs_matched": True, "regret_vs_most_menus": True,
        "menu_vs_most_menus": True}
    assert not verdict(row(5, .05), row(10, .02), row(5, .06))["regret_vs_separate"]
    assert not verdict(row(5, .05), row(10, .04), row(5, .05))["regret_vs_matched"]
    assert not verdict(row(5, .03), row(10, .02), row(5, .05), row(0, .03))["regret_vs_most_menus"]
    assert not verdict(row(5, .03, .8), row(10, .02), row(5, .05))["menu_vs_most_menus"]


def test_a_case_with_one_pick_counts_only_for_that_kind():
    case = compare(CANDIDATES, SCHEMA, SAFE, build_cases(CATALOG, SAFE, groups=1, seed=7)[:1], oracle(CATALOG, 7))["cases"][0]
    alone = dict(case, group=dict(case["group"], picks={"balanced": case["group"]["picks"]["balanced"]}))
    picks = summarize([case, alone])["similar"]["group"]["picks"]
    assert (picks["balanced"]["cases"], picks["no_one_unhappy"]["cases"]) == (2, 1)


def test_most_menus_picks_only_where_every_member_can_eat():
    safe = SAFE | {"milk": offers(3, 6)}  # only Hall 2, the smallest, has a menu without milk
    case = {"situation": "restricted", "size": 2, "members": [{"target": 3, "allergy": "milk"}, {"target": 1, "allergy": None}]}
    most = compare(CANDIDATES, SCHEMA, safe, [case], oracle(CATALOG, 7))["cases"][0]["most_menus"]
    assert list(most["picks"]) == ["balanced"] and most["restaurant"] == ("Hall 2", None, None)
    assert most["min_satisfaction"] > 0


def test_a_group_with_one_restaurant_is_compared_without_questions():
    candidates = [dict(c, offers=[dict(c["offers"][0], restaurant="Hall 0")]) for c in CANDIDATES]
    safe = {key: {(f, ("Hall 0", None, None)) for f, _ in given} for key, given in SAFE.items()}
    cases = build_cases(CandidateCatalog(candidates, SCHEMA), safe, groups=1, seed=7)
    for case in compare(candidates, SCHEMA, safe, cases, oracle(CATALOG, 7))["cases"]:
        assert case["group"]["rounds"] == case["separate_matched"]["questions"] == 0


def test_an_allergic_member_is_judged_on_the_offers_they_can_eat():
    # Menu 3 is served at Hall 2 and, with milk, at Hall 0; the member wants it and has the allergy.
    candidates = [dict(c, offers=c["offers"] + [{"restaurant": "Hall 0", "meal": "LU", "price": 5000}])
                  if c["food_id"] == 3 else c for c in CANDIDATES]
    safe = SAFE | {"milk": offers(1, 3, 4, 6, 7)}
    case = {"situation": "restricted", "size": 2, "members": [{"target": 3, "allergy": "milk"}, {"target": 3, "allergy": None}]}
    result = compare(candidates, SCHEMA, safe, [case], oracle(CATALOG, 7))["cases"][0]
    for arm in ("group", "separate", "separate_matched"):  # Hall 0 would tie Hall 2 if its menu 3 counted
        assert result[arm]["restaurant"] == ("Hall 2", None, None), arm
        assert result[arm]["regret_per_member"] == 0


def test_sizes_are_summarized_as_the_cases_have_them():
    case = compare(CANDIDATES, SCHEMA, SAFE, build_cases(CATALOG, SAFE, groups=1, seed=7)[:1], oracle(CATALOG, 7))["cases"][0]
    assert set(summarize([case, dict(case, size=3)])["similar"]["by_size"]) == {2, 3}
