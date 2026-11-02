"""python manage.py run_store_pipeline --file stores.json [--review PATH]

The restaurants near the stations, start to finish, whenever they are crawled again:
  1. import_stores               - read the crawl, drop notices and drinks, resolve and store
  2. extract_features --stores   - tag the new dishes with feature values
  3. extract_allergens --stores  - tag the new dishes with allergens

It needs the key of METCHU_MENU_MODEL (menus/llm.py). Dishes and lines resolved
before, by this or by the cafeteria pipeline, are reused, so only new ones cost LLM
calls; `import_stores --dry-run` tells how many lines that is. If the import fails, the
command stops there; if a tagging step fails, the other still runs and the command then
exits with an error.
"""

from __future__ import annotations

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from menus import llm, services


class Command(BaseCommand):
    help = "Import, preprocess and tag the restaurants near the stations from a crawl file."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="the crawl JSON")
        parser.add_argument("--review", default=None, help="also write the review CSV here")

    def handle(self, *args, **options):
        if not llm.api_key_available():
            raise CommandError(f"{llm.key_name()}가 없습니다. 레포 루트의 .env에 넣어 주세요.")
        importing = ["import_stores", "--file", options["file"]]
        if options["review"]:
            importing += ["--review", options["review"]]
        steps = [("[1/3] 가게 메뉴 가져오기·전처리", importing),
                 ("[2/3] 새 요리 특징 추출", ["extract_features", "--stores"]),
                 ("[3/3] 새 요리 알레르기 태깅", ["extract_allergens", "--stores"])]
        errors = []
        for title, command in steps:
            self.stdout.write(title)
            try:
                call_command(*command, stdout=self.stdout)
            except CommandError as error:
                if command[0] == "import_stores":
                    # Its rule-fallback lines are replaced by the next import: tagging them wastes calls.
                    raise CommandError(f"import_stores: {error}\n태깅은 건너뜁니다. 다시 실행해 주세요.") from error
                errors.append(f"{command[0]}: {error}")

        candidates, _, _ = services.get_store_catalog()
        self.stdout.write(self.style.SUCCESS(f"일반 식당 추천 후보: {len(candidates)}"))
        if errors:
            raise CommandError("\n".join(errors))
