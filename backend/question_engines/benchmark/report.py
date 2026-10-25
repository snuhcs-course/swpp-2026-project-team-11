# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""Turn session results into report.md, summary.json and one folder per section. No LLM call.
sessions.csv, questions.csv and proposals.csv hold one row per session, question and
proposal, for finding what went wrong.

Every figure is per situation: the situations measure different things (a served menu,
a substitute), so a mean over them means nothing. plots.py draws them into plots/.

    1_main_metrics/    questions, first pick, latency and cost per session
    2_baselines/       first pick against proposing without a question, a random dish
                       and the other engine
    3_situations/      success, giving up and similarity, also by user certainty
    4_paired_tests/    LLM - decision tree on the same scenarios
    5_latency_and_cost/ latency percentiles, LLM calls, tokens, cost, fallbacks, errors,
                       the simulated user's calls and tokens
    6_stability/       each engine over repeats of one scenario
    7_recommend_now/   what "recommend now" would give after k questions
    8_similarity/      similarity of accepted and rejected proposals (not-served threshold)
    9_user_study/      sessions played by people, satisfaction, the simulated user vs people

Sessions with an LLM fallback are counted in every section and reported apart in 1.
"""

from __future__ import annotations

import csv
import json
import pathlib
import statistics
from collections import defaultdict

import numpy as np

from . import CERTAINTY, ENGINES, SITUATIONS, cost, metrics, stats
from .simulator import ANSWER_IDS

GOAL_FIRST_PICK = 0.5      # first-pick acceptance the app aims at
GOAL_OVER_BASELINE = 0.15  # and how far above a baseline (checked as points and as a ratio)
TOLERANCE = 1e-9  # a result exactly at a goal meets it despite floating-point error
SESSIONS_PER_ENGINE = 2    # user study: sessions each tester plays on each engine
TAUS = (0.70, 0.75, 0.80, 0.85, 0.90, 0.95)
DIRECTION = {"yes": 2, "probably_yes": 2, "any": 1, "unknown": 1, "probably_no": 0, "no": 0}


def _values(rows, key):
    return [row[key] for row in rows if row.get(key) is not None]


def _mean(rows, key):
    values = [float(v) for v in _values(rows, key)]
    return statistics.fmean(values) if values else None


def _fmt(value, kind="num"):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "-"
    if kind == "rate":
        return f"{value:.1%}"
    if kind == "usd":
        return f"${value:.5f}"
    if kind == "int":
        return f"{value:,.0f}"
    return f"{value:.3f}" if isinstance(value, float) and abs(value) < 10 else f"{value:,.1f}"


def _group(rows, *keys):
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row[k] for k in keys)].append(row)
    return groups


def _order(key):
    ranks = {**{s: i for i, s in enumerate(SITUATIONS)}, **{c: i for i, c in enumerate(CERTAINTY)},
             **{e: i for i, e in enumerate(ENGINES)}}
    return tuple(ranks.get(part, 99) if not isinstance(part, int) else part for part in key)


def _sorted_groups(rows, *keys):
    return sorted(_group(rows, *keys).items(), key=lambda kv: _order(kv[0]))


def main_metrics(sessions):
    """The four main metrics of a group of sessions in one situation."""
    accepted = [r for r in sessions if r["outcome"] == "accepted"]
    latency = _values(sessions, "engine_ms")
    return {"sessions": len(sessions), "questions": _mean(sessions, "questions"),
            "questions_to_accept": _mean(accepted, "questions"),
            "first_pick": _mean(sessions, "first_guess_accepted"),
            "first_pick_exact": _mean(sessions, "first_guess_exact"),
            "latency_ms_p50": cost.percentile(latency, 50), "latency_ms_p95": cost.percentile(latency, 95),
            "cost_usd": _mean(sessions, "cost_usd")}


MAIN_HEADER = ["sessions", "questions / session", "questions to accept", "first pick", "first pick (exact)",
               "latency p50 (ms)", "latency p95 (ms)", "cost / session"]


def _main_row(m):
    return [m["sessions"], _fmt(m["questions"]), _fmt(m["questions_to_accept"]), _fmt(m["first_pick"], "rate"),
            _fmt(m["first_pick_exact"], "rate"), _fmt(m["latency_ms_p50"]), _fmt(m["latency_ms_p95"]),
            _fmt(m["cost_usd"], "usd")]


def section_main(sessions):
    summary, rows = defaultdict(dict), []
    for (situation, engine), group in _sorted_groups(sessions, "situation", "engine"):
        m = summary[situation][engine] = main_metrics(group)
        rows.append([situation, engine, *_main_row(m),
                     "-" if m["first_pick"] is None else ("yes" if m["first_pick"] >= GOAL_FIRST_PICK else "no")])
    fallback = [[situation, "with a fallback" if flag else "without", *_main_row(main_metrics(group))]
                for (situation, flag), group in _sorted_groups([r for r in sessions if r["engine"] == "llm"],
                                                               "situation", "fallback")]
    lines = ["questions / session: over every session; questions to accept: over accepted sessions.",
             "first pick: the user accepted the first proposal (a wanted menu or a kind of it, or the simulated "
             "user would take it). first pick (exact): the first proposal was a wanted menu or a kind of it by "
             "the name rule alone (not defined when the wanted menu is not served). The gap is what the "
             "simulated user took in place of the named dish.",
             "Latency: engine time per session (the user's time is not counted). Cost: what OpenRouter charged "
             "the LLM engine per session.",
             f"Goal: first pick >= {GOAL_FIRST_PICK:.0%} (and {GOAL_OVER_BASELINE:.0%} above the baselines, "
             "section 2)."]
    tables = [("main.csv", "Per situation", ["situation", "engine", *MAIN_HEADER,
                                             f"first pick >= {GOAL_FIRST_PICK:.0%}"], rows, 20)]
    if fallback:
        tables.append(("main_llm_fallback.csv", "LLM engine sessions with and without a fallback",
                       ["situation", "LLM sessions", *MAIN_HEADER], fallback, 10))
    return {"title": "1. Main metrics", "lines": lines, "tables": tables, "summary": summary}


def _per_scenario(sessions, engine, key):
    """{scenario: mean of `key` over the engine's repeats}."""
    out = {}
    for (scenario,), rows in _group([s for s in sessions if s["engine"] == engine], "scenario").items():
        value = _mean(rows, key)
        if value is not None:
            out[scenario] = value
    return out


def baseline_rows(sessions):
    rows, summary = [], []
    for (situation,), judged in _sorted_groups(sessions, "situation"):
        for engine in ENGINES:
            mine = _per_scenario(judged, engine, "first_guess_exact")
            if not mine:  # not served: first pick (exact) and the baselines are not defined
                continue
            other = next(e for e in ENGINES if e != engine)
            for name, values in (("no question", _per_scenario(judged, engine, "no_question_pick")),
                                 ("random dish", _per_scenario(judged, engine, "random_pick")),
                                 (other, _per_scenario(judged, other, "first_guess_exact"))):
                shared = sorted(mine.keys() & values.keys())
                if not shared:
                    continue
                ours = statistics.fmean(mine[s] for s in shared)
                theirs = statistics.fmean(values[s] for s in shared)
                ratio = ours / theirs - 1 if theirs else None
                points_met = ours - theirs >= GOAL_OVER_BASELINE - TOLERANCE
                ratio_met = ratio is not None and ratio >= GOAL_OVER_BASELINE - TOLERANCE
                low, high = stats.bootstrap_ci([mine[s] - values[s] for s in shared])
                rows.append([situation, engine, name, len(shared), _fmt(ours, "rate"), _fmt(theirs, "rate"),
                             f"{(ours - theirs) * 100:+.1f}", f"[{low * 100:+.1f}, {high * 100:+.1f}]",
                             "-" if ratio is None else f"{ratio:+.0%}", "yes" if points_met else "no",
                             "yes" if ratio_met else "no"])
                summary.append({"situation": situation, "engine": engine, "baseline": name, "scenarios": len(shared),
                                "first_pick": ours, "baseline_first_pick": theirs, "points": ours - theirs,
                                "ratio": ratio})
    return rows, summary


def section_baselines(sessions):
    rows, summary = baseline_rows(sessions)
    title = "2. Baselines"
    if not rows:
        return {"title": title, "skipped": "No session where the wanted menu is served."}
    return {"title": title, "summary": summary, "lines": [
        "First pick (exact) against three baselines in each situation whose wanted menu is served: a "
        "baseline is judged by the name rule only, so the engines are too.",
        "no question: the same engine's \"recommend now\" before any question; random dish: the chance "
        "that a dish picked at random is accepted; and the other engine.",
        "Each scenario counts once (each engine's repeats averaged). The goal is "
        f"+{GOAL_OVER_BASELINE * 100:.0f} points or +{GOAL_OVER_BASELINE:.0%} relative; both are shown."],
        "tables": [("baselines.csv", "First pick vs baselines",
                    ["situation", "engine", "baseline", "scenarios", "first pick (exact)", "baseline",
                     "diff (points)", "95% CI", "relative", f"+{GOAL_OVER_BASELINE * 100:.0f} points",
                     f"+{GOAL_OVER_BASELINE:.0%}"], rows, 20)]}


def situation_rows(sessions, by):
    out = []
    for key, rows in _sorted_groups(sessions, *by):
        out.append([*key, len(rows), _fmt(_mean(rows, "success"), "rate"),
                    _fmt(_mean(rows, "first_guess_accepted"), "rate"), _fmt(_mean(rows, "interactions")),
                    _fmt(statistics.fmean(r["outcome"] == "gave_up" for r in rows), "rate"),
                    _fmt(_mean(rows, "similarity")), _fmt(_mean(rows, "regret")), _fmt(_mean(rows, "rank"))])
    return out


SITUATION_HEADER = ["sessions", "success", "first pick", "interactions", "gave up", "similarity", "regret", "rank"]


def section_situations(sessions):
    return {"title": "3. Situations", "lines": [
        "success: the final menu is a wanted menu or a kind of it (not defined when the wanted menu is not "
        "served; see similarity and section 8). close_alternative: only the wanted menu counts, not its "
        "close alternative.",
        "similarity: 1 - mean feature difference to the closest wanted menu; regret: how much closer the best "
        "candidate was; rank: share of candidates farther away (1 = closest).",
        "Certainty blurs 0% (high), 15% (medium) or 30% (low) of the answers, the same way for both engines."],
        "tables": [("situations.csv", "By situation", ["situation", "engine", *SITUATION_HEADER],
                    situation_rows(sessions, ("situation", "engine")), 20),
                   ("situations_by_certainty.csv", "By situation and user certainty",
                    ["situation", "certainty", "engine", *SITUATION_HEADER],
                    situation_rows(sessions, ("situation", "certainty", "engine")), 30)]}


def paired(sessions, situation):
    """[(situation, metric, n, dt, llm, diff, ci, wilcoxon p, mcnemar p)] on the situation's scenarios
    both engines played."""
    rows = [s for s in sessions if s["situation"] == situation]
    per = defaultdict(lambda: defaultdict(list))
    for row in rows:
        per[row["scenario"]][row["engine"]].append(row)
    out = []
    for metric, binary in (("first_guess_accepted", True), ("first_guess_exact", True), ("questions", False),
                           ("engine_ms", False), ("cost_usd", False), ("success", True), ("interactions", False),
                           ("similarity", False)):
        pairs = []
        for engines in per.values():
            if len(engines) < 2:
                continue
            dt, llm = _mean(engines["decision_tree"], metric), _mean(engines["llm"], metric)
            if dt is not None and llm is not None:
                pairs.append((dt, llm))
        if not pairs:
            continue
        diffs = [llm - dt for dt, llm in pairs]
        low, high = stats.bootstrap_ci(diffs)
        p_wilcoxon = p_mcnemar = None
        if binary:  # repeat means of a yes/no metric are heavily tied, so no Wilcoxon
            only_dt = sum(dt >= 0.5 and llm < 0.5 for dt, llm in pairs)
            only_llm = sum(llm >= 0.5 and dt < 0.5 for dt, llm in pairs)
            p_mcnemar = stats.mcnemar(only_dt, only_llm)
        else:
            p_wilcoxon = stats.wilcoxon(diffs)
        out.append([situation, metric, len(pairs), _fmt(statistics.fmean(p[0] for p in pairs)),
                    _fmt(statistics.fmean(p[1] for p in pairs)), _fmt(statistics.fmean(diffs)),
                    f"[{_fmt(low)}, {_fmt(high)}]", _fmt(p_wilcoxon), _fmt(p_mcnemar)])
    return out


def section_paired(sessions):
    rows = [row for situation in SITUATIONS for row in paired(sessions, situation)]
    title = "4. Paired tests"
    if not rows:
        return {"title": title, "skipped": "No scenario was played by both engines."}
    return {"title": title, "lines": [
        "LLM - decision tree per scenario, each engine's mean over its repeats; positive = the LLM engine is "
        "higher. 95% bootstrap interval; McNemar p for yes/no metrics, Wilcoxon signed-rank p for the others."],
        "tables": [("paired.csv", "Paired comparison", ["situation", "metric", "pairs", "decision tree", "llm",
                                                        "diff", "95% CI", "Wilcoxon p", "McNemar p"], rows, 40)]}


def section_latency_cost(records):
    figures = {situation: cost.summary([r for r in records if r["situation"] == situation])
               for situation in SITUATIONS}
    rows = [[situation, engine, f["sessions"], _fmt(f["session_ms_p50"]), _fmt(f["session_ms_p95"]),
             _fmt(f["step_ms_p50"]), _fmt(f["step_ms_p95"]), _fmt(f["llm_calls"]), _fmt(f["input_tokens"], "int"),
             _fmt(f["output_tokens"], "int"), _fmt(f["cost_usd"], "usd"), _fmt(f["cost_usd_p95"], "usd"),
             _fmt(f["fallback_rate"], "rate"), _fmt(f["error_rate"], "rate"), _fmt(f["user_error_rate"], "rate"),
             f["recommend_now_calls"],
             _fmt(f["recommend_now_cost_usd"], "usd")]
            for situation, per_engine in figures.items() for engine, f in per_engine.items()]
    overhead = [[situation, engine, f["simulator_calls"], _fmt(f["simulator_input_tokens"], "int"),
                 _fmt(f["simulator_output_tokens"], "int")]
                for situation, per_engine in figures.items() for engine, f in per_engine.items()]
    return {"title": "5. Latency and cost", "summary": figures, "lines": [
        "Engine time only. LLM calls (every attempt, retries included), tokens and cost are the engine's own, "
        "as OpenRouter reported them; \"recommend now\" copies are benchmark overhead and counted apart (totals)."],
        "tables": [("latency_cost.csv", "Per situation",
                    ["situation", "engine", "sessions", "session ms p50", "p95", "step ms p50", "p95", "LLM calls",
                     "input tokens", "output tokens", "cost / session", "cost p95", "sessions with a fallback",
                     "engine errors", "simulated-user errors", "recommend-now calls", "recommend-now cost"], rows, 10),
                   ("simulator_usage.csv", "Simulated user (benchmark overhead, totals)",
                    ["situation", "engine", "calls", "input tokens", "output tokens"], overhead, 10)]}


def section_stability(sessions):
    out = []
    for (situation, engine), played in _sorted_groups(sessions, "situation", "engine"):
        groups = [rows for rows in _group(played, "scenario").values() if len(rows) > 1]
        if not groups:
            continue
        same_food, same_outcome, spread = [], [], []
        for rows in groups:
            finals = [r.get("final") for r in rows]
            pairs = [(a, b) for i, a in enumerate(finals) for b in finals[i + 1:]]
            same_food.append(statistics.fmean(a == b for a, b in pairs))
            outcomes = [r["success"] if r["success"] is not None else r["outcome"] for r in rows]
            same_outcome.append(len(set(outcomes)) == 1)
            spread.append(statistics.pstdev(r["questions"] or 0 for r in rows))
        out.append([situation, engine, len(groups), len(groups[0]), _fmt(statistics.fmean(same_food), "rate"),
                    _fmt(statistics.fmean(same_outcome), "rate"), _fmt(statistics.fmean(spread))])
    title = "6. Stability"
    if not out:
        return {"title": title, "skipped": "No scenario was played more than once."}
    return {"title": title, "lines": ["The same scenario played several times."],
            "tables": [("stability.csv", "Over repeats", ["situation", "engine", "scenarios", "repeats",
                                                         "same final menu", "same outcome", "questions SD"], out, 10)]}


def section_recommend_now(points):
    title = "7. Recommend now"
    if not points:
        return {"title": title, "skipped": "No \"recommend now\" checks."}
    rows = [[situation, engine, k, len(group), _fmt(_mean(group, "success"), "rate"), _fmt(_mean(group, "similarity"))]
            for (situation, engine, k), group in _sorted_groups(points, "situation", "engine", "k")]
    return {"title": title, "lines": [
        "What the engine would have proposed if the user had stopped answering after k questions."],
        "tables": [("recommend_now.csv", "After k questions", ["situation", "engine", "k", "sessions", "success",
                                                               "similarity"], rows, 40)]}


def section_similarity(sessions, proposals):
    title = "8. Similarity"
    if not proposals:
        return {"title": title, "skipped": "No proposal with features to compare."}
    rows = []
    for (situation, accepted), group in sorted(_group(proposals, "situation", "accepted").items(),
                                               key=lambda kv: _order(kv[0][:1]) + (kv[0][1],)):
        values = _values(group, "similarity")
        rows.append([situation, "accepted" if accepted else "rejected", len(values),
                     *[_fmt(cost.percentile(values, q)) for q in (10, 25, 50, 75, 90)]])
    thresholds = []
    for engine in ENGINES:
        group = [s for s in sessions if s["engine"] == engine and s["situation"] == "not_in_menu"]
        if group:
            thresholds.append([engine, len(group), *[_fmt(statistics.fmean((r["similarity"] or 0) >= tau
                                                                           for r in group), "rate") for tau in TAUS]])
    tables = [("similarity.csv", "Similarity of proposals to the wanted menu, by verdict (percentiles)",
               ["situation", "verdict", "proposals", "p10", "p25", "p50", "p75", "p90"], rows, 20)]
    if thresholds:
        tables.append(("thresholds.csv", "Share of not-served sessions whose final menu reaches each threshold",
                       ["engine", "sessions", *[f">= {t:.2f}" for t in TAUS]], thresholds, 5))
    return {"title": title, "lines": ["For choosing the similarity that counts as a success when the wanted menu "
                                      "is not served."], "tables": tables, "plot": ("similarity.png", proposals)}


def simulator_agreement(checks):
    """Agreement between people and the simulator: answers to the same questions, verdicts on the same proposals."""
    pairs = [(c["human"], c["simulator"]) for c in checks if "question" in c
             and c["human"] in ANSWER_IDS and c["simulator"] in ANSWER_IDS]
    verdicts = [c["human"] == c["simulator"] for c in checks if "proposal" in c]
    if not pairs and not verdicts:
        return None
    out = {"n": len(pairs), "verdicts": len(verdicts),
           "same_verdict": statistics.fmean(verdicts) if verdicts else None}
    if pairs:
        out |= {"exact": statistics.fmean(h == s for h, s in pairs),
                "direction": statistics.fmean(DIRECTION[h] == DIRECTION[s] for h, s in pairs),
                "kappa": stats.weighted_kappa([DIRECTION[h] for h, _ in pairs], [DIRECTION[s] for _, s in pairs])}
    return out


def section_user_study(human, checks, index):
    title = "9. User study"
    agreement = simulator_agreement(checks)
    if not human and not agreement:
        return {"title": title, "skipped": "No sessions played by people (play_engine_session)."}
    lines, tables = [], []
    if human:
        rows = []
        for record in human:
            row = metrics.session(record, record["scenario_data"], index)
            row.update(tester=record.get("tester"), satisfaction=record.get("satisfaction"))
            rows.append(row)
        by_situation = [[situation, engine, len(group), len({r["tester"] for r in group}),
                         _fmt(_mean(group, "questions")), _fmt(_mean(group, "first_guess_accepted"), "rate"),
                         _fmt(_mean(group, "success"), "rate"),
                         _fmt(cost.percentile(_values(group, "engine_ms"), 50)), _fmt(_mean(group, "satisfaction"))]
                        for (situation, engine), group in _sorted_groups(rows, "situation", "engine")]
        testers = sorted({r["tester"] for r in rows})
        complete = sum(all(sum(r["tester"] == t and r["engine"] == e for r in rows) >= SESSIONS_PER_ENGINE
                           for e in ENGINES) for t in testers)
        lines.append(f"{len(testers)} testers, {complete} of them with {SESSIONS_PER_ENGINE} sessions on each engine. "
                     "The engine was hidden; satisfaction is the 1-5 survey answer after each session.")
        tables.append(("user_study.csv", "Sessions played by people",
                       ["situation", "engine", "sessions", "testers", "questions / session", "first pick",
                        "success", "latency p50 (ms)", "satisfaction (1-5)"], by_situation, 10))
    if agreement and agreement["n"]:
        lines.append(f"The simulated user answered the {agreement['n']} questions people answered: same answer "
                     f"{agreement['exact']:.1%}, same direction (yes / neutral / no) {agreement['direction']:.1%}, "
                     f"weighted kappa {agreement['kappa']:.2f}.")
    if agreement and agreement["verdicts"]:
        lines.append(f"On the {agreement['verdicts']} proposals people judged that the name rule does not accept, "
                     f"the simulated user gave the same verdict {agreement['same_verdict']:.1%} of the time.")
    return {"title": title, "lines": lines, "tables": tables, "summary": {"simulator_agreement": agreement}}


def _plot(proposals, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(1, len(SITUATIONS), figsize=(16, 3.2), squeeze=False)
    bins = np.linspace(0.4, 1.0, 25)
    for axis, situation in zip(axes[0], SITUATIONS):
        for accepted, color in ((True, "#4c72b0"), (False, "#dd8452")):
            values = [p["similarity"] for p in proposals if p["situation"] == situation and p["accepted"] == accepted
                      and p["similarity"] is not None]
            axis.hist(values, bins=bins, alpha=0.7, color=color, label="accepted" if accepted else "rejected")
        axis.set_title(situation, fontsize=10)
        axis.set_xlabel("similarity to the wanted menu")
    axes[0][0].legend()
    figure.tight_layout()
    figure.savefig(path, dpi=110)
    plt.close(figure)


def section_dir(title) -> str:
    """"1. Main metrics" -> "1_main_metrics"."""
    number, _, name = title.partition(". ")
    return f"{number}_{name.lower().replace(' ', '_')}"


def _table(header, rows):
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header),
            *("| " + " | ".join(str(c) for c in row) + " |" for row in rows)]


