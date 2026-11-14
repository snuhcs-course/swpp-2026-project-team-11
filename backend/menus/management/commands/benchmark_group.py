"""Compare group mode with separate sessions aggregated by Nash welfare, on one meal's menus.

`--source cafeteria` reads the day's cafeteria menus; `--source general` the restaurants
near the stations. The first run freezes the cases in DIR/cases.json and stops, so they
can be committed before any result exists. Later runs play those cases.
`--simulator llm` calls the simulated user's paid model (METCHU_SIMULATOR_MODEL); its
answers are cached in DIR/answers.jsonl, so a rerun asks nothing twice.

An allergic member can eat an offer (a menu at one restaurant) when the catalog without
that allergen keeps it. That catalog merges equivalent menus again, under other food IDs,
so its offers are matched to the full catalog's by menu title, features and offer. The
frozen cases record a digest of these restrictions, and a replay checks it.
"""
import datetime
import hashlib
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from menus.offers import safe_offers
from menus.services import get_catalog, get_store_catalog
from question_engines.benchmark.simulator import PROMPT_ID, Simulator, build_llm, describe
from question_engines.decision_tree.catalog import CandidateCatalog
from question_engines.group.evaluation import ALLERGIES, build_cases, compare, oracle


class Command(BaseCommand):
    help = "Run the paired group-mode benchmark (--simulator llm calls a paid model)."

    def add_arguments(self, parser):
        parser.add_argument("--source", choices=["cafeteria", "general"], default="cafeteria")
        parser.add_argument("--date", type=datetime.date.fromisoformat, help="the cafeteria day")
        parser.add_argument("--meal", choices=["BR", "LU", "DN"], default="LU")
        parser.add_argument("--dir", required=True, type=Path, help="holds cases.json and the results")
        parser.add_argument("--simulator", choices=["oracle", "llm"], default="oracle")
        parser.add_argument("--groups", type=int, default=6, help="cases per situation and size, when freezing")
        parser.add_argument("--seed", type=int, default=20261110)
        parser.add_argument("--workers", type=int, default=8)

    def handle(self, *args, **options):
        source, date, meal, folder = options["source"], options["date"], options["meal"], options["dir"]
        if source == "cafeteria" and date is None:
            raise CommandError("학식 메뉴에는 --date가 필요합니다")

        def menus(allergies=frozenset()):
            return (get_catalog(date, meal, allergies) if source == "cafeteria"
                    else get_store_catalog(meal, allergies))

        rows, schema = menus()
        if not rows:
            raise CommandError(f"{source} {meal} 메뉴가 없습니다. 먼저 데이터를 불러오세요")
        safe = {key: _safe_offers(rows, menus(frozenset({key}))[0]) for key in ALLERGIES}
        restrictions = hashlib.sha256(json.dumps({key: sorted(json.dumps(o, ensure_ascii=False) for o in offers)
                                                  for key, offers in safe.items()}).encode()).hexdigest()
        catalog = CandidateCatalog(rows, schema)
        frozen = folder / "cases.json"
        if not frozen.exists():
            cases = build_cases(catalog, safe, groups=options["groups"], seed=options["seed"])
            folder.mkdir(parents=True, exist_ok=True)
            _write(frozen, {"source": source, "date": date and date.isoformat(), "meal": meal,
                            "seed": options["seed"], "catalog": catalog.fingerprint, "restrictions": restrictions,
                            "cases": cases})
            self.stdout.write(f"케이스 {len(cases)}개를 {frozen}에 고정했습니다. 커밋한 뒤 다시 실행하세요.")
            return
        data = json.loads(frozen.read_text(encoding="utf-8"))
        if data["catalog"] != catalog.fingerprint:
            raise CommandError("케이스를 고정한 메뉴와 지금 메뉴가 다릅니다")
        if data.get("restrictions") != restrictions:
            raise CommandError("케이스를 고정한 알레르기 제한과 지금 제한이 다릅니다")
        if options["simulator"] == "llm":
            simulator = Simulator(build_llm(), folder / "answers.jsonl")
            names = {row["food_id"]: row["display_name"] for row in rows}

            def respond(case_no, member_no, target, step):
                return simulator.answer(describe({"targets": [{"name": names[target]}]}), step["text"])
        else:
            respond = oracle(catalog, data["seed"])
        report = compare(rows, schema, safe, data["cases"], respond, workers=options["workers"])
        report["config"] |= {"source": source, "date": data["date"], "meal": meal, "simulator": options["simulator"]}
        if options["simulator"] == "llm":
            report["config"] |= {"simulator_model": simulator.model, "simulator_prompt_id": PROMPT_ID}
            report["simulator_usage"] = simulator.usage
        _write(folder / f"{options['simulator']}.json", report)
        self.stdout.write(json.dumps({s: {k: v for k, v in row.items() if k != "by_size"}
                                      for s, row in report["summary"].items()}, indent=2))


def _safe_offers(rows, safe_rows):
    try:
        return safe_offers(rows, safe_rows)
    except ValueError as error:
        raise CommandError("알레르기 제외 메뉴의 판매처를 전체 메뉴에서 하나로 찾을 수 없습니다") from error


def _write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
