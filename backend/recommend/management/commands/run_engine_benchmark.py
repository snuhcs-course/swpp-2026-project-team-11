# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""python manage.py run_engine_benchmark --name NAME [--date D ...]

Run the question engine benchmark end to end and keep everything in one folder:

    engine_benchmark_results/NAME/
        config.json              what was run: menus, counts, repeats, models, the LLM engine's and the
                                 simulated user's prompts, DT policy, git commit
        scenarios.json           build_engine_scenarios (made once; a new set needs a new NAME)
        sessions/                collect_engine_sessions: sessions.jsonl, the simulated answers cache, and
                                 run.log (the run's output and warnings, such as the engine's retries)
        report.md, summary.json, sessions.csv, questions.csv, proposals.csv,
        1_main_metrics/ ... 9_user_study/   benchmark_engines
        9_user_study/human/      people's sessions (play_engine_session --output here), read by default
        9_user_study/simulator_check.jsonl   validate_simulator, read when present

Running the same NAME again continues a stopped run without repeating finished
sessions, then rewrites the report. config.json's "collection" part (menus, question
limit, DT policy, models, prompts) is written with the first sessions and kept: a
rerun with other settings is refused, so one folder never mixes two setups; more
repeats or a larger --limit are fine. --dry-run prints the LLM calls without making any.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import os
import pathlib
import subprocess
import tempfile

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from question_engines.benchmark import scenarios, simulator
from question_engines.decision_tree.planning import POLICY_VERSION
from question_engines.llm.config import DEFAULT_MODEL
from question_engines.llm.engine import ENGINE_VERSION
from question_engines.llm.prompt import SYSTEM_PROMPT as ENGINE_PROMPT

from .build_engine_scenarios import DEFAULT_COUNTS, build, parse_counts

HUMAN = pathlib.Path("9_user_study", "human")
SIMULATOR_CHECK = pathlib.Path("9_user_study", "simulator_check.jsonl")


class Tee:
    """Writes to the console and to the run log."""

    def __init__(self, console, log):
        self.console, self.log = console, log

    def write(self, text):
        self.console.write(text, ending="")
        self.log.write(text)
        self.log.flush()

    def flush(self):
        self.log.flush()


