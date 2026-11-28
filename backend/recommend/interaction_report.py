"""Numbers from the interaction log (recommend/interaction_log.py), for `manage.py interaction_report`.

    events = read(root, since)            # every record of the daily files, oldest first
    print(report(events, now, full=False))

A session or room counts once it has been quiet for IDLE (or a room has ended); younger ones
are still open and only counted as such. The default report has the key numbers:

- solo: for each k, how many sessions showed question k+1 (k answered) and how many ended there,
  which questions most often ended a session, how many reached a proposal and after how many
  questions and seconds, and how many were completed (directions or a bookmark from the app);
- rooms: how many started rooms decided and where the others ended, the share of timed-out answers
  in each round, and the minutes from start to result and from result to decision.

`full=True` adds answer times, "recommend now", how sessions ended, and room leaves and finds.
Nothing personal is printed: no allergies, names or restaurant choices.
"""
from __future__ import annotations

import datetime
import json
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

IDLE = datetime.timedelta(minutes=30)
TOP_QUESTIONS = 5
MIN_SHOWN = 3  # a question shown fewer times has no meaningful rate
ACCEPTS = ("directions", "bookmark")
CLIENT_EVENTS = ("home", "resume", "directions", "bookmark", "background")
_NAME = re.compile(r"^interactions-(\d{4}-\d{2}-\d{2})\.jsonl$")


def read(root: Path, since: datetime.date | None = None) -> list[dict]:
    """Every well-formed record of the daily files from `since` on, oldest first."""
    events = []
    for path in sorted(root.glob("interactions-*.jsonl")):
        match = _NAME.fullmatch(path.name)
        if not match or (since and datetime.date.fromisoformat(match.group(1)) < since):
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
                event["_at"] = _time(event["timestamp"])
            except (ValueError, KeyError, TypeError):
                continue
            events.append(event)
    events.sort(key=lambda e: e["_at"])
    return events


def _time(text: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))


def _pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.0f}%" if whole else "-"


def _median(values) -> str:
    values = [v for v in values if v is not None]
    return f"{statistics.median(values):.1f}" if values else "-"


def _table(header: tuple, rows: list[tuple]) -> str:
    cells = [tuple(str(c) for c in header)] + [tuple(str(c) for c in row) for row in rows]
    widths = [max(len(row[i]) for row in cells) for i in range(len(header))]
    lines = ["  ".join(c.rjust(w) for c, w in zip(row, widths)) for row in cells]
    return "\n".join(lines[:1] + ["  ".join("-" * w for w in widths)] + lines[1:])


def _shown(event: dict) -> dict | None:
    """The step on screen after this event: the new step, or for an app event the one it happened on."""
    return event.get("after") or event.get("before")


def sessions(events: list[dict], now: datetime.datetime) -> tuple[list[dict], int]:
    """Each ended solo session summarised, and how many are still open."""
    grouped = defaultdict(list)
    for event in events:
        if event.get("record") != "room" and event.get("session"):
            grouped[event["session"]].append(event)
    ended, open_ = [], 0
    for items in grouped.values():
        if not any(e["event"] == "start" for e in items):
            continue  # began before the files read
        if now - items[-1]["_at"] < IDLE:
            open_ += 1
            continue
        start = next(e["_at"] for e in items if e["event"] == "start")
        steps = [(e, _shown(e)) for e in items if _shown(e)]
        questions = {(s["question_count"], s.get("question_id")) for _, s in steps if s["type"] == "question"}
        first_guess = next(((e, s) for e, s in steps if s["type"] == "guess"), None)
        events_ = [e["event"] for e in items]
        last = steps[-1][1] if steps else None
        signals = [name for name in events_ if name in CLIENT_EVENTS]
        accepted = any(name in ACCEPTS for name in events_)
        ended.append({
            "questions": questions,
            "answered": max((s["question_count"] or 0 for _, s in steps if s.get("question_count") is not None), default=0),
            "last": last,
            "accepted": accepted,
            "first_guess": None if first_guess is None else
            (first_guess[1]["question_count"], (first_guess[0]["_at"] - start).total_seconds()),
            "ended_by": "accepted" if accepted else (signals[-1] if signals and signals[-1] in ("home", "background")
                                                     else "no signal"),
            "rejections": sum(e["event"] == "feedback" and e.get("accepted") is False for e in items),
            "recommend_now": [e["before"]["question_count"] for e in items
                              if e["event"] == "recommend_now" and e.get("before")],
            "answer_seconds": [(e["before"]["question_count"], (e["_at"] - prev["_at"]).total_seconds())
                               for prev, e in zip(items, items[1:])
                               if e["event"] == "answer" and e.get("outcome") == "ok" and e.get("before")],
            "signals": bool(signals),
        })
    return ended, open_


