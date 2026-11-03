"""The reason under the proposed dish (i3-A5), with a fake LLM: no API key, no network."""
from dataclasses import replace
from unittest import mock

from django.test import SimpleTestCase

from question_engines.llm.tests.helpers import FakeLLM, ask

from .. import sessions
from ..reasons import Facts, InvalidReason, ReasonDraft, build_message, check, explain, template
from .helpers import check_state
from .test_edge_cases import SmallMenuTestCase
from .test_llm_engine import LLMSessionTestCase

SPICY = "Do you feel like something spicy?"
BROTH = "Do you feel like something with broth?"
FRIED = "Do you feel like something fried?"


def facts(language="en", answers=((SPICY, "yes", .9), (BROTH, "probably_yes", .8), (FRIED, "no", .1))):
    return Facts(language=language, dish="짬뽕", members=(), restaurants=("학생회관식당",),
                 traits=("spicy", "soupy", "noodle"), answers=answers, others=("짜장면", "돈까스"))


def draft(reason, evidence=()):
    return {"evidence": list(evidence), "reason": reason}


class CheckTests(SimpleTestCase):
    def refuses(self, reason, evidence=(), language="en"):
        with self.assertRaises(InvalidReason) as raised:
            check(ReasonDraft(**draft(reason, evidence)), facts(language))
        return str(raised.exception)

    def test_accepts_a_grounded_reason_in_either_language(self):
        check(ReasonDraft(**draft("You wanted something spicy with broth, and 짬뽕 is both.", [1, 2, 3])), facts())
        check(ReasonDraft(**draft("매운 국물이 당긴다고 하셔서 학생회관식당의 짬뽕을 골랐어요.", [1, 2])), facts("ko"))

    def test_refuses_what_the_screen_cannot_show(self):
        self.assertIn("characters", self.refuses("Spicy. " * 40))
        self.assertIn("two sentences", self.refuses("It is spicy. It has broth. It is not fried."))
        self.assertIn("짜장면", self.refuses("Unlike 짜장면, it has a spicy broth."))
        self.assertIn("not in Korean", self.refuses("짬뽕 is spicy.", language="ko"))
        self.assertIn("not in Korean", self.refuses("soupy한 국물이 있어서 짬뽕을 골랐어요.", language="ko"))
        self.assertIn("English", self.refuses("짬뽕 is 매운 and hot."))

    def test_a_shortened_name_is_allowed_but_an_unrelated_dish_is_not(self):
        target = replace(facts(), dish="매운양념치킨", others=("양념치킨", "간장양념치킨"))
        check(ReasonDraft(**draft("The 양념치킨 fits your preference for spice.", [1])), target)
        with self.assertRaises(InvalidReason):
            check(ReasonDraft(**draft("Try the 간장양념치킨.", [1])), target)

    def test_refuses_evidence_that_does_not_point_to_the_dish(self):
        self.assertIn("Q4", self.refuses("It is spicy.", [4]))
        lacking = facts(answers=((SPICY, "yes", .1),))
        with self.assertRaises(InvalidReason):
            check(ReasonDraft(**draft("It is spicy.", [1])), lacking)
        neutral = facts(answers=((SPICY, "any", .9),))
        with self.assertRaises(InvalidReason):
            check(ReasonDraft(**draft("It is spicy.", [1])), neutral)


class ExplainTests(SimpleTestCase):
    def test_a_valid_draft_is_used_as_written(self):
        llm = FakeLLM(draft(" A spicy broth, as you wanted. ", [1, 2]))
        self.assertEqual(explain(facts(), llm), {"reason": "A spicy broth, as you wanted.", "source": "llm"})
        prompt = llm.prompt()
        self.assertIn("Q1. Do you feel like something spicy? -> Yes, sounds good (this dish: 0.9 of 1)", prompt)
        self.assertIn("Write in English", prompt)

    def test_a_refused_draft_goes_back_with_the_reason(self):
        llm = FakeLLM(draft("Unlike 돈까스, it is spicy.", [1]), draft("It is spicy, as you wanted.", [1]))
        self.assertEqual(explain(facts(), llm)["reason"], "It is spicy, as you wanted.")
        self.assertIn('names another dish, "돈까스"', llm.prompt())

    def test_without_a_usable_llm_the_template_answers(self):
        for llm in (None, FakeLLM(TimeoutError(), draft("", []))):
            with self.subTest(llm=llm):
                self.assertEqual(explain(facts(), llm)["source"], "template")


