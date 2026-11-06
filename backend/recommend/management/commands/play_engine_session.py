# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""python manage.py play_engine_session --scenarios scenarios.json --output human.jsonl --tester NAME

The user study (P21): a person plays the engines in the terminal, on the scenario
file's menus, under the simulated user's setup. A tester plays STUDY_ROUNDS rounds, one
per situation (in_menu, multiple, not_in_menu, close_alternative), in turn from a
start chosen by the tester's name, the menus taken in turn. In each round the tester
picks what they really want that fits the situation, says how sure they are (the
certainty level; their answers are not blurred), and plays that same wish on every
engine of STUDY_ENGINES, in a blind order rotated from round to round. Questions are
asked in Korean.

Proposals are judged as the simulated user's are: a menu the tester picked is
accepted by the rule, next to a close alternative nothing else is, and otherwise the
person decides with the simulator's criterion (essentially the same dish; for a dish
that is not served, the same craving). After each session the tester rates the
result from 1 to 5.

Each run plays the rest of the current round; a stopped round continues with the
same wish, and a session that ended in an error is played again. Sessions are
stored like automated ones, so benchmark_engines --human reports them, and
validate_simulator can ask the simulated user the same questions.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import random

from django.core.management.base import BaseCommand, CommandError

from menus.features.schema import FEATURE_VERSION
from menus.models import Food
from menus.normalize import dish_key
from question_engines.benchmark import CERTAINTY, SITUATIONS, STUDY_ENGINES, STUDY_ROUNDS, harness, scenarios
from question_engines.llm.config import LLMConfigError, LLMSettings, build_llm

from .benchmark_engines import read_lines

LANGUAGE = "ko"
PICK = {
    "in_menu": "오늘 메뉴 중 지금 가장 먹고 싶은 메뉴 하나의 번호를 적으세요.",
    "multiple": "오늘 메뉴 중 똑같이 좋은 서로 다른 메뉴 2~3개의 번호를 쉼표로 적으세요.",
    "not_in_menu": "오늘 메뉴에 없는 음식 중 지금 먹고 싶은 음식 이름을 적으세요.",
    "close_alternative": "아래 메뉴에는 특징이 거의 같은 메뉴가 함께 나옵니다. 그중 먹고 싶은 메뉴 하나의 번호를 적으세요. "
                         "이 라운드에서는 고른 그 메뉴만 받아들인 것으로 기록합니다.",
}
SURE = {"high": "확실하다: 바로 그것이 먹고 싶다",
        "medium": "대체로: 끌리지만 질문에 따라 흔들릴 수 있다",
        "low": "애매하다: 어떤 질문은 답하기 어렵다"}
SAME_DISH = ("고른 메뉴와 사실상 같은 음식(같은 종류, 같은 주재료)이라 똑같이 만족할 때만 y. "
             "비슷하거나 든든하거나 맛있어 보여도 다른 음식이면 n.")
INSTEAD = ("먹고 싶은 음식 대신 같은 욕구를 채워 줄 때만 y (생선가스 대신 돈가스는 y, 짜장면은 n). "
           "여러 개를 적었다면 그중 하나를 대신하면 됩니다.")


class HumanUser:
    """Answers and judges like harness.SimulatedUser, with a person in place of the simulator."""

    def __init__(self, scenario, ask, write):
        self.scenario, self.ask, self.write = scenario, ask, write

    def answer(self, step, repeat):
        self.write(f"\nQ{step['question_count'] + 1}. {step['text']}")
        self.write("  ".join(f"{number}) {option['label']}" for number, option in enumerate(step["options"], start=1)))
        while True:
            text = self.ask("> ").strip()
            if text.isdigit() and 1 <= int(text) <= len(step["options"]):
                return {"answer": step["options"][int(text) - 1]["id"]}

    def judge(self, step):
        self.write(f"\n제안: {_label(step['food'])}")
        if harness.accepted_by_rule(self.scenario, step):
            self.write("고른 메뉴라서 받아들인 것으로 기록합니다.")
            return {"accepted": True, "judged_by": "rule"}
        if self.scenario["situation"] == "close_alternative":
            self.write("고른 메뉴가 아니라서 거절한 것으로 기록합니다.")
            return {"accepted": False, "judged_by": "rule_only"}
        while True:
            text = self.ask("이걸로 할까요? (y/n) > ").strip().lower()
            if text in ("y", "n"):
                return {"accepted": text == "y", "judged_by": "person"}


