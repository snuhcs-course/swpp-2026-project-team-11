# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""One recommendation session per client, kept in server memory.

    create(date, meal, engine) -> RecommendSession
    get(session_id)            -> RecommendSession | None
    session.public_state()     -> what the phone is allowed to see

A session runs one of ENGINES, chosen when it is created: the P10 decision tree
or the P13/P14 LLM engine. Both have the same session API and step shapes, so
everything below the constructor is the same for either. The LLM engine calls
Gemini while it starts and after every answer, rejection and "recommend now", so
those requests can take as long as its timeout allows; undo never calls it.

The engine is one session per instance and is not safe to mutate from two
requests at once, so every session carries its own lock. The candidate list is
read once at creation and stays with the engine: a later `fetch_menus` run does
not change a session that is already in progress.

Sessions live in this process only. `runserver` restarts and multi-worker
deployments lose them; persisting `engine.snapshot()` is the planned replacement.
"""

from __future__ import annotations

import datetime
import threading
import uuid
from collections import OrderedDict

from django.conf import settings
from django.utils import timezone

from menus.services import get_candidates, get_feature_schema
from question_engines.decision_tree import DecisionTreeEngine
from question_engines.llm import LLMConfigError, LLMEngine

ENGINES = ("decision_tree", "llm")
MAX_SESSIONS = 500


class StaleStep(Exception):
    """The request refers to a step the session is no longer showing."""


class EngineUnavailable(Exception):
    """The requested engine cannot run on this server as it is configured."""


class RecommendSession:
    def __init__(self, date: datetime.date, meal: str | None, engine: str):
        self.session_id = uuid.uuid4().hex
        self.engine_name = engine
        self.date = date
        self.meal = meal
        self.lock = threading.Lock()
        candidates = get_candidates(date, meal)
        self.candidate_count = len(candidates)
        self.max_questions = settings.RECOMMEND_MAX_QUESTIONS
        config = {"max_questions": self.max_questions}
        if engine == "llm":
            try:
                self.engine = LLMEngine(candidates, config=config)
            except LLMConfigError as error:  # no API key, or a malformed LLM setting
                raise EngineUnavailable(str(error)) from error
        else:
            self.engine = DecisionTreeEngine(
                candidates, get_feature_schema(),
                context={"date": date.isoformat(), "meal": meal}, config=config,
            )
        self.engine.start()

    def answer(self, question_id: str, answer_id: str) -> None:
        step = self.engine.next_step()
        if step["type"] != "question" or step["question_id"] != question_id:
            raise StaleStep("That question is no longer the current step.")
        if answer_id not in [option["id"] for option in step["options"]]:
            raise ValueError(f"Unknown answer_id: {answer_id!r}")
        self.engine.answer(question_id, answer_id)

    def feedback(self, guess_id: str, accepted: bool) -> None:
        step = self.engine.next_step()
        if step["type"] != "guess" or step["guess_id"] != guess_id:
            raise StaleStep("That guess is no longer the current step.")
        self.engine.feedback(guess_id, accepted)

    def recommend_now(self) -> None:
        # A guess is already a concrete proposal; asking again must not stack events.
        if self.engine.next_step()["type"] == "question":
            self.engine.recommend_now()

    def undo(self) -> None:
        self.engine.undo()

    def public_state(self) -> dict:
        step = self.engine.next_step()
        group = step.get("group")
        if group:
            # Only the decision tree proposes groups. It lists members by ID only;
            # the phone needs names to show them.
            foods = self.engine.catalog.by_id
            group["members"] = [
                {"food_id": food_id, "display_name": foods[food_id].display_name}
                for food_id in group.pop("food_ids")
            ]
        return {
            "session_id": self.session_id,
            "engine": self.engine_name,
            "date": self.date.isoformat(),
            "meal": self.meal,
            "candidate_count": self.candidate_count,
            "max_questions": self.max_questions,
            "can_undo": bool(self.engine.snapshot()["events"]),
            "step": step,
        }


_sessions: OrderedDict[str, RecommendSession] = OrderedDict()
_sessions_lock = threading.Lock()


def create(date: datetime.date | None = None, meal: str | None = None,
           engine: str | None = None) -> RecommendSession:
    """Raises EngineUnavailable when `engine` is "llm" and the server has no API key."""
    session = RecommendSession(date or settings.RECOMMEND_DEFAULT_DATE or timezone.localdate(),
                               meal, engine or settings.RECOMMEND_DEFAULT_ENGINE)
    with _sessions_lock:
        _sessions[session.session_id] = session
        while len(_sessions) > MAX_SESSIONS:
            _sessions.popitem(last=False)
    return session


def get(session_id: str) -> RecommendSession | None:
    with _sessions_lock:
        return _sessions.get(session_id)
