"""Synthetic benchmark for the LLM engine: a second LLM plays a user craving one menu.

Every trial draws its target menu with a fixed seed, so two prompt versions are
compared on the same targets. Per trial it records whether the engine found the
target, how many questions and guesses that took, and, with a judge LLM, which
questions were repeated or already answered. Use a different model family for the
user and the judge than for the engine, so the engine is not graded by itself.
Judges disagree on borderline cases; without one, read the transcripts in the report.

This measures question quality on synthetic users, not human acceptance.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import inspect
import random
import statistics
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, create_model

from question_engines.decision_tree.contracts import ANSWER_OPTIONS

from . import prompt
from .engine import ENGINE_VERSION, LLMEngine

ANSWER_IDS = tuple(option["id"] for option in ANSWER_OPTIONS)

USER_PROMPT = """You are a student at Seoul National University choosing a meal at the campus
cafeterias. Today you are craving exactly this menu: {target}

Answer the app's question as this student, judging only from that menu:
- yes / no: the question clearly fits / clearly does not fit the menu.
- probably_yes / probably_no: it likely fits / likely does not.
- any: the menu could go either way, so you have no preference.
- unknown: you cannot tell from the menu name."""

JUDGE_PROMPT = """A food recommendation app asked one user the numbered yes/no questions below,
in order, with the user's answers. Find every question whose answer was already known:
- same_topic: it asks the same thing as an earlier question, in other words
  (e.g. "Do you feel like noodles?" after "Are you in the mood for a noodle dish?",
  "A double burger?" after "A double patty burger?").
- implied: its answer follows from earlier answers
  (e.g. "Do you want ramen?" after no to noodles, "A stew?" after no to broth).
These are NOT wasted:
- a narrower question after yes or probably yes to the broader one
  (e.g. "Spicy noodles?" or "Jjamppong?" after yes to noodles);
- a different attribute of the same kind of dish (e.g. "Cheese?" after "A burger?").
Report each wasted question once, with the earlier question that already settled it."""


class UserAnswer(BaseModel):
    answer: Literal[ANSWER_IDS]


class WastedQuestion(BaseModel):
    question: int = Field(description="Number of the wasted question.")
    earlier: int = Field(description="Number of the earlier question it repeats.")
    kind: Literal["same_topic", "implied"]


class JudgeVerdict(BaseModel):
    wasted: list[WastedQuestion]


def same_menu(a, b):
    return a.strip().casefold() == b.strip().casefold()


def ask_user(user_llm, target, question):
    structured = user_llm.with_structured_output(UserAnswer)
    try:
        return structured.invoke([SystemMessage(content=USER_PROMPT.format(target=target)),
                                  HumanMessage(content=question)]).answer
    except Exception:  # an unanswerable call should not end the trial
        return "unknown"


def judge_questions(judge_llm, history, votes=3):
    """[(question, answer id)] -> wasted questions as dicts, 1-based numbers.

    The judge runs `votes` times; a question counts when most runs flag it.
    """
    if len(history) < 2:
        return []
    labels = {option["id"]: option["label"] for option in ANSWER_OPTIONS}
    listing = "\n".join(f"{i}. {question} -> {labels[answer]}"
                        for i, (question, answer) in enumerate(history, start=1))
    judge = judge_llm.with_structured_output(JudgeVerdict)
    flagged = {}
    for _ in range(votes):
        verdict = judge.invoke([SystemMessage(content=JUDGE_PROMPT), HumanMessage(content=listing)])
        for item in {item.question: item for item in verdict.wasted}.values():
            if 1 <= item.earlier < item.question <= len(history):
                flagged.setdefault(item.question, []).append(item)
    return [items[0].model_dump() for number, items in sorted(flagged.items()) if len(items) * 2 > votes]


# Without a question limit the LLM decides when to guess; a trial stops here regardless.
QUESTION_CAP = 20


def run_trial(candidates, target, engine_llm, user_llm, judge_llm, *, max_questions, max_guesses):
    engine = LLMEngine(candidates, llm=engine_llm, config={"max_questions": max_questions})
    step, events, history, found = engine.start(), [], [], False
    while step["type"] in ("question", "guess"):
        if step["type"] == "question":
            if len(history) >= QUESTION_CAP:
                break
            answer = ask_user(user_llm, target, step["text"])
            history.append((step["text"], answer))
            events.append({"question": step["text"], "answer": answer})
            step = engine.answer(step["question_id"], answer)
            continue
        found = same_menu(step["food"]["display_name"], target)
        events.append({"guess": step["food"]["display_name"], "hit": found})
        guesses = sum("guess" in event for event in events)
        if found or guesses >= max_guesses:
            break
        step = engine.feedback(step["guess_id"], False)
    diagnostics = engine.diagnostics()
    return {"target": target, "found": found, "questions": len(history),
            "guesses": sum("guess" in event for event in events),
            "wasted": judge_questions(judge_llm, history) if judge_llm else None, "events": events,
            "fallbacks": diagnostics["fallback_count"], "cost_usd": diagnostics["llm_cost_usd"],
            "latency_ms": diagnostics["llm_latency_ms"], "llm_calls": len(diagnostics["llm_calls"])}


def summarize(trials):
    def mean(values):
        return round(statistics.mean(values), 3) if values else None

    asked = sum(trial["questions"] for trial in trials)
    judged = all(trial["wasted"] is not None for trial in trials)
    wasted = [item for trial in trials for item in trial["wasted"] or []]
    calls = sum(trial["llm_calls"] for trial in trials)
    summary = {
        "trials": len(trials),
        "found_rate": mean([trial["found"] for trial in trials]),
        "questions_mean": mean([trial["questions"] for trial in trials]),
        "questions_when_found": mean([trial["questions"] for trial in trials if trial["found"]]),
        "first_guess_hit_rate": mean([trial["found"] and trial["guesses"] == 1 for trial in trials]),
        "fallback_rate": round(sum(trial["fallbacks"] for trial in trials) / calls, 3) if calls else None,
        "cost_usd": round(sum(trial["cost_usd"] for trial in trials), 4),
        "latency_ms_per_call": round(sum(trial["latency_ms"] for trial in trials) / calls) if calls else None,
    }
    if judged:
        summary.update(wasted_question_rate=round(len(wasted) / asked, 3) if asked else None,
                       same_topic=sum(item["kind"] == "same_topic" for item in wasted),
                       implied=sum(item["kind"] == "implied" for item in wasted),
                       trials_with_waste=sum(bool(trial["wasted"]) for trial in trials))
    return summary


def run_benchmark(candidates, engine_llm, user_llm, judge_llm=None, *, trials=20, seed=20261016,
                  max_questions=10, max_guesses=3, workers=5):
    names = sorted({candidate["display_name"] for candidate in candidates})
    if not 1 <= trials <= len(names):
        raise ValueError(f"trials must be between 1 and {len(names)}")
    targets = random.Random(seed).sample(names, trials)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda target: run_trial(
            candidates, target, engine_llm, user_llm, judge_llm,
            max_questions=max_questions, max_guesses=max_guesses), targets))
    return {"engine_version": ENGINE_VERSION,
            "prompt_sha256": hashlib.sha256(inspect.getsource(prompt).encode()).hexdigest()[:12],
            "config": {"trials": trials, "seed": seed, "max_questions": max_questions,
                       "max_guesses": max_guesses},
            "summary": summarize(results), "trials": results}