def _seed(tester) -> int:
    return int(hashlib.sha256(tester.encode()).hexdigest(), 16)


def situations(tester) -> list[str]:
    """The tester's STUDY_ROUNDS situations, each once, from a start chosen by the name."""
    start = _seed(tester) % len(SITUATIONS)
    return [SITUATIONS[(start + i) % len(SITUATIONS)] for i in range(STUDY_ROUNDS)]


def engine_order(tester, number) -> list[str]:
    """The blind order of round `number`: the tester's shuffle, rotated by one each round."""
    order = list(STUDY_ENGINES)
    random.Random(_seed(tester)).shuffle(order)
    shift = number % len(order)
    return order[shift:] + order[:shift]


def _label(candidate) -> str:
    places = dict.fromkeys(f"{o['restaurant']} {o['price'] if o['price'] is not None else '?'}원"
                           for o in candidate.get("offers", []))
    return f"{candidate['display_name']} ({', '.join(places)})" if places else candidate["display_name"]


def _numbers(text, count, low, high) -> list[int] | None:
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if not all(p.isdigit() for p in parts) or not low <= len(set(parts)) == len(parts) <= high:
        return None
    numbers = [int(p) for p in parts]
    return numbers if all(1 <= n <= count for n in numbers) else None


def choose_targets(situation, candidates, ask, write) -> list[dict]:
    """The wanted menus a person picks for `situation`, made as scenarios.py makes them."""
    picks = scenarios.choices(candidates)
    close = {}
    if situation == "close_alternative":
        for pick in picks:
            names = scenarios.close_to(scenarios.menu_target(pick, candidates), pick, picks)
            if names:
                close[pick["food_id"]] = names
        picks = [pick for pick in picks if pick["food_id"] in close]
    write("")
    for number, pick in enumerate(picks, start=1):
        similar = f"  ~ 비슷한 메뉴: {', '.join(close[pick['food_id']])}" if close else ""
        write(f"{number:3}) {_label(pick)}{similar}")
    write(f"\n{PICK[situation]}")
    while True:
        text = ask("> ").strip()
        if situation == "not_in_menu":
            if not text:
                continue
            key = dish_key(text)
            served = [c["display_name"] for c in picks
                      if any(key and key in dish_key(name) for name in (c["name"], c["display_name"]))]
            if served:
                write(f"오늘 메뉴에 있습니다: {', '.join(served[:5])}. 메뉴에 없는 음식을 적으세요.")
                continue
            food = Food.objects.filter(name=text, is_food=True, feature_version=FEATURE_VERSION).first()
            return [scenarios.target(text, food.features if food else None, food.food_group if food else "",
                                     candidates)]
        low, high = (2, 3) if situation == "multiple" else (1, 1)
        numbers = _numbers(text, len(picks), low, high)
        if numbers:
            made = [scenarios.menu_target(picks[n - 1], candidates) for n in numbers]
            if situation == "close_alternative":
                made[0]["close"] = close[picks[numbers[0] - 1]["food_id"]]
            return made


def choose_certainty(ask, write) -> str:
    write("\n지금 먹고 싶은 것이 얼마나 확실한가요?")
    for number, level in enumerate(CERTAINTY, start=1):
        write(f"  {number}) {SURE[level]}")
    while True:
        text = ask("> ").strip()
        if text.isdigit() and 1 <= int(text) <= len(CERTAINTY):
            return CERTAINTY[int(text) - 1]


