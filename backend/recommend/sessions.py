"""One recommendation session per client, kept in server memory.

    create(date, meal, engine, allergies, areas, language, price_levels, user_id) -> RecommendSession
    get(session_id)            -> RecommendSession | None
    prewarm(meal, allergies, areas) -> builds the restaurant catalogue ahead of create
    session.public_state()     -> what the phone is allowed to see
    session.reason()           -> why the proposed dish suits the user (recommend/reasons.py)
    session.menu(restaurant)   -> the session's dishes that restaurant serves
    session.ban(food_id, food_group, banned) -> keep a dish, or every dish of a group, out of
                               the rest of the session, or let it back

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

`areas` are where the user picked to eat (recommend/areas.py), at least one: "campus", the
day's SNU cafeteria menu (menus.services.get_catalog), and "snu_station" or "nakseongdae",
the restaurants near that station (get_store_catalog). The candidates are the union of the
picked areas; with every area picked no restaurant is cut, as before areas. Only campus-only
sessions support the LLM engine, which would otherwise send thousands of dish names per
question. The server never learns where the user is.

`menu(restaurant)` lists the candidates a restaurant serves, so dishes withheld for
an allergy, outside the area or out of the price range are not listed either.

`price_levels` are the user's price ranges, at least one of 1 to 3 (recommend/prices.py).
Only offers priced inside one of those bands reach the engine, so every later proposal and
"find another" stays in them. With every level picked nothing is cut, not even offers of
unknown price.

A banned menu, or one holding a dish of a banned group (its `food_groups`), is never
proposed again in the session, even after undo: a guess of one is turned down with `feedback` as soon as an
action reaches it, and an undo that reaches one goes back further. Bans last only as
long as the session.

`timings` holds how long creation took to read the candidates and to build and start
the engine, in seconds; the API reports them as a Server-Timing header.

`user_id` is the signed-in user who started the session, or None for a guest; the API
records each dish such a session proposes in the user's history (accounts/history.py).

`reason()` calls the LLM outside the session lock, so a tap on the result screen
never waits for it, and keeps each reason for the answers it was written for.

Sessions live in this process only. `runserver` restarts and multi-worker
deployments lose them; persisting `engine.snapshot()` is the planned replacement.
"""

from __future__ import annotations

import datetime
import json
import threading
import time
import uuid
from collections import OrderedDict

from django.conf import settings
from django.utils import timezone

from menus.features.schema import FEATURE_VERSION
from menus.services import MEAL_ORDER, get_catalog, get_store_catalog
from recommend import reasons
from recommend.areas import AREAS, STATIONS, near_stations
from recommend.prices import PRICE_BANDS, within_price
from question_engines.decision_tree import DecisionTreeEngine
from question_engines.llm import LLMConfigError, LLMEngine
from question_engines.rl import RLEngine

ENGINES = ("decision_tree", "llm", "rl")
MAX_SESSIONS = 500


class StaleStep(Exception):
    """The request refers to a step the session is no longer showing."""


class EngineUnavailable(Exception):
    """The requested engine cannot run on this server as it is configured."""


def load_candidates(date: datetime.date, meal: str | None, allergies: frozenset[str],
                    areas: tuple[str, ...] = ("campus",),
                    price_levels: tuple[int, ...] = tuple(PRICE_BANDS)) -> tuple[list, list, int]:
    """(candidates, schema, count before the station and price cuts) for a session or a group room."""
    stations = [area for area in areas if area in STATIONS]
    campus, stores = [], []
    try:
        if "campus" in areas:
            campus, schema = get_catalog(date, meal, allergies)
        if stations:
            stores, schema = get_store_catalog(meal, allergies)
    except ValueError as error:
        raise EngineUnavailable("Invalid stored menu features.") from error
    before = len(campus) + len(stores)
    if set(areas) != set(AREAS):  # every area keeps every restaurant, also those without coordinates
        stores = near_stations(stores, stations)
    candidates = campus + stores
    if set(price_levels) != set(PRICE_BANDS):
        candidates = within_price(candidates, price_levels)
    return candidates, schema, before


def restaurant_menus(candidates: list, key=lambda offer: offer["restaurant"]) -> dict:
    """{key(offer): [{"food_id", "display_name", "meal", "price"}]}, breakfast first and by name within a meal."""
    menus = {}
    for candidate in candidates:
        for offer in candidate["offers"]:
            menus.setdefault(key(offer), []).append({
                "food_id": candidate["food_id"], "display_name": offer.get("menu_name") or candidate["display_name"],
                "meal": offer["meal"], "price": offer["price"]})
    for dishes in menus.values():
        dishes.sort(key=lambda dish: (MEAL_ORDER[dish["meal"]], dish["display_name"]))
    return menus


