# AI-generated: written with Claude (Anthropic) and reviewed by the team.
import csv
import datetime
import io
import json
import os
import pathlib
import tempfile
from collections import Counter
from types import SimpleNamespace
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase

from menus.features.schema import FEATURE_VERSION
from menus.models import Food, MenuItem, Restaurant
from question_engines.benchmark import cost, harness, metrics, report, scenarios, simulator, stats
from recommend.management.commands import play_engine_session

from .helpers import CANDIDATES, MENU, OTHERS, FakeEngineLLM, FakeUserLLM, ScriptedUser

MENU_ID = "2026-10-13/LU"
COUNTS = {"in_menu": 3, "multiple": 3, "not_in_menu": 3, "close_alternative": 3}
SIMULATOR_KEY = {"GOOGLE_API_KEY": "key", "METCHU_SIMULATOR_MODEL": ""}


def scenario(situation, *names, certainty="high"):
    targets = []
    for name in names:
        known = next((c for c in CANDIDATES if c["name"] == name), None) or next(o for o in OTHERS if o["name"] == name)
        targets.append(scenarios.target(name, known["features"], known["food_group"], CANDIDATES))
    return {"id": f"{situation}-x", "situation": situation, "certainty": certainty, "menu": MENU_ID, "targets": targets}


class ScenarioTests(SimpleTestCase):
    def test_a_wanted_menu_matches_itself_and_its_kinds_only(self):
        self.assertEqual(scenarios.matches("볶음밥", CANDIDATES), [1, 2, 3])
        self.assertEqual(scenarios.matches("닭고기볶음밥", CANDIDATES), [3])  # not 소고기볶음밥
        self.assertEqual(scenarios.matches("돈까스", CANDIDATES), [6])
        self.assertEqual(scenarios.matches("돈 까스", CANDIDATES), [6])  # spacing is ignored
        self.assertEqual(scenarios.matches("마라탕", CANDIDATES), [])

    def test_build_makes_each_situation_with_certainty_in_turn(self):
        data = scenarios.build({MENU_ID: MENU}, OTHERS, COUNTS, seed=1)
        self.assertEqual(Counter(s["situation"] for s in data["scenarios"]), COUNTS)
        self.assertEqual([s["certainty"] for s in data["scenarios"][:4]], ["high", "medium", "low", "high"])
        for item in data["scenarios"]:
            targets = item["targets"]
            if item["situation"] in ("in_menu", "close_alternative"):
                self.assertEqual(len(targets), 1)
                self.assertTrue(targets[0]["matches"])
            elif item["situation"] == "not_in_menu":
                self.assertIn(targets[0]["name"], ("마라탕", "치즈볶음밥"))  # no candidate is either
                self.assertEqual(targets[0]["matches"], [])
            else:
                self.assertIn(len(targets), (2, 3))
                ids = [i for t in targets for i in t["matches"]]
                self.assertEqual(len(ids), len(set(ids)))
                self.assertEqual(len({t["food_group"] for t in targets}), len(targets))

    def test_a_close_alternative_is_near_in_features_but_not_accepted(self):
        data = scenarios.build({MENU_ID: MENU}, OTHERS, {"close_alternative": 4}, seed=0)
        by_name = {c["display_name"]: c for c in CANDIDATES}
        for item in data["scenarios"]:
            wanted = item["targets"][0]
            self.assertIn(wanted["name"], ("소고기볶음밥", "닭고기볶음밥"))  # 볶음밥 is only a step away
            self.assertEqual(wanted["close"], ["볶음밥"])
            self.assertLessEqual(scenarios.gap(wanted["features"], by_name["볶음밥"]["features"]), scenarios.CLOSE_GAP)
            self.assertFalse(harness.accepted_by_rule(item, {"food": {"food_id": 1, "display_name": "볶음밥"}}))

    def test_build_refuses_what_it_cannot_make(self):
        with self.assertRaisesMessage(ValueError, "not_in_menu"):
            scenarios.build({MENU_ID: MENU}, [], {"not_in_menu": 1})


class AcceptanceTests(SimpleTestCase):
    def test_a_kind_of_the_wanted_menu_is_accepted_but_a_sibling_is_not(self):
        beef = {"food": {"food_id": 2, "display_name": "소고기볶음밥"}}
        self.assertTrue(harness.accepted_by_rule(scenario("in_menu", "볶음밥"), beef))
        self.assertFalse(harness.accepted_by_rule(scenario("in_menu", "닭고기볶음밥"), beef))

    def test_a_group_must_lie_inside_the_wanted_menus(self):
        group = {"food": {"food_id": 2, "display_name": "소고기볶음밥"},
                 "group": {"display_name": "볶음밥", "food_ids": [1, 2, 3]}}
        self.assertTrue(harness.accepted_by_rule(scenario("in_menu", "볶음밥"), group))
        self.assertFalse(harness.accepted_by_rule(scenario("in_menu", "닭고기볶음밥"), group))

    def test_any_of_several_wanted_menus_will_do(self):
        several = scenario("multiple", "짬뽕", "물냉면")
        self.assertTrue(harness.accepted_by_rule(several, {"food": {"food_id": 5, "display_name": "물냉면"}}))
        self.assertFalse(harness.accepted_by_rule(several, {"food": {"food_id": 6, "display_name": "치즈돈까스"}}))


class CertaintyTests(SimpleTestCase):
    def test_blur_rates_and_determinism(self):
        for level, rate in simulator.NOISE.items():
            changed = sum(simulator.blur("yes", level, "s", i, 0) != "yes" for i in range(4000)) / 4000
            self.assertAlmostEqual(changed, rate, delta=0.03)
        self.assertEqual(simulator.blur("yes", "low", "s", 1, 0), simulator.blur("yes", "low", "s", 1, 0))

    def test_blurred_answers_are_vague_or_turned_around(self):
        answers = Counter(simulator.blur("probably_yes", "low", "s", i, 0) for i in range(4000))
        self.assertEqual(set(answers) - {"probably_yes"}, {"unknown", "any", "probably_no"})


