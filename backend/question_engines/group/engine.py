"""Group mode: every member answers the same question each round; the group gets up to two restaurants.

Every member keeps a decision-tree intent belief b_i(f): the probability that menu f is the
one they feel like. S_i(r) = sum_f b_i(f) fit_i(r, f) is i's expected satisfaction at
restaurant r, where fit_i(r, f) is the similarity of f to the closest menu at r that i can
eat. A restaurant is a place, (name, lat, lng): branches of one chain are different restaurants. The group score is the Nash welfare G(r) = sum_i log S_i(r); it chooses the questions
and the first pick, and a second pick is scored differently (see PICKS).
No ORM, HTTP or LLM imports.
"""
from dataclasses import dataclass
from threading import Lock

import numpy as np

from question_engines.decision_tree.catalog import CandidateCatalog
from question_engines.decision_tree.contracts import LANGUAGES, answer_options, translate
from question_engines.decision_tree.planning import IntentModel
from question_engines.decision_tree.preference import PreferencePlanner

FLOOR = 1e-12  # keeps log S_i(r) finite where a member has nothing to eat
MAX_MEMBERS = 8


@dataclass(frozen=True)
class GroupConfig:
    max_rounds: int = 4
    language: str = "en"

    def __post_init__(self):
        if self.language not in LANGUAGES:
            raise ValueError(f"language must be one of {', '.join(LANGUAGES)}")
        if type(self.max_rounds) is not int or self.max_rounds < 1:
            raise ValueError("max_rounds must be a positive integer")


def place(offer):
    """The restaurant of an offer: (name, lat, lng)."""
    return offer["restaurant"], offer.get("lat"), offer.get("lng")


def restaurants(catalog):
    """Restaurants, sorted by name, and which menus each serves: (places, serves[R, F])."""
    places = sorted({place(offer) for c in catalog.candidates for offer in c.offers}, key=lambda p: (p[0], str(p[1:])))
    index = {p: i for i, p in enumerate(places)}
    serves = np.zeros((len(places), len(catalog.candidates)), dtype=bool)
    for f, c in enumerate(catalog.candidates):
        for offer in c.offers:
            serves[index[place(offer)], f] = True
    return places, serves


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


def _closest_similarity(x, eligible):
    table = np.zeros(eligible.shape)
    for r, row in enumerate(eligible):
        if row.any():
            table[r] = np.maximum(1 - np.abs(x[:, None] - x[row]).mean(-1).min(1), FLOOR)
    return table


_FITS, _FITS_LOCK = {}, Lock()  # catalog fingerprint -> read-only fit to every served menu


def fit(catalog, eligible):
    """fit[r, f]: similarity (1 - mean absolute feature difference) of menu f to the closest
    menu at restaurant r with eligible[r] set; 0 where there is none, positive elsewhere.

    The table over every served menu is built once per catalog (the last four are kept);
    only the rows a member's exclusions change are computed again. Read-only.
    """
    _, serves = restaurants(catalog)
    with _FITS_LOCK:
        if catalog.fingerprint not in _FITS:
            _FITS[catalog.fingerprint] = _closest_similarity(features(catalog), serves)
            _FITS[catalog.fingerprint].setflags(write=False)
            while len(_FITS) > 4:
                del _FITS[next(iter(_FITS))]
        table = _FITS[catalog.fingerprint]
    changed = np.flatnonzero((serves != eligible).any(1))
    if changed.size:
        table = table.copy()
        table[changed] = _closest_similarity(features(catalog), eligible[changed])
        table.setflags(write=False)
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
    eligible: np.ndarray  # (R, F): the menus the member can eat at each restaurant
    fit: np.ndarray
    belief: np.ndarray
    salience: np.ndarray
    answers: dict


