from django.test import SimpleTestCase
from pydantic import ValidationError

from ..engine import LLMEngine
from ..prompt import build_user_message
from ..schema import build_turn_model
from .helpers import CANDIDATES, FakeLLM, ask, recommend


class TurnModelTests(SimpleTestCase):
    def test_food_must_be_a_listed_name(self):
        model = build_turn_model(["육개장", "물냉면"])
        self.assertEqual(model.model_validate(recommend("물냉면")).food, "물냉면")
        with self.assertRaises(ValidationError):
            model.model_validate(recommend("짜장면"))

    def test_food_is_an_enum_in_the_json_schema(self):
        schema = build_turn_model(["육개장", "물냉면"]).model_json_schema()
        self.assertEqual(schema["properties"]["food"]["enum"], ["육개장", "물냉면"])


class PromptTests(SimpleTestCase):
    def test_llm_sees_names_answers_and_rejections_but_no_features(self):
        llm = FakeLLM(ask("Do you feel like something with broth?"), recommend("물냉면"),
                      ask("Do you feel like noodles?"))
        engine = LLMEngine(CANDIDATES, llm=llm)
        step = engine.start()
        step = engine.answer(step["question_id"], "probably_no")
        engine.feedback(step["guess_id"], False)
        prompt = llm.prompt()

        self.assertIn("- 육개장", prompt)
        self.assertIn("Q1. Do you feel like something with broth? -> Probably not", prompt)
        self.assertIn("## Menus the user rejected\n- 물냉면", prompt)
        self.assertNotIn("spicy", prompt)
        self.assertNotIn("0.9", prompt)

    def test_questions_left(self):
        self.assertIn("Questions left: 3.", build_user_message(["육개장"], [], [], 3))
        self.assertIn("action=recommend", build_user_message(["육개장"], [], [], 0))
        self.assertNotIn("Questions left", build_user_message(["육개장"], [], [], None))