def rooms(events: list[dict], now: datetime.datetime) -> tuple[list[dict], int]:
    """Each closed room's records, and how many are still open."""
    grouped = defaultdict(list)
    for event in events:
        if event.get("record") == "room" and event.get("room"):
            grouped[event["room"]].append(event)
    closed, open_ = [], 0
    for items in grouped.values():
        if not any(e["event"] == "create" for e in items):
            continue
        if items[-1]["event"] != "end" and now - items[-1]["_at"] < IDLE:
            open_ += 1
        else:
            closed.append(items)
    return closed, open_


def _solo(ended: list[dict], open_: int, full: bool) -> list[str]:
    out = [f"SOLO SESSIONS: {len(ended)} ended, {open_} still open", ""]
    if not ended:
        return out
    top = max(k for s in ended for k, _ in s["questions"]) if any(s["questions"] for s in ended) else -1
    rows = []
    for k in range(top + 1):
        saw = [s for s in ended if any(q == k for q, _ in s["questions"])]
        left = [s for s in saw if not s["accepted"] and s["last"] and s["last"]["type"] == "question"
                and s["last"]["question_count"] == k]
        rows.append((k, len(saw), len(left), _pct(len(left), len(saw)),
                     _pct(sum(s["answered"] >= k for s in ended), len(ended))))
    out += ["1. Where sessions end: question k+1 on screen after k answers",
            _table(("answered k", "saw k+1", "ended there", "drop", "reached k"), rows), ""]

    shown, exits = Counter(), Counter()
    for s in ended:
        for qid in {qid for _, qid in s["questions"]}:
            shown[qid] += 1
        if not s["accepted"] and s["last"] and s["last"]["type"] == "question":
            exits[s["last"].get("question_id")] += 1
    worst = sorted((qid for qid in shown if shown[qid] >= MIN_SHOWN and exits[qid]),
                   key=lambda qid: (-exits[qid] / shown[qid], -exits[qid]))[:TOP_QUESTIONS]
    out += [f"2. Questions that most often ended a session (shown in at least {MIN_SHOWN})",
            _table(("question", "shown", "ended", "rate"),
                   [(qid, shown[qid], exits[qid], _pct(exits[qid], shown[qid])) for qid in worst]) if worst
            else "   none yet", ""]

    guessed = [s for s in ended if s["first_guess"]]
    out += ["3. Reaching a proposal",
            f"   {len(guessed)} of {len(ended)} ({_pct(len(guessed), len(ended))}); median "
            f"{_median(q for q, _ in (s['first_guess'] for s in guessed))} questions and "
            f"{_median(t for _, t in (s['first_guess'] for s in guessed))} s to the first", ""]

    with_signals = [s for s in ended if s["signals"]]
    if with_signals:
        done = sum(s["accepted"] for s in with_signals)
        out += ["4. Completed (directions or a bookmark), sessions from apps that report it",
                f"   {done} of {len(with_signals)} ({_pct(done, len(with_signals))}); "
                f"{_pct(sum(s['accepted'] for s in with_signals if s['first_guess']), sum(bool(s['first_guess']) for s in with_signals))}"
                " of those that reached a proposal", ""]
    else:
        out += ["4. Completed: no app reports these yet (needs the app's exit signals)", ""]

    if full:
        by_k = defaultdict(list)
        for s in ended:
            for k, seconds in s["answer_seconds"]:
                by_k[k].append(seconds)
        out += ["Answer time by question (seconds)",
                _table(("answered k", "answers", "median s"), [(k, len(v), _median(v)) for k, v in sorted(by_k.items())]),
                ""]
        pressed = [q for s in ended for q in s["recommend_now"]]
        out += [f"Recommend now: {sum(bool(s['recommend_now']) for s in ended)} sessions; "
                f"after {_median(pressed)} answers (median)", ""]
        at_guess = [s for s in guessed if not s["accepted"] and s["last"]["type"] == "guess"]
        out += [f"Ended on a proposal without accepting: {len(at_guess)} of {len(guessed)} "
                f"({_pct(len(at_guess), len(guessed))}), median {_median(s['rejections'] for s in at_guess)} "
                "'find another' before", ""]
        ways = Counter(s["ended_by"] for s in ended)
        out += ["How sessions ended: " + ", ".join(f"{way} {n}" for way, n in ways.most_common()), ""]
    return out