class SimulatorTests(SimpleTestCase):
    def test_a_question_is_asked_once_and_counted(self):
        llm = FakeUserLLM(answer="no")
        user = simulator.Simulator(llm)
        for _ in range(2):
            self.assertEqual(user.answer("You feel like eating: 짬뽕.", "Spicy?"), "no")
        self.assertEqual(len(llm.calls), 1)
        self.assertEqual(user.usage, {"calls": 1, "input_tokens": 300, "output_tokens": 10})

    def test_cache_file_survives_a_restart_and_can_be_read(self):
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "cache.jsonl"
            simulator.Simulator(FakeUserLLM(answer="yes"), path).answer("p", "Spicy?")
            line = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual({k: line[k] for k in ("value", "kind", "persona", "question", "prompt_id")},
                             {"value": "yes", "kind": "answer", "persona": "p", "question": "Spicy?",
                              "prompt_id": simulator.PROMPT_ID})
            again = FakeUserLLM(answer="no")
            self.assertEqual(simulator.Simulator(again, path).answer("p", "Spicy?"), "yes")
            self.assertEqual(again.calls, [])

    def test_another_model_asks_again(self):
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "cache.jsonl"
            simulator.Simulator(FakeUserLLM(answer="yes"), path, model="google:a").answer("p", "Spicy?")
            other = FakeUserLLM(answer="no")
            self.assertEqual(simulator.Simulator(other, path, model="openai:b").answer("p", "Spicy?"), "no")
            self.assertEqual(len(other.calls), 1)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8").splitlines()[-1])["model"], "openai:b")

    def test_persona_names_every_wanted_menu(self):
        self.assertEqual(simulator.describe(scenario("multiple", "짬뽕", "물냉면")),
                         "You would be happy with any one of these: 짬뽕, 물냉면.")

    def test_model_setting_and_the_engine_check(self):
        with mock.patch.dict(os.environ, {"METCHU_SIMULATOR_MODEL": "openai:gpt-5.4-mini"}):
            self.assertEqual(simulator.MODEL.key_name(), "OPENAI_API_KEY")
        with mock.patch.dict(os.environ, {"METCHU_SIMULATOR_MODEL": ""}):
            self.assertEqual(simulator.MODEL.model_id(), "google:gemini-3.5-flash")
            self.assertFalse(simulator.same_as_engine("google/gemini-3.5-flash-lite"))
            self.assertTrue(simulator.same_as_engine("google/gemini-3.5-flash"))

    def test_several_menus_are_answered_yes_when_one_of_them_fits(self):
        self.assertIn("yes when it is true of at least one of", simulator.SYSTEM_PROMPT)
        self.assertNotIn('differ on a question, answer "any"', simulator.SYSTEM_PROMPT)


class PlayTests(SimpleTestCase):
    def test_decision_tree_session_until_a_proposal_is_accepted(self):
        record = harness.play(harness.EngineFactory("decision_tree", MENU), scenario("in_menu", "짬뽕"),
                              ScriptedUser(accept=True))
        self.assertEqual(record["outcome"], "accepted")
        self.assertTrue(record["first_guess_accepted"])
        self.assertIsNotNone(record["final_food_id"])
        self.assertEqual(record["guesses"], 1)
        self.assertEqual(len(record["step_ms"]), record["questions"] + 3)  # build, start, answers, feedback
        self.assertIsNone(record["llm"])

    def test_the_trace_explains_every_step(self):
        item = scenario("in_menu", "짬뽕", certainty="low")
        for factory in (harness.EngineFactory("decision_tree", MENU),
                        harness.EngineFactory("llm", MENU, FakeEngineLLM(questions=3))):
            user = harness.SimulatedUser(item, simulator.Simulator(FakeUserLLM(answer="yes", accept=False)))
            record = harness.play(factory, item, user)
            asked = [t for t in record["trace"] if "question" in t]
            self.assertTrue(all(t["blurred"] == (t["answer"] != t["raw"]) and t["raw"] == "yes" for t in asked))
            self.assertTrue({t["judged_by"] for t in record["trace"] if "proposal" in t} <= {"rule", "simulator"})
            if factory.engine == "decision_tree":
                state = record["trace"][0]["state"]
                self.assertEqual(len(state["top"]), 5)
                self.assertEqual(set(state["planning"]), {"reason", "best_question_id", "best_question_gain"})
                self.assertIsNone(record["llm_calls"])
            else:
                self.assertIsNone(record["trace"][0]["state"])
                self.assertEqual(len(record["llm_calls"]), record["llm"]["calls"])
                self.assertEqual(set(record["llm_calls"][0]),
                                 {"latency_ms", "attempts", "fallback", "input_tokens", "output_tokens", "cost_usd"})

    def test_the_decision_tree_uses_the_servers_policy(self):
        with self.settings(RECOMMEND_DT_POLICY="greedy"):
            engine = harness.EngineFactory("decision_tree", MENU).build()
        self.assertEqual(engine.config.policy, "greedy")

    def test_the_user_gives_up_after_the_rejection_limit(self):
        record = harness.play(harness.EngineFactory("decision_tree", MENU), scenario("in_menu", "짬뽕"),
                              ScriptedUser(accept=False))
        self.assertEqual((record["outcome"], record["guesses"]), ("gave_up", harness.MAX_REJECTIONS))
        self.assertFalse(record["first_guess_accepted"])

    def test_llm_session_takes_calls_tokens_and_cost_from_the_engine(self):
        llm = FakeEngineLLM(questions=3, pick="물냉면")
        record = harness.play(harness.EngineFactory("llm", MENU, llm), scenario("in_menu", "물냉면"),
                              ScriptedUser(accept=True), anytime=(0, 2))
        self.assertEqual(record["outcome"], "accepted")
        self.assertEqual(record["questions"], 3)
        self.assertEqual({key: record["llm"][key] for key in ("calls", "input_tokens", "cost_usd", "fallbacks")},
                         {"calls": 4, "input_tokens": 4000, "cost_usd": 0.0008, "fallbacks": 0})  # 3 questions + 1
        self.assertEqual(record["anytime_llm"]["calls"], 2)  # the recommend-now copies, apart
        self.assertEqual(set(record["anytime"]), {"0", "2"})

    def test_an_engine_error_is_recorded_not_raised(self):
        factory = harness.EngineFactory("llm", MENU, FakeEngineLLM())
        with mock.patch.object(factory, "build", side_effect=RuntimeError("boom")):
            record = harness.play(factory, scenario("in_menu", "짬뽕"), ScriptedUser())
        self.assertEqual((record["outcome"], record["error_source"]), ("error", "engine"))
        self.assertIn("boom", record["error"])
        self.assertIsNone(record["llm"])

    def test_a_user_failure_keeps_the_question_count_and_says_so(self):
        class FailingUser(ScriptedUser):
            asked = 0

            def answer(self, step, repeat):
                self.asked += 1
                if self.asked == 3:
                    raise TimeoutError("simulator down")
                return super().answer(step, repeat)
        record = harness.play(harness.EngineFactory("llm", MENU, FakeEngineLLM(questions=5)),
                              scenario("in_menu", "짬뽕"), FailingUser())
        self.assertEqual((record["outcome"], record["error_source"], record["questions"]), ("error", "user", 2))

    def test_recommend_now_is_also_taken_at_a_proposal(self):
        record = harness.play(harness.EngineFactory("llm", MENU, FakeEngineLLM(questions=0)),
                              scenario("in_menu", "짬뽕"), ScriptedUser(), anytime=(0,))
        self.assertEqual(record["questions"], 0)
        self.assertIn("0", record["anytime"])  # the no-question baseline of a session that proposes at once

    def test_llm_calls_count_every_attempt(self):
        call = {"attempts": 2, "input_tokens": 10, "output_tokens": 1, "cost_usd": 0.01, "fallback": None}
        engine = SimpleNamespace(diagnostics=lambda: {"llm_calls": [call, call | {"attempts": 1}]})
        self.assertEqual({k: harness.llm_use([engine])[k] for k in ("calls", "decisions")}, {"calls": 3, "decisions": 2})
        self.assertEqual(metrics.llm_calls({"llm_calls": [call]}), 2)

    def test_both_engines_ask_the_simulated_user_one_question_at_a_time(self):
        item = scenario("not_in_menu", "마라탕")
        for factory in (harness.EngineFactory("decision_tree", MENU),
                        harness.EngineFactory("llm", MENU, FakeEngineLLM(questions=3))):
            llm = FakeUserLLM(answer="no")
            record = harness.play(factory, item, harness.SimulatedUser(item, simulator.Simulator(llm)))
            asked = [text for name, text in llm.calls if name == "Reply"]
            self.assertEqual(len(asked), record["questions"])  # one call per question, the same way
            self.assertEqual({name for name, _ in llm.calls}, {"Reply", "Verdict"})
            self.assertEqual(record["outcome"], "gave_up")  # the user never accepts a substitute


