# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""Run the P13/P14 LLM engine against a dated cafeteria candidate set (API key needed)."""
import datetime
import json
from pathlib import Path
import time

from django.core.management.base import BaseCommand, CommandError

from menus.services import get_candidates
from question_engines.llm import LLMConfigError, LLMEngine


class Command(BaseCommand):
    help = "Run an interactive or automated LLM question-engine demo."

    def add_arguments(self, parser):
        parser.add_argument("--date", required=True, type=datetime.date.fromisoformat)
        parser.add_argument("--meal", choices=["BR", "LU", "DN"], default="LU")
        parser.add_argument("--max-questions", type=int, default=10)
        parser.add_argument("--smoke", action="store_true", help="Exercise answer, rejection and acceptance without input")
        parser.add_argument("--output", type=Path, help="Save steps, timings, diagnostics and a replayable snapshot")

    def handle(self, *args, **options):
        rows = get_candidates(options["date"], options["meal"])
        try:
            engine = LLMEngine(rows, config={"max_questions": options["max_questions"]})
        except (LLMConfigError, ValueError) as error:
            raise CommandError(str(error)) from error
        events = []

        def act(name, method, *values):
            calls_before = len(engine.diagnostics()["llm_calls"])
            tick = time.perf_counter()
            result = method(*values)
            events.append({"action": name, "elapsed_ms": (time.perf_counter() - tick) * 1000, "step": result})
            calls = engine.diagnostics()["llm_calls"]
            if len(calls) > calls_before:  # undo and accepting a guess make no LLM call
                note = f", fallback: {calls[-1]['fallback']}" if calls[-1]["fallback"] else ""
                self.stdout.write(f"  [LLM {calls[-1]['latency_ms']} ms{note}]")
            return result

        try:
            step = act("start", engine.start)
            if options["smoke"]:
                if step["type"] == "question":
                    step = act("answer", engine.answer, step["question_id"], "any")
                if step["type"] != "unavailable":
                    step = act("recommend_now", engine.recommend_now)
                    step = act("reject", engine.feedback, step["guess_id"], False)
                if step["type"] != "unavailable":
                    step = act("recommend_now", engine.recommend_now)
                    step = act("accept", engine.feedback, step["guess_id"], True)
                self.stdout.write(json.dumps({"final_step": step, "diagnostics": engine.diagnostics()},
                                             ensure_ascii=False, indent=2))
            else:
                step = self.play(engine, step, act)
        except (ValueError, EOFError) as error:
            raise CommandError(str(error)) from error

        if options["output"]:
            options["output"].parent.mkdir(parents=True, exist_ok=True)
            options["output"].write_text(json.dumps({
                "context": {"date": options["date"].isoformat(), "meal": options["meal"]},
                "events": events, "diagnostics": engine.diagnostics(), "snapshot": engine.snapshot(),
            }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def play(self, engine, step, act):
        while step["type"] in {"question", "guess"}:
            self.stdout.write(step["text"])
            if step["type"] == "question":
                for index, option in enumerate(step["options"], 1):
                    self.stdout.write(f"{index}. {option['label']}")
                choice = input("Number / u undo / g recommend now / x exit: ").strip().lower()
                if choice.isdigit() and 1 <= int(choice) <= len(step["options"]):
                    step = act("answer", engine.answer, step["question_id"], step["options"][int(choice) - 1]["id"])
                    continue
            else:
                self.stdout.write(step["food"]["display_name"])
                choice = input("y accept / n another menu / u undo / x exit: ").strip().lower()
                if choice in {"y", "n"}:
                    step = act("feedback", engine.feedback, step["guess_id"], choice == "y")
                    continue
            if choice == "x":
                return step
            if choice == "u":
                step = act("undo", engine.undo)
            elif choice == "g" and step["type"] == "question":
                step = act("recommend_now", engine.recommend_now)
            else:
                self.stdout.write("Choose one of the displayed options.")

        if step["type"] == "recommendation":
            self.stdout.write(self.style.SUCCESS(f"Recommended meal: {step['food']['display_name']}"))
            for offer in step["food"]["offers"]:
                self.stdout.write(f"{offer['restaurant']} / {offer['meal']} / {offer['price']}")
        else:
            self.stdout.write(step["text"])
        diagnostics = engine.diagnostics()
        self.stdout.write(f"Questions: {diagnostics['question_count']}, LLM time: {diagnostics['llm_latency_ms']} ms, "
                          f"fallbacks: {diagnostics['fallback_count']}")
        return step
