from django.test import SimpleTestCase

from ..evaluation import judge_questions, run_benchmark
from .helpers import CANDIDATES, FakeLLM, ask, recommend


class ScriptedChat:
    """Plays the simulated user or the judge: returns the queued replies in order."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.schemas = []

    def with_structured_output(self, schema):
        self.schemas.append(schema)
        return self

    def invoke(self, messages):
        return self.schemas[-1].model_validate(self.replies.pop(0))


class BenchmarkTests(SimpleTestCase):
    def test_a_trial_plays_until_the_target_is_guessed(self):
        engine = FakeLLM(ask("Do you feel like noodles?"), recommend("육개장"), recommend("물냉면"))
        user = ScriptedChat({"answer": "yes"})
        report = run_benchmark([c for c in CANDIDATES if c["display_name"] != "왕돈까스"], engine, user,
                               trials=1, seed=1, workers=1)
        trial = report["trials"][0]
        self.assertEqual(trial["target"], "물냉면")
        self.assertEqual(trial["events"], [{"question": "Do you feel like noodles?", "answer": "yes"},
                                           {"guess": "육개장", "hit": False}, {"guess": "물냉면", "hit": True}])
        self.assertEqual((trial["found"], trial["questions"], trial["guesses"], trial["wasted"]),
                         (True, 1, 2, None))
        self.assertEqual(report["summary"]["first_guess_hit_rate"], 0)
        self.assertNotIn("same_topic", report["summary"])  # nobody judged the questions

    def test_trial_stops_after_max_guesses(self):
        engine = FakeLLM(recommend("육개장"), recommend("왕돈까스"))
        report = run_benchmark(CANDIDATES, engine, ScriptedChat(), trials=1, seed=1, max_guesses=2, workers=1)
        self.assertEqual(report["trials"][0]["target"], "물냉면")
        self.assertEqual(report["summary"]["found_rate"], 0)

    def test_judge_counts_what_most_votes_flag(self):
        history = [("Do you feel like noodles?", "no"), ("Do you feel like ramen?", "no"),
                   ("Do you feel like rice?", "yes")]
        flag = {"question": 2, "earlier": 1, "kind": "implied"}
        judge = ScriptedChat({"wasted": [flag]}, {"wasted": [flag, {**flag, "question": 3}]}, {"wasted": []})
        self.assertEqual(judge_questions(judge, history), [flag])