class JudgeTests(SimpleTestCase):
    def judge(self, item, proposal, take):
        llm = FakeUserLLM(accept=take)
        user = harness.SimulatedUser(item, simulator.Simulator(llm))
        verdict = user.judge({"food": proposal})
        return verdict["accepted"], verdict["judged_by"], [name for name, _ in llm.calls]

    def test_the_name_rule_accepts_without_asking(self):
        beef = {"food_id": 2, "name": "소고기볶음밥", "display_name": "소고기볶음밥"}
        self.assertEqual(self.judge(scenario("in_menu", "볶음밥"), beef, False), (True, "rule", []))

    def test_otherwise_the_simulated_user_decides(self):
        cheese = {"food_id": 6, "name": "치즈돈까스", "display_name": "치즈돈까스"}
        self.assertEqual(self.judge(scenario("in_menu", "짬뽕"), cheese, True), (True, "simulator", ["Verdict"]))
        self.assertEqual(self.judge(scenario("not_in_menu", "마라탕"), cheese, False), (False, "simulator", ["Verdict"]))

    def test_a_not_served_menu_is_judged_as_a_substitute(self):
        llm = FakeUserLLM(accept=True)
        user = harness.SimulatedUser(scenario("not_in_menu", "마라탕"), simulator.Simulator(llm))
        user.judge({"food": {"food_id": 4, "name": "짬뽕", "display_name": "짬뽕"}})
        self.assertIn("What you named is not available today", llm.calls[0][1])
        served = FakeUserLLM(accept=True)
        harness.SimulatedUser(scenario("in_menu", "물냉면"), simulator.Simulator(served)).judge(
            {"food": {"food_id": 4, "name": "짬뽕", "display_name": "짬뽕"}})
        self.assertIn("essentially the dish you have in mind", served.calls[0][1])

    def test_only_the_wanted_menu_counts_next_to_a_close_alternative(self):
        item = scenario("close_alternative", "소고기볶음밥")
        plain = {"food_id": 1, "name": "볶음밥", "display_name": "볶음밥"}
        self.assertEqual(self.judge(item, plain, True), (False, "rule_only", []))

    def test_a_set_and_its_single_dish_get_one_verdict(self):
        llm = FakeUserLLM(accept=False)
        user = harness.SimulatedUser(scenario("in_menu", "물냉면"), simulator.Simulator(llm))
        for display in ("짬뽕", "짬뽕 (세트)"):
            self.assertFalse(user.judge({"food": {"food_id": 4, "name": "짬뽕", "display_name": display}})["accepted"])
        self.assertEqual(len(llm.calls), 1)
        self.assertIn("The app proposes: 짬뽕\n", llm.calls[0][1])

    def test_the_verdict_prompt_is_strict_and_a_new_prompt_asks_again(self):
        llm = FakeUserLLM(accept=True)
        user = simulator.Simulator(llm)
        user.takes("You feel like eating: 햄버거.", "치즈버거")
        self.assertIn("just as happy", llm.calls[0][1])
        self.assertIn("Reject a different dish even if it is similar", llm.calls[0][1])
        with mock.patch.object(simulator, "TAKE_PROMPT", simulator.TAKE_PROMPT + " Be fair."):
            user.takes("You feel like eating: 햄버거.", "치즈버거")
        self.assertEqual(len(llm.calls), 2)

    def test_the_first_pick_is_also_judged_strictly(self):
        item = scenario("in_menu", "짬뽕")
        user = harness.SimulatedUser(item, simulator.Simulator(FakeUserLLM(answer="no", accept=True)))
        record = harness.play(harness.EngineFactory("decision_tree", MENU), item, user)
        self.assertTrue(record["first_guess_accepted"])  # the simulated user takes whatever comes first
        self.assertEqual(record["first_guess_exact"], record["final_food_id"] == 4)