def git_commit() -> str:
    """The checked-out commit, with "-dirty" when the working tree has uncommitted changes."""
    try:
        return subprocess.run(["git", "describe", "--always", "--dirty"], capture_output=True, text=True,
                              cwd=settings.BASE_DIR, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def collection_config(data) -> dict:
    """What decides the sessions; a folder's sessions all share it."""
    scenarios_sha256 = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return {"menus": sorted(data["menus"]), "scenarios_sha256": scenarios_sha256, "seed": data["seed"],
            "max_questions": settings.RECOMMEND_MAX_QUESTIONS,
            "dt_policy": settings.RECOMMEND_DT_POLICY, "dt_policy_version": POLICY_VERSION,
            "llm_model": os.environ.get("METCHU_LLM_MODEL") or DEFAULT_MODEL, "llm_engine_version": ENGINE_VERSION,
            "llm_engine_prompt_id": hashlib.sha256(ENGINE_PROMPT.encode()).hexdigest()[:12],
            "llm_engine_prompt": ENGINE_PROMPT, "simulator_model": simulator.MODEL.model_id(),
            "simulator_prompt_id": simulator.PROMPT_ID, "simulator_prompts": simulator.PROMPTS}


def checked_collection(folder, current) -> dict:
    """The folder's collection settings: the saved ones when sessions exist and match `current`."""
    config, sessions = folder / "config.json", folder / "sessions" / "sessions.jsonl"
    if not (config.exists() and sessions.exists()):
        return current | {"git_commit": git_commit()}
    saved = json.loads(config.read_text(encoding="utf-8"))["collection"]
    changed = [key for key in current if saved.get(key) != current[key]]
    if changed:
        raise CommandError(f"이 폴더의 세션과 설정이 다릅니다 ({', '.join(changed)}). 같은 설정으로 실행하거나 "
                           "새 --name을 쓰세요.")
    return saved


def write_config(folder, data, counts, options, collection) -> None:
    """config.json: what this run played, with which models, prompts and code."""
    played = {s: sum(x["situation"] == s for x in data["scenarios"]) for s in counts}
    if options["limit"] is not None:
        played = {s: min(n, options["limit"]) for s, n in played.items()}
    (folder / "config.json").write_text(json.dumps({
        "name": options["name"], "updated_at": timezone.now().isoformat(), "collection": collection,
        "counts": played, "repeats": options["repeats"], "limit": options["limit"],
        "report_git_commit": git_commit(),
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


class Command(BaseCommand):
    help = "Build scenarios, play both engines and write the engine benchmark report into one folder."

    def add_arguments(self, parser):
        parser.add_argument("--name", required=True, help="folder name under --results-dir, e.g. 2026-10-20")
        parser.add_argument("--date", type=datetime.date.fromisoformat, action="append",
                            help="a menu date for new scenarios; repeat for several (default: today)")
        parser.add_argument("--meal", action="append", choices=("BR", "LU", "DN"), help="default: LU")
        parser.add_argument("--counts", default=DEFAULT_COUNTS, help=f"default: {DEFAULT_COUNTS}")
        parser.add_argument("--seed", type=int, default=0)
        parser.add_argument("--repeats", type=int, default=3, help="sessions per scenario and engine")
        parser.add_argument("--limit", type=int, default=None, help="first N scenarios per situation")
        parser.add_argument("--results-dir",
                            default=str(pathlib.Path(settings.BASE_DIR).parent / "engine_benchmark_results"))
        parser.add_argument("--dry-run", action="store_true", help="print the LLM calls and stop")

    def handle(self, *args, **options):
        counts = parse_counts(options["counts"])
        folder = pathlib.Path(options["results_dir"]) / options["name"]
        scenario_path = folder / "scenarios.json"
        dates, meals = options["date"] or [timezone.localdate()], options["meal"] or ["LU"]
        warn = lambda text: self.stdout.write(self.style.WARNING(text))
        play_options = ["--repeats", str(options["repeats"])]
        play_options += ["--limit", str(options["limit"])] if options["limit"] is not None else []

        if options["dry_run"]:
            if scenario_path.exists():
                checked_collection(folder, collection_config(scenarios.load(scenario_path)))
            with tempfile.TemporaryDirectory() as scratch:
                path = scenario_path if scenario_path.exists() else pathlib.Path(scratch) / "scenarios.json"
                if not scenario_path.exists():
                    scenarios.save(path, build(dates, meals, counts, options["seed"], warn))
                sessions = folder / "sessions" / "sessions.jsonl"  # read only: what is left to play
                output = sessions if sessions.exists() else pathlib.Path(scratch) / "sessions.jsonl"
                call_command("collect_engine_sessions", "--scenarios", str(path), "--output", str(output),
                             *play_options, "--dry-run", stdout=self.stdout)
            return

        (folder / "sessions").mkdir(parents=True, exist_ok=True)
        if scenario_path.exists():
            self.stdout.write(f"기존 시나리오를 씁니다: {scenario_path}")
        else:
            scenarios.save(scenario_path, build(dates, meals, counts, options["seed"], warn))
        data = scenarios.load(scenario_path)
        write_config(folder, data, counts, options, checked_collection(folder, collection_config(data)))
        with open(folder / "sessions" / "run.log", "a", encoding="utf-8") as log:
            warnings = logging.StreamHandler(log)  # the engine's retries and fallbacks
            warnings.setLevel(logging.WARNING)
            logging.getLogger().addHandler(warnings)
            try:
                self.play_and_report(folder, scenario_path, play_options, Tee(self.stdout, log))
            finally:
                logging.getLogger().removeHandler(warnings)

    def play_and_report(self, folder, scenario_path, play_options, out):
        out.write(f"== {timezone.now().isoformat()} {folder.name}\n")
        sessions = folder / "sessions" / "sessions.jsonl"
        call_command("collect_engine_sessions", "--scenarios", str(scenario_path), "--output", str(sessions),
                     "--simulator-cache", str(folder / "sessions" / "simulator_cache.jsonl"), *play_options, stdout=out)
        if not sessions.exists():
            return
        human = sorted(str(path) for path in (folder / HUMAN).glob("*.jsonl"))
        check = [str(folder / SIMULATOR_CHECK)] if (folder / SIMULATOR_CHECK).exists() else []
        call_command("benchmark_engines", "--scenarios", str(scenario_path), "--sessions", str(sessions),
                     "--output-dir", str(folder), *(["--human", *human] if human else []),
                     *(["--simulator-check", *check] if check else []), stdout=out)
        out.write(f"결과 -> {folder}\n")
