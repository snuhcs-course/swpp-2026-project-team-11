"""Group mode: each member answers their own question every round; the group gets one restaurant.

Every member keeps a decision-tree preference state. Member i's fit for restaurant r
is U_i(r), the best preference fit among the menus r serves and i can eat. The group
score is the Nash welfare G(r) = sum_i log(EPSILON + U_i(r)).
No ORM, HTTP or LLM imports.
"""
from dataclasses import dataclass

import numpy as np

from question_engines.decision_tree.catalog import CandidateCatalog
from question_engines.decision_tree.contracts import LANGUAGES, answer_options, translate
from question_engines.decision_tree.planning import IntentModel
from question_engines.decision_tree.preference import ANSWER_STRENGTH, PreferencePlanner

EPSILON = .05
MAX_MEMBERS = 6  # The stop rule enumerates all 6^members joint answers of a round.


@dataclass(frozen=True)
class GroupConfig:
    question_cost: float = .02  # Nash welfare units per member question; uncalibrated
    max_rounds: int = 4
    language: str = "en"

    def __post_init__(self):
        if self.language not in LANGUAGES:
            raise ValueError(f"language must be one of {', '.join(LANGUAGES)}")
        if type(self.max_rounds) is not int or self.max_rounds < 1:
            raise ValueError("max_rounds must be a positive integer")
        if not 0 <= self.question_cost < 1:
            raise ValueError("question_cost must be in [0,1)")


def restaurants(catalog):
    """Restaurant names, sorted, and which menus each serves: (names, serves[R, F])."""
    names = sorted({offer["restaurant"] for c in catalog.candidates for offer in c.offers})
    serves = np.array([[any(o["restaurant"] == name for o in c.offers) for c in catalog.candidates]
                       for name in names], dtype=bool).reshape(len(names), len(catalog.candidates))
    return names, serves


def restaurant_fit(serves, fit):
    """U(r) for fits shaped (..., F): the best fit among each restaurant's menus, 0 when none."""
    return np.where(serves, fit[..., None, :], 0).max(-1)


def welfare(serves, fits):
    """G(r) for member fits shaped (members, F)."""
    return np.log(EPSILON + restaurant_fit(serves, fits)).sum(0)


@dataclass
class _Member:
    allowed: np.ndarray
    belief: np.ndarray
    salience: np.ndarray
    answers: dict


