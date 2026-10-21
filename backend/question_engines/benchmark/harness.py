# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""Play one session: an engine against a simulated (or real) user, step by step.

The engines are built as the app builds them (recommend/sessions.py): the
server's question limit, the decision tree's policy (RECOMMEND_DT_POLICY) and the
menu's feature version. Time is measured around engine calls only, so the user's
thinking (or the simulator's LLM call) is never counted as latency. The LLM
engine's calls, tokens and cost (as OpenRouter reports it) come from its own
diagnostics.

A proposal is accepted when it is a wanted menu or a kind of it (accepted_by_rule).
Otherwise the simulated user decides whether they would take it anyway, except for
a close alternative, where only the wanted menu counts. `first_guess_exact` keeps
the strict view: the first proposal was a wanted menu by the rule.

Everything needed to tell later what went wrong is recorded: each question with the
answer the engine got, the simulated user's raw answer and whether it was blurred;
each proposal with its verdict and how it was reached (judged_by: rule, simulator,
rule_only for a close alternative, person); at each decision-tree step its state
(top candidates, entropy, why it asked or proposed); and each LLM engine call
(latency, attempts, fallback reason, tokens, cost).

A session ends when a proposal is accepted, after MAX_REJECTIONS rejected
proposals ("gave_up"), when the engine has nothing left ("unavailable"), or on an
engine error. At each question count in `anytime`, a copy of the session is
restored from a snapshot and asked to "recommend now": how good would the
proposal have been if the user had stopped answering there? At 0 questions that is
the no-question baseline. The copy's LLM use is counted apart from the session's.
"""

from __future__ import annotations

import time

from django.conf import settings

from menus.services import get_feature_schema
from question_engines.decision_tree import DecisionTreeEngine
from question_engines.llm import LLMEngine

from .scenarios import is_wanted
from .simulator import blur, describe

MAX_REJECTIONS = 5
MAX_STEPS = 100  # a safety bound on one session's steps, not a product limit
ANYTIME = (0, 2, 4)  # question counts for "recommend now"; 0 is the no-question baseline
TOP_CANDIDATES = 5  # decision-tree candidates kept per step in the trace


def accepted_by_rule(scenario, step) -> bool:
    """A proposal is fine when everything it offers is a wanted menu or a kind of one."""
    return is_wanted(scenario, step["food"]["food_id"], (step.get("group") or {}).get("food_ids"))


def proposal_text(step, key="display_name") -> str:
    """How a proposal reads. key="name" drops the set marker ("떡볶이 (세트)" -> "떡볶이"): the
    simulated user judges a dish once, whether it comes as a set or alone."""
    food = step["food"][key]
    if step.get("group"):
        return f"a kind of dish, {step['group']['display_name']} (for example {food})"
    return food


class EngineFactory:
    """Builds and restores engines for one menu, as the app would."""

    def __init__(self, engine, menu, llm=None):
        self.engine, self.menu, self.llm = engine, menu, llm
        self.config = {"max_questions": settings.RECOMMEND_MAX_QUESTIONS}
        self.schema = get_feature_schema(menu["feature_version"])
        self.context = {"date": menu["date"], "meal": menu["meal"], "feature_version": menu["feature_version"]}

    def build(self):
        if self.engine == "decision_tree":
            return DecisionTreeEngine(self.menu["candidates"], self.schema, context=self.context,
                                      config=self.config | {"policy": settings.RECOMMEND_DT_POLICY})
        return LLMEngine(self.menu["candidates"], llm=self.llm, config=self.config)

    def restore(self, snapshot):
        if self.engine == "decision_tree":
            return DecisionTreeEngine.from_snapshot(self.menu["candidates"], self.schema, snapshot,
                                                    context=self.context)
        return LLMEngine.from_snapshot(self.menu["candidates"], snapshot, llm=self.llm)


class Clock:
    def __init__(self):
        self.steps = []

    def __call__(self, function, *args):
        start = time.perf_counter()
        try:
            return function(*args)
        finally:
            self.steps.append(round((time.perf_counter() - start) * 1000, 2))


def llm_use(engines) -> dict:
    """The LLM calls, tokens and cost of LLM engines, from their diagnostics."""
    calls = [call for engine in engines for call in engine.diagnostics()["llm_calls"]]
    return {"calls": len(calls), "input_tokens": sum(call["input_tokens"] for call in calls),
            "output_tokens": sum(call["output_tokens"] for call in calls),
            "cost_usd": round(sum(call["cost_usd"] for call in calls), 6),
            "fallbacks": sum(call["fallback"] is not None for call in calls)}


def explain(engine) -> dict | None:
    """The decision tree's state behind its current step: top candidates, entropy, planning."""
    if not isinstance(engine, DecisionTreeEngine):
        return None
    state = engine.diagnostics()
    top = sorted(state["posterior"].items(), key=lambda item: -item[1])[:TOP_CANDIDATES]
    planning = state["planning"]
    return {"top": [[int(food_id), round(p, 4)] for food_id, p in top], "entropy_bits": round(state["entropy_bits"], 3),
            "planning": {key: planning.get(key) for key in ("reason", "best_question_id", "best_question_gain")}}


def play(factory, scenario, user, repeat=0, anytime=ANYTIME) -> dict:
    """Run one session. `user` answers questions ({"answer", ...}) and judges proposals
    ({"accepted", "judged_by"}): SimulatedUser, HumanUser."""
    record = {"scenario": scenario["id"], "situation": scenario["situation"], "certainty": scenario["certainty"],
              "menu": scenario["menu"], "engine": factory.engine, "repeat": repeat, "outcome": None,
              "final_food_id": None, "first_guess_accepted": None, "first_guess_exact": None,
              "questions": 0, "guesses": 0,
              "trace": [], "anytime": {}, "error": None}
    clock, engine, branches = Clock(), None, []
    try:
        engine = clock(factory.build)
        step = clock(engine.start)
        pending = set(anytime)
        for _ in range(MAX_STEPS):
            if step["type"] == "question" and step["question_count"] in pending:
                pending.discard(step["question_count"])
                record["anytime"][str(step["question_count"])] = _recommend_now(factory, engine, branches)
            if step["type"] == "question":
                reply = user.answer(step, repeat)
                record["trace"].append({"question": step["text"], **reply, "state": explain(engine)})
                step = clock(engine.answer, step["question_id"], reply["answer"])
            elif step["type"] == "guess":
                verdict = user.judge(step)
                accepted = verdict["accepted"]
                record["guesses"] += 1
                if record["first_guess_accepted"] is None:
                    record["first_guess_accepted"] = accepted
                    if scenario["situation"] != "not_in_menu":
                        record["first_guess_exact"] = accepted_by_rule(scenario, step)
                record["trace"].append({"proposal": step["food"]["food_id"],
                                        "group": (step.get("group") or {}).get("food_ids"),
                                        "label": proposal_text(step, "name"), **verdict,
                                        "state": explain(engine)})
                step = clock(engine.feedback, step["guess_id"], accepted)
                if not accepted and record["guesses"] >= MAX_REJECTIONS:
                    record["outcome"] = "gave_up"
                    break
            elif step["type"] == "recommendation":
                record["outcome"], record["final_food_id"] = "accepted", step["food"]["food_id"]
                break
            else:
                record["outcome"] = "unavailable"
                break
        else:
            record["outcome"] = "step_limit"
        record["questions"] = engine.question_count
    except Exception as error:  # an engine bug must not stop a 500-session run
        record["outcome"], record["error"] = "error", f"{type(error).__name__}: {error}"[:300]
    record["engine_ms"] = round(sum(clock.steps), 2)
    record["step_ms"] = clock.steps
    is_llm = factory.engine == "llm" and engine is not None
    record["llm"] = llm_use([engine]) if is_llm else None
    record["llm_calls"] = engine.diagnostics()["llm_calls"] if is_llm else None
    record["anytime_llm"] = llm_use(branches) if is_llm else None
    return record


def _recommend_now(factory, engine, branches):
    branch = factory.restore(engine.snapshot())
    branches.append(branch)
    step = branch.recommend_now()
    if step["type"] not in ("guess", "recommendation"):
        return None
    return {"food_id": step["food"]["food_id"], "group": (step.get("group") or {}).get("food_ids")}


class SimulatedUser:
    """Answers with the simulator and blurs answers by the scenario's certainty."""

    def __init__(self, scenario, simulator):
        self.scenario, self.simulator = scenario, simulator
        self.persona = describe(scenario)

    def answer(self, step, repeat):
        raw = self.simulator.answer(self.persona, step["text"])
        given = blur(raw, self.scenario["certainty"], self.scenario["id"], step["text"], repeat)
        return {"answer": given, "raw": raw, "blurred": given != raw}

    def judge(self, step):
        if accepted_by_rule(self.scenario, step):
            return {"accepted": True, "judged_by": "rule"}
        if self.scenario["situation"] == "close_alternative":
            return {"accepted": False, "judged_by": "rule_only"}
        taken = self.simulator.takes(self.persona, proposal_text(step, "name"),
                                     served=self.scenario["situation"] != "not_in_menu")
        return {"accepted": taken, "judged_by": "simulator"}
