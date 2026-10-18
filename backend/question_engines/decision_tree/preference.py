# AI-generated: written with Codex (OpenAI) and reviewed by the team.
"""Decision-value planning with explicit, signed feature preferences.

Food-intent belief forecasts answers; it is not a satisfaction probability.
Each question compares choosing before versus after revealing that preference.
This is a local EVSI approximation, not a learned joint preference model.
"""
import numpy as np

from .planning import Action

ANSWER_STRENGTH = np.array([1., .5, 0., -.5, -1., 0.])


class PreferencePlanner:
    def __init__(self, model, question_cost=.06, beam=4):
        self.model = model
        self.cost = question_cost
        self.beam = beam
        self.food_nodes = np.array([model.node_index[f["id"]] for f in model.catalog.foods])
        # The same recipe-variation attenuation used by the response forecast.
        self.values = model.values[:, self.food_nodes].T

    def scores(self, answers):
        weights = np.zeros(len(self.model.questions))
        for qi, ai in answers.items():
            weights[qi] = ANSWER_STRENGTH[ai]
        return self.values @ weights

    def fit(self, answers):
        weights = np.array([ANSWER_STRENGTH[ai] for ai in answers.values()])
        total = np.abs(weights).sum()
        if total == 0:
            return np.full(len(self.values), .5)
        return (self.scores(answers) - np.minimum(weights, 0).sum()) / total

    def _values(self, scores, belief, salience, asked, allowed):
        likelihood = self.model.all_likelihoods(salience, np.arange(len(belief)))
        mass = likelihood @ belief
        future = scores[None, None, :] + (
            ANSWER_STRENGTH[None, :, None] * self.values.T[:, None, :]
        )
        # Compare decisions on the same utility scale, including the expected
        # contribution of this as-yet unanswered feature on BOTH sides.
        choose_after = np.einsum("qa,qa->q", future[:, :, allowed].max(axis=2), mass)
        choose_before = np.einsum("qaf,qa->qf", future, mass)[:, allowed].max(axis=1)
        gains = np.maximum(0, choose_after - choose_before)
        gains[list(asked)] = -np.inf
        return gains, mass, future

    def plan(self, belief, salience, answers, rejected, *, force_guess=False):
        allowed = self.model.proposal_mask(rejected)[self.food_nodes]
        if not allowed.any():
            return None, {"policy": "preference", "reason": "candidates_exhausted"}
        scores = self.scores(answers)
        food_belief = self.model.intent_to_food.T @ belief
        order = np.lexsort((np.arange(len(scores)), -food_belief, -scores))
        best = next(int(i) for i in order if allowed[i])
        proposal = Action("guess", int(self.food_nodes[best]))
        diagnostics = {"policy": "preference", "question_cost": self.cost,
                       "recommendation_fit": float(self.fit(answers)[best]),
                       "lookahead_used": False}
        if force_guess:
            return proposal, diagnostics | {"reason": "explicit_question_limit"}
        asked = set(answers)
        gains, mass, future = self._values(scores, belief, salience, asked, allowed)
        qi = int(np.argmax(gains))
        finite = np.isfinite(gains[qi])
        gain = float(gains[qi]) if finite else 0.
        diagnostics["best_question_gain"] = gain
        diagnostics["best_question_id"] = self.model.questions[qi]["id"] if finite else None
        if finite and gain > self.cost + 1e-12:
            return Action("question", qi), diagnostics | {"reason": "positive_decision_value"}
        # Before stopping, allow a first question to unlock a valuable second.
        # Integrate all six answers, with no sampled outcomes or time cutoffs.
        best_net, best_qi = 0., None
        for first in np.argsort(-gains, kind="stable")[:self.beam]:
            if not np.isfinite(gains[first]):
                continue
            continuation = 0.
            for ai, probability in enumerate(mass[first]):
                if probability <= 1e-12:
                    continue
                _, posterior, updated = self.model.observe(belief, salience, int(first), ai)
                child, _, _ = self._values(
                    future[first, ai], posterior, updated, asked | {int(first)}, allowed)
                continuation += probability * max(0., float(child.max()) - self.cost)
            net = float(gains[first]) - self.cost + continuation
            if net > best_net + 1e-12:
                best_net, best_qi = net, int(first)
        if best_qi is not None:
            return Action("question", best_qi), diagnostics | {
                "reason": "positive_two_question_value", "lookahead_used": True,
                "two_question_net_value": best_net,
                "best_question_id": self.model.questions[best_qi]["id"],
                "best_question_gain": float(gains[best_qi]),
            }
        return proposal, diagnostics | {"reason": "question_cost_exceeds_value"}