class GroupEngine:
    """Rounds of per-member questions, then one restaurant and each member's menu there.

    `excluded` holds, per member, the food IDs they cannot eat (allergies, bans).
    Members answer in any order; a round ends when all of its questions are answered.
    """
    def __init__(self, candidates, feature_schema, excluded, *, context=None, config=None):
        self.catalog = CandidateCatalog(candidates, feature_schema, context=context)
        self.config = config if isinstance(config, GroupConfig) else GroupConfig(**(config or {}))
        if not 2 <= len(excluded) <= MAX_MEMBERS:
            raise ValueError(f"A group has 2 to {MAX_MEMBERS} members")
        self.model = IntentModel(self.catalog)
        if not self.model.identity_intents:
            raise ValueError("Group mode needs actual sales menus")
        self.preference = PreferencePlanner(self.model)
        self.names, self.serves = restaurants(self.catalog)
        ids = np.array([c.food_id for c in self.catalog.candidates])
        self.members = []
        for banned in excluded:
            allowed = ~np.isin(ids, list(banned))
            if not (allowed & self.serves.any(0)).any():
                raise ValueError("Every member needs a menu they can eat")
            belief = self.model.prior * allowed
            self.members.append(_Member(allowed, belief / belief.sum(),
                                        self.model.salience_prior.copy(), {}))
        self.round = 0
        self._pending = self._plan() if len(self.names) > 1 else {}

    @property
    def finished(self):
        return not self._pending

    def fits(self):
        """Each member's preference fit for every menu, 0 for what they cannot eat: (members, F)."""
        return np.array([np.where(m.allowed, self.preference.fit(m.answers), 0) for m in self.members])

    def _outcomes(self, member):
        """Restaurant fits after each possible answer to each question: (Q, 6, R)."""
        weights = np.array([ANSWER_STRENGTH[a] for a in member.answers.values()])
        total = np.abs(weights).sum() + np.abs(ANSWER_STRENGTH)
        negative = np.minimum(weights, 0).sum() + np.minimum(ANSWER_STRENGTH, 0)
        scores = (self.preference.scores(member.answers)
                  + ANSWER_STRENGTH[None, :, None] * self.preference.values.T[:, None, :])
        fit = np.divide(scores - negative[:, None], total[:, None], out=np.full(scores.shape, .5),
                        where=total[:, None] > 0)
        return restaurant_fit(self.serves, np.where(member.allowed, fit, 0))

    def _choose(self, member, others, total):
        """The question whose answer best improves the group decision, and its outcome table.

        Value of information: E_a[max_r G] - max_r E_a[G]. When no single answer can change
        the leading restaurant, prefer the question that moves the leader's margin most.
        """
        logs = np.log(EPSILON + self._outcomes(member))
        group = others + logs
        mass = self.model.all_likelihoods(member.salience, np.arange(len(member.belief))) @ member.belief
        gain = (np.einsum("qa,qa->q", group.max(-1), mass)
                - np.einsum("qa,qar->qr", mass, group).max(-1))
        leader = int(total.argmax())
        margin = group[..., leader] - np.delete(group, leader, -1).max(-1)
        moved = np.einsum("qa,qa->q", mass, np.abs(margin - (total[leader] - np.delete(total, leader).max())))
        order = [int(q) for q in np.lexsort((-moved, -gain.round(12))) if q not in member.answers]
        return (order[0], mass[order[0]], logs[order[0]]) if order else None

    def _plan(self):
        """The next round's questions by member, or {} when another round is not worth it."""
        if self.round >= self.config.max_rounds:
            return {}
        current = np.log(EPSILON + restaurant_fit(self.serves, self.fits()))
        total = current.sum(0)
        questions, joint, probability = {}, np.zeros((1, len(self.names))), np.ones(1)
        for i, member in enumerate(self.members):
            choice = self._choose(member, total - current[i], total)
            if choice is None:
                mass, logs = np.ones(1), current[i][None]
            else:
                questions[i], mass, logs = choice
            joint = (joint[:, None] + logs[None]).reshape(-1, len(self.names))
            probability = (probability[:, None] * mass[None]).reshape(-1)
        value = probability @ joint.max(-1) - (probability @ joint).max()
        if self.round and value <= self.config.question_cost * len(questions):
            return {}
        return questions

    def questions(self):
        """The current round's unanswered question steps, by member index."""
        language = self.config.language
        steps = {}
        for i, qi in self._pending.items():
            q = self.model.questions[qi]
            steps[i] = {"type": "question", "round": self.round, "question_id": q["id"],
                        "text": translate(q["text"], language), "options": answer_options(language)}
        return steps

    def answer(self, member, question_id, answer_id):
        qi = self._pending.get(member)
        if qi is None or self.model.questions[qi]["id"] != question_id or answer_id not in self.model.answer_ids:
            raise ValueError("Answer must match the member's current question and a supported answer ID")
        m = self.members[member]
        ai = self.model.answer_ids.index(answer_id)
        _, m.belief, m.salience = self.model.observe(m.belief, m.salience, qi, ai)
        m.answers[qi] = ai
        del self._pending[member]
        if not self._pending:
            self.round += 1
            self._pending = self._plan()

    def recommendation(self):
        """The restaurant with the highest Nash welfare and each member's best menu there."""
        if not self.finished:
            raise ValueError("The group still has questions to answer")
        fits = self.fits()
        r = int(welfare(self.serves, fits).argmax())
        menus = []
        for i, member in enumerate(self.members):
            options = self.serves[r] & member.allowed
            best = int(np.argmax(np.where(options, fits[i], -1)))
            menus.append(self.catalog.candidates[best].summary() if options.any() else None)
        return {"type": "recommendation", "rounds": self.round, "restaurant": self.names[r], "menus": menus}
