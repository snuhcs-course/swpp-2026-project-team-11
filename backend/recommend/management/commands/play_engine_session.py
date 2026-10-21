# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""python manage.py play_engine_session --scenarios scenarios.json --output human.jsonl --tester NAME

A person plays one session in the terminal, on a menu from the scenario file:
the user study. With --engine blind (the default) the engine is hidden, and each
tester plays SESSIONS_PER_ENGINE sessions on each engine in the order A B B A (A
chosen from the tester's name), so neither engine always comes first. The tester
first says what they want (or plays a scenario's wanted menu with --scenario),
answers the questions, judges the proposals, and rates the result from 1 to 5.

The session is stored like an automated one, so benchmark_engines --human reports
it, and validate_simulator can ask the simulated user the same questions.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import random

from django.core.management.base import BaseCommand, CommandError

from menus.models import Food
from question_engines.benchmark import ENGINES, harness, scenarios
from question_engines.benchmark.report import SESSIONS_PER_ENGINE
from question_engines.benchmark.simulator import ANSWER_IDS, ANSWER_LABELS
from question_engines.llm.config import LLMConfigError, LLMSettings, build_llm

from .benchmark_engines import read_lines


class HumanUser:
    def __init__(self, ask, write):
        self.ask, self.write = ask, write

    def answer(self, step, repeat):
        self.write(f"\nQ{step['question_count'] + 1}. {step['text']}")
        for number, answer in enumerate(ANSWER_IDS, start=1):
            self.write(f"  {number}) {ANSWER_LABELS[answer]}")
        while True:
            text = self.ask("> ").strip()
            if text.isdigit() and 1 <= int(text) <= len(ANSWER_IDS):
                return {"answer": ANSWER_IDS[int(text) - 1]}

    def judge(self, step):
        self.write(f"\n제안: {harness.proposal_text(step)}")
        while True:
            text = self.ask("이걸로 할까요? (y/n) > ").strip().lower()
            if text in ("y", "n"):
                return {"accepted": text == "y", "judged_by": "person"}


def wanted(names, menu) -> list[dict]:
    """Targets for what a tester typed, with features from the menu or the database."""
    targets = []
    candidates = menu["candidates"]
    for name in names:
        exact = next((c for c in candidates if name in (c["display_name"], c["name"])), None)
        food = exact or Food.objects.filter(name=name).exclude(features={}).values("features", "food_group").first()
        targets.append(scenarios.target(name, (food or {}).get("features"), (food or {}).get("food_group", ""),
                                        candidates))
    return targets


class Command(BaseCommand):
    help = "Play one engine session by hand and store it for the benchmark's user study."

    def add_arguments(self, parser):
        parser.add_argument("--scenarios", required=True)
        parser.add_argument("--output", required=True, help="human sessions file (JSON lines), appended to")
        parser.add_argument("--tester", required=True)
        parser.add_argument("--menu", default=None, help="menu id such as 2026-10-13/LU (default: the first)")
        parser.add_argument("--scenario", default=None, help="play this scenario's wanted menu")
        parser.add_argument("--engine", choices=(*ENGINES, "blind"), default="blind")

    def handle(self, *args, **options):
        data = scenarios.load(options["scenarios"])
        ask, write = input, self.stdout.write
        output = pathlib.Path(options["output"])
        if options["scenario"]:
            scenario = next((s for s in data["scenarios"] if s["id"] == options["scenario"]), None)
            if scenario is None:
                raise CommandError(f"시나리오 {options['scenario']}가 없습니다.")
            scenario = dict(scenario)
            write(f"이 세션에서 먹고 싶은 것: {', '.join(t['name'] for t in scenario['targets'])}")
        else:
            menu_key = options["menu"] or next(iter(data["menus"]))
            if menu_key not in data["menus"]:
                raise CommandError(f"메뉴 {menu_key}가 없습니다. 있는 메뉴: {', '.join(data['menus'])}")
            names = [n.strip() for n in ask("지금 먹고 싶은 메뉴 (여러 개면 쉼표로) > ").split(",") if n.strip()]
            if not names:
                raise CommandError("먹고 싶은 메뉴를 하나 이상 적어 주세요.")
            targets = wanted(names, data["menus"][menu_key])
            situation = ("multiple" if len(targets) > 1 else "in_menu" if targets[0]["matches"] else "not_in_menu")
            scenario = {"situation": situation, "certainty": "human", "menu": menu_key, "targets": targets}

        previous = read_lines([output]) if output.exists() else []
        mine = sum(r.get("tester") == options["tester"] for r in previous)
        engine = options["engine"]
        if engine == "blind":
            first = list(ENGINES)
            random.Random(hashlib.sha256(options["tester"].encode()).hexdigest()).shuffle(first)
            order = first * (SESSIONS_PER_ENGINE // 2) + first[::-1] * (SESSIONS_PER_ENGINE // 2)
            engine = order[mine % len(order)]
            write(f"세션 {mine % len(order) + 1}/{len(order)}")
        scenario["id"] = f"human-{options['tester']}-{mine + 1:02d}"
        llm = None
        if engine == "llm":
            try:
                llm = build_llm(LLMSettings.from_env())
            except LLMConfigError as error:
                raise CommandError(str(error)) from error

        menu = data["menus"][scenario["menu"]]
        write(f"\n{menu['date']} {menu['meal']}, 후보 {len(menu['candidates'])}개. 질문에 번호로 답하세요.")
        factory = harness.EngineFactory(engine, menu, llm)
        record = harness.play(factory, scenario, HumanUser(ask, write), anytime=())
        final = next((c for c in menu["candidates"] if c["food_id"] == record["final_food_id"]), None)
        write(f"\n결과: {final['display_name'] if final else '추천 없음'}")
        while True:
            text = ask("만족도 1~5 > ").strip()
            if text in {"1", "2", "3", "4", "5"}:
                break
        record.update(tester=options["tester"], satisfaction=int(text), scenario_data=scenario)
        with open(output, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        self.stdout.write(self.style.SUCCESS(f"저장 -> {output} (엔진은 결과 파일에만 기록됩니다)"))
