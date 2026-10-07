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


class FakeLLM:
    """Plays the structured-output Gemini client: replies with the queued turns in order.

    A queued exception is raised instead, like a timeout or network error.
    """

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []
        self.models = []

    def with_structured_output(self, model):
        self.models.append(model)
        return self

    def invoke(self, messages):
        self.calls.append(messages)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return self.models[-1].model_validate(reply)

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