class TemplateTests(SimpleTestCase):
    def test_names_the_last_two_yes_answers_the_dish_fits(self):
        self.assertEqual(template(facts()), "You felt like something spicy and something with broth, "
                                            "and 짬뽕 is a good match.")
        self.assertEqual(template(facts("ko")), "매운 음식, 국물 있는 음식을 원하셔서 짬뽕을 골랐어요.")
        beef = facts("ko", answers=(("Do you feel like beef?", "yes", .9),))
        self.assertEqual(template(beef), "소고기를 원하셔서 짬뽕을 골랐어요.")

    def test_without_such_an_answer_it_stays_general_in_the_session_language(self):
        for answers in ((), ((SPICY, "no", .9),), ((SPICY, "yes", None),), ((SPICY, "any", .9),)):
            self.assertEqual(template(facts("en", answers)), "짬뽕 is one of the available dishes.")
            self.assertEqual(template(facts("ko", answers)), "메뉴 중에서 짬뽕을 골라 봤어요.")

    def test_the_korean_object_particle_follows_the_dish_name(self):
        for dish, reason in (("짜장면", "짜장면을"), ("돈까스", "돈까스를"), ("제육덮밥(L)", "제육덮밥(L)을")):
            korean = Facts("ko", dish, (), (), (), (), ())
            self.assertIn(reason, template(korean))

    def test_the_message_lists_a_group_and_no_answers(self):
        group = Facts("en", "Noodles", ("Beef noodles", "Chicken noodles"), (), (), (), ())
        message = build_message(group)
        self.assertIn("Noodles (one of Beef noodles, Chicken noodles)", message)
        self.assertIn("## The user's answers\n(none)", message)


class ReasonApiTests(SmallMenuTestCase):
    def use_reason_llm(self, *replies):
        llm = FakeLLM(*replies)
        patcher = mock.patch("recommend.reasons.default_llm", return_value=llm)
        patcher.start()
        self.addCleanup(patcher.stop)
        return llm

    def test_explains_the_guess_once_for_the_same_answers(self):
        llm = self.use_reason_llm(draft("It fits what you wanted.", [1]))
        state, url = self.start()
        question = state["step"]
        state = self.call(url + "answer/", {"question_id": question["question_id"], "answer_id": "yes"})
        if state["step"]["type"] == "question":
            state = self.call(url + "recommend-now/")
        check_state(self, state)
        reason = self.client.get(url + "reason/").json()
        self.assertEqual(reason, {"food_id": state["step"]["food"]["food_id"],
                                  "reason": "It fits what you wanted.", "source": "llm"})
        # The question in its first phrasing, whichever phrasing the session showed.
        [answered] = sessions.get(state["session_id"]).engine.answered()
        self.assertEqual(answered["question_id"], question["question_id"])
        self.assertIn(f"Q1. {answered['text']} -> Yes, sounds good", llm.prompt())
        self.assertEqual(self.client.get(url + "reason/").json(), reason)
        self.assertEqual(len(llm.calls), 1)

    def test_without_a_key_the_template_explains_in_the_session_language(self):
        with mock.patch("recommend.reasons.default_llm", return_value=None):
            _, url = self.start(language="ko")
            self.call(url + "recommend-now/")
            reason = self.client.get(url + "reason/").json()
        self.assertEqual(reason["source"], "template")
        self.assertRegex(reason["reason"], "^메뉴 중에서 .+ 골라 봤어요\\.$")

    def test_no_dish_on_screen_is_stale_and_an_unknown_session_404(self):
        state, url = self.start()
        response = self.client.get(url + "reason/")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "stale_step")
        self.assertEqual(response.json()["state"], state)
        self.assertEqual(self.client.get("/api/sessions/nope/reason/").status_code, 404)
        self.assertEqual(self.client.post(url + "reason/").status_code, 405)


class LLMSessionReasonTests(LLMSessionTestCase):
    def test_an_llm_session_is_explained_from_its_english_questions(self):
        self.use_llm(ask("Do you feel like noodles?", "Beef noodles"), {"action": "recommend", "question": "",
                                                                         "food": "Beef noodles"})
        reason_llm = FakeLLM(draft("Noodles, as you wanted.", [1]))
        with mock.patch("recommend.reasons.default_llm", return_value=reason_llm):
            state, url = self.start()
            self.call(url + "answer/", {"question_id": state["step"]["question_id"], "answer_id": "yes"})
            reason = self.client.get(url + "reason/").json()
        self.assertEqual(reason["reason"], "Noodles, as you wanted.")
        self.assertIn("Q1. Do you feel like noodles? -> Yes, sounds good (this dish: 0.9 of 1)", reason_llm.prompt())

    def test_unmapped_question_does_not_explain_a_dish_fit(self):
        self.use_llm(ask("In the mood for chili heat?", "Rice bowl"),
                     {"action": "recommend", "question": "", "food": "Rice bowl"})
        reason_llm = FakeLLM()
        with mock.patch("recommend.reasons.default_llm", return_value=reason_llm):
            state, url = self.start()
            self.call(url + "answer/", {"question_id": state["step"]["question_id"], "answer_id": "yes"})
            reason = self.client.get(url + "reason/").json()
        self.assertEqual(reason["reason"], "Rice bowl is one of the available dishes.")
        self.assertEqual(reason["source"], "template")
        self.assertFalse(reason_llm.calls)