class GroupEngine:
    """Rounds of one shared question, then up to two restaurants and each member's menu at each.

    `candidates` is a list of menu rows or a prebuilt CandidateCatalog. `excluded` holds,
    per member, the (food ID, restaurant) offers they cannot eat, a restaurant as `place`
    gives it: equivalent menus share a food ID, and one restaurant's may hold an allergen
    another's does not. Members answer in any order; a round ends when all of its
    questions are answered.
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
        self.planner = PreferencePlanner(self.model)
        self.places, self.serves = restaurants(self.catalog)
        self.features = features(self.catalog)
        row = {p: r for r, p in enumerate(self.places)}
        column = {c.food_id: f for f, c in enumerate(self.catalog.candidates)}
        self.members = []
        for offers in excluded:
            eligible = self.serves.copy()
            for food_id, at in offers:
                eligible[row[at], column[food_id]] = False
            if not eligible.any():
                raise ValueError("Every member needs a menu they can eat")
            belief = self.model.prior * eligible.any(0)
            self.members.append(_Member(eligible, fit(self.catalog, eligible), belief / belief.sum(),
                                        self.model.salience_prior.copy(), {}))
        if not (self.satisfaction() > 0).all(0).any():
            raise ValueError("No restaurant has a menu for every member")
        self.round = 0
        self._pending = self._plan() if len(self.places) > 1 else {}

    @property
    def finished(self):
        return not self._pending

    def satisfaction(self):
        """Each member's expected satisfaction at each restaurant: (members, R)."""
        return np.array([m.fit @ m.belief for m in self.members])

    def _logs(self, member):
        """Log S(r) now (R,), after each answer to each question (Q, 6, R), P(answer) (Q, 6),
        and each answer's expected information about the member's intent (Q,)."""
        likelihood = self.model.all_likelihoods(member.salience, np.arange(len(member.belief)))
        weights = likelihood * member.belief
        mass = weights.sum(-1)
        after = (weights @ member.fit.T) / np.maximum(mass, FLOOR)[..., None]
        ratio = likelihood / np.maximum(mass, FLOOR)[..., None]
        information = (weights * np.log(np.maximum(ratio, FLOOR))).sum((1, 2))
        return (np.log(np.maximum(member.fit @ member.belief, FLOOR)), np.log(np.maximum(after, FLOOR)),
                mass, information)

    def _would_ask(self, member):
        """Whether the member's own preference session would ask another question."""
        rejected = {int(self.model.alias_ids[f]) for f in np.flatnonzero(~member.eligible.any(0))}
        action, _ = self.planner.plan(member.belief, member.salience, member.answers, rejected)
        return action is not None and action.kind == "question"

    def _plan(self):
        """The next round's question, the same for every member: {member: question}.

        The question whose answers best improve the group decision, summed over members
        with the others fixed: E_a[max_r G] - max_r E_a[G]. When no answer can change the
        leading restaurant, the most informative question about the members' tastes, as
        long as one member's own session would still ask. {} after `max_rounds`, after every
        question, or then.
        """
        asked = list(self.members[0].answers)
        if self.round >= self.config.max_rounds or len(asked) == len(self.model.questions):
            return {}
        tables = [self._logs(m) for m in self.members]
        total = sum(current for current, _, _, _ in tables)
        gain = sum(np.einsum("qa,qa->q", (total - current + logs).max(-1), mass)
                   - np.einsum("qa,qar->qr", mass, total - current + logs).max(-1)
                   for current, logs, mass, _ in tables)
        gain[asked] = -np.inf
        if gain.max() > 1e-12:
            qi = int(gain.argmax())
        elif any(self._would_ask(m) for m in self.members):
            information = sum(info for _, _, _, info in tables)
            information[asked] = -np.inf
            qi = int(information.argmax())
        else:
            return {}
        return dict.fromkeys(range(len(self.members)), qi)

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
        """Up to two restaurants (PICKS), where they are, and each member's closest menu at each."""
        if not self.finished:
            raise ValueError("The group still has questions to answer")
        return {"type": "recommendation", "rounds": self.round,
                "picks": [{"kind": kind, **dict(zip(("restaurant", "lat", "lng"), self.places[r])),
                           "menus": self._menus_at(r)} for kind, r in picks(self.satisfaction())]}

    def _menus_at(self, r):
        menus = []
        for member in self.members:
            options = np.flatnonzero(member.eligible[r])
            menus.append(self.catalog.candidates[closest(self.features, member.belief, options)].summary()
                         if options.size else None)
        return menus
