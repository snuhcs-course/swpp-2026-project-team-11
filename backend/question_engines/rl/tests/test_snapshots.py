import json
from pathlib import Path

import pytest

from question_engines.rl import RLEngine
from question_engines.rl.policy import FEATURE_KEYS


def menu():
    return [
        {"food_id": i + 1, "name": f"Menu {i}", "features": {
            key: float((i >> (j % 4)) & 1) for j, key in enumerate(FEATURE_KEYS)
        }, "offers": [{"restaurant": "Hall", "meal": "LU", "price": 5000}]}
        for i in range(12)
    ]


def test_frozen_v20_trace_on_archived_school_menu():
    # Expected actions from the original CPU PyTorch checkpoint on this fixture.
    fixture = Path(__file__).resolve().parents[2] / "decision_tree/tests/fixtures/lunch_20261013.json"
    source = json.loads(fixture.read_text(encoding="utf-8"))
    candidates = [{"food_id": food_id, "name": name, "display_name": display,
                   "features": dict(zip(source["keys"], means)),
                   "feature_std": dict(zip(source["keys"], deviations))}
                  for food_id, name, display, means, deviations in source["foods"]]
    engine = RLEngine(candidates)
    assert engine.start()["question_id"] == "q:soupy"
    assert engine.answer("q:soupy", "probably_yes")["question_id"] == "q:japanese"
    assert engine.answer("q:japanese", "no")["question_id"] == "q:noodle"
    assert engine.answer("q:noodle", "probably_no")["question_id"] == "q:chinese"
    assert engine.recommend_now()["guess_id"] == "food:128"
    assert engine.feedback("food:128", False)["question_id"] == "q:chicken"
    assert engine.recommend_now()["guess_id"] == "food:144"


def test_json_restore_preserves_refusals_forced_guess_and_each_undo():
    foods = menu()
    engine = RLEngine(foods, max_questions=2, language="ko")
    start = engine.start()
    question = engine.answer(start["question_id"], "probably_yes")
    assert question["type"] == "question"
    first = engine.recommend_now()
    engine.feedback(first["guess_id"], False)
    second = engine.recommend_now()
    assert second["guess_id"] != first["guess_id"]
    final = engine.feedback(second["guess_id"], True)
    snapshot = json.loads(json.dumps(engine.snapshot()))
    restored = RLEngine.from_snapshot(foods, snapshot)
    assert restored.next_step() == final
    assert restored.snapshot() == snapshot
    assert restored.diagnostics() == engine.diagnostics()
    assert restored.diagnostics()["rejection_count"] == 1
    assert restored.language == "ko"
    expected = [{"question_id": start["question_id"], "answer_id": "probably_yes",
                 "text": RLEngine(foods).start()["text"]}]
    assert restored.answered() == engine.answered() == expected
    while engine.can_undo:
        assert restored.undo() == engine.undo()
    assert restored.next_step() == start and not restored.can_undo
    assert restored.answered() == []
    assert engine.diagnostics()["rejection_count"] == 0


def test_restore_checks_catalogue_policy_and_action_identity():
    foods = menu()
    engine = RLEngine(foods)
    offer = engine.recommend_now()
    engine.feedback(offer["guess_id"], False)
    saved = engine.snapshot()
    for changes in ({"engine_version": "other"}, {"config": {"max_questions": 1}},
                    {"events": [["feedback", "food:missing", False]]}, {"pending": ["guess", -1]}):
        with pytest.raises(ValueError):
            RLEngine.from_snapshot(foods, {**saved, **changes})
    for changed in (list(reversed(foods)), [{**foods[0], "features": {"rice": None}}, *foods[1:]],
                    [{**foods[0], "offers": []}, *foods[1:]]):
        with pytest.raises(ValueError, match="catalogue"):
            RLEngine.from_snapshot(changed, saved)


@pytest.mark.parametrize("foods", [[], [{"food_id": 1, "name": "One", "features": {}}]])
def test_restore_terminal_catalogue(foods):
    engine = RLEngine(foods)
    if foods:
        engine.feedback(engine.start()["guess_id"], False)
    restored = RLEngine.from_snapshot(foods, engine.snapshot())
    assert restored.next_step() == engine.next_step()
    assert restored.undo() == engine.undo()
