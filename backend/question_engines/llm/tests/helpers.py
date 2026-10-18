import json

from langchain_core.messages import AIMessage
from pydantic import ValidationError

from question_engines.decision_tree.contracts import ANSWER_OPTIONS

ANSWER_IDS = [option["id"] for option in ANSWER_OPTIONS]


def candidate(food_id, display_name, group="", name=None):
    return {"food_id": food_id, "name": name or display_name, "display_name": display_name,
            "food_group": group, "features": {"spicy": .9, "soupy": .1},
            "offers": [{"restaurant": "Test hall", "meal": "LU", "price": 5000}]}


CANDIDATES = [candidate(1, "육개장", "국/탕"), candidate(2, "물냉면", "냉면"), candidate(3, "왕돈까스", "돈까스")]


def ask(question, food="육개장"):
    return {"action": "ask", "question": question, "food": food}


def recommend(food):
    return {"action": "recommend", "question": "", "food": food}


# What FakeLLM reports for every answered call, as OpenRouter does.
USAGE = {"input_tokens": 100, "output_tokens": 10, "cost_usd": 0.0001}


class FakeLLM:
    """Plays the structured-output OpenRouter client: replies with the queued turns in order.

    A queued exception is raised instead, like a timeout or network error. A reply
    outside the schema comes back as a parsing error, as with include_raw=True.
    """

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []
        self.models = []

    def with_structured_output(self, model, include_raw=False):
        assert include_raw, "the engine reads usage from the raw response"
        self.models.append(model)
        return self

    def invoke(self, messages):
        self.calls.append(messages)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        raw = AIMessage(content=json.dumps(reply, ensure_ascii=False),
                        usage_metadata={"input_tokens": USAGE["input_tokens"],
                                        "output_tokens": USAGE["output_tokens"],
                                        "total_tokens": USAGE["input_tokens"] + USAGE["output_tokens"]},
                        response_metadata={"token_usage": {"cost": USAGE["cost_usd"]}})
        try:
            return {"raw": raw, "parsed": self.models[-1].model_validate(reply), "parsing_error": None}
        except ValidationError as error:
            return {"raw": raw, "parsed": None, "parsing_error": error}

    def offered_foods(self, call=-1):
        """The food enum the LLM was allowed to answer with in one call."""
        return list(self.models[call].model_json_schema()["properties"]["food"]["enum"])

    def prompt(self, call=-1):
        return "\n".join(message.content for message in self.calls[call])


def check_step(test, step):
    """The step contract the P17 API and the Android client decode (same as P10)."""
    test.assertIsInstance(step["question_count"], int)
    test.assertTrue(step["text"])
    kind = step["type"]
    if kind == "question":
        test.assertEqual(set(step), {"type", "question_count", "question_id", "text", "options"})
        test.assertTrue(step["question_id"])
        test.assertEqual([option["id"] for option in step["options"]], ANSWER_IDS)
    elif kind in ("guess", "recommendation"):
        keys = {"type", "question_count", "food", "target_kind", "text"}
        test.assertEqual(set(step), keys | ({"guess_id"} if kind == "guess" else set()))
        test.assertEqual(step["target_kind"], "food")
        test.assertEqual(set(step["food"]), {"food_id", "name", "display_name", "food_group", "offers"})
        if kind == "guess":
            test.assertEqual(step["guess_id"], f"food:{step['food']['food_id']}")
    elif kind == "unavailable":
        test.assertEqual(set(step), {"type", "question_count", "reason", "text"})
        test.assertIn(step["reason"], ("empty_candidates", "candidates_exhausted"))
    else:
        test.fail(f"Unexpected step type: {kind}")