class MetricsTests(SimpleTestCase):
    INDEX = metrics.MenuIndex({"menus": {MENU_ID: MENU}})

    def record(self, final, **extra):
        return {"scenario": "s", "situation": "in_menu", "certainty": "high", "engine": "llm", "repeat": 0,
                "outcome": "accepted" if final else "gave_up", "final_food_id": final, "first_guess_accepted": True,
                "questions": 3, "guesses": 1, "engine_ms": 5.0, "trace": [], **extra}

    def test_success_similarity_regret_and_rank(self):
        row = metrics.session(self.record(2), scenario("in_menu", "볶음밥"), self.INDEX)
        self.assertTrue(row["success"])
        self.assertLess(row["similarity"], 1.0)  # a kind of the wanted menu, not the same features
        self.assertEqual(row["best_similarity"], 1.0)
        self.assertAlmostEqual(row["regret"], 1.0 - row["similarity"])
        wrong = metrics.session(self.record(6), scenario("in_menu", "닭고기볶음밥"), self.INDEX)
        self.assertFalse(wrong["success"])
        self.assertLess(wrong["rank"], 0.5)

    def test_not_served_has_no_success_and_no_final_has_no_similarity(self):
        row = metrics.session(self.record(4), scenario("not_in_menu", "마라탕"), self.INDEX)
        self.assertIsNone(row["success"])
        self.assertEqual(row["rank"], 1.0)  # 짬뽕 is the closest to 마라탕
        self.assertEqual((row["random_pick"], row["no_question_pick"]), (None, None))
        empty = metrics.session(self.record(None), scenario("in_menu", "짬뽕"), self.INDEX)
        self.assertEqual((empty["success"], empty["similarity"]), (False, None))

    def test_baselines_and_llm_figures(self):
        record = self.record(1, anytime={"0": {"food_id": 2, "group": None}},
                             llm={"calls": 2, "input_tokens": 10, "output_tokens": 2, "cost_usd": 0.01, "fallbacks": 1})
        row = metrics.session(record, scenario("in_menu", "볶음밥"), self.INDEX)
        self.assertEqual(row["random_pick"], 0.5)  # 3 of the 6 dishes are 볶음밥 or a kind of it
        self.assertTrue(row["no_question_pick"])
        self.assertEqual((row["cost_usd"], row["fallback"]), (0.01, True))
        decision_tree = metrics.session(self.record(1), scenario("in_menu", "볶음밥"), self.INDEX)
        self.assertEqual((decision_tree["cost_usd"], decision_tree["fallback"], decision_tree["no_question_pick"]),
                         (0.0, False, None))

    def test_question_proposal_and_recommend_now_rows(self):
        trace = [{"question": "Spicy?", "answer": "no", "raw": "yes", "blurred": True},
                 {"proposal": 6, "group": None, "label": "치즈돈까스", "accepted": False, "judged_by": "simulator"},
                 {"proposal": 4, "group": None, "label": "짬뽕", "accepted": True, "judged_by": "rule"}]
        record = self.record(4, trace=trace,
                             anytime={"0": {"food_id": 6, "group": None}, "2": {"food_id": 4, "group": None}})
        item = scenario("in_menu", "짬뽕")
        [question] = metrics.questions(record)
        self.assertEqual((question["step"], question["answer"], question["raw"], question["blurred"]),
                         (1, "no", "yes", True))
        rows = metrics.proposals(record, item, self.INDEX)
        self.assertEqual([(p["step"], p["label"], p["wanted"], p["accepted"], p["judged_by"]) for p in rows],
                         [(2, "치즈돈까스", False, False, "simulator"), (3, "짬뽕", True, True, "rule")])
        self.assertEqual(rows[1]["similarity"], 1.0)
        self.assertEqual([(p["k"], p["success"]) for p in metrics.anytime(record, item, self.INDEX)],
                         [(0, False), (2, True)])

    def test_a_wanted_menu_without_features_gives_no_similarity(self):
        item = {"situation": "in_menu", "menu": MENU_ID, "targets": [scenarios.target("짬뽕", None, "", CANDIDATES)]}
        row = metrics.session(self.record(4), item, self.INDEX)
        self.assertEqual((row["success"], row["similarity"]), (True, None))


class CostTests(SimpleTestCase):
    def test_latency_and_cost_per_engine(self):
        records = [{"engine": "decision_tree", "engine_ms": 2.0, "step_ms": [1.0, 1.0], "outcome": "accepted",
                    "llm": None, "anytime_llm": None},
                   {"engine": "llm", "engine_ms": 900.0, "step_ms": [400.0, 500.0], "outcome": "accepted",
                    "llm": {"calls": 2, "input_tokens": 100, "output_tokens": 10, "cost_usd": 0.002, "fallbacks": 0},
                    "anytime_llm": {"calls": 1, "cost_usd": 0.001}},
                   {"engine": "llm", "engine_ms": 1100.0, "step_ms": [1100.0], "outcome": "error",
                    "llm": {"calls": 1, "input_tokens": 50, "output_tokens": 5, "cost_usd": 0.004, "fallbacks": 1},
                    "anytime_llm": {"calls": 0, "cost_usd": 0.0}}]
        figures = cost.summary(records)
        self.assertEqual(figures["decision_tree"]["cost_usd"], 0.0)
        self.assertEqual(figures["llm"]["session_ms_p50"], 1000.0)
        self.assertAlmostEqual(figures["llm"]["cost_usd"], 0.003)
        self.assertEqual((figures["llm"]["fallback_rate"], figures["llm"]["error_rate"]), (0.5, 0.5))
        self.assertEqual((figures["llm"]["recommend_now_calls"], figures["llm"]["recommend_now_cost_usd"]), (1, 0.001))


