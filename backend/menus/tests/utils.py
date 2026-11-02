# AI-generated: written with Claude (Anthropic) and reviewed by the team.
import json
import pathlib
from unittest import mock

_MISSING = pathlib.Path("__no_committed_rules__.json")
_RULE_FILES = ("menus.preprocess.fixed.CATALOG_PATH", "menus.preprocess.overrides.OVERRIDES_PATH")


def without_committed_rules(cls):
    """Class decorator: from setUp on, the test sees no fixed_menus.json and no
    overrides.json, whatever the committed files currently contain.

    (A class-level mock.patch would only cover the test methods, not setUp.)
    """
    original_setup = cls.setUp

    def setUp(self):
        for target in _RULE_FILES:
            patcher = mock.patch(target, new=_MISSING)
            patcher.start()
            self.addCleanup(patcher.stop)
        original_setup(self)

    cls.setUp = setUp
    return cls


class FakeStoreLLM:
    """Answers the restaurant-menu prompt (store_prompt.py) from `answers`, without a network call.

    `answers` maps an input_name to (is_meal, dishes); other lines get no answer.
    """

    def __init__(self, answers, fail=False):
        self.answers, self.fail = answers, fail
        self.calls = []

    def invoke(self, messages):
        from menus.preprocess.mapper import LineBatch

        text = messages[-1].content
        known = text.split("[기존 표준 이름]\n", 1)[1].split("\n", 1)[0]
        rows = [json.loads(line) for line in text.split("개]\n", 1)[1].splitlines()]
        self.calls.append({"rows": rows, "known": known})
        if self.fail:
            raise ValueError("model returned invalid JSON")
        return LineBatch.model_validate({"items": [
            {"input_name": row["input_name"], "is_meal": self.answers[row["input_name"]][0],
             "dishes": self.answers[row["input_name"]][1]}
            for row in rows if row["input_name"] in self.answers]})
