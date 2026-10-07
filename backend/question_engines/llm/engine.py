"""P13: the LLM chooses every question and the proposed food from food names alone.

It has the same session API and step shapes as the P10 DecisionTreeEngine, so the
P17 session wrapper and the P19 client can run either engine:

    engine = LLMEngine(get_candidates(date, "LU"), llm=chat_model)
    step = engine.start()
    step = engine.answer(step["question_id"], "probably_yes")
    step = engine.feedback(step["guess_id"], accepted=False)   # "another menu"

One instance owns one session and is not safe to mutate from two requests at once.
`llm` is a LangChain chat model; tests pass a fake one and need no API key.
"""
import copy
from dataclasses import asdict, dataclass
import hashlib
import json
import time

from question_engines.decision_tree.contracts import ANSWER_OPTIONS

from .prompt import SYSTEM_PROMPT, build_user_message
from .schema import build_turn_model

ENGINE_VERSION = "llm-v1"
ANSWER_LABELS = {option["id"]: option["label"] for option in ANSWER_OPTIONS}
GUESS_TEXT = "Is this what you feel like eating?"
RECOMMENDATION_TEXT = "Enjoy your meal."
UNAVAILABLE_TEXT = "No available meal matches this session. Try starting again."


@dataclass(frozen=True)
class EngineConfig:
    max_questions: int | None = 10

    def __post_init__(self):
        if self.max_questions is not None and (type(self.max_questions) is not int or self.max_questions < 1):
            raise ValueError("max_questions must be positive or None")


class InvalidTurn(ValueError):
    """The LLM answered in the schema but broke a rule the schema cannot express."""


def food_summary(candidate):
    """The candidate as P10 shows it in a step: no features, offers kept."""
    return {"food_id": candidate["food_id"], "name": candidate["name"],
            "display_name": candidate["display_name"], "food_group": candidate["food_group"],
            "offers": copy.deepcopy(list(candidate["offers"]))}


