"""One recommendation session per client, kept in server memory.

    create(date, meal, engine, location, allergies, source, language) -> RecommendSession
    get(session_id)            -> RecommendSession | None
    session.public_state()     -> what the phone is allowed to see
    session.reason()           -> why the proposed dish suits the user (recommend/reasons.py)

A session runs one of ENGINES, chosen when it is created: the decision tree,
the feature-only RL policy, or the LLM engine. They share the session API and step shapes, so
everything below the constructor is the same for all three. Dishes with one of the
user's `allergies` never reach the engine (menus.services.get_catalog), and the engine
writes its questions and texts in the session's `language` ("en" or "ko"). The LLM engine calls
the LLM while it starts and after every answer, rejection and "recommend now", so
those requests can take as long as its timeout allows; undo never calls it.

The engine is one session per instance and is not safe to mutate from two
requests at once, so every session carries its own lock. The candidate list is
read once at creation and stays with the engine: a later `fetch_menus` run does
not change a session that is already in progress.

`source` is what the dishes come from: "cafeteria", the day's SNU cafeteria menu
(menus.services.get_catalog), or "general", the restaurants near 서울대입구역 and
낙성대역 (get_store_catalog). A general session supports the decision tree and RL: the LLM
engine would send thousands of dish names with every question.

`location` is the user's (lat, lng), if the phone sent one. Each offer then
carries its `distance_m`, and with RECOMMEND_MAX_DISTANCE_M set, cafeterias
farther than that are left out before the engine sees the candidates.

`reason()` calls the LLM outside the session lock, so a tap on the result screen
never waits for it, and keeps each reason for the answers it was written for.

Sessions live in this process only. `runserver` restarts and multi-worker
deployments lose them; persisting `engine.snapshot()` is the planned replacement.
"""

from __future__ import annotations

import datetime
import json
import threading
import uuid
from collections import OrderedDict

from django.conf import settings
from django.utils import timezone

from menus.services import get_catalog, get_store_catalog
from recommend import reasons
from recommend.distance import with_distances
from question_engines.decision_tree import DecisionTreeEngine
from question_engines.llm import LLMConfigError, LLMEngine
from question_engines.rl import RLEngine

ENGINES = ("decision_tree", "llm", "rl")
SOURCES = ("cafeteria", "general")
MAX_SESSIONS = 500


class StaleStep(Exception):
    """The request refers to a step the session is no longer showing."""


class EngineUnavailable(Exception):
    """The requested engine cannot run on this server as it is configured."""


class RecommendSession:
    def __init__(self, date: datetime.date, meal: str | None, engine: str,
                 location: tuple[float, float] | None, allergies: frozenset[str],
                 source: str = "cafeteria", language: str = "en"):
        self.session_id = uuid.uuid4().hex
        self.engine_name = engine
        self.date = date
        self.meal = meal
        self.language = language
        self.lock = threading.Lock()
        if source == "general":
            candidates, schema, version = get_store_catalog(meal, allergies)
        else:
            candidates, schema, version = get_catalog(date, meal, allergies, prefer_v2=(engine == "rl"))
        candidates = with_distances(candidates, location, settings.RECOMMEND_MAX_DISTANCE_M)
        self.feature_version = version
        self.candidate_count = len(candidates)
        # Reasons need only dish names and feature means after the engine is built.
        self.reason_data = {c["food_id"]: (c["display_name"], c.get("features") or {}) for c in candidates}
        self.reasons = {}
        self.max_questions = settings.RECOMMEND_MAX_QUESTIONS
        config = {"max_questions": self.max_questions, "language": language}
        if engine == "llm":
            try:
                self.engine = LLMEngine(candidates, config=config)
            except LLMConfigError as error:  # no API key, or a malformed LLM setting
                raise EngineUnavailable(str(error)) from error
        elif engine == "rl":
            if candidates and version != "v2":
                raise EngineUnavailable("The RL engine requires v2 food features.")
            try:
                self.engine = RLEngine(candidates, **config)
            except ValueError as error:
                raise EngineUnavailable("Invalid v2 catalogue for the RL engine.") from error
        else:
            self.engine = DecisionTreeEngine(
                candidates, schema,
                context={"date": date.isoformat(), "meal": meal, "feature_version": version},
                config=config | {"policy": settings.RECOMMEND_DT_POLICY},
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

    def reason(self) -> dict:
        """{"food_id", "reason", "source"} for the dish on screen. Raises StaleStep without one."""
        with self.lock:
            step = self.engine.next_step()
            if step["type"] not in ("guess", "recommendation"):
                raise StaleStep("No dish is proposed now.")
            answered = self.engine.answered()
            key = json.dumps([step.get("guess_id"), step["food"]["food_id"], answered])
            cached = self.reasons.get(key)
        if cached is None:
            cached = {"food_id": step["food"]["food_id"],
                      **reasons.explain(self._facts(step, answered), reasons.default_llm())}
            with self.lock:
                self.reasons[key] = cached
        return cached

    def _facts(self, step: dict, answered: list[dict]) -> reasons.Facts:
        food, group = step["food"], step.get("group")
        features = self.reason_data[food["food_id"]][1]
        members = tuple(self.reason_data[food_id][0] for food_id in group["food_ids"]) if group else ()
        names = {food["display_name"], *members}
        return reasons.Facts(
            language=self.language,
            dish=group["display_name"] if group else food["display_name"],
            members=members,
            restaurants=tuple(dict.fromkeys(offer["restaurant"] for offer in food["offers"])),
            traits=tuple(key.replace("_", " ") for key, value in features.items() if value is not None and value >= .6),
            answers=tuple((answer["text"], answer["answer_id"], features.get(answer["question_id"].removeprefix("q:")))
                          for answer in answered),
            others=tuple({name for name, _ in self.reason_data.values()} - names),
        )

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
            "language": self.language,
            "candidate_count": self.candidate_count,
            "max_questions": self.max_questions,
            "can_undo": self.engine.can_undo,
            "step": step,
        }


_sessions: OrderedDict[str, RecommendSession] = OrderedDict()
_sessions_lock = threading.Lock()


def create(date: datetime.date | None = None, meal: str | None = None,
           engine: str | None = None, location: tuple[float, float] | None = None,
           allergies: frozenset[str] = frozenset(), source: str | None = None,
           language: str = "en") -> RecommendSession:
    """General sessions fall back to DT if the configured default is LLM."""
    source = source or "cafeteria"
    if engine is None:
        engine = settings.RECOMMEND_DEFAULT_ENGINE
        if source == "general" and engine == "llm":
            engine = "decision_tree"
    session = RecommendSession(date or settings.RECOMMEND_DEFAULT_DATE or timezone.localdate(),
                               meal, engine, location, allergies, source, language)
    with _sessions_lock:
        _sessions[session.session_id] = session
        while len(_sessions) > MAX_SESSIONS:
            _sessions.popitem(last=False)
    return session


def get(session_id: str) -> RecommendSession | None:
    with _sessions_lock:
        return _sessions.get(session_id)
