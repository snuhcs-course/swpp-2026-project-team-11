# AI-generated: written with OpenAI Codex and reviewed by the team.
"""Run the P10 engine against a dated cafeteria candidate set, without a key."""
import datetime
import json
from pathlib import Path
import time

from django.core.management.base import BaseCommand, CommandError

from menus.services import get_candidates, get_feature_schema
from question_engines.decision_tree import DecisionTreeEngine


class Command(BaseCommand):
    help = "Run an interactive or automated P10 cafeteria-engine demo."

    def add_arguments(self, parser):
        parser.add_argument("--date", required=True, type=datetime.date.fromisoformat)
        parser.add_argument("--meal", choices=["BR", "LU", "DN"], default="LU")
        parser.add_argument("--policy", choices=["greedy", "lookahead"], default="greedy")
        parser.add_argument("--smoke", action="store_true", help="Exercise answer, rejection and acceptance without input")
        parser.add_argument("--output", type=Path, help="Save steps, timings and a replayable snapshot")

    def handle(self, *args, **options):
        context = {"date": options["date"].isoformat(), "meal": options["meal"]}
        rows = get_candidates(options["date"], options["meal"])
        start = time.perf_counter()
        engine = DecisionTreeEngine(rows, get_feature_schema(), context=context, config={"policy": options["policy"]})
        step = engine.start()
        events = [{"action": "start", "elapsed_ms": (time.perf_counter() - start) * 1000, "step": step}]

        def act(name, method, *values):
            tick = time.perf_counter()
            result = method(*values)
            events.append({"action": name, "elapsed_ms": (time.perf_counter()-tick)*1000, "step": result})
            return result

        try:
            if options["smoke"]:
                if step["type"] == "question":
                    step = act("answer", engine.answer, step["question_id"], "any")
                if step["type"] != "unavailable":
                    step = act("recommend_now", engine.recommend_now)
                    step = act("reject", engine.feedback, step["guess_id"], False)
                if step["type"] != "unavailable":
                    step = act("recommend_now", engine.recommend_now)
                    step = act("accept", engine.feedback, step["guess_id"], True)
                self.stdout.write(json.dumps({"final_step": step, "question_count": engine.question_count,
                    "decision_ms": [e["elapsed_ms"] for e in events]}, ensure_ascii=False, indent=2))
            else:
                while step["type"] not in {"recommendation", "unavailable"}:
                    self.stdout.write(step["text"])
                    if step["type"] == "question":
                        for index, option in enumerate(step["options"], 1):
                            self.stdout.write(f"{index}. {option['label']}")
                        choice = input("Number / u undo / g recommend now / x exit: ").strip().lower()
                        if choice == "x":
                            break
                        if choice == "u":
                            step = act("undo", engine.undo)
                        elif choice == "g":
                            step = act("recommend_now", engine.recommend_now)
                        elif choice.isdigit() and 1 <= int(choice) <= len(step["options"]):
                            step = act("answer", engine.answer, step["question_id"], step["options"][int(choice)-1]["id"])
                        else:
                            self.stdout.write("Choose one of the displayed options.")
                    else:
                        label = step.get("group", step["food"])["display_name"]
                        self.stdout.write(label)
                        choice = input("y accept / n another menu / u undo / x exit: ").strip().lower()
                        if choice == "x":
                            break
                        if choice == "u":
                            step = act("undo", engine.undo)
                        elif choice in {"y", "n"}:
                            step = act("feedback", engine.feedback, step["guess_id"], choice == "y")
                        else:
                            self.stdout.write("Choose y or n.")
                if step["type"] == "recommendation":
                    self.stdout.write(f"Recommended meal: {step['food']['display_name']}")
                    for offer in step["food"]["offers"]:
                        self.stdout.write(f"{offer['restaurant']} / {offer['meal']} / {offer['price']}")
                elif step["type"] == "unavailable":
                    self.stdout.write(step["text"])
        except (ValueError, EOFError) as error:
            raise CommandError(str(error)) from error
        if options["output"]:
            options["output"].parent.mkdir(parents=True, exist_ok=True)
            options["output"].write_text(json.dumps({"context": context, "policy": options["policy"], "events": events,
                "diagnostics": engine.diagnostics(), "snapshot": engine.snapshot()}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
