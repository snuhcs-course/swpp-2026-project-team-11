"""Group rooms: friends on their own phones answer the same questions and get restaurants.

    create(name, allergies, language, settings) -> (Room, host Member)
    join(code, name, allergies, language)       -> (Room, Member)
    get(code)                                   -> Room | None
    room.start(member) / answer(member, question_id, answer_id) / recommend_now(member)
    room.decide(member, restaurant) / leave(member)
    room.public_state(member)                   -> what that member's phone draws

A room has a four-digit code and 2 to 8 members. Each phone holds its member's secret
token. The host sets the meal, the restaurants and the location, starts the questions,
may stop them early ("recommend now") and decides on a restaurant. Nobody joins after
the start. When the host leaves, a random remaining member becomes host.

Every round asks all members the same question (question_engines/group). A member who
has not answered ROUND_SECONDS after the round began answers "any" (doesn't matter);
an answer cannot be changed. A member who left answers "any" at once. Deadlines are
checked whenever the room is read or acted on, so phones polling the room move it on.

The result is up to two restaurants, each with every member's dish there, the restaurant's
other dishes (by meal and name, like a session's menu), and how well the place fits them: "great" among their best tenth of the restaurants they can eat at, otherwise
"good". A member's allergies only remove dishes from their own choice. Rooms live in this process only,
like sessions (recommend/sessions.py).
"""

from __future__ import annotations

import datetime
import random
import secrets
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field

import numpy as np

from question_engines.decision_tree.contracts import Answer, answer_options, translate
from question_engines.group import GroupConfig, GroupEngine
from question_engines.group.engine import MAX_MEMBERS, place

from .sessions import EngineUnavailable, StaleStep, load_candidates, restaurant_menus

ROUND_SECONDS = 10
TIMEOUT_ANSWER = Answer.ANY.value
ANSWER_IDS = {answer.value for answer in Answer}
MAX_ROOMS = 200
GREAT_SHARE = 0.1
clock = time.monotonic


