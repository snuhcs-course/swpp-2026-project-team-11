"""`language` on the REST API: every text of a Korean session is Korean, names stay as they are."""
import re

from question_engines.decision_tree.contracts import GUESS_TEXT, KOREAN
from question_engines.llm.tests.helpers import ask_ko

from .helpers import check_state, post
from .test_edge_cases import SmallMenuTestCase
from .test_llm_engine import LLMSessionTestCase

HANGUL = re.compile("[가-힣]")


class DecisionTreeLanguageTests(SmallMenuTestCase):
    def test_a_korean_session_asks_and_guesses_in_korean(self):
        state, url = self.start(language="ko")
        check_state(self, state)
        self.assertEqual(state["language"], "ko")
        self.assertTrue(HANGUL.search(state["step"]["text"]))
        self.assertTrue(all(HANGUL.search(option["label"]) for option in state["step"]["options"]))
        guess = self.call(url + "recommend-now/")
        self.assertEqual(guess["step"]["text"], KOREAN[GUESS_TEXT])
        self.assertIn(guess["step"]["food"]["display_name"], ("Beef noodles", "Chicken noodles", "Rice bowl"))

    def test_english_is_the_default(self):
        state, _ = self.start()
        self.assertEqual(state["language"], "en")
        self.assertTrue(state["step"]["text"].isascii())

    def test_an_unknown_language_is_400(self):
        for language in ("ja", "KO", None, ["ko"]):
            response = post(self.client, "/api/sessions/", {"language": language})
            self.assertEqual(response.status_code, 400, language)
            self.assertEqual(response.json()["error"]["code"], "invalid_request")


class LLMLanguageTests(LLMSessionTestCase):
    def test_a_korean_llm_session_shows_the_korean_question_only(self):
        self.use_llm(ask_ko("Do you feel like noodles?", "면 요리가 당기나요?", "Beef noodles"))
        state, _ = self.start(language="ko")
        check_state(self, state)
        self.assertEqual(state["step"]["text"], "면 요리가 당기나요?")
        self.assertNotIn("english", state["step"])
