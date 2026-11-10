"""Compare group mode with separate sessions aggregated by Nash welfare, on a day's menu.

The first run freezes the cases in DIR/cases.json and stops, so they can be committed
before any result exists. Later runs play those cases. `--simulator llm` calls the
simulated user's paid model (METCHU_SIMULATOR_MODEL); its answers are cached in
DIR/answers.jsonl, so a rerun asks nothing twice.
"""
import datetime
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from menus.services import get_catalog
from question_engines.benchmark.simulator import PROMPT_ID, Simulator, build_llm, describe
from question_engines.decision_tree.catalog import CandidateCatalog
from question_engines.group.evaluation import ALLERGIES, build_cases, compare, oracle


class Command(BaseCommand):
    help = "Run the paired group-mode benchmark (--simulator llm calls a paid model)."

    def add_arguments(self, parser):
        parser.add_argument("--date", required=True, type=datetime.date.fromisoformat)
        parser.add_argument("--meal", choices=["BR", "LU", "DN"], default="LU")
        parser.add_argument("--dir", required=True, type=Path, help="holds cases.json and the results")
        parser.add_argument("--simulator", choices=["oracle", "llm"], default="oracle")
        parser.add_argument("--groups", type=int, default=6, help="cases per situation and size, when freezing")
        parser.add_argument("--seed", type=int, default=20261110)
        parser.add_argument("--workers", type=int, default=8)

    def handle(self, *args, **options):
        date, meal, folder = options["date"], options["meal"], options["dir"]
        rows, schema = get_catalog(date, meal)
        if not rows:
            raise CommandError(f"No {meal} menu on {date}; load its snapshot first")
        safe = {key: {c["food_id"] for c in get_catalog(date, meal, frozenset({key}))[0]} for key in ALLERGIES}
        catalog = CandidateCatalog(rows, schema)
        frozen = folder / "cases.json"
        if not frozen.exists():
            cases = build_cases(catalog, safe, groups=options["groups"], seed=options["seed"])
            folder.mkdir(parents=True, exist_ok=True)
            _write(frozen, {"date": date.isoformat(), "meal": meal, "seed": options["seed"],
                            "catalog": catalog.fingerprint, "cases": cases})
            self.stdout.write(f"Froze {len(cases)} cases in {frozen}; commit them, then run again.")
            return
        data = json.loads(frozen.read_text(encoding="utf-8"))
        if data["catalog"] != catalog.fingerprint:
            raise CommandError("This menu differs from the one the cases were frozen on")
        if options["simulator"] == "llm":
            simulator = Simulator(build_llm(), folder / "answers.jsonl")
            names = {row["food_id"]: row["display_name"] for row in rows}

            def respond(case_no, member_no, target, step):
                return simulator.answer(describe({"targets": [{"name": names[target]}]}), step["text"])
        else:
            respond = oracle(catalog, data["seed"])
        report = compare(rows, schema, safe, data["cases"], respond, workers=options["workers"])
        report["config"] |= {"date": date.isoformat(), "meal": meal, "simulator": options["simulator"]}
        if options["simulator"] == "llm":
            report["config"] |= {"simulator_model": simulator.model, "simulator_prompt_id": PROMPT_ID}
            report["simulator_usage"] = simulator.usage
        _write(folder / f"{options['simulator']}.json", report)
        self.stdout.write(json.dumps({s: {k: v for k, v in row.items() if k != "by_size"}
                                      for s, row in report["summary"].items()}, indent=2))


def _write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
