# AI-generated: written with Claude Code (Anthropic) and reviewed by the team.
"""The report's plots, one panel per situation, drawn into plots/ from the CSVs that
report.write has just written (sessions.csv, 4_paired_tests/paired.csv):

    1_first_pick.png               first-pick acceptance, exact by the name rule, and the baselines
    2_outcomes.png                 how sessions ended
    3_paired_differences.png       LLM - decision tree with 95% intervals
    4_questions_latency_cost.png   questions, latency and cost per session
    5_first_pick_by_certainty.png  first pick by how many answers were blurred
"""

from __future__ import annotations

import csv
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from . import CERTAINTY, ENGINES, SITUATIONS  # noqa: E402

TITLES = {"in_menu": "menu served", "multiple": "several menus would do", "not_in_menu": "menu not served",
          "close_alternative": "served next to a close alternative"}
COLOR = {"decision_tree": "#4c72b0", "llm": "#dd8452"}
LABEL = {"decision_tree": "decision tree", "llm": "LLM engine"}
X = np.arange(len(ENGINES))
OUTCOMES = {"first proposal accepted": "#55a868", "accepted later": "#a1d99b",
            "gave up (5 proposals rejected)": "#c44e52", "error / unavailable": "#cccccc"}
PAIRED = [("first_guess_accepted", "first pick accepted"), ("first_guess_exact", "first pick exact"),
          ("success", "ended on a wanted menu"), ("questions", "questions per session")]


def _read(path):
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _num(value):
    return None if value in ("", None) else float(value)


def _flag(value):
    return None if value in ("", None) else value == "True"


def _mean(values):
    values = [v for v in values if v is not None]
    return float(np.mean(values)) if values else np.nan


def _grid(title, rows=1, height=3.4):
    figure, axes = plt.subplots(rows, len(SITUATIONS), figsize=(4.2 * len(SITUATIONS), height * rows), squeeze=False)
    figure.suptitle(title, fontsize=13)
    for axis, situation in zip(axes[0], SITUATIONS):
        axis.set_title(f"{situation}\n({TITLES[situation]})", fontsize=10)
    return figure, axes


def _save(figure, path, legend=None):
    if legend:
        figure.legend(*legend, loc="lower center", ncol=len(legend[0]), fontsize=8)
    figure.tight_layout(rect=(0, 0.07 if legend else 0, 1, 1))
    figure.savefig(path, dpi=120)
    plt.close(figure)


def _label_bars(axis, bars, fmt="{:.0%}"):
    for bar in bars:
        height = bar.get_height()
        if not np.isnan(height):
            axis.annotate(fmt.format(height), (bar.get_x() + bar.get_width() / 2, height), ha="center",
                          va="bottom", fontsize=8, xytext=(0, 2), textcoords="offset points")


def _engine_ticks(axis):
    axis.set_xticks(X, [LABEL[e] for e in ENGINES])


def _missing(axis, group, situation) -> bool:
    if any(group[situation, e] for e in ENGINES):
        return False
    axis.text(0.5, 0.5, "no sessions", ha="center", va="center", color="gray", transform=axis.transAxes)
    return True


def _outcome(row):
    if row["outcome"] == "accepted":
        return "first proposal accepted" if _flag(row["first_guess_accepted"]) else "accepted later"
    return "gave up (5 proposals rejected)" if row["outcome"] == "gave_up" else "error / unavailable"


def first_pick(group, path):
    figure, axes = _grid("First-pick acceptance (bar: accepted by the user; hatched: the wanted menu by the name rule)")
    for axis, situation in zip(axes[0], SITUATIONS):
        if _missing(axis, group, situation):
            continue
        accepted = [_mean(_flag(r["first_guess_accepted"]) for r in group[situation, e]) for e in ENGINES]
        exact = [_mean(_flag(r["first_guess_exact"]) for r in group[situation, e]) for e in ENGINES]
        _label_bars(axis, axis.bar(X, accepted, 0.6, color=[COLOR[e] for e in ENGINES], alpha=0.85))
        if situation != "not_in_menu":
            axis.bar(X, exact, 0.6, fill=False, hatch="//", edgecolor="black", linewidth=0.6)
            for i, engine in enumerate(ENGINES):
                no_question = _mean(_flag(r["no_question_pick"]) for r in group[situation, engine])
                axis.plot([i - 0.3, i + 0.3], [no_question] * 2, color="black", linestyle="--", linewidth=1)
            axis.axhline(_mean(_num(r["random_pick"]) for r in group[situation, ENGINES[0]]), color="gray",
                         linestyle=":", linewidth=1)
        axis.axhline(0.5, color="red", linewidth=0.8, alpha=0.6)
        _engine_ticks(axis)
        axis.set_ylim(0, 1)
    axes[0][0].set_ylabel("share of sessions")
    lines = [plt.Line2D([], [], color="black", linestyle="--"), plt.Line2D([], [], color="gray", linestyle=":"),
             plt.Line2D([], [], color="red")]
    _save(figure, path, (lines, ["no-question baseline (same engine, no question asked)", "random dish", "goal 50%"]))


