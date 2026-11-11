"""Group mode: each member answers their own question every round; the group gets up to two restaurants.

Every member keeps a decision-tree intent belief b_i(f): the probability that menu f is the
one they feel like. S_i(r) = sum_f b_i(f) fit_i(r, f) is i's expected satisfaction at
restaurant r, where fit_i(r, f) is the similarity of f to the closest menu at r that i can
eat. The group score is the Nash welfare G(r) = sum_i log S_i(r). It chooses the
questions; the result adds a restaurant scored differently (see PICKS).
No ORM, HTTP or LLM imports.
"""
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from question_engines.decision_tree.catalog import CandidateCatalog
from question_engines.decision_tree.contracts import LANGUAGES, answer_options, translate
from question_engines.decision_tree.planning import IntentModel

FLOOR = 1e-12  # log S_i(r) of a restaurant with nothing the member can eat
MAX_MEMBERS = 8
JOINT_LIMIT = 6 ** 5  # the stop rule enumerates this many joint answers of a round, then samples


@dataclass(frozen=True)
class GroupConfig:
    question_cost: float = .0005  # log-satisfaction per member question (README, dev check)
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
    index = {name: i for i, name in enumerate(names)}
    serves = np.zeros((len(names), len(catalog.candidates)), dtype=bool)
    for f, c in enumerate(catalog.candidates):
        for offer in c.offers:
            serves[index[offer["restaurant"]], f] = True
    return names, serves


def features(catalog):
    """Menu feature vectors in the catalog's order: (F, keys)."""
    return np.array([[c.features[key] for key in catalog.feature_keys] for c in catalog.candidates])


def closest(features, belief, options):
    """The menu among `options` closest, in expectation over `belief`, to the one wanted.

    Closeness is 1 - mean absolute feature difference. The likeliest menu is a poor choice
    while the belief is still spread over many similar menus.
    """
    distance = [np.abs(features - features[g]).mean(-1) @ belief for g in options]
    return int(options[int(np.argmin(distance))])


@lru_cache(maxsize=16)
def fit(catalog, banned):
    """fit[r, f]: similarity (1 - mean absolute feature difference) of menu f to the closest
    menu restaurant r serves that is not in `banned`; 0 where there is none, positive elsewhere."""
    ids = [c.food_id for c in catalog.candidates]
    x = features(catalog)
    _, serves = restaurants(catalog)
    table = np.zeros(serves.shape)
    for r, row in enumerate(serves & ~np.isin(ids, list(banned))):
        if row.any():
            table[r] = np.maximum(1 - np.abs(x[:, None] - x[row]).mean(-1).min(1), FLOOR)
    return table


# Recommendation kinds, in order; each is a restaurant the earlier kinds did not pick and
# where every member has a menu. A kind with no such restaurant left is omitted.
PICKS = (
    "balanced",        # highest Nash welfare sum_i log S_i(r)
    "no_one_unhappy",  # highest min_i S_i(r): the least satisfied member is best served
)


def picks(satisfaction):
    """[(kind, restaurant index)] for expected satisfactions S shaped (members, R); S is 0
    exactly where a member has nothing to eat."""
    servable = (satisfaction > 0).all(0)
    scores = (np.log(np.maximum(satisfaction, FLOOR)).sum(0), satisfaction.min(0))
    chosen = []
    for score in scores:
        rest = [int(r) for r in np.argsort(-score, kind="stable") if servable[r] and r not in chosen]
        chosen += rest[:1]
    return list(zip(PICKS, chosen))


@dataclass
class _Member:
    allowed: np.ndarray
    fit: np.ndarray
    belief: np.ndarray
    salience: np.ndarray
    answers: dict