def write(scenario_data, records, output_dir, human=None, checks=None, plots=True) -> pathlib.Path:
    output = pathlib.Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    index = metrics.MenuIndex(scenario_data)
    scenarios = {s["id"]: s for s in scenario_data["scenarios"]}
    records = [r for r in records if r["scenario"] in scenarios]
    sessions, questions, proposals, points = [], [], [], []
    for record in records:
        scenario = scenarios[record["scenario"]]
        row = metrics.session(record, scenario, index)
        row["final"] = record.get("final_food_id")
        sessions.append(row)
        questions += metrics.questions(record)
        proposals += metrics.proposals(record, scenario, index)
        points += metrics.anytime(record, scenario, index)

    results = [section_main(sessions), section_baselines(sessions), section_situations(sessions),
               section_paired(sessions), section_latency_cost(records), section_stability(sessions),
               section_recommend_now(points), section_similarity(sessions, proposals),
               section_user_study(human or [], checks or [], index)]
    engines = sorted({r["engine"] for r in records}, key=ENGINES.index)
    per_engine = ", ".join(f"{e} {sum(r['engine'] == e for r in records)}" for e in engines)
    text = ["# Question engine benchmark: decision tree (MVP1) vs LLM engine (MVP2)", "",
            f"{len(scenarios)} scenarios on {len(scenario_data['menus'])} menus, {len(records)} sessions "
            f"({per_engine}).", ""]
    for result in results:
        text += [f"## {result['title']}", ""]
        if "skipped" in result:
            text += [f"Skipped: {result['skipped']}", ""]
            continue
        folder = section_dir(result["title"])
        (output / folder).mkdir(exist_ok=True)
        text += [f"- {line}" for line in result["lines"]] + [""]
        if plots and "plot" in result:
            name, data = result["plot"]
            _plot(data, output / folder / name)
            text += [f"![{result['title']}]({folder}/{name})", ""]
        for file_name, title, header, rows, shown in result["tables"]:
            with open(output / folder / file_name, "w", encoding="utf-8-sig", newline="") as f:
                csv.writer(f).writerows([header, *rows])
            more = f", first {shown} of {len(rows)}" if len(rows) > shown else ""
            text += [f"**{title}** (`{folder}/{file_name}`{more})", "", *_table(header, rows[:shown]), ""]
    for name, rows in (("sessions.csv", sessions), ("questions.csv", questions), ("proposals.csv", proposals)):
        if rows:
            with open(output / name, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
    if plots:
        from .plots import write as draw

        draw(output)
        text[2:2] = ["Plots by situation: `plots/` (first pick, outcomes, paired differences, questions / latency / "
                     "cost, first pick by certainty).", ""]
    summary = {"scenarios": len(scenarios), "sessions": len(records),
               **{section_dir(r["title"]): r["summary"] for r in results if "summary" in r}}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=str) + "\n",
                                         encoding="utf-8")
    path = output / "report.md"
    path.write_text("\n".join(text), encoding="utf-8")
    return path