class RoomError(Exception):
    """A request the room cannot take; `code` is the API error code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class RoomSettings:
    date: datetime.date
    meal: str | None
    source: str
    distance_scope: str | None
    location: tuple[float, float] | None


@dataclass
class Member:
    id: int
    name: str
    allergies: frozenset[str]
    language: str
    token: str = field(default_factory=lambda: secrets.token_urlsafe(24))
    left: bool = False


class Room:
    def __init__(self, code: str, settings: RoomSettings):
        self.code = code
        self.settings = settings
        self.members: list[Member] = []
        self.host_id = 0
        self.status = "lobby"
        self.engine: GroupEngine | None = None
        self.round_started = 0.0
        self.round_answers: dict[int, str] = {}
        self.picks: list[dict] | None = None
        self.menus: dict[tuple, list[dict]] = {}
        self.decided: str | None = None
        self.lock = threading.Lock()

    def member(self, token: str | None) -> Member | None:
        return next((m for m in self.members if token and secrets.compare_digest(m.token, token)), None)

    def _add(self, name: str, allergies: frozenset[str], language: str) -> Member:
        if self.status != "lobby":
            raise RoomError("room_started", "The questions have already started.")
        if len(self._present()) >= MAX_MEMBERS:
            raise RoomError("room_full", f"A room has at most {MAX_MEMBERS} people.")
        member = Member(len(self.members), name, allergies, language)
        self.members.append(member)
        return member

    def _present(self) -> list[Member]:
        return [m for m in self.members if not m.left]

    def _require_host(self, member: Member) -> None:
        if member.id != self.host_id:
            raise RoomError("not_host", "Only the host can do that.")

    def start(self, member: Member) -> None:
        self._require_host(member)
        if self.status != "lobby":
            raise StaleStep("The questions have already started.")
        present = self._present()
        if len(present) < 2:
            raise RoomError("too_few_members", "A group needs at least two people.")
        # The engine numbers members 0..n-1; members who left the lobby are dropped for good.
        self.members = [Member(i, m.name, m.allergies, m.language, m.token) for i, m in enumerate(present)]
        self.host_id = next(m.id for m in self.members if m.token == member.token)
        s = self.settings
        candidates, schema, _ = load_candidates(s.date, s.meal, frozenset(), s.source, s.location, s.distance_scope)
        self.menus = restaurant_menus(candidates, place)
        excluded = []
        for m in self.members:
            if m.allergies:
                allowed, _, _ = load_candidates(s.date, s.meal, m.allergies, s.source, s.location, s.distance_scope)
                excluded.append(_offers(candidates) - _offers(allowed))
            else:
                excluded.append(set())
        try:
            self.engine = GroupEngine(candidates, schema, excluded, config=GroupConfig(language="en"))
        except ValueError as error:
            raise RoomError("group_unavailable", str(error)) from error
        self.status = "asking"
        self._new_round()

    def _new_round(self) -> None:
        self.round_started = clock()
        self.round_answers = {}
        if self.engine.finished:
            self._finish()
            return
        self._answer_for([m.id for m in self.members if m.left])

    def _answer_for(self, member_ids: list[int]) -> None:
        """Answers "any" for those members until the round they were in ends."""
        round_ = self.engine.round
        for member_id in member_ids:
            if self.status != "asking" or self.engine.round != round_:
                return
            if member_id in self.engine.questions():
                self._give(self.members[member_id], TIMEOUT_ANSWER)

    def _give(self, member: Member, answer_id: str) -> None:
        """Records one answer; when it completes the round, moves to the next round or the result."""
        step = self.engine.questions()[member.id]
        before = self.engine.round
        self.engine.answer(member.id, step["question_id"], answer_id)
        self.round_answers[member.id] = answer_id
        if self.engine.round != before or self.engine.finished:
            self._new_round()

    def tick(self) -> None:
        """Answers "any" for everyone still silent once the round's time is up."""
        if self.status == "asking" and clock() - self.round_started >= ROUND_SECONDS:
            self._answer_for(sorted(self.engine.questions()))

    def answer(self, member: Member, question_id: str, answer_id: str) -> None:
        self.tick()
        if answer_id not in ANSWER_IDS:
            raise ValueError(f"Unknown answer_id: {answer_id!r}")
        step = self.engine.questions().get(member.id) if self.status == "asking" else None
        if step is None or step["question_id"] != question_id:
            raise StaleStep("That question is no longer waiting for your answer.")
        self._give(member, answer_id)

    def recommend_now(self, member: Member) -> None:
        self._require_host(member)
        self.tick()
        if self.status != "asking":
            raise StaleStep("The questions are over.")
        self.engine.stop()
        self._finish()

    def _finish(self) -> None:
        self.status = "done"
        self.picks = []
        satisfaction = self.engine.satisfaction()
        index = {p: r for r, p in enumerate(self.engine.places)}
        for pick in self.engine.recommendation()["picks"]:
            at = (pick["restaurant"], pick["lat"], pick["lng"])
            r = index[at]
            suggested = {food["food_id"] for food in pick["menus"] if food}
            offer = next(o for food in pick["menus"] if food for o in food["offers"] if place(o) == at)
            self.picks.append({
                "restaurant": pick["restaurant"], "kind": pick["kind"],
                "lat": pick["lat"], "lng": pick["lng"], "distance_m": offer.get("distance_m"),
                "menus": [{"member_id": m.id, "food": food, "fit": _fit(satisfaction[m.id], r)}
                          for m, food in zip(self.members, pick["menus"])],
                "others": [dish for dish in self.menus.get(at, []) if dish["food_id"] not in suggested]})

    def decide(self, member: Member, restaurant: str) -> None:
        self._require_host(member)
        if self.status != "done":
            raise StaleStep("There is no result to decide on yet.")
        if restaurant not in [p["restaurant"] for p in self.picks]:
            raise ValueError("restaurant must be one of the suggested restaurants.")
        self.decided = restaurant

    def leave(self, member: Member) -> None:
        if member.left:
            return
        member.left = True
        present = self._present()
        if member.id == self.host_id and present:
            self.host_id = random.choice(present).id
        if self.status == "asking":
            self._answer_for([member.id])

    def public_state(self, member: Member) -> dict:
        self.tick()
        asking = self.status == "asking"
        pending = self.engine.questions() if asking else {}
        question = None
        if asking:
            step = next(iter(pending.values()))
            question = {"question_id": step["question_id"], "text": translate(step["text"], member.language),
                        "options": answer_options(member.language)}
        return {
            "code": self.code,
            "status": self.status,
            "date": self.settings.date.isoformat(),
            "meal": self.settings.meal,
            "me": member.id,
            "host": self.host_id,
            "members": [{"id": m.id, "name": m.name, "allergies": sorted(m.allergies), "left": m.left,
                         "answered": asking and m.id not in pending} for m in self.members],
            "round": self.engine.round if self.engine else 0,
            "max_rounds": self.engine.config.max_rounds if self.engine else GroupConfig().max_rounds,
            "question": question,
            "my_answer": self.round_answers.get(member.id) if asking else None,
            "seconds_left": max(0.0, round(ROUND_SECONDS - (clock() - self.round_started), 1)) if asking else None,
            "picks": self.picks,
            "decided": self.decided,
        }


def _offers(candidates: list) -> set:
    """Every (food ID, place) a candidate list offers, as the engine's `excluded` names them."""
    return {(c["food_id"], place(o)) for c in candidates for o in c["offers"]}


def _fit(satisfaction: np.ndarray, r: int) -> str:
    """"great" when restaurant r is among the member's best tenth of the places they can eat at, else "good"."""
    own = satisfaction[satisfaction > 0]
    return "great" if satisfaction[r] >= np.quantile(own, 1 - GREAT_SHARE) else "good"


_rooms: OrderedDict[str, Room] = OrderedDict()
_rooms_lock = threading.Lock()


def _register(room_settings: RoomSettings) -> Room:
    with _rooms_lock:
        code = f"{secrets.randbelow(10000):04d}"
        while code in _rooms:
            code = f"{secrets.randbelow(10000):04d}"
        room = Room(code, room_settings)
        _rooms[code] = room
        while len(_rooms) > MAX_ROOMS:
            _rooms.popitem(last=False)
    return room


def create(name: str, allergies: frozenset[str], language: str, room_settings: RoomSettings) -> tuple[Room, Member]:
    room = _register(room_settings)
    with room.lock:
        return room, room._add(name, allergies, language)


def join(code: str, name: str, allergies: frozenset[str], language: str) -> tuple[Room, Member]:
    room = get(code)
    if room is None:
        raise RoomError("room_not_found", "No room is open with this code.")
    with room.lock:
        return room, room._add(name, allergies, language)


def get(code: str) -> Room | None:
    with _rooms_lock:
        return _rooms.get(code)


__all__ = ["EngineUnavailable", "Room", "RoomError", "RoomSettings", "StaleStep", "create", "get", "join"]
