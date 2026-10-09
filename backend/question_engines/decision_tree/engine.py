# AI-generated: written with OpenAI Codex and reviewed by the team.
"""Public P10 session API. No ORM, HTTP, Android, or model-provider imports."""
import copy
from dataclasses import asdict, dataclass
import hashlib
import json
import math

import numpy as np

from .catalog import CandidateCatalog
from .contracts import ANSWER_OPTIONS
from .planning import IntentModel, Planner, PlannerConfig, POLICY_VERSION


@dataclass(frozen=True)
class EngineConfig:
    policy: str = "greedy"
    max_questions: int | None = None
    greedy_acceptance_threshold: float = .65
    greedy_information_floor: float = .001

    def __post_init__(self):
        if self.policy not in {"lookahead", "greedy"}:
            raise ValueError("policy must be lookahead or greedy")
        if self.max_questions is not None and (type(self.max_questions) is not int or self.max_questions < 1):
            raise ValueError("max_questions must be positive or None")
        for key in ("greedy_acceptance_threshold", "greedy_information_floor"):
            value = getattr(self, key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{key} must be in [0,1]")


class DecisionTreeEngine:
    """start/answer/feedback/recommend_now/undo -> JSON-compatible step.

    A guess may identify a group; its representative is always a real input
    food ID. Accepting it returns that food and its original cafeteria offers.
    Engineering diagnostics are available separately from product steps.
    """
    def __init__(self, candidates, feature_schema=None, *, priors=None, context=None,
                 config=None, planner_config=None):
        self.catalog = (candidates if isinstance(candidates, CandidateCatalog)
                        else CandidateCatalog(candidates, feature_schema or [], priors=priors, context=context))
        if isinstance(candidates, CandidateCatalog) and any(value is not None for value in (feature_schema, priors, context)):
            raise ValueError("A prebuilt catalog already defines schema, priors, and context")
        self.config = config if isinstance(config, EngineConfig) else EngineConfig(**(config or {}))
        self.planner_config = (planner_config if isinstance(planner_config, PlannerConfig)
                               else PlannerConfig(**(planner_config or {})))
        self.model = IntentModel(self.catalog, self.planner_config) if self.catalog.candidates else None
        meaning = {"version": POLICY_VERSION, "catalog": self.catalog.fingerprint,
                   "engine": asdict(self.config), "planner": asdict(self.planner_config)}
        self.fingerprint = hashlib.sha256(json.dumps(meaning, sort_keys=True).encode()).hexdigest()
        self._reset()

    def _reset(self):
        self.belief = self.model.prior.copy() if self.model else np.empty(0)
        self.salience = self.model.salience_prior.copy() if self.model else np.empty((0, 4))
        self._asked, self._rejected = set(), set()
        self._events = []
        self._accepted = None
        self._pending = self._descriptor = None

    @property
    def question_count(self):
        return len(self._asked)

    @property
    def probabilities(self):
        if self.model is None:
            return {}
        values = np.einsum("zf,z->f", self.model.intent_to_food, self.belief)
        return {c.food_id: float(value) for c, value in zip(self.catalog.candidates, values)}

    def _representative(self, node_id):
        if self.model is None or node_id not in self.model.node_index:
            raise ValueError("Unknown menu proposal")
        probabilities = self.probabilities
        eligible = []
        for food_node in self.catalog.food_tree.descendant_food_ids(node_id):
            pi = self.model.node_index[food_node]
            if int(self.model.alias_ids[pi]) not in self._rejected:
                candidate = self.catalog.candidate_for_node(food_node)
                eligible.append(candidate.food_id)
        if not eligible:
            raise ValueError("Proposal has no eligible concrete food")
        return min(eligible, key=lambda food_id: (-probabilities[food_id], food_id))

    def _render(self, descriptor):
        kind = descriptor["kind"]
        common = {"type": kind, "question_count": self.question_count}
        if kind == "unavailable":
            return {**common, "reason": descriptor.get("reason", "candidates_exhausted"),
                    "text": "No available meal matches this session. Try starting again."}
        if self.model is None:
            raise ValueError("No candidates available")
        if kind == "question":
            question_id = descriptor["id"]
            if question_id not in self.model.question_index:
                raise ValueError("Unknown question")
            qi = self.model.question_index[question_id]
            if qi in self._asked or self._accepted is not None:
                raise ValueError("Question was already answered or the session has ended")
            q = self.model.questions[qi]
            return {**common, "question_id": question_id, "text": q["text"],
                    "options": copy.deepcopy(list(ANSWER_OPTIONS))}
        if kind not in {"guess", "recommendation"}:
            raise ValueError("Unknown step type")
        node_id = descriptor["id"]
        if node_id not in self.model.node_index:
            raise ValueError("Unknown menu proposal")
        pi = self.model.node_index[node_id]
        if kind == "guess" and (not self.model.proposal_mask(self._rejected)[pi] or self._accepted is not None):
            raise ValueError("Proposal was rejected or the session has ended")
        if kind == "recommendation" and self._accepted != (node_id, descriptor["food_id"]):
            raise ValueError("Recommendation does not match accepted feedback")
        food_id = descriptor["food_id"]
        member_ids = [int(key.split(":", 1)[1]) for key in self.catalog.food_tree.descendant_food_ids(node_id)]
        if food_id not in member_ids:
            raise ValueError("Representative is outside the proposal")
        if kind == "guess" and int(self.model.alias_ids[self.model.node_index[f"food:{food_id}"]]) in self._rejected:
            raise ValueError("Representative was previously rejected")
        node = self.catalog.food_tree.nodes[node_id]
        result = {**common, "food": self.catalog.by_id[food_id].summary(),
                  "target_kind": "group" if node.kind == "family" else "food",
                  "text": "Is this what you feel like eating?" if kind == "guess" else "Enjoy your meal."}
        if kind == "guess":
            result["guess_id"] = node_id
        if node.kind == "family":
            eligible_members = [member_id for member_id in member_ids
                                if int(self.model.alias_ids[self.model.node_index[f"food:{member_id}"]]) not in self._rejected]
            result["group"] = {"group_id": node_id, "display_name": node.label, "food_ids": eligible_members}
        return result

    def _set_pending(self, descriptor):
        self._pending = self._render(descriptor)
        self._descriptor = copy.deepcopy(descriptor)
        return copy.deepcopy(self._pending)

    def _greedy_action(self):
        acceptance = np.einsum("vz,z->v", self.model.acceptance, self.belief)
        allowed = self.model.proposal_mask(self._rejected)
        if not np.any(allowed):
            return None
        proposal = int(np.argmax(np.where(allowed, acceptance, -1)))
        likelihood = self.model.all_likelihoods(self.salience, np.arange(len(self.belief)))
        answer_mass = np.einsum("qaz,z->qa", likelihood, self.belief)
        information = np.einsum("qaz,z->q", likelihood * np.log2(likelihood / answer_mass[:, :, None]), self.belief)
        if self._asked:
            information[list(self._asked)] = -np.inf
        qi = int(np.argmax(information))
        from .planning import Action
        if acceptance[proposal] >= self.config.greedy_acceptance_threshold or information[qi] <= self.config.greedy_information_floor:
            return Action("guess", proposal)
        return Action("question", qi)

    def start(self):
        return self.next_step()

    def next_step(self):
        if self._pending is not None:
            return copy.deepcopy(self._pending)
        if self._accepted is not None:
            node_id, food_id = self._accepted
            return self._set_pending({"kind": "recommendation", "id": node_id, "food_id": food_id})
        if self.model is None:
            return self._set_pending({"kind": "unavailable", "reason": "empty_candidates"})
        force = self.config.max_questions is not None and self.question_count >= self.config.max_questions
        trace = [(e["type"], e.get("question_id"), e.get("answer_id"), e.get("guess_id")) for e in self._events]
        seed = int(hashlib.sha256(json.dumps(trace).encode()).hexdigest()[:8], 16)
        if self.config.policy == "greedy" and not force:
            action, planning = self._greedy_action(), {"policy": "greedy"}
        else:
            action, planning = Planner(self.model).plan(self.belief, self.salience, self._asked,
                self._rejected, seed=seed, force_guess=force,
                has_guessed=any(e["type"] == "feedback" for e in self._events))
        if action is None:
            descriptor = {"kind": "unavailable", "reason": "candidates_exhausted"}
        elif action.kind == "question":
            descriptor = {"kind": "question", "id": self.model.questions[action.index]["id"]}
        else:
            node_id = self.model.node_ids[action.index]
            descriptor = {"kind": "guess", "id": node_id, "food_id": self._representative(node_id)}
        descriptor["planning"] = planning
        return self._set_pending(descriptor)

    def _transition(self, event):
        """Replay actual displayed actions, without rerunning a timed planner."""
        before = self._render(event["before"])
        kind = event["type"]
        if kind == "answer":
            if before["type"] != "question" or before["question_id"] != event["question_id"]:
                raise ValueError("Answer does not match the recorded question")
            if event["answer_id"] not in self.model.answer_ids:
                raise ValueError("Unknown answer ID")
            qi = self.model.question_index[event["question_id"]]
            _, self.belief, self.salience = self.model.observe(self.belief, self.salience, qi, self.model.answer_ids.index(event["answer_id"]))
            self._asked.add(qi)
        elif kind == "feedback":
            if before["type"] != "guess" or before["guess_id"] != event["guess_id"] or type(event["accepted"]) is not bool:
                raise ValueError("Feedback does not match the recorded guess")
            pi = self.model.node_index[event["guess_id"]]
            acceptance = self.model.acceptance[pi]
            self.belief *= acceptance if event["accepted"] else 1 - acceptance
            self.belief = np.maximum(self.belief, np.finfo(float).tiny)
            self.belief /= self.belief.sum()
            if event["accepted"]:
                self._accepted = (event["guess_id"], before["food"]["food_id"])
            else:
                self._rejected.update(self.model.rejection_aliases(pi))
        elif kind == "recommend_now":
            if before["type"] not in {"question", "guess"}:
                raise ValueError("The session is not active")
            node_id = event["guess_id"]
            if node_id not in self.model.node_index or self._representative(node_id) != event["food_id"]:
                raise ValueError("Invalid immediate recommendation")
        else:
            raise ValueError("Unknown recorded event")
        self._events.append(copy.deepcopy(event))
        self._pending = self._descriptor = None

    def answer(self, question_id, answer_id):
        pending = self.next_step()
        if pending["type"] != "question" or pending["question_id"] != question_id or answer_id not in self.model.answer_ids:
            raise ValueError("Answer must match the current question and a supported answer ID")
        self._transition({"type": "answer", "question_id": question_id, "answer_id": answer_id, "before": self._descriptor})
        return self.next_step()

    def feedback(self, guess_id, accepted):
        pending = self.next_step()
        if pending["type"] != "guess" or pending["guess_id"] != guess_id or type(accepted) is not bool:
            raise ValueError("Feedback must match the current guess and be boolean")
        self._transition({"type": "feedback", "guess_id": guess_id, "accepted": accepted, "before": self._descriptor})
        return self.next_step()

    def recommend_now(self):
        pending = self.next_step()
        if pending["type"] not in {"question", "guess"}:
            raise ValueError("The session is not active")
        probabilities = self.probabilities
        ids = [c.food_id for c in self.catalog.candidates
               if int(self.model.alias_ids[self.model.node_index[f"food:{c.food_id}"]]) not in self._rejected]
        if not ids:
            raise ValueError("No candidate remains")
        food_id = min(ids, key=lambda key: (-probabilities[key], key))
        node_id = f"food:{food_id}"
        self._transition({"type": "recommend_now", "guess_id": node_id, "food_id": food_id, "before": self._descriptor})
        return self._set_pending({"kind": "guess", "id": node_id, "food_id": food_id,
                                  "planning": {"reason": "user_requested"}})

    def diagnostics(self):
        probabilities = list(self.probabilities.values())
        entropy = -math.fsum(p * math.log2(p) for p in probabilities if p > 0)
        return {"engine_version": POLICY_VERSION, "policy": self.config.policy,
                "question_count": self.question_count,
                "guess_count": sum(e["before"]["kind"] == "guess" for e in self._events) + int((self._descriptor or {}).get("kind") == "guess"),
                "feedback_count": sum(e["type"] == "feedback" for e in self._events),
                "entropy_bits": entropy, "posterior": self.probabilities,
                "salience": {name: float(row[0] / row[:2].sum()) for name, row in zip(self.model.group_names, self.salience)} if self.model else {},
                "planning": copy.deepcopy((self._descriptor or {}).get("planning")),
                "probability_interpretation": "uncalibrated_response_model"}

    def snapshot(self):
        self.next_step()
        return {"version": 1, "engine_version": POLICY_VERSION, "fingerprint": self.fingerprint,
                "config": asdict(self.config), "planner_config": asdict(self.planner_config),
                "events": copy.deepcopy(self._events), "pending": copy.deepcopy(self._descriptor)}

    @classmethod
    def from_snapshot(cls, candidates, feature_schema, snapshot, *, priors=None, context=None):
        if not isinstance(snapshot, dict) or snapshot.get("version") != 1 or snapshot.get("engine_version") != POLICY_VERSION:
            raise ValueError("Unsupported snapshot version")
        if (not isinstance(snapshot.get("events"), list) or not isinstance(snapshot.get("pending"), dict)
                or not isinstance(snapshot.get("config"), dict) or not isinstance(snapshot.get("planner_config"), dict)
                or any(not isinstance(event, dict) for event in snapshot["events"])):
            raise ValueError("Malformed snapshot structure")
        engine = cls(candidates, feature_schema, priors=priors, context=context,
                     config=snapshot["config"], planner_config=snapshot["planner_config"])
        if snapshot.get("fingerprint") != engine.fingerprint:
            raise ValueError("Snapshot data, context, prior, or configuration differs")
        for event in snapshot["events"]:
            engine._transition(event)
        engine._set_pending(snapshot["pending"])
        return engine

    def undo(self):
        if not self._events:
            return self.next_step()
        descriptor = copy.deepcopy(self._events[-1]["before"])
        events = copy.deepcopy(self._events[:-1])
        self._reset()
        for event in events:
            self._transition(event)
        return self._set_pending(descriptor)
