# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""python manage.py build_fixed_menus [--start D] [--end D] [--review PATH] [--no-llm]

Find the menu lines each cafeteria serves (almost) every day, resolve each once,
and write menus/preprocess/fixed_menus.json. Review the CSV from --review, fix
fixed_menus.json where needed, and commit it: from then on those lines are
handled by rule, the same way in every database, without an LLM call.

Re-running keeps the entries already in the file (they may have been corrected
by hand) and drops lines no longer served, e.g. after a menu board changes.
"""

from __future__ import annotations

import datetime
import json
import pathlib

from django.core.management.base import BaseCommand
from django.utils import timezone

from menus.features.extractor import api_key_available
from menus.preprocess import fixed, mapper
from menus.preprocess.review import write_csv
from menus.sources import siksha


class Command(BaseCommand):
    help = "Build the fixed-menu catalog (menus/preprocess/fixed_menus.json) from menu history."

    def add_arguments(self, parser):
        parser.add_argument("--start", type=datetime.date.fromisoformat, default=None,
                            help="first day of history (default: 15 days before --end)")
        parser.add_argument("--end", type=datetime.date.fromisoformat, default=None,
                            help="last day of history (default: today in Asia/Seoul)")
        parser.add_argument("--from-json", default=None,
                            help="read a saved Siksha payload instead of downloading")
        parser.add_argument("--output", default=str(fixed.CATALOG_PATH))
        parser.add_argument("--review", default=None, help="also write a review CSV here")
        parser.add_argument("--no-llm", action="store_true")
        parser.add_argument("--fixed-overlap", type=float, default=0.9)
        parser.add_argument("--min-ratio", type=float, default=0.8)
        parser.add_argument("--recent-days", type=int, default=5)

    def handle(self, *args, **options):
        end = options["end"] or timezone.localdate()
        start = options["start"] or end - datetime.timedelta(days=15)
        if options["from_json"]:
            payload = json.loads(pathlib.Path(options["from_json"]).read_text(encoding="utf-8"))
        else:
            self.stdout.write(f"Siksha {start} ~ {end} 다운로드 중...")
            payload = siksha.fetch_days(start, end)
        history = fixed.classify(siksha.parse(payload), fixed_overlap=options["fixed_overlap"],
                                 min_ratio=options["min_ratio"], recent_days=options["recent_days"])

        output = pathlib.Path(options["output"])
        reviewed = fixed.catalog_lines(fixed.load_catalog(output))
        to_resolve = {key: name for h in history for key, name in h.fixed_lines.items()
                      if key not in reviewed}

        llm = None
        if not options["no_llm"] and api_key_available():
            llm = mapper.build_llm()
        elif to_resolve:
            self.stdout.write("LLM 없이 실행: 처음 보는 고정 메뉴는 목록에 넣지 않습니다.")
        mappings = mapper.map_lines(to_resolve, llm, on_progress=self.stdout.write, use_catalog=False)

        catalog = {"version": mapper.PREPROCESS_VERSION, "built_from": [str(start), str(end)],
                   "restaurants": {}}
        review_rows, skipped = [], 0
        self.stdout.write(f"\n{'식당':24s} {'유형':6s} {'영업일':>4s} {'겹침':>5s} {'고정 줄':>6s}")
        for h in history:
            self.stdout.write(f"{h.name:24s} {h.kind:6s} {h.open_days:4d} {h.overlap:5.2f} "
                              f"{len(h.fixed_lines):6d}")
            if h.kind == fixed.DAILY:
                continue
            entries = {}
            for key, name in sorted(h.fixed_lines.items(), key=lambda kv: kv[1]):
                if key in reviewed:
                    entries[key] = reviewed[key]
                elif mappings[key].source == "llm":
                    m = mappings[key]
                    entries[key] = {"name": name, "is_meal": m.is_meal, "dishes": list(m.dishes),
                                    "source": "llm"}
                else:
                    skipped += 1  # never cache a guess as a permanent rule
                    continue
                e = entries[key]
                review_rows.append([h.name, h.kind, e["name"], "Y" if e["is_meal"] else "N",
                                    " | ".join(e["dishes"]), e.get("source", "")])
            catalog["restaurants"][h.code] = {"name": h.name, "type": h.kind,
                                              "open_days": h.open_days, "overlap": h.overlap,
                                              "lines": entries}

        output.write_text(json.dumps(catalog, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        total = sum(len(r["lines"]) for r in catalog["restaurants"].values())
        self.stdout.write(self.style.SUCCESS(f"\n고정 메뉴 {total}줄 -> {output}"))
        if skipped:
            self.stdout.write(self.style.WARNING(f"LLM 답이 없어 넣지 않은 줄 {skipped}개: 키를 넣고 다시 실행하세요."))
        if options["review"]:
            write_csv(options["review"], ["cafeteria", "type", "line", "is_meal", "dishes", "source"],
                      review_rows)
            self.stdout.write(f"검토용 CSV -> {options['review']}")