class RecommendSession:
    def __init__(self, date: datetime.date, meal: str | None, engine: str,
                 allergies: frozenset[str], areas: tuple[str, ...] = ("campus",), language: str = "en",
                 price_levels: tuple[int, ...] = tuple(PRICE_BANDS), user_id: int | None = None):
        self.session_id = uuid.uuid4().hex
        self.user_id = user_id
        self.interaction_id = uuid.uuid4().hex
        self.areas = areas
        self.price_levels = price_levels
        self.logged_allergies = sorted(allergies)
        self.engine_name = engine
        self.date = date
        self.meal = meal
        self.language = language
        self.lock = threading.Lock()
        started = time.perf_counter()
        candidates, schema, self.candidates_before_area = load_candidates(date, meal, allergies, areas, price_levels)
        loaded = time.perf_counter()
        self.candidate_count = len(candidates)
        # Reasons need only dish names and feature means after the engine is built.
        self.reason_data = {c["food_id"]: (c["display_name"], c.get("features") or {}) for c in candidates}
        self.reasons = {}
        self.banned_foods, self.banned_groups = set(), set()
        self.food_groups = {c["food_id"]: set(c["food_groups"]) for c in candidates}
        self.menus = restaurant_menus(candidates)
        self.max_questions = settings.RECOMMEND_MAX_QUESTIONS
        config = {"max_questions": self.max_questions, "language": language}
        if engine == "llm":
            try:
                self.engine = LLMEngine(candidates, config=config)
            except LLMConfigError as error:  # no API key, or a malformed LLM setting
                raise EngineUnavailable(str(error)) from error
        elif engine == "rl":
            try:
                self.engine = RLEngine(candidates, **config)
            except ValueError as error:
                raise EngineUnavailable("Invalid catalogue for the RL engine.") from error
        else:
            self.engine = DecisionTreeEngine(
                candidates, schema,
                context={"date": date.isoformat(), "meal": meal, "feature_version": FEATURE_VERSION,
                         "candidate_kind": "menu-rms-v1"},
                config=config | {"policy": settings.RECOMMEND_DT_POLICY},
            )
        self.engine.start()
        self.timings = {"candidates": loaded - started, "engine": time.perf_counter() - loaded}

    def answer(self, question_id: str, answer_id: str) -> None:
        step = self.engine.next_step()
        if step["type"] != "question" or step["question_id"] != question_id:
            raise StaleStep("That question is no longer the current step.")
        if answer_id not in [option["id"] for option in step["options"]]:
            raise ValueError(f"Unknown answer_id: {answer_id!r}")
        self.engine.answer(question_id, answer_id)
        self._skip_banned()

    def feedback(self, guess_id: str, accepted: bool) -> None:
        step = self.engine.next_step()
        if step["type"] != "guess" or step["guess_id"] != guess_id:
            raise StaleStep("That guess is no longer the current step.")
        self.engine.feedback(guess_id, accepted)
        self._skip_banned()

    def recommend_now(self) -> None:
        # A guess is already a concrete proposal; asking again must not stack events.
        if self.engine.next_step()["type"] == "question":
            self.engine.recommend_now()
            self._skip_banned()

    def undo(self) -> None:
        self.engine.undo()
        self._skip_banned(back=True)

    def ban(self, food_id: int | None, food_group: str | None, banned: bool) -> None:
        """Bans one dish or one group. The dish on screen stays; the next action that reaches it skips it."""
        if (food_id is None) == (food_group is None):
            raise ValueError("Send either food_id or food_group.")
        if food_id is not None and type(food_id) is not int:
            raise ValueError("food_id must be a food ID.")
        if food_group is not None and not (isinstance(food_group, str) and food_group):
            raise ValueError("food_group must be a group name.")
        if type(banned) is not bool:
            raise ValueError("banned must be true or false.")
        bans, key = (self.banned_foods, food_id) if food_id is not None else (self.banned_groups, food_group)
        if banned:
            bans.add(key)
        else:
            bans.discard(key)

    def _banned(self, step: dict) -> bool:
        if step["type"] != "guess":
            return False
        food_id = step["food"]["food_id"]
        return food_id in self.banned_foods or not self.banned_groups.isdisjoint(self.food_groups[food_id])

    def _skip_banned(self, back: bool = False) -> None:
        """Turns down each banned guess, or with `back` undoes past it while it can."""
        step = self.engine.next_step()
        while self._banned(step):
            if back and self.engine.can_undo:
                self.engine.undo()
            else:
                self.engine.feedback(step["guess_id"], False)
            step = self.engine.next_step()

    def menu(self, restaurant: str) -> dict:
        """{"restaurant", "dishes"}: each {"food_id", "display_name", "meal", "price"}, by meal and name."""
        return {"restaurant": restaurant, "dishes": self.menus.get(restaurant, [])}

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
        food = step["food"]
        features = self.reason_data[food["food_id"]][1]
        names = {food["display_name"]}
        return reasons.Facts(
            language=self.language,
            dish=food["display_name"],
            members=(),
            restaurants=tuple(dict.fromkeys(offer["restaurant"] for offer in food["offers"])),
            traits=tuple(key.replace("_", " ") for key, value in features.items() if value is not None and value >= .6),
            answers=tuple(reasons.answer_facts(answered, features)),
            others=tuple({name for name, _ in self.reason_data.values()} - names),
        )

    def public_state(self) -> dict:
        step = self.engine.next_step()
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
           engine: str | None = None, allergies: frozenset[str] = frozenset(),
           areas: tuple[str, ...] = ("campus",), language: str = "en",
           price_levels: tuple[int, ...] = tuple(PRICE_BANDS), user_id: int | None = None) -> RecommendSession:
    """Sessions beyond campus fall back to DT if the configured default is LLM."""
    if engine is None:
        engine = settings.RECOMMEND_DEFAULT_ENGINE
        if areas != ("campus",) and engine == "llm":
            engine = "decision_tree"
    session = RecommendSession(date or settings.RECOMMEND_DEFAULT_DATE or timezone.localdate(),
                               meal, engine, allergies, areas, language, price_levels, user_id)
    with _sessions_lock:
        _sessions[session.session_id] = session
        while len(_sessions) > MAX_SESSIONS:
            _sessions.popitem(last=False)
    return session


def prewarm(meal: str | None, allergies: frozenset[str], areas: tuple[str, ...]) -> None:
    """Builds the restaurant catalogue a session would read, which takes about a second."""
    if any(area in STATIONS for area in areas):
        get_store_catalog(meal, allergies)


def get(session_id: str) -> RecommendSession | None:
    with _sessions_lock:
        return _sessions.get(session_id)
