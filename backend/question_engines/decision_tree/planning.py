"""Budgeted belief-space planning over questions and menu proposals.

The full posterior is never pruned. Stratified particles approximate planning
only. Search evaluates interaction cost, including rejected guesses, with a
bounded simulated continuation followed by a finite guess-only tail policy.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import random
import time
from numbers import Real

import numpy as np

from .contracts import ANSWER_OPTIONS

POLICY_VERSION = "decision-tree.1.0"


@dataclass(frozen=True)
class PlannerConfig:
    depth: int = 2
    beam: int = 4
    child_beam: int = 1
    guess_beam: int = 1
    particles: int = 96
    outcome_samples: int = 2
    rollout_samples: int = 8
    rollout_steps: int = 16
    node_budget: int = 640
    time_budget_ms: float = 180.0
    question_cost: float = 1.0
    guess_cost: float = 1.0
    miss_cost: float = 3.0
    first_miss_cost: float = 12.0
    guess_confidence_z: float = 1.645
    failure_cost: float = 30.0
    general_intent_mass: float = .35

    def __post_init__(self):
        for field in ("depth", "beam", "child_beam", "guess_beam", "node_budget",
                      "rollout_samples", "rollout_steps"):
            value = getattr(self, field)
            if type(value) is not int or value < 1:
                raise ValueError(f"{field} must be a positive integer")
        if self.depth > 4 or self.beam > 12 or self.child_beam > 6:
            raise ValueError("Planner breadth/depth exceeds the supported interactive budget")
        if type(self.particles) is not int or self.particles < 0:
            raise ValueError("particles must be zero (full belief) or positive")
        if type(self.outcome_samples) is not int or self.outcome_samples < 0:
            raise ValueError("outcome_samples must be zero (exact) or positive")
        for field in ("time_budget_ms", "question_cost", "guess_cost", "miss_cost", "first_miss_cost", "failure_cost", "guess_confidence_z"):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, Real) or not np.isfinite(value) or value <= 0:
                raise ValueError(f"{field} must be finite and positive")
        if isinstance(self.general_intent_mass, bool) or not isinstance(self.general_intent_mass, Real) or not np.isfinite(self.general_intent_mass) or not 0 <= self.general_intent_mass <= 1:
            raise ValueError("general_intent_mass must be in [0,1]")


@dataclass(frozen=True)
class Action:
    kind: str
    index: int


class IntentModel:
    """Distinct intent states: a particular food, or indifference within a menu.

    Response/acceptance constants are explicit uncalibrated model assumptions.
    Identical rules apply to every food and family; no dish-specific stopping.
    """
    def __init__(self, catalog, config=PlannerConfig(), prior_mode="catalog"):
        self.config = config
        self.catalog = catalog
        self.tree = catalog.food_tree
        if not catalog.foods:
            raise ValueError("The intent model requires at least one candidate")
        self.node_ids = tuple(self.tree.proposal_ids)
        self.node_index = {node_id: i for i, node_id in enumerate(self.node_ids)}
        self.names = tuple(self.tree.nodes[node_id].label for node_id in self.node_ids)
        self.alias_ids = np.array([sorted(set(self.names)).index(name) for name in self.names])
        n, m = len(catalog.foods), len(self.node_ids)
        if prior_mode not in {"catalog", "uniform"}:
            raise ValueError("Unknown prior mode")
        base = np.array([f.get("prior_probability", 1 / n) for f in catalog.foods], dtype=float)
        if prior_mode == "uniform":
            base[:] = 1 / n
        base /= base.sum()
        self.intent_to_food = np.zeros((m, n))
        self.members = []
        for i, node_id in enumerate(self.node_ids):
            ids = [self.tree.food_index[fid] for fid in self.tree.descendant_food_ids(node_id)]
            self.members.append(frozenset(ids))
            self.intent_to_food[i, ids] = base[ids] / base[ids].sum()
        self.prior = np.zeros(m)
        for j, food in enumerate(catalog.foods):
            ancestors = [i for i, node_id in enumerate(self.node_ids)
                         if self.tree.nodes[node_id].kind == "family" and j in self.members[i]]
            generic = config.general_intent_mass if ancestors else 0.0
            self.prior[self.node_index[food["id"]]] += base[j] * (1 - generic)
            for i in ancestors:
                self.prior[i] += base[j] * generic / len(ancestors)
        self.prior /= self.prior.sum()
        # Guessing a broad family is less likely to satisfy a specific intent.
        # A specific variant can satisfy a general intent. Disjoint guesses
        # retain small noise, so rejection never makes a hypothesis impossible.
        self.acceptance = np.full((m, m), .005)
        for v in range(m):
            for z in range(m):
                if v == z:
                    self.acceptance[v, z] = .97
                elif self.members[z] <= self.members[v]:
                    self.acceptance[v, z] = .72
                elif self.members[v] <= self.members[z]:
                    self.acceptance[v, z] = .88
        self.questions = [dict(q, kind="attribute") for q in catalog.questions]
        # Named, actionable menu nodes are proposals. A positive response ends
        # the dialogue instead of asking the same menu twice (confirm, guess).
        self.question_index = {q["id"]: i for i, q in enumerate(self.questions)}
        families = sorted({q.get("family", q.get("attribute")) for q in self.questions})
        self.group_names = tuple(families)
        self.groups = np.array([families.index(q.get("family", q.get("attribute")))
                                for q in self.questions])
        self.salience_prior = np.tile([3.0, 1.0, 9.0, 1.0], (len(families), 1))
        if "menu_confirmation" in families:
            self.salience_prior[families.index("menu_confirmation")] = [5.4, .6, 8.5, 1.5]
        self.values = np.zeros((len(self.questions), m))
        self.resolution = np.ones_like(self.values)
        for qi, q in enumerate(self.questions):
            if q["kind"] == "attribute":
                values = np.array([f["attributes"][q["attribute"]] for f in catalog.foods])
                # Team features already represent P(binary yes | food).
                mean = np.einsum("zf,f->z", self.intent_to_food, values)
                variance = np.einsum("zf,f->z", self.intent_to_food, values * values) - mean * mean
                self.values[qi] = mean
                # Variation *inside an indifferent intent* makes this trait
                # less relevant. Uncertainty between specific intents does not.
                self.resolution[qi] = np.clip(1 - 4 * variance, .05, 1)
            else:
                mask = np.zeros(n)
                mask[list(self.members[self.node_index[q["node_id"]]])] = 1
                self.values[qi] = np.einsum("zf,f->z", self.intent_to_food, mask)
        self.options = [dict(option) for option in ANSWER_OPTIONS]
        self.answer_ids = tuple(option["id"] for option in self.options)
        meaning = {"policy": POLICY_VERSION, "catalog": catalog.fingerprint,
                   "config": asdict(config), "prior_mode": prior_mode}
        self.fingerprint = hashlib.sha256(json.dumps(meaning, sort_keys=True).encode()).hexdigest()

    def all_likelihoods(self, salience, support):
        x = self.values[:, support]
        resolution = self.resolution[:, support]
        rows = salience[self.groups]
        r = rows[:, 0] / (rows[:, 0] + rows[:, 1])
        known = rows[:, 2] / (rows[:, 2] + rows[:, 3])
        informative = (known * r)[:, None] * resolution
        positive = np.array([.68, .24, .06, .02])[None, :, None]
        channel = positive * x[:, None, :] + positive[:, ::-1] * (1 - x[:, None, :])
        result = np.empty((len(x), 6, len(support)))
        result[:, [0, 1, 3, 4], :] = informative[:, None, :] * channel
        result[:, 2, :] = known[:, None] * (1 - r[:, None] * resolution)
        result[:, 5, :] = 1 - known[:, None]
        return result

    def likelihood(self, qi, salience, support=None):
        x = self.values[qi] if support is None else self.values[qi, support]
        resolution = self.resolution[qi] if support is None else self.resolution[qi, support]
        alpha, beta, ka, kb = salience[self.groups[qi]]
        relevance, known = alpha / (alpha + beta), ka / (ka + kb)
        informative = known * relevance * resolution
        # Weak agreement is weaker evidence of the same sign, not x=.75/.25.
        positive = np.array([.68, .24, .06, .02])[:, None]
        negative = positive[::-1]
        channel = positive * x + negative * (1 - x)
        result = np.empty((6, len(x)))
        result[[0, 1, 3, 4]] = informative * channel
        result[2] = known * (1 - relevance * resolution)
        result[5] = 1 - known
        return result

    def observe(self, belief, salience, qi, answer, support=None):
        weights = belief * self.likelihood(qi, salience, support)[answer]
        weights = np.where(belief > 0, np.maximum(weights, np.finfo(float).tiny), 0)
        probability = float(weights.sum())
        posterior = weights / probability
        updated = salience.copy()
        group = self.groups[qi]
        if answer == 5:
            updated[group, 3] += 1
        else:
            updated[group, 2] += 1
            if answer == 2:
                alpha, beta = salience[group, :2]
                r = alpha / (alpha + beta)
                resolution = self.resolution[qi] if support is None else self.resolution[qi, support]
                # Responsibility for general indifference vs variation within
                # a broad intent. This is an assumed-density factorization.
                updated[group, 1] += float(np.sum(posterior * (1 - r) / (1 - r * resolution)))
            else:
                updated[group, 0] += 1
        return probability, posterior, updated

    def rejection_aliases(self, proposal_index):
        indices = self.tree.descendants[self.node_ids[proposal_index]]
        descendants = {int(self.alias_ids[self.node_index[self.tree.food_ids[i]]]) for i in indices}
        return descendants | {int(self.alias_ids[proposal_index])}

    def proposal_mask(self, rejected):
        eligible = np.array([int(alias) not in rejected for alias in self.alias_ids])
        for i, node_id in enumerate(self.node_ids):
            if self.tree.nodes[node_id].kind == "family":
                members = self.tree.descendants[node_id]
                eligible[i] &= any(int(self.alias_ids[self.node_index[self.tree.food_ids[j]]]) not in rejected
                                   for j in members)
        return eligible


class SearchBudgetExceeded(Exception):
    pass


class Planner:
    def __init__(self, model, *, clock=time.perf_counter):
        self.model = model
        self.cfg = model.config
        self.clock = clock

    def _check(self):
        self.nodes += 1
        if self.nodes > self.cfg.node_budget or self.clock() >= self.deadline:
            raise SearchBudgetExceeded

    def _proposals(self, belief, rejected):
        probabilities = np.einsum("vz,z->v", self.acceptance[self.candidate_ids], belief)
        valid = self.model.proposal_mask(rejected)[self.candidate_ids] & (probabilities > .005 + 1e-10)
        order = np.argsort(-probabilities, kind="stable")
        order = self.candidate_ids[order[valid[order]]]
        # Avoid saying the same visible name as a family and then as its leaf.
        _, first = np.unique(self.model.alias_ids[order], return_index=True)
        return order[np.sort(first)], probabilities

    def guess_schedule(self, belief, rejected, has_guessed=True):
        """Exact cost of a fixed, acceptance-ranked guess-only continuation.

        It is a feasible baseline policy on the sampled belief, not a zero-cost
        truncation. Each rejected guess changes the surviving intent weights.
        """
        order, _ = self._proposals(belief, rejected)
        if not len(order):
            return self.cfg.failure_cost
        survival = np.cumprod(1 - self.acceptance[order], axis=0)
        after = np.einsum("vz,z->v", survival, belief)
        before = np.r_[1.0, after[:-1]]
        return float(self.cfg.guess_cost * before.sum() + self.cfg.miss_cost * after.sum()
                     + self.cfg.failure_cost * after[-1]
                     + (0 if has_guessed else self.cfg.first_miss_cost * after[0]))

    def _question_order(self, belief, salience, asked):
        likelihood = self.model.all_likelihoods(salience, self.support)
        pa = np.einsum("qaz,z->qa", likelihood, belief)
        ratio = likelihood / pa[:, :, None]
        information = np.einsum("qaz,z->q", likelihood * np.log(np.maximum(ratio, 1e-300)), belief)
        if asked:
            information[list(asked)] = -np.inf
        order = np.argsort(-information, kind="stable")
        return order[np.isfinite(information[order]) & (information[order] > 1e-10)], information

    def rollout(self, belief, salience, asked, rejected, has_guessed):
        """Sample actual responses under an explicit continuation policy.

        The rollout policy asks a high-variance relevant attribute until
        a proposal has 65% predicted acceptance, then proposes it. This cutoff
        belongs only to the feasible baseline; the searched action minimizes
        total interaction cost. Unfinished rollouts use a full guess schedule.
        """
        size = len(self.uniforms)
        beliefs = np.tile(belief, (size, 1))
        saliences = np.tile(salience, (size, 1, 1))
        used = np.zeros((size, len(self.model.questions)), dtype=bool)
        if asked:
            used[:, list(asked)] = True
        excluded = [set(rejected) for _ in range(size)]
        allowed = np.tile(self.model.proposal_mask(rejected)[self.candidate_ids], (size, 1))
        uniforms = np.asarray(self.uniforms)
        targets = np.minimum(np.searchsorted(np.cumsum(belief), uniforms[:, 0], side="right"), len(belief) - 1)
        costs, done = np.zeros(size), np.zeros(size, dtype=bool)
        guessed = np.full(size, has_guessed, dtype=bool)
        values = self.model.values[:, self.support]
        resolution = self.model.resolution[:, self.support]
        for turn in range(self.cfg.rollout_steps):
            if self.clock() >= self.deadline:
                raise SearchBudgetExceeded
            active = np.flatnonzero(~done)
            if not len(active):
                break
            self.rollout_ticks += len(active)
            accept = np.einsum("vp,sp->sv", self.acceptance[self.candidate_ids], beliefs)
            mean = np.einsum("qp,sp->sq", values, beliefs)
            variance = np.maximum(0, np.einsum("qp,sp->sq", values * values, beliefs) - mean * mean)
            rows = saliences[:, self.model.groups]
            relevance = rows[:, :, 0] / (rows[:, :, 0] + rows[:, :, 1])
            known = rows[:, :, 2] / (rows[:, :, 2] + rows[:, :, 3])
            information = variance * relevance * known * np.einsum("qp,sp->sq", resolution, beliefs)
            information[used] = -1
            for scenario in active:
                if not np.any(allowed[scenario]):
                    costs[scenario] += self.cfg.failure_cost
                    done[scenario] = True
                    continue
                local_proposal = int(np.argmax(np.where(allowed[scenario], accept[scenario], -1)))
                proposal = int(self.candidate_ids[local_proposal])
                qi = int(np.argmax(information[scenario]))
                if accept[scenario, local_proposal] >= .65 or information[scenario, qi] <= 1e-10:
                    costs[scenario] += self.cfg.guess_cost
                    if uniforms[scenario, turn + 1] < self.acceptance[proposal, targets[scenario]]:
                        done[scenario] = True
                        continue
                    costs[scenario] += self.cfg.miss_cost + (0 if guessed[scenario] else self.cfg.first_miss_cost)
                    guessed[scenario] = True
                    beliefs[scenario] *= 1 - self.acceptance[proposal]
                    beliefs[scenario] /= beliefs[scenario].sum()
                    aliases = self.model.rejection_aliases(proposal)
                    excluded[scenario].update(aliases)
                    allowed[scenario, np.isin(self.model.alias_ids[self.candidate_ids], list(aliases))] = False
                else:
                    likelihood = self.model.likelihood(qi, saliences[scenario], self.support)
                    answer = min(int(np.searchsorted(np.cumsum(likelihood[:, targets[scenario]]),
                                                    uniforms[scenario, turn + 1], side="right")), 5)
                    _, beliefs[scenario], saliences[scenario] = self.model.observe(
                        beliefs[scenario], saliences[scenario], qi, answer, self.support)
                    used[scenario, qi] = True
                    costs[scenario] += self.cfg.question_cost
        for scenario in np.flatnonzero(~done):
            costs[scenario] += self.guess_schedule(beliefs[scenario], excluded[scenario], bool(guessed[scenario]))
        return costs

    def _actions(self, belief, salience, asked, rejected, root=False):
        order, _ = self._proposals(belief, rejected)
        guesses = [Action("guess", int(i)) for i in order[:self.cfg.guess_beam if root else 1]]
        order, _ = self._question_order(belief, salience, asked)
        beam = self.cfg.beam if root else self.cfg.child_beam
        selected = [int(qi) for qi in order[:beam]]
        return [Action("question", qi) for qi in selected] + guesses

    def _cost(self, action, belief, salience, asked, rejected, depth, has_guessed):
        self._check()
        if action.kind == "guess":
            accept = self.acceptance[action.index]
            rejected_weights = belief * (1 - accept)
            probability = float(rejected_weights.sum())
            excluded = rejected | self.model.rejection_aliases(action.index)
            continuation = self._value(rejected_weights / probability, salience,
                                       asked, excluded, depth - 1, True)
            return self.cfg.guess_cost + probability * (self.cfg.miss_cost + continuation
                + (0 if has_guessed else self.cfg.first_miss_cost))
        total = self.cfg.question_cost
        likelihood = self.model.likelihood(action.index, salience, self.support)
        probabilities = np.einsum("az,z->a", likelihood, belief)
        # Stratified samples of possible answers; exact posterior update in
        # each sampled branch. These are search samples, not invented input.
        if self.cfg.outcome_samples == 0:
            samples, weights = np.arange(6), probabilities
        else:
            positions = (np.arange(self.cfg.outcome_samples) + .5) / self.cfg.outcome_samples
            samples, counts = np.unique(np.searchsorted(np.cumsum(probabilities), positions), return_counts=True)
            weights = counts / self.cfg.outcome_samples
        for answer, weight in zip(samples, weights):
            _, posterior, updated = self.model.observe(
                belief, salience, action.index, answer, self.support)
            total += weight * self._value(posterior, updated,
                                               asked | {action.index}, rejected, depth - 1, has_guessed)
        return total

    def _value(self, belief, salience, asked, rejected, depth, has_guessed):
        self._check()
        if depth <= 0:
            return self.rollout(belief, salience, asked, rejected, has_guessed)
        actions = self._actions(belief, salience, asked, rejected)
        if not actions:
            return np.full(self.cfg.rollout_samples, self.cfg.failure_cost)
        costs = [self._cost(action, belief, salience, asked, rejected, depth, has_guessed)
                 for action in actions]
        return min(costs, key=lambda value: float(np.mean(value)))

    def plan(self, belief, salience, asked, rejected, *, seed=0, force_guess=False, has_guessed=False):
        start = self.clock()
        self.deadline = start + self.cfg.time_budget_ms / 1000
        self.nodes = 0
        self.rollout_ticks = 0
        rng = random.Random(seed)
        self.uniforms = [[(i + .5) / self.cfg.rollout_samples]
                         + [rng.random() for _ in range(self.cfg.rollout_steps)]
                         for i in range(self.cfg.rollout_samples)]
        count = self.cfg.particles
        if count and count < len(belief):
            positions = (np.arange(count) + random.Random(seed).random()) / count
            indices = np.searchsorted(np.cumsum(belief), positions, side="right")
            self.support, counts = np.unique(np.minimum(indices, len(belief) - 1), return_counts=True)
            sampled = counts.astype(float) / count
        else:
            self.support = np.arange(len(belief))
            sampled = belief.copy()
        self.acceptance = self.model.acceptance[:, self.support]
        self.candidate_ids = np.flatnonzero(np.max(self.acceptance, axis=1) > .005)
        # Always have a full-belief safe fallback before spending search budget.
        full_acceptance = np.einsum("vz,z->v", self.model.acceptance, belief)
        valid = self.model.proposal_mask(rejected)
        if not np.any(valid):
            return None, {"policy": POLICY_VERSION, "completed_depth": 0, "nodes": 0}
        fallback = Action("guess", int(np.argmax(np.where(valid, full_acceptance, -1))))
        if force_guess:
            return fallback, {"policy": POLICY_VERSION, "completed_depth": 0, "nodes": 0,
                              "elapsed_ms": (self.clock() - start) * 1000, "forced_by_user_or_experiment": True}
        actions = self._actions(sampled, salience, asked, rejected, root=True)
        if not actions:
            return fallback, {"policy": POLICY_VERSION, "completed_depth": 0, "nodes": 0,
                              "elapsed_ms": (self.clock() - start) * 1000,
                              "fallback_reason": "sampled_actions_exhausted"}
        selected, selected_cost, completed = (actions[0] if actions else fallback), None, 0
        comparison = None
        exhausted = False
        skipped_refinement = False
        iteration_ms = 0.0
        for depth in range(1, self.cfg.depth + 1):
            # Reserve only work likely to finish as a *complete* deeper root
            # comparison. Receding-horizon rollout already looks beyond the
            # optimized depth; spending the deadline on a discarded level adds
            # latency without changing the chosen action.
            if depth > 1:
                branch_factor = self.cfg.child_beam * max(2, self.cfg.outcome_samples) + 2
                if (self.deadline - self.clock()) * 1000 < iteration_ms * branch_factor:
                    skipped_refinement = True
                    break
            iteration_start = self.clock()
            try:
                costs = []
                for i, action in enumerate(actions):
                    samples = self._cost(action, sampled, salience, asked, rejected, depth, has_guessed)
                    costs.append((float(np.mean(samples)), i, action, np.asarray(samples)))
            except SearchBudgetExceeded:
                exhausted = True
                break
            # Commit only complete, equally deep comparisons across root actions.
            best = min(costs, key=lambda item: (item[0], item[1]))
            comparison = None
            questions = [item for item in costs if item[2].kind == "question"]
            if best[2].kind == "guess" and questions:
                question = min(questions, key=lambda item: (item[0], item[1]))
                differences = question[3] - best[3]
                stderr = float(np.std(differences, ddof=1) / np.sqrt(len(differences))) if differences.ndim and len(differences) > 1 else 0.0
                advantage = float(np.mean(differences))
                comparison = {"guess_cost_advantage": advantage, "paired_standard_error": stderr,
                              "accepted_by_error_guard": advantage > self.cfg.guess_confidence_z * stderr}
                if not comparison["accepted_by_error_guard"]:
                    best = question
            selected_cost, _, selected, _ = best
            completed = depth
            iteration_ms = (self.clock() - iteration_start) * 1000
        return selected, {"policy": POLICY_VERSION, "completed_depth": completed,
                          "nodes": self.nodes, "planning_support": len(self.support),
                          "rollout_steps_evaluated": self.rollout_ticks,
                          "expected_interaction_cost": selected_cost,
                          "guess_comparison": comparison,
                          "budget_exhausted": exhausted,
                          "refinement_skipped_for_budget": skipped_refinement,
                          "elapsed_ms": (self.clock() - start) * 1000}
