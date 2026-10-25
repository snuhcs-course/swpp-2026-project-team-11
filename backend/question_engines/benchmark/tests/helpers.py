# AI-generated: written with Claude (Anthropic) and reviewed by the team.
import random
import re
from types import SimpleNamespace

from menus.features.schema import FEATURE_KEYS, FEATURE_VERSION
from question_engines.benchmark.simulator import ANSWER_IDS


def features(**values):
    return {key: values.get(key, 0.0) for key in FEATURE_KEYS}


def candidate(food_id, name, group, **values):
    return {"food_id": food_id, "name": name, "display_name": name, "food_group": group,
            "features": features(**values), "feature_std": features(),
            "offers": [{"restaurant": "학생회관식당", "meal": "LU", "price": 5000}]}


CANDIDATES = [
    candidate(1, "볶음밥", "볶음밥", rice=1.0, grilled=0.8, korean=0.6),
    candidate(2, "소고기볶음밥", "볶음밥", rice=1.0, grilled=0.8, beef=1.0, korean=0.6),
    candidate(3, "닭고기볶음밥", "볶음밥", rice=1.0, grilled=0.8, chicken=1.0, korean=0.6),
    candidate(4, "짬뽕", "중식", spicy=1.0, soupy=1.0, hot=1.0, noodle=1.0, seafood=0.8, chinese=1.0),
    candidate(5, "물냉면", "냉면", cold=1.0, soupy=0.9, noodle=1.0, sour_fresh=0.8, korean=1.0),
    candidate(6, "치즈돈까스", "돈까스", fried=1.0, greasy=0.9, pork=1.0, japanese=0.7),
]
MENU = {"date": "2026-10-13", "meal": "LU", "feature_version": FEATURE_VERSION, "candidates": CANDIDATES}
OTHERS = [{"name": "마라탕", "features": features(spicy=1.0, soupy=1.0, hot=1.0, chinese=1.0), "food_group": "중식"},
          {"name": "치즈볶음밥", "features": features(rice=1.0, greasy=0.8), "food_group": "볶음밥"}]


TOPICS = ("spicy", "soup", "rice", "noodles", "meat", "fried", "cold", "cheese")


class FakeEngineLLM:
    """Plays the LLM engine's model: asks `questions` generic questions, then recommends
    `pick` (or the first menu). Replies carry token usage and cost like OpenRouter's."""

    def __init__(self, questions=2, pick=None):
        self.questions, self.pick = questions, pick
        self.calls = 0

    def with_structured_output(self, schema, include_raw=False):
        return _EngineRun(self, schema, include_raw)


class _EngineRun:
    def __init__(self, owner, schema, include_raw):
        self.owner, self.schema, self.include_raw = owner, schema, include_raw

    def invoke(self, messages):
        self.owner.calls += 1
        text = messages[-1].content
        foods = list(self.schema.model_json_schema()["properties"]["food"]["enum"])
        asked = len(re.findall(r"^Q\d+\.", text, re.M))
        food = self.owner.pick if self.owner.pick in foods else foods[0]
        if asked < self.owner.questions and "Questions left: 0" not in text:
            reply = {"action": "ask", "question": f"Do you want {TOPICS[asked]}?", "food": food}
        else:
            reply = {"action": "recommend", "question": "", "food": food}
        parsed = self.schema.model_validate(reply)
        if not self.include_raw:
            return parsed
        return {"raw": SimpleNamespace(usage_metadata={"input_tokens": 1000, "output_tokens": 50},
                                       response_metadata={"token_usage": {"cost": 0.0002}}),
                "parsed": parsed, "parsing_error": None}


class FakeUserLLM:
    """Plays the simulated user's model: a fixed answer, and takes a proposal when told to.
    Replies carry token usage like a real chat model's."""

    def __init__(self, answer="yes", accept=False, seed=None):
        self.answer, self.accept = answer, accept
        self.rng = random.Random(seed) if seed is not None else None
        self.calls = []

    def with_structured_output(self, model, include_raw=False):
        owner = self

        class Run:
            def invoke(self, messages):
                text = messages[-1].content
                owner.calls.append((model.__name__, text))
                pick = (lambda: owner.rng.choice(ANSWER_IDS)) if owner.rng else (lambda: owner.answer)
                if model.__name__ == "Reply":
                    parsed = model(answer=pick())
                else:
                    parsed = model(accept=owner.accept)
                return {"raw": SimpleNamespace(usage_metadata={"input_tokens": 300, "output_tokens": 10}),
                        "parsed": parsed, "parsing_error": None}
        return Run()


class ScriptedUser:
    """A user for harness.play: fixed answers and a fixed verdict on every proposal."""

    def __init__(self, answer="yes", accept=True):
        self.answer_id, self.accept = answer, accept

    def answer(self, step, repeat):
        return {"answer": self.answer_id}

    def judge(self, step):
        return {"accepted": self.accept, "judged_by": "script"}
