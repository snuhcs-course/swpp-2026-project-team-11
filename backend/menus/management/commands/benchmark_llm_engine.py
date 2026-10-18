"""Run the LLM engine against LLM-simulated users and judge its questions."""
import datetime
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from menus.services import get_candidates
from question_engines.llm import LLMConfigError, LLMSettings
from question_engines.llm.config import build_llm
from question_engines.llm.evaluation import run_benchmark

USER_MODEL = "anthropic/claude-haiku-5.5"  # another model family than the engine's


class Command(BaseCommand):
    help = "Benchmark the LLM engine on synthetic users (needs OPENROUTER_API_KEY; about $0.015 per trial)."

    def add_arguments(self, parser):
        parser.add_argument("--date", required=True, type=datetime.date.fromisoformat)
        parser.add_argument("--meal", choices=["BR", "LU", "DN"], default="LU")
        parser.add_argument("--trials", type=int, default=20)
        parser.add_argument("--seed", type=int, default=20261016)
        parser.add_argument("--max-questions", type=int, default=10, help="0: no limit, like the server default")
        parser.add_argument("--max-guesses", type=int, default=3)
        parser.add_argument("--user-model", default=USER_MODEL, help="plays the user")
        parser.add_argument("--judge-model", help="flags repeated questions (3 votes per trial); "
                                                  "omit it to read the transcripts yourself")
        parser.add_argument("--workers", type=int, default=5)
        parser.add_argument("--output", type=Path)

    def handle(self, *args, **options):
        try:
            settings = LLMSettings.from_env()
            user_llm = build_llm(LLMSettings(settings.api_key, options["user_model"], settings.timeout_s))
            judge_llm = (build_llm(LLMSettings(settings.api_key, options["judge_model"], 60))
                         if options["judge_model"] else None)
            report = run_benchmark(
                get_candidates(options["date"], options["meal"]), build_llm(settings), user_llm, judge_llm,
                trials=options["trials"], seed=options["seed"], max_questions=options["max_questions"] or None,
                max_guesses=options["max_guesses"], workers=options["workers"])
        except (LLMConfigError, ValueError) as error:
            raise CommandError(str(error)) from error
        report["config"].update(date=options["date"].isoformat(), meal=options["meal"],
                                engine_model=settings.model, user_model=options["user_model"],
                                judge_model=options["judge_model"])
        self.stdout.write(json.dumps({"prompt_sha256": report["prompt_sha256"], **report["summary"]}, indent=2))
        if options["output"]:
            options["output"].parent.mkdir(parents=True, exist_ok=True)
            options["output"].write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