class StatsTests(SimpleTestCase):
    def test_mcnemar(self):
        self.assertAlmostEqual(stats.mcnemar(0, 6), 0.03125)
        self.assertEqual(stats.mcnemar(3, 3), 1.0)
        self.assertEqual(stats.mcnemar(0, 0), 1.0)

    def test_wilcoxon(self):
        self.assertEqual(stats.wilcoxon([0.3] * 3 + [0.7 - 0.4] * 3 + [-0.1, 0.5]),
                         stats.wilcoxon([0.3] * 6 + [-0.1, 0.5]))  # 0.7 - 0.4 is 0.29999999999999993
        self.assertLess(stats.wilcoxon([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]), 0.01)
        self.assertGreater(stats.wilcoxon([1, -1, 2, -2, 3, -3, 4, -4]), 0.9)
        self.assertTrue(stats.wilcoxon([1, 0, 0]) != stats.wilcoxon([1, 0, 0]))  # nan below 5 pairs

    def test_bootstrap_interval_contains_the_mean(self):
        low, high = stats.bootstrap_ci([0, 1, 0, 1, 1, 1, 0, 1])
        self.assertLess(low, 0.625)
        self.assertGreater(high, 0.625)

    def test_weighted_kappa(self):
        self.assertAlmostEqual(stats.weighted_kappa([0, 1, 2, 2], [0, 1, 2, 2]), 1.0)
        self.assertLess(stats.weighted_kappa([0, 2, 0, 2], [2, 0, 2, 0]), 0)


class ReportPieceTests(SimpleTestCase):
    def row(self, scenario_id, engine, first, no_question=None, random_pick=0.25, **extra):
        return {"scenario": scenario_id, "situation": "in_menu", "engine": engine, "first_guess_exact": first,
                "no_question_pick": no_question, "random_pick": random_pick, **extra}

    def test_first_pick_against_each_baseline(self):
        sessions = [self.row("a", "decision_tree", True, False), self.row("b", "decision_tree", False, False),
                    self.row("a", "llm", True, True), self.row("a", "llm", False, True),
                    self.row("b", "llm", True, False), self.row("b", "llm", True, False)]
        not_served = [self.row("c", e, None, situation="not_in_menu") for e in ("decision_tree", "llm")]
        rows, summary = report.baseline_rows(sessions + not_served)
        table = {tuple(r[:3]): r[3:] for r in rows}
        self.assertEqual({key[0] for key in table}, {"in_menu"})  # no baseline when the menu is not served
        self.assertEqual(table[("in_menu", "llm", "no question")][1:4], ["75.0%", "50.0%", "+25.0"])  # (0.5 + 1) / 2
        self.assertEqual(table[("in_menu", "llm", "random dish")][6:], ["yes", "yes"])  # +50 points, +200%
        self.assertEqual(table[("in_menu", "decision_tree", "llm")][3], "-25.0")
        self.assertEqual(table[("in_menu", "decision_tree", "no question")][5], "-")  # no ratio over a 0% baseline
        self.assertEqual({(s["situation"], s["engine"], s["baseline"]) for s in summary}, set(table))

    def test_a_result_exactly_at_the_goal_meets_it(self):
        sessions = [self.row(f"s{i}", "decision_tree", i < 7, random_pick=0.2) for i in range(20)]
        rows, _ = report.baseline_rows(sessions)
        row = next(r for r in rows if r[2] == "random dish")
        self.assertEqual((row[6], row[9]), ("+15.0", "yes"))  # 0.35 - 0.2 is 0.14999999999999997

    def test_simulator_agreement(self):
        checks = [{"question": "q1", "human": "yes", "simulator": "probably_yes"},
                  {"question": "q2", "human": "no", "simulator": "no"},
                  {"question": "q3", "human": "any", "simulator": "yes"},
                  {"proposal": "치즈버거", "human": True, "simulator": True},
                  {"proposal": "알리오올리오", "human": False, "simulator": True}]
        agreement = report.simulator_agreement(checks)
        self.assertEqual(agreement["n"], 3)
        self.assertAlmostEqual(agreement["exact"], 1 / 3)
        self.assertAlmostEqual(agreement["direction"], 2 / 3)
        self.assertEqual((agreement["verdicts"], agreement["same_verdict"]), (2, 0.5))

    def test_paired_rows_average_repeats_per_scenario(self):
        base = {"scenario": "a", "situation": "in_menu", "cost_usd": 0.0}
        rows = [base | {"engine": "decision_tree", "success": False, "first_guess_accepted": False, "questions": 4,
                        "interactions": 5, "similarity": 0.7, "engine_ms": 3.0},
                base | {"engine": "llm", "success": True, "first_guess_accepted": True, "questions": 2,
                        "interactions": 3, "similarity": 0.9, "engine_ms": 900.0},
                base | {"engine": "llm", "success": False, "first_guess_accepted": False, "questions": 4,
                        "interactions": 5, "similarity": 0.8, "engine_ms": 800.0}]
        table = {row[1]: row for row in report.paired(rows, "in_menu")}
        self.assertEqual(table["success"][2:6], [1, "0.000", "0.500", "0.500"])
        self.assertEqual(table["questions"][5], "-1.000")


    def test_yes_no_metrics_get_mcnemar_and_the_others_wilcoxon(self):
        rows = [{"scenario": f"s{i}", "situation": "in_menu", "engine": engine, "success": engine == "llm" or i < 2,
                 "questions": 4 + i if engine == "llm" else 2}
                for i in range(8) for engine in ("decision_tree", "llm")]
        table = {row[1]: row for row in report.paired(rows, "in_menu")}
        self.assertEqual(table["success"][7], "-")  # 0/1 means are all tied: no Wilcoxon
        self.assertNotEqual(table["success"][8], "-")
        self.assertNotEqual(table["questions"][7], "-")
        self.assertEqual(table["questions"][8], "-")

    def test_main_metrics_of_one_situation(self):
        base = {"engine": "llm", "questions": 3, "outcome": "accepted", "scenario": "a", "repeat": 0, "cost_usd": 0.01}
        served = [base | {"situation": "in_menu", "first_guess_accepted": accepted, "first_guess_exact": False,
                          "engine_ms": ms} for accepted, ms in ((True, 100.0), (False, 200.0), (False, 300.0))]
        m = report.main_metrics(served)
        self.assertEqual((m["first_pick"], m["first_pick_exact"]), (1 / 3, 0.0))
        self.assertEqual((m["latency_ms_p50"], m["cost_usd"]), (200.0, 0.01))
        not_served = report.main_metrics([base | {"situation": "not_in_menu", "first_guess_accepted": True,
                                                  "first_guess_exact": None, "engine_ms": 100.0}])
        self.assertEqual((not_served["first_pick"], not_served["first_pick_exact"]), (1.0, None))

    def test_no_figure_spans_situations(self):
        base = {"scenario": "a", "engine": "llm", "questions": 3, "outcome": "accepted", "repeat": 0,
                "cost_usd": 0.0, "engine_ms": 1.0, "first_guess_accepted": True, "first_guess_exact": True,
                "fallback": False}
        sessions = [base | {"situation": "in_menu"}, base | {"scenario": "b", "situation": "multiple"}]
        section = report.section_main(sessions)
        self.assertEqual(set(section["summary"]), {"in_menu", "multiple"})
        self.assertEqual([row[0] for _, _, _, rows, _ in section["tables"] for row in rows],
                         ["in_menu", "multiple", "in_menu", "multiple"])  # main, then the fallback table

    def test_section_folders(self):
        self.assertEqual(report.section_dir("1. Main metrics"), "1_main_metrics")
        self.assertEqual(report.section_dir("9. User study"), "9_user_study")