class GroupEngine:
    """Rounds of per-member questions, then up to two restaurants and each member's menu at each.

    `candidates` is a list of menu rows or a prebuilt CandidateCatalog. `excluded` holds,
    per member, the food IDs they cannot eat (allergies, bans). Members answer in any
    order; a round ends when all of its questions are answered.
    """
    def __init__(self, candidates, feature_schema, excluded, *, context=None, config=None):
        self.catalog = (candidates if isinstance(candidates, CandidateCatalog)
                        else CandidateCatalog(candidates, feature_schema, context=context))
        self.config = config if isinstance(config, GroupConfig) else GroupConfig(**(config or {}))
        if not 2 <= len(excluded) <= MAX_MEMBERS:
            raise ValueError(f"A group has 2 to {MAX_MEMBERS} members")
        self.model = IntentModel(self.catalog)
        if not self.model.identity_intents:
            raise ValueError("Group mode needs actual sales menus")
        self.names, self.serves = restaurants(self.catalog)
        self.features = features(self.catalog)
        ids = np.array([c.food_id for c in self.catalog.candidates])
        self.members = []
        for banned in excluded:
            allowed = ~np.isin(ids, list(banned)) & self.serves.any(0)
            if not allowed.any():
                raise ValueError("Every member needs a menu they can eat")
            belief = self.model.prior * allowed
            self.members.append(_Member(allowed, fit(self.catalog, frozenset(banned)), belief / belief.sum(),
                                        self.model.salience_prior.copy(), {}))
        if not (self.satisfaction() > 0).all(0).any():
            raise ValueError("No restaurant has a menu for every member")
        self.round = 0
        self._pending = self._plan() if len(self.names) > 1 else {}

    @property
    def finished(self):
        return not self._pending

    def satisfaction(self):
        """Each member's expected satisfaction at each restaurant: (members, R)."""
        return np.array([m.fit @ m.belief for m in self.members])

    def _logs(self, member):
        """Log S(r) now (R,), after each answer to each question (Q, 6, R), and P(answer) (Q, 6)."""
        likelihood = self.model.all_likelihoods(member.salience, np.arange(len(member.belief)))
        weights = likelihood * member.belief
        mass = weights.sum(-1)
        after = (weights @ member.fit.T) / np.maximum(mass, FLOOR)[..., None]
        return np.log(np.maximum(member.fit @ member.belief, FLOOR)), np.log(np.maximum(after, FLOOR)), mass

    def _choose(self, member, others, total, logs, mass):
        """The question whose answer best improves the group decision.

        Value of information: E_a[max_r G] - max_r E_a[G]. When no single answer can change
        the leading restaurant, prefer the question that moves the leader's margin most.
        """
        group = others + logs
        gain = (np.einsum("qa,qa->q", group.max(-1), mass)
                - np.einsum("qa,qar->qr", mass, group).max(-1))
        leader = int(total.argmax())
        margin = group[..., leader] - np.delete(group, leader, -1).max(-1)
        moved = np.einsum("qa,qa->q", mass, np.abs(margin - (total[leader] - np.delete(total, leader).max())))
        order = [int(q) for q in np.lexsort((-moved, -gain.round(12))) if q not in member.answers]
        return order[0] if order else None

    def _plan(self):
        """The next round's questions by member, or {} when another round is not worth it."""
        if self.round >= self.config.max_rounds:
            return {}
        tables = [self._logs(m) for m in self.members]
        total = sum(current for current, _, _ in tables)
        questions, joint, probability = {}, np.zeros((1, len(self.names))), np.ones(1)
        rng = np.random.default_rng(self.round)
        for i, (member, (current, logs, mass)) in enumerate(zip(self.members, tables)):
            qi = self._choose(member, total - current, total, logs, mass)
            if qi is None:
                outcomes, chances = current[None], np.ones(1)
            else:
                questions[i], outcomes, chances = qi, logs[qi], mass[qi]
            joint = (joint[:, None] + outcomes[None]).reshape(-1, len(self.names))
            probability = (probability[:, None] * chances[None]).reshape(-1)
            if len(probability) > JOINT_LIMIT:
                rows = rng.choice(len(probability), JOINT_LIMIT, p=probability / probability.sum())
                joint, probability = joint[rows], np.full(JOINT_LIMIT, 1 / JOINT_LIMIT)
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
        """Up to two restaurants (PICKS) and each member's closest menu at each."""
        if not self.finished:
            raise ValueError("The group still has questions to answer")
        return {"type": "recommendation", "rounds": self.round,
                "picks": [{"kind": kind, "restaurant": self.names[r], "menus": self._menus_at(r)}
                          for kind, r in picks(self.satisfaction())]}

    def _menus_at(self, r):
        menus = []
        for member in self.members:
            options = np.flatnonzero(self.serves[r] & member.allowed)
            menus.append(self.catalog.candidates[closest(self.features, member.belief, options)].summary()
                         if options.size else None)
        return menus
