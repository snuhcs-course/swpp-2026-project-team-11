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
        self._penalty = np.zeros(len(ids), dtype=np.float64)
        self._events = []
        self._step = None

    def _choose(self, force=False):
        if self.world is None or self._rejected.all():
            return "unavailable", None
        q, m, _ = self.world.decide(self._answers, self._rejected, refusal_sum=self._penalty)
        if q >= 0 and not force and (self._max_questions is None or self.question_count < self._max_questions):
            return "question", q
        return "guess", m

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
        self._events.append((self._step, ("answer", question_id, answer_id)))
        self._answers[self._step[1]] = _ANSWERS.index(answer_id)
        self._step = None
        return self.next_step()

    def feedback(self, guess_id, accepted):
        step = self.next_step()
        if step["type"] != "guess" or guess_id != step["guess_id"] or type(accepted) is not bool:
            raise ValueError("Invalid feedback for the current proposal")
        index = self._step[1]
        self._events.append((self._step, ("feedback", guess_id, accepted)))
        if accepted:
            self._step = ("recommendation", index)
        else:
            self._rejected[index] = True
            self._penalty += self.world.refusal_row(index)
            self._step = None
        return self.next_step()

    def recommend_now(self):
        if self.next_step()["type"] == "question":
            self._events.append((self._step, ("recommend_now",)))
            self._step = self._choose(force=True)
        return self.next_step()

    def undo(self):
        if self._events:
            self._step, event = self._events.pop()
            index = self._step[1]
            if event[0] == "answer":
                self._answers[index] = -1
            elif event[0] == "feedback" and not event[2]:
                self._rejected[index] = False
                self._penalty -= self.world.refusal_row(index)
        return self.next_step()

    def answered(self):
        return [{"question_id": event[1], "answer_id": event[2], "text": FEATURE_PRESENTATION[FEATURE_KEYS[index]][0]}
                for (_, index), event in self._events if event[0] == "answer"]

    def diagnostics(self):
        return {"engine_version": MODEL_VERSION, "checkpoint_sha256": CHECKPOINT_SHA256,
                "feature_version": "v2", "candidate_count": len(self._foods),
                "question_count": self.question_count, "rejection_count": int(self._rejected.sum())}

    def snapshot(self):
        if self._step is None:
            self._step = self._choose()
        return {"version": 1, "engine_version": MODEL_VERSION, "fingerprint": self.fingerprint,
                "config": {"max_questions": self._max_questions, "language": self.language},
                "events": [list(event) for _, event in self._events], "pending": list(self._step)}

    @classmethod
    def from_snapshot(cls, candidates, snapshot):
        if (not isinstance(snapshot, dict) or snapshot.get("version") != 1
                or snapshot.get("engine_version") != MODEL_VERSION or not isinstance(snapshot.get("events"), list)
                or not isinstance(snapshot.get("config"), dict) or set(snapshot["config"]) != {"max_questions", "language"}):
            raise ValueError("Unsupported RL snapshot")
        engine = cls(candidates, **snapshot["config"])
        if snapshot.get("fingerprint") != engine.fingerprint:
            raise ValueError("RL snapshot catalogue or configuration differs")
        engine.start()
        for event in snapshot["events"]:
            match event:
                case ["answer", question_id, answer_id]:
                    engine.answer(question_id, answer_id)
                case ["feedback", guess_id, accepted]:
                    engine.feedback(guess_id, accepted)
                case ["recommend_now"] if engine._step[0] == "question":
                    engine.recommend_now()
                case _:
                    raise ValueError("Malformed RL snapshot event")
        if list(engine._step) != snapshot.get("pending"):
            raise ValueError("RL snapshot pending step differs")
        return engine
