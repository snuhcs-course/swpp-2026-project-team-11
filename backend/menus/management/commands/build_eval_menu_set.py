# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""python manage.py build_eval_menu_set --output menu_set.json [--start D] [--end D]

Collect the dishes to benchmark feature extraction on from many past days, split
into invariant dishes (the fixed-menu catalog) and variant dishes (lines that
change from day to day). See menus/features/benchmark/menu_set.py.

Each line is preprocessed like fetch_menus does it. Catalog lines need no LLM;
the other lines are sent to the preprocessing LLM once and cached in MenuLine,
so a rebuild over the same days is free. --dry-run prints how many lines would
be sent. Without a key (or with --no-llm) a new line stays one dish.

Then: collect_feature_runs --menu-set menu_set.json
"""

from __future__ import annotations

import datetime
import json
import pathlib
from collections import Counter

from django.core.management.base import BaseCommand
from django.utils import timezone

from menus import llm as menu_llm
from menus.features.benchmark import menu_set
from menus.features.extractor import api_key_available
from menus.management.commands.fetch_menus import menu_lines
from menus.preprocess import fixed, mapper
from menus.sources import siksha


class Command(BaseCommand):
    help = "Collect invariant and variant dishes from a menu history for the feature benchmark."

    def add_arguments(self, parser):
        parser.add_argument("--output", required=True)
        parser.add_argument("--end", type=datetime.date.fromisoformat, default=None,
                            help="last day (default: yesterday in Asia/Seoul)")
        parser.add_argument("--start", type=datetime.date.fromisoformat, default=None,
                            help="first day (default: 27 days before --end)")
        parser.add_argument("--from-json", default=None,
                            help="read a saved Siksha payload instead of downloading")
        parser.add_argument("--no-llm", action="store_true",
                            help="do not call the preprocessing LLM; new lines stay one dish")
        parser.add_argument("--dry-run", action="store_true", help="print the plan and stop")

    def handle(self, *args, **options):
        end = options["end"] or timezone.localdate() - datetime.timedelta(days=1)
        start = options["start"] or end - datetime.timedelta(days=27)
        if options["from_json"]:
            payload = json.loads(pathlib.Path(options["from_json"]).read_text(encoding="utf-8"))
        else:
            self.stdout.write(f"Siksha {start} ~ {end} 다운로드 중...")
            payload = siksha.fetch_days(start, end)
        records = [r for r in siksha.parse(payload) if start <= r.date <= end]

        catalog = fixed.load_catalog()
        lines = menu_lines(records)
        pending = menu_set.lines_to_resolve(lines, catalog)
        self.stdout.write(f"{len({r.date for r in records})}일, 메뉴 줄 {len(lines)}개 중 새로 전처리할 줄 "
                          f"{pending}개 -> 전처리 LLM 호출 약 {menu_set.preprocessing_calls(pending)}번")
        if options["dry_run"]:
            return

        llm = None
        if pending and not options["no_llm"]:
            if api_key_available():
                llm = mapper.build_llm()
            else:
                self.stdout.write(f"{menu_llm.key_name()}가 없어 새 메뉴 줄은 LLM 없이 한 덩어리로 둡니다.")
        mappings = mapper.map_lines(lines, llm, on_progress=self.stdout.write)
        result = menu_set.build(records, mappings, catalog)
        menu_set.save(options["output"], result)

        variant = result["variant"]
        repeated = sum(1 for dish in variant if dish["days"] > 1)
        unresolved = sum(1 for dish in variant if dish["source"] == "rule")
        self.stdout.write(self.style.SUCCESS(
            f"invariant {len(result['invariant'])}개 / variant {len(variant)}개 "
            f"(하루만 나온 요리 {len(variant) - repeated}, 여러 날 {repeated}) -> {options['output']}"))
        if unresolved:
            self.stdout.write(self.style.WARNING(
                f"전처리 LLM 답이 없어 줄 그대로인 variant {unresolved}개: 키를 넣고 다시 실행하세요."))
        sources = Counter(m.source for m in mappings.values())
        self.stdout.write(f"메뉴 줄 출처: {', '.join(f'{k} {v}' for k, v in sorted(sources.items()))}")