class LLMEngine:
    """start/answer/feedback/recommend_now/undo -> JSON-compatible step, like P10.

    The session is its list of displayed steps and the user's responses to them
    (`events`), so undo and snapshot replay never call the LLM again.
    """

    def __init__(self, candidates, *, llm, config=None):
        self.llm = llm
        self.config = config if isinstance(config, EngineConfig) else EngineConfig(**(config or {}))
        # Dishes sharing a display name are one choice: the LLM cannot tell them apart.
        self.choices = {}
        for candidate in candidates:
            self.choices.setdefault(candidate["display_name"], candidate)
        identity = sorted((c["food_id"], c["display_name"]) for c in candidates)
        self.fingerprint = hashlib.sha256(json.dumps(
            {"version": ENGINE_VERSION, "candidates": identity, "config": asdict(self.config)},
            ensure_ascii=False).encode()).hexdigest()
        self._events = []
        self._pending = None
        self._calls = []  # one record per LLM decision, for diagnostics()

    # Session state, derived from the events

    @property
    def question_count(self):
        return sum(event["type"] == "answer" for event in self._events)

    def _history(self):
        return [(event["before"]["text"], ANSWER_LABELS[event["answer_id"]])
                for event in self._events if event["type"] == "answer"]

    def _rejected(self):
        return [event["before"]["food"]["display_name"] for event in self._events
                if event["type"] == "feedback" and not event["accepted"]]

    def _accepted_food(self):
        for event in self._events:
            if event["type"] == "feedback" and event["accepted"]:
                return event["before"]["food"]
        return None

    # Steps

    def _question_step(self, text):
        return {"type": "question", "question_count": self.question_count,
                "question_id": f"q:llm-{len(self._events)}", "text": text,
                "options": copy.deepcopy(list(ANSWER_OPTIONS))}

    def _food_step(self, kind, food):
        step = {"type": kind, "question_count": self.question_count, "food": copy.deepcopy(food),
                "target_kind": "food", "text": GUESS_TEXT if kind == "guess" else RECOMMENDATION_TEXT}
        if kind == "guess":
            step["guess_id"] = f"food:{food['food_id']}"
        return step

    def _unavailable_step(self, reason):
        return {"type": "unavailable", "question_count": self.question_count,
                "reason": reason, "text": UNAVAILABLE_TEXT}

    def _decide(self, force_guess=False):
        accepted = self._accepted_food()
        if accepted is not None:
            return self._food_step("recommendation", accepted)
        if not self.choices:
            return self._unavailable_step("empty_candidates")
        rejected = set(self._rejected())
        available = {name: c for name, c in self.choices.items() if name not in rejected}
        if not available:
            return self._unavailable_step("candidates_exhausted")
        if len(available) == 1:
            return self._food_step("guess", food_summary(next(iter(available.values()))))

        if force_guess:
            questions_left = 0
        elif self.config.max_questions is None:
            questions_left = None
        else:
            questions_left = max(self.config.max_questions - self.question_count, 0)
        turn = self._request_turn(list(available), questions_left)
        if turn.action == "recommend" or questions_left == 0:
            return self._food_step("guess", food_summary(available[turn.food]))
        return self._question_step(turn.question.strip())

    def _request_turn(self, food_names, questions_left):
        """One LLM call. Raises on a network error, invalid JSON or an InvalidTurn."""
        from langchain_core.messages import HumanMessage, SystemMessage

        history = self._history()
        start = time.perf_counter()
        structured = self.llm.with_structured_output(build_turn_model(food_names))
        turn = structured.invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=build_user_message(food_names, history, self._rejected(), questions_left)),
        ])
        check_turn(turn, history, questions_left)
        self._calls.append({"latency_ms": round((time.perf_counter() - start) * 1000)})
        return turn

    def _record(self, event):
        self._events.append(copy.deepcopy(event))
        self._pending = None

    # Public session API (same as DecisionTreeEngine)

    def start(self):
        return self.next_step()

    def next_step(self):
        if self._pending is None:
            self._pending = self._decide()
        return copy.deepcopy(self._pending)

    def answer(self, question_id, answer_id):
        pending = self.next_step()
        if pending["type"] != "question" or pending["question_id"] != question_id or answer_id not in ANSWER_LABELS:
            raise ValueError("Answer must match the current question and a supported answer ID")
        self._record({"type": "answer", "question_id": question_id, "answer_id": answer_id, "before": pending})
        return self.next_step()

    def feedback(self, guess_id, accepted):
        pending = self.next_step()
        if pending["type"] != "guess" or pending["guess_id"] != guess_id or type(accepted) is not bool:
            raise ValueError("Feedback must match the current guess and be boolean")
        self._record({"type": "feedback", "guess_id": guess_id, "accepted": accepted, "before": pending})
        return self.next_step()

    def recommend_now(self):
        pending = self.next_step()
        if pending["type"] not in {"question", "guess"}:
            raise ValueError("The session is not active")
        self._record({"type": "recommend_now", "before": pending})
        self._pending = self._decide(force_guess=True)
        return copy.deepcopy(self._pending)

    def undo(self):
        if self._events:
            self._pending = self._events.pop()["before"]
        return self.next_step()

    def diagnostics(self):
        shown = [event["before"] for event in self._events] + [self._pending or {}]
        return {"engine_version": ENGINE_VERSION,
                "question_count": self.question_count,
                "guess_count": sum(step.get("type") == "guess" for step in shown),
                "feedback_count": sum(event["type"] == "feedback" for event in self._events),
                "llm_calls": copy.deepcopy(self._calls),
                "llm_latency_ms": sum(call["latency_ms"] for call in self._calls)}

    def snapshot(self):
        self.next_step()
        return {"version": 1, "engine_version": ENGINE_VERSION, "fingerprint": self.fingerprint,
                "config": asdict(self.config), "events": copy.deepcopy(self._events),
                "pending": copy.deepcopy(self._pending)}

    @classmethod
    def from_snapshot(cls, candidates, snapshot, *, llm):
        """Restore a session without calling the LLM: its steps are all recorded."""
        if not isinstance(snapshot, dict) or snapshot.get("version") != 1 or snapshot.get("engine_version") != ENGINE_VERSION:
            raise ValueError("Unsupported snapshot version")
        if (not isinstance(snapshot.get("events"), list) or not isinstance(snapshot.get("pending"), dict)
                or not isinstance(snapshot.get("config"), dict)):
            raise ValueError("Malformed snapshot structure")
        engine = cls(candidates, llm=llm, config=snapshot["config"])
        if snapshot.get("fingerprint") != engine.fingerprint:
            raise ValueError("Snapshot candidates or configuration differ")
        engine._events = copy.deepcopy(snapshot["events"])
        engine._pending = copy.deepcopy(snapshot["pending"])
        return engine


def check_turn(turn, history, questions_left):
    if turn is None:
        raise InvalidTurn("The structured response was empty")
    if turn.action == "recommend" or questions_left == 0:
        return
    question = turn.question.strip()
    if not question:
        raise InvalidTurn("action=ask with an empty question")
    if question.casefold() in {asked.strip().casefold() for asked, _ in history}:
        raise InvalidTurn(f"Repeated question: {question}")