class Command(BaseCommand):
    help = "Play the next user-study round by hand: one wish on every engine, blind."

    def add_arguments(self, parser):
        parser.add_argument("--scenarios", required=True, help="the benchmark's scenario file (its menus)")
        parser.add_argument("--output", required=True, help="human sessions file (JSON lines), appended to")
        parser.add_argument("--tester", required=True)

    def handle(self, *args, **options):
        data = scenarios.load(options["scenarios"])
        tester, ask, write = options["tester"], input, self.stdout.write
        output = pathlib.Path(options["output"])
        output.parent.mkdir(parents=True, exist_ok=True)
        mine = [r for r in (read_lines([output]) if output.exists() else []) if r.get("tester") == tester]
        played = {(r["scenario_data"]["round"], r["engine"]) for r in mine if r["outcome"] != "error"}
        number = next((n for n in range(STUDY_ROUNDS) if any((n, e) not in played for e in STUDY_ENGINES)), None)
        if number is None:
            write(self.style.SUCCESS(f"{tester}: {STUDY_ROUNDS}라운드를 모두 마쳤습니다. 감사합니다."))
            return
        left = [e for e in engine_order(tester, number) if (number, e) not in played]
        llm = None
        if "llm" in left:
            try:
                llm = build_llm(LLMSettings.from_env())
            except LLMConfigError as error:
                raise CommandError(str(error)) from error

        scenario = next((r["scenario_data"] for r in reversed(mine) if r["scenario_data"]["round"] == number), None)
        if scenario is None:
            situation = situations(tester)[number]
            keys = sorted(data["menus"])
            key = keys[number % len(keys)]
            menu = data["menus"][key]
            write(f"라운드 {number + 1}/{STUDY_ROUNDS}: {menu['date']} {menu['meal']} 메뉴 {len(menu['candidates'])}개")
            targets = choose_targets(situation, menu["candidates"], ask, write)
            scenario = {"id": f"human-{tester}-r{number + 1}", "situation": situation,
                        "certainty": choose_certainty(ask, write), "menu": key, "targets": targets, "round": number}
        else:
            write(f"라운드 {number + 1}/{STUDY_ROUNDS}를 이어서 합니다.")
        write(f"\n이번 라운드에서 원하는 것: {', '.join(t['name'] for t in scenario['targets'])}. "
              f"이것을 원하는 사람으로서, 세션마다 처음부터 솔직하게 답하세요. 앞 세션의 결과는 잊으세요.")
        write(f"제안 판정: {INSTEAD if scenario['situation'] == 'not_in_menu' else SAME_DISH}")

        menu = data["menus"][scenario["menu"]]
        for position, engine in enumerate(left, start=len(STUDY_ENGINES) - len(left) + 1):
            write(f"\n== 세션 {position}/{len(STUDY_ENGINES)} (질문에 번호로 답하세요)")
            factory = harness.EngineFactory(engine, menu, llm, language=LANGUAGE)
            record = harness.play(factory, scenario, HumanUser(scenario, ask, write))
            final = next((c for c in menu["candidates"] if c["food_id"] == record["final_food_id"]), None)
            if record["outcome"] == "error":
                write(self.style.ERROR("세션이 오류로 끝났습니다. 다시 실행하면 이 세션을 다시 합니다."))
                satisfaction = None
            else:
                write(f"\n결과: {final['display_name'] if final else '추천 없음'}")
                while (text := ask("이 세션 만족도 1~5 > ").strip()) not in {"1", "2", "3", "4", "5"}:
                    pass
                satisfaction = int(text)
            record.update(tester=tester, satisfaction=satisfaction, scenario_data=scenario)
            with open(output, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            if record["outcome"] == "error":
                return
        self.stdout.write(self.style.SUCCESS(f"라운드 {number + 1}/{STUDY_ROUNDS} 저장 -> {output} "
                                             "(엔진은 결과 파일에만 기록됩니다)"))
