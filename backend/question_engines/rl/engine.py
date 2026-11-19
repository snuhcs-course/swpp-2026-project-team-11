"""Session adapter for the inductive feature-only dialogue policy."""
import copy
import hashlib
import json
from functools import cached_property

import numpy as np

from question_engines.decision_tree.contracts import (
    ANSWER_OPTIONS, FEATURE_PRESENTATION, GUESS_TEXT, LANGUAGES, RECOMMENDATION_TEXT,
    UNAVAILABLE_TEXT, answer_options, translate,
)
from .policy import CHECKPOINT_SHA256, FEATURE_KEYS, MODEL_VERSION, prepare

_ANSWERS = tuple(option["id"] for option in ANSWER_OPTIONS)


class RLEngine:
    def __init__(self, candidates, *, max_questions=None, language="en"):
        candidates = list(candidates)
        ids = [food["food_id"] for food in candidates]
        if any(type(i) is not int or i <= 0 for i in ids) or len(set(ids)) != len(ids):
            raise ValueError("Each RL candidate needs a distinct positive integer food ID")
        if max_questions is not None and (type(max_questions) is not int or max_questions < 1):
            raise ValueError("max_questions must be a positive integer or None")
        if language not in LANGUAGES:
            raise ValueError("Unsupported session language")
        self.language = language
        self.world = prepare(candidates) if candidates else None
        # The numeric catalogue is shared. A session only retains the presentation
        # and location-filtered offers which belonged to this specific request.
        self._foods = [
            {"food_id": f["food_id"], "name": f["name"], "display_name": f.get("display_name") or f["name"],
             "food_group": f.get("food_group", ""), "offers": [dict(offer) for offer in f.get("offers", [])]}
            for f in candidates
        ]
        self._max_questions = max_questions
        self._answers = np.full(len(FEATURE_KEYS), -1, dtype=np.int8)
        self._rejected = np.zeros(len(ids), dtype=bool)
        self._rng = np.random.default_rng()
        self._rng_history = []
        self._events = []
        self._step = None

    def _choose(self, force=False):
        if self.world is None or self._rejected.all():
            return "unavailable", None
        if len(self._foods)==1:
            return "guess", 0
        q, m, _ = self.world.decide(self._answers, self._rejected, requests=self.requests, offers=sum(e[0] == "feedback" for _,e in self._events), force=force, rng=self._rng)
        if q >= 0 and not force and (self._max_questions is None or self.question_count < self._max_questions):
            return "question", q
        return "guess", m

    @property
    def requests(self):
        return sum(event[0] in ("answer", "feedback") for _,event in self._events)

    @property
    def question_count(self):
        return int((self._answers >= 0).sum())

    @property
    def can_undo(self):
        return bool(self._events)

    @cached_property
    def fingerprint(self):
        # Snapshot identity is computed only when saving/restoring. The HTTP
        # hot path can report can_undo without serializing the whole catalogue.
        identity = [CHECKPOINT_SHA256, self.world.numeric_fingerprint if self.world else None,
                    self._foods, self._max_questions, self.language]
        encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(encoded.encode()).hexdigest()

    def start(self):
        return self.next_step()

    def next_step(self):
        if self._step is None:
            self._step = self._choose()
        kind, index = self._step
        step = {"type": kind, "question_count": self.question_count}
        if kind == "unavailable":
            reason = "candidates_exhausted" if self._foods else "empty_candidates"
            return {**step, "reason": reason, "text": translate(UNAVAILABLE_TEXT, self.language)}
        if kind == "question":
            key = FEATURE_KEYS[index]
            return {**step, "question_id": "q:"+key, "text": translate(FEATURE_PRESENTATION[key][0], self.language),
                    "options": answer_options(self.language)}
        food = copy.deepcopy(self._foods[index])
        step.update(food=food, target_kind="food")
        if kind == "guess":
            return {**step, "guess_id": "food:"+str(food["food_id"]), "text": translate(GUESS_TEXT, self.language)}
        return {**step, "text": translate(RECOMMENDATION_TEXT, self.language)}

    def answer(self, question_id, answer_id):
        step = self.next_step()
        if step["type"] != "question" or question_id != step["question_id"] or answer_id not in _ANSWERS:
            raise ValueError("Invalid answer for the current question")
        self._rng_history.append(copy.deepcopy(self._rng.bit_generator.state))
        self._events.append((self._step, ("answer", question_id, answer_id)))
        self._answers[self._step[1]] = _ANSWERS.index(answer_id)
        self._step = None
        return self.next_step()

    def feedback(self, guess_id, accepted):
        step = self.next_step()
        if step["type"] != "guess" or guess_id != step["guess_id"] or type(accepted) is not bool:
            raise ValueError("Invalid feedback for the current proposal")
        index = self._step[1]
        self._rng_history.append(copy.deepcopy(self._rng.bit_generator.state))
        self._events.append((self._step, ("feedback", guess_id, accepted)))
        if accepted:
            self._step = ("recommendation", index)
        else:
            self._rejected[index] = True
            self._step = None
        return self.next_step()

    def recommend_now(self):
        if self.next_step()["type"] == "question":
            self._rng_history.append(copy.deepcopy(self._rng.bit_generator.state))
            self._events.append((self._step, ("recommend_now",)))
            self._step = self._choose(force=True)
        return self.next_step()

    def undo(self):
        if self._events:
            self._step, event = self._events.pop()
            self._rng.bit_generator.state = self._rng_history.pop()
            index = self._step[1]
            if event[0] == "answer":
                self._answers[index] = -1
            elif event[0] == "feedback" and not event[2]:
                self._rejected[index] = False
        return self.next_step()

    def answered(self):
        return [{"question_id": event[1], "answer_id": event[2], "text": FEATURE_PRESENTATION[FEATURE_KEYS[index]][0]}
                for (_, index), event in self._events if event[0] == "answer"]

    def diagnostics(self):
        return {"engine_version": MODEL_VERSION, "checkpoint_sha256": CHECKPOINT_SHA256,
                "feature_version": "v3", "candidate_count": len(self._foods),
                "proposal_only": self.requests >= 20, "requests": self.requests,
                "question_count": self.question_count, "rejection_count": int(self._rejected.sum())}

    def snapshot(self):
        self.next_step()
        return {"version": 2, "engine_version": MODEL_VERSION, "fingerprint": self.fingerprint,
                "config": {"max_questions": self._max_questions, "language": self.language},
                "events": [[list(step), list(event)] for step, event in self._events],
                "event_rng": copy.deepcopy(self._rng_history),
                "pending": list(self._step), "rng": copy.deepcopy(self._rng.bit_generator.state)}

    def _validate_step(self, step):
        if not isinstance(step,list) or len(step)!=2 or step[0] not in ("question","guess","recommendation","unavailable"):
            raise ValueError("Malformed saved step")
        kind,index=step
        if kind=="unavailable":
            if index is not None or (self._foods and not self._rejected.all()):raise ValueError("Invalid unavailable step")
        elif type(index) is not int or not 0<=index<(len(FEATURE_KEYS) if kind=="question" else len(self._foods)):
            raise ValueError("Invalid saved index")
        elif kind=="question" and (self._answers[index]>=0 or self.requests>=20):
            raise ValueError("Invalid repeated or capped question")
        elif kind!="question" and self._rejected[index]:raise ValueError("Invalid rejected proposal")
        return tuple(step)

    @classmethod
    def from_snapshot(cls, candidates, snapshot):
        if not isinstance(snapshot,dict) or snapshot.get("version")!=2 or snapshot.get("engine_version")!=MODEL_VERSION:
            raise ValueError("Unsupported RL snapshot")
        config=snapshot.get("config")
        if not isinstance(config,dict) or set(config)!={"max_questions","language"}:raise ValueError("Invalid config")
        engine=cls(candidates,**config)
        if snapshot.get("fingerprint")!=engine.fingerprint:raise ValueError("RL snapshot catalogue differs")
        for before,event in snapshot.get("events",[]):
            engine._step=engine._validate_step(before)
            match event:
                case ["answer",qi,ai]:engine.answer(qi,ai)
                case ["feedback",gi,accepted]:engine.feedback(gi,accepted)
                case ["recommend_now"]:engine.recommend_now()
                case _:raise ValueError("Malformed RL snapshot event")
        engine._rng_history=copy.deepcopy(snapshot["event_rng"])
        if len(engine._rng_history)!=len(engine._events):raise ValueError("Invalid RNG history")
        engine._step=engine._validate_step(snapshot.get("pending"))
        engine._rng.bit_generator.state=snapshot["rng"]
        return engine
