# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""python manage.py collect_engine_sessions --scenarios scenarios.json --output sessions.jsonl

Let a simulated user play every scenario on both engines, --repeats times each: the
same number for both, since the blurred answers change with the repeat and the LLM
engine with every call. One JSON line per session is appended as soon as it ends,
and sessions already in --output are skipped, so a stopped run continues where it stopped. A session that
ended in an error (a lost connection, an expired key) is removed and played again,
and MAX_FAILURES errors in a row stop the run instead of spending every session.

The LLM engine runs on OpenRouter as on the server (OPENROUTER_API_KEY,
METCHU_LLM_MODEL). The simulated user is METCHU_SIMULATOR_MODEL (default
google:gemini-3.5-flash); its answers are cached in --simulator-cache, and each
session records the calls and tokens it caused. --dry-run prints the sessions and an
estimate of the LLM calls. See question_engines/benchmark.
"""

from __future__ import annotations

import json
import pathlib

from django.core.management.base import BaseCommand, CommandError

from question_engines.benchmark import ENGINES, SITUATIONS, harness, scenarios, simulator
from question_engines.llm.config import LLMConfigError, LLMSettings, build_llm

MAX_FAILURES = 3
# Per-session averages of an LLM engine session in the first real run (2026-10-20), for --dry-run only.
QUESTIONS, PROPOSALS = 10, 4


def _list(text, allowed):
    items = [item.strip() for item in text.split(",") if item.strip()]
    unknown = sorted(set(items) - set(allowed))
    if unknown:
        raise CommandError(f"Unknown value: {', '.join(unknown)}. Choose from {', '.join(allowed)}.")
    return items


def choose(data, situations, limit) -> list[dict]:
    """The scenarios of `situations`, the first `limit` of each."""
    chosen, per = [], {}
    for scenario in data["scenarios"]:
        if scenario["situation"] in situations:
            per[scenario["situation"]] = per.get(scenario["situation"], 0) + 1
            if limit is None or per[scenario["situation"]] <= limit:
                chosen.append(scenario)
    return chosen


def finished(output) -> tuple[list[str], int]:
    """The session lines already in `output` that need no replay, and how many ended in an error."""
    kept, failed = [], 0
    if output.exists():
        for line in filter(str.strip, output.read_text(encoding="utf-8").splitlines()):
            if json.loads(line)["outcome"] == "error":
                failed += 1
            else:
                kept.append(line)
    return kept, failed


def estimate(tasks) -> tuple[int, int]:
    """Rough (engine, simulated user) LLM calls of `tasks`, before the cache."""
    dt = [t for t in tasks if t[1] == "decision_tree"]
    llm = [t for t in tasks if t[1] == "llm"]
    judged = sum(t[0]["situation"] != "close_alternative" for t in tasks)
    # the decision tree asks the same fixed questions on every repeat, answered from the cache
    user = (len({t[0]["id"] for t in dt}) + len(llm)) * QUESTIONS + judged * PROPOSALS
    return len(llm) * (QUESTIONS + PROPOSALS + len(harness.ANYTIME)), user


class Command(BaseCommand):
    help = "Play every scenario with a simulated user on both engines and store the sessions."

    def add_arguments(self, parser):
        parser.add_argument("--scenarios", required=True)
        parser.add_argument("--output", required=True, help="sessions file (JSON lines), appended to")
        parser.add_argument("--situations", default=",".join(SITUATIONS))
        parser.add_argument("--repeats", type=int, default=3, help="sessions per scenario and engine")
        parser.add_argument("--limit", type=int, default=None, help="first N scenarios per situation")
        parser.add_argument("--simulator-cache", default=None,
                            help="simulated answers cache (default: next to --output)")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        data = scenarios.load(options["scenarios"])
        chosen = choose(data, _list(options["situations"], SITUATIONS), options["limit"])
        output = pathlib.Path(options["output"])
        kept, failed = finished(output)
        done = {(row["scenario"], row["engine"], row["repeat"]) for row in map(json.loads, kept)}
        tasks = [(scenario, engine, repeat) for engine in ENGINES for repeat in range(options["repeats"])
                 for scenario in chosen if (scenario["id"], engine, repeat) not in done]
        llm = [t for t in tasks if t[1] == "llm"]
        engine_calls, user_calls = estimate(tasks)
        self.stdout.write(f"시나리오 {len(chosen)}개, 남은 세션 decision_tree {len(tasks) - len(llm)} / llm {len(llm)} -> "
                          f"LLM 호출 약 {engine_calls + user_calls}번 (엔진 {engine_calls}, 가상 사용자 {user_calls}; "
                          f"세션당 질문 {QUESTIONS}·제안 {PROPOSALS} 가정, 캐시 제외 전)")
        if failed:
            self.stdout.write(f"오류로 끝난 세션 {failed}개를 다시 실행합니다.")
        if options["dry_run"] or not tasks:
            return
        if failed:
            output.write_text("".join(line + "\n" for line in kept), encoding="utf-8")

        engine_llm = None
        if llm:
            try:
                engine_settings = LLMSettings.from_env()
            except LLMConfigError as error:
                raise CommandError(str(error)) from error
            engine_llm = build_llm(engine_settings)
            if simulator.same_as_engine(engine_settings.model):
                self.stdout.write(self.style.WARNING("가상 사용자와 LLM 엔진이 같은 모델입니다. LLM 엔진에 유리할 수 있습니다."))
        try:
            if not simulator.MODEL.api_key_available():
                raise CommandError(f"가상 사용자 모델의 키({simulator.MODEL.key_name()})가 없습니다.")
            user = simulator.Simulator(simulator.build_llm(),
                                       options["simulator_cache"] or output.with_suffix(".simcache.jsonl"))
        except ValueError as error:
            raise CommandError(str(error)) from error

        factories, failures = {}, 0
        for number, (scenario, engine, repeat) in enumerate(tasks, start=1):
            key = (scenario["menu"], engine)
            if key not in factories:
                factories[key] = harness.EngineFactory(engine, data["menus"][scenario["menu"]], engine_llm)
            before = dict(user.usage)
            record = harness.play(factories[key], scenario, harness.SimulatedUser(scenario, user), repeat)
            record["simulator"] = {field: user.usage[field] - before[field] for field in before}
            with open(output, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            if record["outcome"] == "error":
                self.stdout.write(self.style.WARNING(f"  {scenario['id']} {engine}#{repeat}: {record['error']}"))
            failures = failures + 1 if record["outcome"] == "error" else 0
            if failures == MAX_FAILURES:
                raise CommandError(f"세션 {MAX_FAILURES}개가 연달아 오류로 끝나 멈춥니다. 네트워크와 API 키를 확인하고 "
                                   "같은 명령으로 다시 실행하면, 오류 세션부터 이어서 합니다.")
            if number % 20 == 0 or number == len(tasks):
                self.stdout.write(f"  {number}/{len(tasks)} 세션")
        self.stdout.write(self.style.SUCCESS(f"저장 -> {output} (가상 사용자 호출 {user.usage['calls']}번)"))
