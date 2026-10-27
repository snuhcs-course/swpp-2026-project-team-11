#!/usr/bin/env python3
"""Shared CLI for task evidence, Codex/Claude usage and the project schedule."""

import argparse
import json
from pathlib import Path
import subprocess
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools import worklog, sheets

ROOT = Path(__file__).resolve().parent.parent


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    groups = p.add_subparsers(dest="command", required=True)
    task = groups.add_parser("task", help="Create/resume a task, record evidence, or print its current state.")
    task.add_argument("id", nargs="?")
    task.add_argument("--owner")
    task.add_argument("--title", default="")
    task.add_argument("--set", action="append", default=[], metavar="FIELD=VALUE",
                      help=f"Fields: {', '.join(worklog.TASK_FIELDS)}. end_date: YYYY-MM-DD; "
                           f"wiki_state: {', '.join(worklog.WIKI_STATES)}. Hours must be nonnegative.")
    task.add_argument("--note")
    task.add_argument("--kind", default="decision", choices=("decision", "failure", "verification", "prompt-revision", "manual-fix", "wiki", "handoff"))
    task.add_argument("--ref", default="")
    usage = groups.add_parser("usage", help="Collect usage; optionally attach or extend a session interval first.")
    usage.add_argument("--task")
    usage.add_argument("--file")
    usage.add_argument("--tool", choices=("codex", "claude"))
    usage.add_argument("--since", help="Timezone-aware ISO timestamp; default: task creation.")
    usage.add_argument("--until", help="Exclusive interval end; default: attachment time.")
    sheet = groups.add_parser("sheet", help="Preview by default; --apply rereads, writes and verifies.")
    sheet.add_argument("--task")
    sheet.add_argument("--apply", action="store_true")
    sheet.add_argument("--login", metavar="CLIENT_JSON", help="Explicitly authorize with a local Desktop OAuth client.")
    groups.add_parser("bundle", help="Collect private iteration evidence and input prompts.").add_argument("iteration", type=int)
    return p


def run(args, root=ROOT):
    if args.command == "bundle":
        return worklog.bundle(root, args.iteration)
    if args.command == "task":
        fields = {}
        for entry in args.set:
            key, sep, value = entry.partition("=")
            if not sep:
                raise ValueError("Use --set FIELD=VALUE.")
            fields[key] = value
        note = {"kind": args.kind, "text": args.note, "ref": args.ref} if args.note else None
        return worklog.task(root, args.id, args.owner, args.title, fields, note)
    if args.command == "sheet" and args.login:
        return sheets.login(root, args.login)
    task = worklog.task(root, args.task)
    if args.command == "usage":
        if args.file:
            if not args.tool:
                raise ValueError("Attaching a file requires --tool codex or --tool claude.")
            worklog.attach(root, task, args.tool, args.file, args.since, args.until)
        elif args.tool or args.since or args.until:
            raise ValueError("Interval options require --file.")
        task["usage"] = worklog.collect(task["sources"])
        worklog.save_task(root, task)
        return task["usage"]
    client = sheets.GoogleSheet(root)
    path = Path(root) / ".harness/plans" / (task["id"] + ".json")
    if not args.apply:
        plan = sheets.make_plan(client.snapshot(task["id"]), task)
        worklog.write_json(path, plan)
        return plan
    if not path.exists():
        raise ValueError("Run sheet without --apply to preview first.")
    return client.apply(task, json.loads(path.read_text()))


def main(argv=None, root=ROOT):
    args = parser().parse_args(argv)
    try:
        result = run(args, root)
    except (ValueError, OSError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result.get("exit_code", 0)


if __name__ == "__main__":
    raise SystemExit(main())
