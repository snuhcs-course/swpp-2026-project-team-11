"""One recommendation session per client, kept in server memory.

    create(date, meal)        -> RecommendSession
    get(session_id)           -> RecommendSession | None
    session.public_state()    -> what the phone is allowed to see

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

ENGINE_NAME = "decision_tree"
MAX_SESSIONS = 500


class StaleStep(Exception):
    """The request refers to a step the session is no longer showing."""


class RecommendSession:
    def __init__(self, date: datetime.date, meal: str | None):
        self.session_id = uuid.uuid4().hex
        self.date = date
        self.meal = meal
        self.lock = threading.Lock()
        candidates = get_candidates(date, meal)
        self.candidate_count = len(candidates)
        self.max_questions = settings.RECOMMEND_MAX_QUESTIONS
        self.engine = DecisionTreeEngine(
            candidates, get_feature_schema(),
            context={"date": date.isoformat(), "meal": meal},
            config={"max_questions": self.max_questions},
        )
        self.engine.start()

    def answer(self, question_id: str, answer_id: str) -> None:
        step = self.engine.next_step()
        if step["type"] != "question" or step["question_id"] != question_id:
            raise StaleStep("That question is no longer the current step.")
        if answer_id not in {option["id"] for option in step["options"]}:
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
            # The engine lists members by ID only; the phone needs names to show them.
            foods = self.engine.catalog.by_id
            group["members"] = [
                {"food_id": food_id, "display_name": foods[food_id].display_name}
                for food_id in group.pop("food_ids")
            ]
        return {
            "session_id": self.session_id,
            "engine": ENGINE_NAME,
            "date": self.date.isoformat(),
            "meal": self.meal,
            "candidate_count": self.candidate_count,
            "max_questions": self.max_questions,
            "can_undo": bool(self.engine.snapshot()["events"]),
            "step": step,
        }


_sessions: OrderedDict[str, RecommendSession] = OrderedDict()
_sessions_lock = threading.Lock()


def create(date: datetime.date | None = None, meal: str | None = None) -> RecommendSession:
    session = RecommendSession(date or settings.RECOMMEND_DEFAULT_DATE or timezone.localdate(), meal)
    with _sessions_lock:
        _sessions[session.session_id] = session
        while len(_sessions) > MAX_SESSIONS:
            _sessions.popitem(last=False)
    return session


def get(session_id: str) -> RecommendSession | None:
    with _sessions_lock:
        return _sessions.get(session_id)
