from question_engines.decision_tree.catalog import CandidateCatalog
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
SAFE = {key: {1, 2, 3, 4, 5} for key in ALLERGIES} | {"wheat": set()}  # no menu is free of wheat


def test_cases_are_deterministic_and_cover_every_situation_and_size():
    cases = build_cases(CATALOG, SAFE, groups=2, seed=7)
    assert cases == build_cases(CATALOG, SAFE, groups=2, seed=7)
    assert {(c["situation"], c["size"]) for c in cases} == {(s, n) for s in SITUATIONS for n in SIZES}
    assert all(len(c["members"]) == c["size"] for c in cases)
    restricted = [c["members"][0] for c in cases if c["situation"] == "restricted"]
    assert all(m["allergy"] != "wheat" and m["target"] in SAFE[m["allergy"]] for m in restricted)


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
        assert all(case[arm]["regret"] >= 0 and 0 < case[arm]["menu_satisfaction"] <= 1 for arm in ARMS)


def test_parallel_cases_give_the_same_report():
    cases = build_cases(CATALOG, SAFE, groups=1, seed=3)
    one, many = (compare(CANDIDATES, SCHEMA, SAFE, cases, oracle(CATALOG, 3), workers=w) for w in (1, 4))
    assert one == many


def test_pass_needs_half_the_questions_and_little_regret_in_every_check():
    def row(questions, regret):
        return {"best": True, "regret_per_member": regret, "min_satisfaction": .9, "menu_satisfaction": .9, "questions": questions, "rounds": 1}

    def verdict(group, separate, matched, most=row(0, .1)):
        case = {"situation": "similar", "size": 2, "group": group, "separate": separate,
                "separate_matched": matched, "most_menus": most}
        return summarize([case])["similar"]["checks"]

    assert all(verdict(row(5, .03), row(10, .02), row(5, .05)).values())
    assert verdict(row(6, .03), row(10, .02), row(5, .05)) == {
        "questions": False, "regret_vs_separate": True, "regret_vs_matched": True, "regret_vs_most_menus": True}
    assert not verdict(row(5, .05), row(10, .02), row(5, .06))["regret_vs_separate"]
    assert not verdict(row(5, .05), row(10, .04), row(5, .05))["regret_vs_matched"]
    assert not verdict(row(5, .03), row(10, .02), row(5, .05), row(0, .03))["regret_vs_most_menus"]
