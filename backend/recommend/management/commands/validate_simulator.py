# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""python manage.py validate_simulator --human human.jsonl --output simulator_check.jsonl

Ask the simulated user every question people answered in play_engine_session,
as someone who wanted what that person wanted, and whether it would take each
proposal people judged that the name rule does not accept (the verdicts it gives
in the benchmark). benchmark_engines --simulator-check then reports how often they
agree: the evidence for trusting the automated benchmark. Answers are cached, so a
rerun asks nothing twice.
"""

from __future__ import annotations

import json
import pathlib

from django.core.management.base import BaseCommand, CommandError

from question_engines.benchmark import scenarios, simulator

from .benchmark_engines import read_lines


class Command(BaseCommand):
    help = "Ask the simulated user the questions people answered, for the benchmark report."

    def add_arguments(self, parser):
        parser.add_argument("--human", nargs="+", required=True)
        parser.add_argument("--output", required=True)
        parser.add_argument("--simulator-cache", default=None)

    def handle(self, *args, **options):
        sessions = read_lines(options["human"])
        questions = sum(1 for s in sessions for step in s["trace"] if "question" in step)
        if not questions:
            raise CommandError("사람이 답한 질문이 없습니다.")
        try:
            user = simulator.Simulator(simulator.build_llm(), options["simulator_cache"])
        except Exception as error:
            raise CommandError(f"가상 사용자 모델을 만들 수 없습니다: {error}") from error
        rows = []
        for session in sessions:
            persona = simulator.describe(session["scenario_data"])
            served = session["scenario_data"]["situation"] != "not_in_menu"
            for step in session["trace"]:
                row = {"session": session["scenario"], "engine": session["engine"]}
                if "question" in step:
                    rows.append(row | {"question": step["question"], "human": step["answer"],
                                       "simulator": user.answer(persona, step["question"])})
                elif not scenarios.is_wanted(session["scenario_data"], step["proposal"], step["group"]):
                    rows.append(row | {"proposal": step["label"], "human": step["accepted"],
                                       "simulator": user.takes(persona, step["label"], served)})
        pathlib.Path(options["output"]).write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
        verdicts = sum("proposal" in row for row in rows)
        self.stdout.write(self.style.SUCCESS(f"질문 {len(rows) - verdicts}개, 제안 판정 {verdicts}개 "
                                             f"(가상 사용자 호출 {user.usage['calls']}번) -> {options['output']}"))