def outcomes(group, path):
    figure, axes = _grid("How sessions ended")
    for axis, situation in zip(axes[0], SITUATIONS):
        if _missing(axis, group, situation):
            continue
        bottom = np.zeros(len(ENGINES))
        for name, color in OUTCOMES.items():
            shares = np.array([_mean(_outcome(r) == name for r in group[situation, e]) for e in ENGINES])
            axis.bar(X, shares, 0.6, bottom=bottom, color=color, label=name)
            for i, share in enumerate(shares):
                if share >= 0.06:
                    axis.text(i, bottom[i] + share / 2, f"{share:.0%}", ha="center", va="center", fontsize=8)
            bottom += np.nan_to_num(shares)
        _engine_ticks(axis)
        axis.set_ylim(0, 1)
    axes[0][0].set_ylabel("share of sessions")
    _save(figure, path, axes[0][0].get_legend_handles_labels())


def paired_differences(paired, path):
    figure, axes = plt.subplots(1, len(PAIRED), figsize=(4.2 * len(PAIRED), 3.4))
    figure.suptitle("LLM engine minus decision tree, same scenarios (95% bootstrap interval; black: excludes 0)",
                    fontsize=12)
    for axis, (metric, title) in zip(axes, PAIRED):
        rows = {r["situation"]: r for r in paired if r["metric"] == metric}
        ys = [s for s in SITUATIONS if s in rows]
        for y, situation in enumerate(ys):
            low, high = (float(v) for v in rows[situation]["95% CI"].strip("[]").split(","))
            diff = float(rows[situation]["diff"])
            color = "black" if low > 0 or high < 0 else "#aaaaaa"
            axis.plot([low, high], [y, y], color=color, linewidth=2)
            axis.plot(diff, y, "o", color=color)
            axis.annotate(f"{diff:+.2f}", (diff, y), fontsize=8, xytext=(0, 6), textcoords="offset points",
                          ha="center")
        axis.axvline(0, color="black", linewidth=0.8)
        axis.set_yticks(range(len(ys)), ys)
        axis.set_ylim(len(ys) - 0.5, -0.7)
        axis.set_title(title, fontsize=10)
    _save(figure, path)


def questions_latency_cost(group, path):
    figure, axes = _grid("Questions, latency and cost per session", rows=3, height=2.9)
    for axis, situation in zip(axes[0], SITUATIONS):
        if _missing(axis, group, situation):
            continue
        values = [[_num(r["questions"]) for r in group[situation, e]] for e in ENGINES]
        axis.boxplot(values, positions=X, widths=0.4, showfliers=False, showmeans=True,
                     meanprops={"marker": "D", "markerfacecolor": "white", "markeredgecolor": "black"})
        for i, v in enumerate(values):
            axis.annotate(f"mean {_mean(v):.1f}", (i + 0.22, _mean(v)), fontsize=8, va="center")
        axis.set_ylim(0, None)
    for row, key, fmt, ylabel in ((1, "engine_ms", "{:,.0f}", "latency median (ms, log)"),
                                  (2, "cost_usd", "${:.4f}", "cost mean (USD)")):
        for axis, situation in zip(axes[row], SITUATIONS):
            if _missing(axis, group, situation):
                continue
            values = [[_num(r[key]) for r in group[situation, e]] for e in ENGINES]
            center = [float(np.median(v)) if key == "engine_ms" else _mean(v) for v in values]
            _label_bars(axis, axis.bar(X, center, 0.6, color=[COLOR[e] for e in ENGINES]), fmt)
            if key == "engine_ms":
                axis.set_yscale("log")
                axis.set_ylim(10, 2e5)
            else:
                axis.set_ylim(0, max(max(center), 0.001) * 1.4)
        axes[row][0].set_ylabel(ylabel)
    axes[0][0].set_ylabel("questions")
    for axis in axes.flat:
        _engine_ticks(axis)
    _save(figure, path)


def first_pick_by_certainty(group, path):
    figure, axes = _grid("First-pick acceptance by user certainty (blurred answers: high 0%, medium 15%, low 30%)")
    for axis, situation in zip(axes[0], SITUATIONS):
        if _missing(axis, group, situation):
            continue
        for engine in ENGINES:
            values = [_mean(_flag(r["first_guess_accepted"]) for r in group[situation, engine] if r["certainty"] == c)
                      for c in CERTAINTY]
            axis.plot(CERTAINTY, values, marker="o", color=COLOR[engine], label=LABEL[engine])
            for c, v in zip(CERTAINTY, values):
                axis.annotate(f"{v:.0%}", (c, v), fontsize=7, xytext=(4, 3), textcoords="offset points")
        sizes = [sum(r["certainty"] == c for r in group[situation, ENGINES[0]]) for c in CERTAINTY]
        axis.set_xlabel(f"{min(sizes)}-{max(sizes)} sessions per point")
        axis.set_ylim(0, 1)
        axis.axhline(0.5, color="red", linewidth=0.8, alpha=0.6)
    axes[0][0].set_ylabel("first pick accepted")
    _save(figure, path, axes[0][0].get_legend_handles_labels())


def write(folder) -> None:
    out = folder / "plots"
    out.mkdir(exist_ok=True)
    group = defaultdict(list)
    for row in _read(folder / "sessions.csv"):
        group[row["situation"], row["engine"]].append(row)
    first_pick(group, out / "1_first_pick.png")
    outcomes(group, out / "2_outcomes.png")
    paired = folder / "4_paired_tests" / "paired.csv"
    if paired.exists():
        paired_differences(_read(paired), out / "3_paired_differences.png")
    questions_latency_cost(group, out / "4_questions_latency_cost.png")
    first_pick_by_certainty(group, out / "5_first_pick_by_certainty.png")
