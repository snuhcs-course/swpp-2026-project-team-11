# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""python manage.py collect_feature_runs --output runs.jsonl --condition repeat [--repeats 3]

Extract the same dishes several times and store every answer, so benchmark_features
can run without calling the LLM again. This is the only benchmark step that costs
API calls; --dry-run prints how many. Run it once per condition (runs.py):
repeat, shuffle_foods, shuffle_features. Runs already in --output are skipped, so a
stopped collection continues where it stopped; a run made with another model or prompt
is refused instead of being mixed in.

Dishes come from --menu-set (build_eval_menu_set, marked variant or invariant) or
from one day in the database (--date, marked by the fixed-menu catalog), plus the
dishes of the triplet file. --limit samples the variant dishes and
--invariant-limit the invariant ones, spread over cafeterias or food groups.

--stored copies the v2 features the database already holds for --date as one run,
with no LLM call: enough for the integrity and distribution sections. It carries
meal_variety (33 keys), so it goes in a file of its own.
"""

from __future__ import annotations

import datetime
import pathlib

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from menus import llm as menu_llm
from menus.features import extractor, prompt
from menus.features.benchmark import menu_set, runs, triplets
from menus.features.schema import FEATURE_VERSION
from menus.models import Food


def stored_foods(date) -> list[Food]:
    return list(Food.objects.filter(menu_items__date=date, is_food=True).distinct().order_by("name", "is_set"))


def menu_dishes(options) -> dict[str, dict]:
    """{dish name: {"source": variant | invariant, "group": for sampling}}."""
    if options["menu_set"]:
        data = menu_set.load(options["menu_set"])
        return {dish["name"]: {"source": kind, "group": (dish["restaurants"] or [""])[0]}
                for kind in (runs.VARIANT, runs.INVARIANT) for dish in data[kind]}
    fixed_dishes = menu_set.catalog_dishes()
    return {food.name: {"source": menu_set.segment(food.name, fixed_dishes), "group": food.food_group}
            for food in stored_foods(options["date"] or timezone.localdate())}


def existing(output) -> list[runs.Record]:
    return runs.load(output) if output.exists() else []


def check_resume(records, plan, model) -> None:
    """Refuse to continue runs that an earlier collection made with another model or prompt."""
    if any(r.condition == runs.STORED for r in records):
        raise CommandError("이 파일에는 --stored 기록이 있습니다. LLM 추출은 다른 --output에 저장하세요.")
    expected = {run: runs.prompt_hash(prompt.build_system_prompt(features)) for run, _, features in plan}
    for record in records:
        if record.run in expected and (record.model, record.prompt_hash) != (model, expected[record.run]):
            raise CommandError(f"{record.run}은 다른 설정(모델 {record.model}, 프롬프트 {record.prompt_hash})으로 "
                               f"추출됐습니다. 지금 설정(모델 {model}, 프롬프트 {expected[record.run]})으로 이어서 "
                               "추출할 수 없으니 다른 --output을 쓰세요.")


def sample(dishes, source, limit, seed) -> list[str]:
    names = sorted(name for name, dish in dishes.items() if dish["source"] == source)
    if limit is None:
        return names
    return runs.stratified_sample(names, lambda name: dishes[name]["group"], limit, seed)


class Command(BaseCommand):
    help = "Extract dishes several times with the LLM and store the answers for benchmark_features."

    def add_arguments(self, parser):
        parser.add_argument("--output", required=True, help="runs file (JSON lines), appended to")
        parser.add_argument("--menu-set", default=None, help="dishes from build_eval_menu_set")
        parser.add_argument("--date", type=datetime.date.fromisoformat, default=None,
                            help="a day in the database (default: today in Asia/Seoul)")
        parser.add_argument("--stored", action="store_true",
                            help="copy the stored v2 features of --date as one run; no LLM call")
        parser.add_argument("--condition", choices=runs.CONDITIONS, default="repeat")
        parser.add_argument("--repeats", type=int, default=3)
        parser.add_argument("--batch-size", type=int, default=25)
        parser.add_argument("--limit", type=int, default=None, help="at most N variant dishes (default: all)")
        parser.add_argument("--invariant-limit", type=int, default=30,
                            help="at most N invariant dishes, as a reference (default: 30)")
        parser.add_argument("--triplets", default=None, help="triplet file whose dishes are added "
                            "(default: the AI draft in menus/features/benchmark/data)")
        parser.add_argument("--no-triplet-dishes", action="store_true")
        parser.add_argument("--seed", type=int, default=0)
        parser.add_argument("--dry-run", action="store_true", help="print the plan and stop")

    def handle(self, *args, **options):
        if options["menu_set"] and (options["date"] or options["stored"]):
            raise CommandError("--menu-set은 --date, --stored와 함께 쓸 수 없습니다.")
        if options["stored"]:
            return self.copy_stored(options)

        dishes = menu_dishes(options)
        source = {name: runs.VARIANT for name in sample(dishes, runs.VARIANT, options["limit"], options["seed"])}
        source |= {name: runs.INVARIANT
                   for name in sample(dishes, runs.INVARIANT, options["invariant_limit"], options["seed"])}
        if not options["no_triplet_dishes"]:
            fixed_dishes = menu_set.catalog_dishes()
            for name in triplets.names(triplets.load(options["triplets"])):
                source.setdefault(name, dishes.get(name, {}).get("source")
                                  or (runs.INVARIANT if name in fixed_dishes else runs.SUITE))
        names = sorted(source)
        if not names:
            raise CommandError("추출할 음식이 없습니다. --menu-set이나 --date를 확인하세요.")

        output = pathlib.Path(options["output"])
        records = existing(output)
        planned = runs.plan(names, options["condition"], options["repeats"], options["seed"])
        check_resume(records, planned, menu_llm.model_id())
        done = {(r.run, r.name) for r in records}
        plan = [(run, [n for n in order if (run, n) not in done], features) for run, order, features in planned]
        total = sum(runs.calls(todo, options["batch_size"]) for _, todo, _ in plan)
        counts = {kind: sum(s == kind for s in source.values()) for kind in (runs.VARIANT, runs.INVARIANT, runs.SUITE)}
        self.stdout.write(f"variant {counts['variant']}개 + invariant {counts['invariant']}개 + triplet용 "
                          f"{counts['suite']}개 = {len(names)}개, {options['condition']} x {options['repeats']}회 "
                          f"-> LLM 호출 약 {total}번")
        if options["dry_run"] or not total:
            return
        if not extractor.api_key_available():
            raise CommandError(f"{menu_llm.key_name()}가 없습니다. 레포 루트의 .env에 넣어 주세요.")

        llm = extractor.build_llm()
        for run, todo, features in plan:
            if not todo:
                continue
            system_prompt = prompt.build_system_prompt(features)
            self.stdout.write(f"[{run}] {len(todo)}개")
            results, failed = extractor.extract(todo, llm, batch_size=options["batch_size"],
                                                on_progress=self.stdout.write, system_prompt=system_prompt)
            # Saved run by run, so a stopped collection keeps its progress.
            new = []
            for name, item in results.items():
                values = item.features.model_dump()
                new.append(runs.Record(
                    run=run, condition=options["condition"], source=source[name], name=name,
                    means={k: v["mean"] for k, v in values.items()}, stds={k: v["std"] for k, v in values.items()},
                    group=dishes.get(name, {}).get("group", ""), model=menu_llm.model_id(),
                    prompt_hash=runs.prompt_hash(system_prompt)))
            runs.append(output, new)
            for name in failed:
                self.stdout.write(self.style.WARNING(f"  실패: {name}"))
        self.stdout.write(self.style.SUCCESS(f"저장 -> {output}"))

    def copy_stored(self, options):
        run = f"{runs.STORED}-0"
        records = existing(pathlib.Path(options["output"]))
        if any(r.condition != runs.STORED for r in records):
            raise CommandError("이 파일에는 LLM 추출 기록이 있습니다. --stored는 다른 --output에 저장하세요.")
        if any(r.run == run for r in records):
            self.stdout.write(f"{run}이 이미 있어 건너뜁니다 -> {options['output']}")
            return
        fixed_dishes = menu_set.catalog_dishes()
        foods = [f for f in stored_foods(options["date"] or timezone.localdate()) if f.feature_version == FEATURE_VERSION]
        if not foods:
            raise CommandError("그 날짜에 v2 feature가 저장된 음식이 없습니다.")
        runs.append(options["output"], [
            runs.Record(run=run, condition=runs.STORED,
                        source=menu_set.segment(food.name, fixed_dishes),
                        name=f"{food.name} (세트)" if food.is_set else food.name,
                        means=food.features, stds=food.feature_std, group=food.food_group,
                        model=food.extraction_model)
            for food in foods])
        self.stdout.write(self.style.SUCCESS(f"저장된 v2 feature {len(foods)}개 복사 (LLM 호출 없음) -> {options['output']}"))