class CommandTests(TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = pathlib.Path(folder.name)
        self.scenarios = self.folder / "scenarios.json"
        self.sessions = self.folder / "sessions.jsonl"
        hall = Restaurant.objects.create(code="hall", name="학생회관식당")
        for c in CANDIDATES:
            food = Food.objects.create(name=c["name"], display_name=c["name"], is_food=True, food_group=c["food_group"],
                                       features=c["features"], feature_std=c["feature_std"],
                                       feature_version=FEATURE_VERSION)
            MenuItem.objects.create(date=datetime.date(2026, 10, 13), meal="LU", restaurant=hall, raw_name=c["name"],
                                    food=food, price=5000)
        for other in OTHERS:
            Food.objects.create(name=other["name"], is_food=True, food_group=other["food_group"],
                                features=other["features"], feature_version=FEATURE_VERSION)
        environment = mock.patch.dict(os.environ, SIMULATOR_KEY)
        environment.start()
        self.addCleanup(environment.stop)

    def build(self, counts="in_menu:1,multiple:1,not_in_menu:1,close_alternative:1"):
        call_command("build_engine_scenarios", "--date", "2026-10-13", "--counts", counts,
                     "--output", str(self.scenarios), stdout=io.StringIO())
        return scenarios.load(self.scenarios)

    def fakes(self, engine_llm=None, user_llm=None):
        """The engine's OpenRouter model and the simulated user's model, both fake."""
        stack = [mock.patch("recommend.management.commands.collect_engine_sessions.build_llm",
                            return_value=engine_llm or FakeEngineLLM()),
                 mock.patch("recommend.management.commands.collect_engine_sessions.LLMSettings.from_env",
                            return_value=SimpleNamespace(model="fake/lite")),
                 mock.patch("question_engines.benchmark.simulator.build_llm",
                            return_value=user_llm or FakeUserLLM(seed=1))]
        for patcher in stack:
            patcher.start()
            self.addCleanup(patcher.stop)

    def collect(self, *args):
        out = io.StringIO()
        call_command("collect_engine_sessions", "--scenarios", str(self.scenarios), "--output", str(self.sessions),
                     *args, stdout=out)
        return out.getvalue()

    def lines(self, path):
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def test_scenarios_freeze_the_candidates_and_their_feature_version(self):
        data = self.build()
        self.assertEqual(list(data["menus"]), [MENU_ID])
        self.assertEqual(data["menus"][MENU_ID]["feature_version"], FEATURE_VERSION)
        self.assertEqual(len(data["menus"][MENU_ID]["candidates"]), len(CANDIDATES))
        self.assertEqual(Counter(s["situation"] for s in data["scenarios"]),
                         {"in_menu": 1, "multiple": 1, "not_in_menu": 1, "close_alternative": 1})
        with self.assertRaisesMessage(CommandError, "situation:count"):
            self.build("in_menu:x")

    def test_menus_with_different_feature_versions_are_refused(self):
        hall = Restaurant.objects.get(code="hall")
        food = Food.objects.create(name="라면", is_food=True, features={"spicy": 0.5}, feature_version="v1")
        MenuItem.objects.create(date=datetime.date(2026, 10, 14), meal="LU", restaurant=hall, raw_name="라면",
                                food=food, price=4000)
        with self.assertRaisesMessage(CommandError, "feature 버전이 섞여"):
            call_command("build_engine_scenarios", "--date", "2026-10-13", "--date", "2026-10-14",
                         "--output", str(self.scenarios), stdout=io.StringIO())

    def test_dry_run_estimates_without_calling(self):
        self.build()
        user = FakeUserLLM()
        self.fakes(user_llm=user)
        self.assertIn("decision_tree 12 / llm 12", self.collect("--dry-run"))  # 3 repeats each
        self.assertEqual(user.calls, [])
        self.assertFalse(self.sessions.exists())

    def test_collect_stores_every_session_and_continues(self):
        self.build()
        self.fakes()
        self.collect("--repeats", "2", "--situations", "in_menu,multiple")
        rows = self.lines(self.sessions)
        self.assertEqual(Counter(r["engine"] for r in rows), {"decision_tree": 4, "llm": 4})
        self.assertEqual({r["repeat"] for r in rows}, {0, 1})
        decision_tree = [r for r in rows if r["engine"] == "decision_tree"]
        self.assertEqual(sum(r["simulator"]["calls"] for r in decision_tree if r["repeat"] == 1), 0)  # cached
        self.assertGreater(rows[-1]["llm"]["cost_usd"], 0)
        self.assertEqual(set(rows[0]["simulator"]), {"calls", "input_tokens", "output_tokens"})
        self.assertEqual(sum(r["simulator"]["calls"] for r in rows),
                         sum(r["simulator"]["input_tokens"] for r in rows) // 300)
        self.assertIn("decision_tree 2 / llm 2", self.collect("--repeats", "3", "--situations", "in_menu,multiple"))
        self.assertEqual(len(self.lines(self.sessions)), 12)
        self.assertTrue(self.sessions.with_suffix(".simcache.jsonl").exists())

    def test_failed_sessions_stop_the_run_and_are_played_again(self):
        self.build()
        broken = FakeUserLLM()
        broken.with_structured_output = mock.Mock(side_effect=ConnectionError("Connection error."))
        self.fakes(user_llm=broken)
        with self.assertRaisesMessage(CommandError, "연달아 오류"):
            self.collect("--repeats", "1")
        self.assertEqual([r["outcome"] for r in self.lines(self.sessions)], ["error"] * 3)
        self.fakes()  # the connection is back
        self.assertIn("오류로 끝난 세션 3개를 다시 실행합니다", self.collect("--repeats", "1"))
        rows = self.lines(self.sessions)
        self.assertEqual(len(rows), 8)  # 4 scenarios x 2 engines, each once
        self.assertNotIn("error", {r["outcome"] for r in rows})

    def test_collect_needs_the_simulated_users_key(self):
        self.build()
        self.fakes()
        with mock.patch.dict(os.environ, {"GOOGLE_API_KEY": "", "GEMINI_API_KEY": ""}), \
                self.assertRaisesMessage(CommandError, "GOOGLE_API_KEY"):
            self.collect()

    def test_report_writes_every_section_into_its_folder(self):
        self.build()
        self.fakes()
        self.collect("--repeats", "2")
        folder = self.folder / "report"
        call_command("benchmark_engines", "--scenarios", str(self.scenarios), "--sessions", str(self.sessions),
                     "--output-dir", str(folder), stdout=io.StringIO())
        text = (folder / "report.md").read_text(encoding="utf-8")
        for heading in ("## 1. Main metrics", "## 2. Baselines", "## 3. Situations", "## 4. Paired tests",
                        "## 5. Latency and cost", "## 6. Stability", "## 7. Recommend now", "## 8. Similarity",
                        "## 9. User study\n\nSkipped"):
            self.assertIn(heading, text)
        self.assertIn("(`1_main_metrics/main.csv`)", text)
        self.assertIn("| situation | engine | sessions | questions / session | questions to accept | first pick | "
                      "first pick (exact) |", text)
        self.assertNotIn("| all |", text)
        self.assertTrue((folder / "5_latency_and_cost" / "simulator_usage.csv").exists())
        self.assertTrue((folder / "2_baselines" / "baselines.csv").exists())
        with open(folder / "questions.csv", encoding="utf-8-sig") as f:
            self.assertEqual(next(csv.reader(f))[-4:], ["question", "answer", "raw", "blurred"])
        with open(folder / "proposals.csv", encoding="utf-8-sig") as f:
            self.assertIn("judged_by", next(csv.reader(f)))
        self.assertTrue((folder / "8_similarity" / "similarity.png").exists())
        self.assertEqual(sorted(p.name for p in (folder / "plots").iterdir()),
                         ["1_first_pick.png", "2_outcomes.png", "3_paired_differences.png",
                          "4_questions_latency_cost.png", "5_first_pick_by_certainty.png"])
        summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(set(summary["1_main_metrics"]), set(COUNTS))
        self.assertEqual(set(summary["1_main_metrics"]["in_menu"]), {"decision_tree", "llm"})
        self.assertEqual(summary["5_latency_and_cost"]["in_menu"]["decision_tree"]["cost_usd"], 0.0)

    def play(self, human, tester="lee", engine=None, wanted="짬뽕", rating="4"):
        answers = iter([wanted] + ["1"] * 30 + ["y"] * 10 + [rating])
        out = io.StringIO()
        with mock.patch("builtins.input", lambda prompt="": next(answers)), \
             mock.patch("recommend.management.commands.play_engine_session.build_llm",
                        return_value=FakeEngineLLM(questions=1, pick="짬뽕")), \
             mock.patch("recommend.management.commands.play_engine_session.LLMSettings.from_env"):
            call_command("play_engine_session", "--scenarios", str(self.scenarios), "--output", str(human),
                         "--tester", tester, *(["--engine", engine] if engine else []), stdout=out)
        return out.getvalue()

    def test_a_person_plays_blind_and_the_simulator_is_checked(self):
        self.build()
        human = self.folder / "human" / "kim.jsonl"  # the folder is made on the first session
        out = self.play(human, tester="kim", engine="decision_tree")
        record = self.lines(human)[0]
        self.assertEqual((record["engine"], record["outcome"], record["satisfaction"]), ("decision_tree", "accepted", 4))
        self.assertEqual(record["scenario_data"]["situation"], "in_menu")
        self.assertNotIn("decision_tree", out)

        check = self.folder / "check.jsonl"
        user = FakeUserLLM(answer="yes")
        with mock.patch("question_engines.benchmark.simulator.build_llm", return_value=user):
            args = ["validate_simulator", "--human", str(human), "--output", str(check)]
            call_command(*args, "--dry-run", stdout=io.StringIO())
            self.assertEqual((user.calls, check.exists()), ([], False))
            call_command(*args, stdout=io.StringIO())
            calls = len(user.calls)
            call_command(*args, stdout=io.StringIO())
        self.assertEqual(len(user.calls), calls)  # cached next to --output
        rows = self.lines(check)
        self.assertEqual({(r["human"], r["simulator"]) for r in rows if "question" in r}, {("yes", "yes")})
        self.assertEqual([(r["human"], r["simulator"]) for r in rows if "proposal" in r],
                         [(True, False)])  # the person took a dish that is not 짬뽕; the simulator would not

        self.fakes()
        self.collect("--repeats", "1", "--situations", "in_menu")
        folder = self.folder / "report"
        call_command("benchmark_engines", "--scenarios", str(self.scenarios), "--sessions", str(self.sessions),
                     "--human", str(human), "--simulator-check", str(check), "--output-dir", str(folder),
                     "--no-plots", stdout=io.StringIO())
        text = (folder / "report.md").read_text(encoding="utf-8")
        self.assertIn("1 testers, 0 of them with 2 sessions on each engine", text)
        self.assertIn("same answer 100.0%", text)
        self.assertIn("same verdict 0.0% of the time", text)

    def test_typed_dishes_none_of_them_served_are_not_in_menu(self):
        served, gone = {"matches": [4]}, {"matches": []}
        self.assertEqual([play_engine_session.situation_of(t) for t in ([gone, gone], [served, gone], [served], [gone])],
                         ["not_in_menu", "multiple", "in_menu", "not_in_menu"])

    def test_the_blind_order_balances_any_session_count(self):
        with mock.patch.object(play_engine_session, "SESSIONS_PER_ENGINE", 3):
            order = play_engine_session.blind_order("kim")
        self.assertEqual(Counter(order), {"decision_tree": 3, "llm": 3})
        self.assertEqual(order[:2], order[2:4][::-1])

    def test_not_served_targets_share_the_menus_feature_version(self):
        Food.objects.update(feature_version="v1")
        data = self.build("not_in_menu:1")
        self.assertEqual(data["menus"][MENU_ID]["feature_version"], "v1")
        self.assertIn(data["scenarios"][0]["targets"][0]["name"], ("마라탕", "치즈볶음밥"))

    def test_each_tester_plays_two_sessions_per_engine_in_a_balanced_order(self):
        self.build()
        human = self.folder / "human.jsonl"
        for _ in range(4):
            self.play(human)
        engines = [row["engine"] for row in self.lines(human)]
        self.assertEqual(Counter(engines), {"decision_tree": 2, "llm": 2})
        self.assertEqual(engines[:2], engines[:1:-1])  # A B B A

    def test_pipeline_keeps_scenarios_sessions_and_sections_in_one_folder(self):
        results = self.folder / "results"
        args = ["run_engine_benchmark", "--name", "trial", "--date", "2026-10-13", "--counts",
                "in_menu:1,close_alternative:1", "--repeats", "1", "--results-dir", str(results)]
        engine = FakeEngineLLM()
        self.fakes(engine_llm=engine)
        out = io.StringIO()
        call_command(*args, "--dry-run", stdout=out)
        self.assertIn("decision_tree 2 / llm 2", out.getvalue())
        self.assertFalse(results.exists())
        call_command(*args, stdout=io.StringIO())
        folder = results / "trial"
        config = json.loads((folder / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(config["counts"], {"in_menu": 1, "close_alternative": 1})
        limited = ["run_engine_benchmark", "--name", "limited", "--date", "2026-10-13", "--counts", "in_menu:2",
                   "--limit", "1", "--repeats", "1", "--results-dir", str(results)]
        call_command(*limited, stdout=io.StringIO())
        self.assertEqual(json.loads((results / "limited" / "config.json").read_text(encoding="utf-8"))["counts"],
                         {"in_menu": 1})  # played, not built
        collection = config["collection"]
        self.assertEqual(collection["simulator_model"], "google:gemini-3.5-flash")
        self.assertEqual((collection["simulator_prompt_id"], collection["simulator_prompts"]["system"]),
                         (simulator.PROMPT_ID, simulator.SYSTEM_PROMPT))
        self.assertIn("question engine", collection["llm_engine_prompt"])
        log = (folder / "sessions" / "run.log").read_text(encoding="utf-8")
        self.assertIn("4/4 세션", log)
        self.assertIn("결과 ->", log)
        self.assertEqual(len(self.lines(folder / "sessions" / "sessions.jsonl")), 4)
        self.assertIn("## 1. Main metrics", (folder / "report.md").read_text(encoding="utf-8"))
        self.assertTrue((folder / "1_main_metrics" / "main.csv").exists())

        self.scenarios = folder / "scenarios.json"
        human_dir = folder / "9_user_study" / "human"
        human_dir.mkdir(parents=True)
        self.play(human_dir / "lee.jsonl", engine="decision_tree")
        calls = engine.calls
        call_command(*args, stdout=io.StringIO())  # continues: no new session, people's sessions read
        self.assertEqual(engine.calls, calls)
        self.assertIn("1 testers", (folder / "report.md").read_text(encoding="utf-8"))
        self.assertEqual(json.loads((folder / "config.json").read_text(encoding="utf-8"))["collection"], collection)
        with self.settings(RECOMMEND_MAX_QUESTIONS=5), self.assertRaisesMessage(CommandError, "(max_questions)"):
            call_command(*args, stdout=io.StringIO())