def _rooms(closed: list[list[dict]], open_: int, full: bool) -> list[str]:
    out = [f"GROUP ROOMS: {len(closed)} closed, {open_} still open", ""]
    if not closed:
        return out
    started = [r for r in closed if any(e["event"] == "start" and e["outcome"] == "ok" for e in r)]
    decided = [r for r in started if any(e["event"] == "decide" for e in r)]
    decided_ids = {id(r) for r in decided}
    stages = Counter()
    for r in closed:
        if id(r) in decided_ids:
            continue
        # Where the room stood at its last record before the end: the last leave, or the last
        # state it reached before it was let go.
        last = next((e for e in reversed(r) if e["event"] != "end"), r[-1])
        stage = {"lobby": "lobby", "done": "result"}.get(last["status"], f"round {last['round'] + 1}")
        stages[stage] += 1
    unavailable = sum(any(e["event"] == "start" and e["outcome"] == "group_unavailable" for e in r) for r in closed)
    out += ["1. Rooms decided",
            f"   {len(decided)} of {len(started)} started ({_pct(len(decided), len(started))}); "
            f"{len(started)} of {len(closed)} created rooms started",
            "   undecided rooms ended at: " + (", ".join(f"{stage} {n}" for stage, n in sorted(stages.items())) or "-"),
            ""]

    by_round = defaultdict(lambda: [0, 0, 0])
    for r in closed:
        for e in r:
            if e["event"] == "round":
                row = by_round[e["round"]]
                row[0] += 1
                row[1] += e["answered"] + e["timeout"]
                row[2] += e["timeout"]
    out += ["2. Timed-out answers by round (members who were still there)",
            _table(("round", "rooms", "answers", "timed out", "share"),
                   [(k, n, a, t, _pct(t, a)) for k, (n, a, t) in sorted(by_round.items())]) if by_round
            else "   no round finished yet", ""]

    def times(event, key):
        return [e[key] / 60 for r in closed for e in r if e["event"] == event and e.get(key) is not None]
    out += ["3. Minutes per room (median)",
            f"   start to result {_median(times('result', 'asking_s'))}, "
            f"result to decision {_median(times('decide', 'deciding_s'))}", ""]

    if full:
        out += [f"Lobby wait (create to start): {_median(times('start', 'waited_s'))} min; "
                f"no restaurant for everyone at start: {unavailable}", ""]
        leaves = Counter(e["status"] for r in closed for e in r if e["event"] == "leave")
        hosts = sum(e.get("was_host", False) for r in closed for e in r if e["event"] == "leave")
        out += ["Leaves by stage: " + (", ".join(f"{s} {n}" for s, n in sorted(leaves.items())) or "-")
                + f"; hosts who left: {hosts}", ""]
        early = [e for r in closed for e in r if e["event"] == "result" and e.get("how") == "recommend_now"]
        results = sum(e["event"] == "result" for r in closed for e in r)
        out += [f"Host stopped early: {len(early)} of {results} results, after {_median(e['round'] for e in early)} rounds", ""]
        decisions = [e for r in closed for e in r if e["event"] == "decide"]
        out += [f"Finds before deciding: median {_median(e['finds'] for e in decisions)}; "
                f"agreeing members at the decided place: median "
                f"{_median(100 * e['votes'] / e['members'] for e in decisions if e['members'])}%", ""]
        by_limit = defaultdict(lambda: [0, 0])
        for r in closed:
            for e in r:
                if e["event"] == "round":
                    by_limit[e["round_seconds"]][0] += e["answered"] + e["timeout"]
                    by_limit[e["round_seconds"]][1] += e["timeout"]
        out += ["Timed-out share by round time: " + (", ".join(
            f"{limit} s {_pct(t, a)}" for limit, (a, t) in sorted(by_limit.items())) or "-"), ""]
    return out


def report(events: list[dict], now: datetime.datetime | None = None, full: bool = False) -> str:
    now = now or datetime.datetime.now(datetime.timezone.utc)
    lines = _solo(*sessions(events, now), full) + _rooms(*rooms(events, now), full)
    return "\n".join(lines).rstrip() + "\n"
