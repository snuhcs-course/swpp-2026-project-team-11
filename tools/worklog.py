"""Private task records and accounting for explicitly assigned Codex/Claude sessions."""

from __future__ import annotations

import json
import hashlib
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
from datetime import datetime, timezone, date

TASK_FIELDS = ("human_hours", "agent_hours", "end_date", "status", "commit", "pr", "wiki_owner", "wiki_state")
WIKI_STATES = ("pending", "prepared", "published", "not-needed")

def now():
    return datetime.now(timezone.utc).isoformat()


def timestamp(value):
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc)
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timestamps must include a timezone, such as +09:00 or Z.")
    return result.astimezone(timezone.utc)


def task_id(value):
    if not re.fullmatch(r"i[1-9]\d*-[PA][1-9]\d*", value):
        raise ValueError("Use a task ID such as i3-P3 or i3-A1.")
    return value


def write_json(path, value):
    write_text(path, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def write_text(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def all_tasks(root):
    return [json.loads(p.read_text(encoding="utf-8"))
            for p in sorted((Path(root) / ".harness/tasks").glob("*.json"))]


def save_task(root, value):
    value["updated_at"] = now()
    write_json(Path(root) / ".harness/tasks" / (task_id(value["id"]) + ".json"), value)


def task(root, identifier=None, owner=None, title="", fields=None, note=None):
    directory = Path(root) / ".harness"
    if identifier is None:
        current = directory / "current.json"
        if not current.exists():
            raise ValueError("Start with task <id> --owner <name>.")
        identifier = json.loads(current.read_text())["task"]
    path = directory / "tasks" / (task_id(identifier) + ".json")
    if path.exists():
        value = json.loads(path.read_text(encoding="utf-8"))
        if owner and owner != value["owner"]:
            raise ValueError("This record belongs to another contributor.")
    else:
        if not owner or not owner.strip():
            raise ValueError("A new task requires --owner <name>.")
        value = {"schema_version": 1, "id": identifier, "owner": owner, "title": title,
                 "started_at": now(), "branch": git(root, "branch", "--show-current"),
                 "base_commit": git(root, "rev-parse", "HEAD"), "fields": {}, "notes": [], "sources": []}
    for key, field in (fields or {}).items():
        if key not in TASK_FIELDS:
            raise ValueError(f"Unsupported task field: {key}")
        if key in ("human_hours", "agent_hours"):
            field = float(field)
            if not math.isfinite(field) or field < 0:
                raise ValueError("Hours must be finite and nonnegative.")
        elif key == "end_date":
            date.fromisoformat(field)
        elif key == "commit":
            field = git(root, "rev-parse", "--verify", field + "^{commit}")
        elif key == "wiki_state" and field not in WIKI_STATES:
            raise ValueError("Invalid wiki state.")
        value["fields"][key] = field
    if note and not any(all(n.get(k) == note.get(k) for k in ("kind", "text", "ref")) for n in value["notes"]):
        value["notes"].append({"at": now(), **note})
    if not path.exists() or fields or note:
        save_task(root, value)
    write_json(directory / "current.json", {"task": identifier})
    return value


def bundle(root, number):
    tasks = [t for t in all_tasks(root) if t["id"].startswith(f"i{number}-")]
    if number < 1 or not tasks:
        raise ValueError("No local tasks for that iteration.")
    directory = Path(root) / ".harness/bundles" / f"iteration-{number}"
    write_json(directory / "tasks.json", tasks)
    write_json(directory / "input-prompts.private.json", input_prompts([s for t in tasks for s in t["sources"]]))
    return {"directory": str(directory), "tasks": [t["id"] for t in tasks],
            "review_required": "Private local evidence only. Review all contributors' histories and redact before publishing."}


KEYS = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens")


def events(path, warnings):
    with Path(path).open(encoding="utf-8") as f:
        for number, line in enumerate(f, 1):
            try:
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise ValueError()
            except ValueError:
                warnings.add(f"Malformed record at {Path(path).name}:{number}; excluded.")
                continue
            yield event


def source_identity(path, tool):
    warnings = set()
    for event in events(path, warnings):
        if tool == "codex" and event.get("type") == "session_meta":
            return str(event["payload"]["id"])
        if tool == "claude" and event.get("sessionId"):
            return str(event["sessionId"])
    raise ValueError("No supported session identity found in that JSONL file.")


def attach(root, task, tool, path, since=None, until=None):
    path = str(Path(path).expanduser().resolve(strict=True))
    since, until = since or task["started_at"], until or now()
    start, end = timestamp(since), timestamp(until)
    if start >= end:
        raise ValueError("The usage interval must have a start before its end.")
    identity = source_identity(path, tool)
    for other in all_tasks(root):
        if other["id"] == task["id"]:
            continue
        for source in other["sources"]:
            if (source["tool"], source["session_id"]) == (tool, identity):
                if start < timestamp(source["until"]) and timestamp(source["since"]) < end:
                    raise ValueError(f"This session interval overlaps {other['id']}; resolve attribution first.")
    source = {"tool": tool, "path": path, "session_id": identity,
              "since": start.isoformat(), "until": end.isoformat()}
    # Reattaching extends/replaces the same interval; collection never adds saved totals.
    task["sources"] = [s for s in task["sources"] if
                       (s["tool"], s["session_id"], s["since"]) != (tool, identity, source["since"])]
    task["sources"].append(source)
    task.pop("usage", None)
    save_task(root, task)
    return source


def numeric(values, key):
    value = values.get(key, 0)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"Invalid {key} in a usage record.")
    return value


def codex(source, samples, spans, warnings):
    start, end = timestamp(source["since"]), timestamp(source["until"])
    previous = None
    for event in events(source["path"], warnings):
        if event.get("type") != "event_msg":
            continue
        payload = event.get("payload", {})
        kind = payload.get("type")
        if kind not in ("token_count", "task_complete"):
            continue
        if not event.get("timestamp"):
            warnings.add("A Codex event has no timestamp; excluded.")
            continue
        t = timestamp(event["timestamp"])
        if kind == "task_complete":
            if start <= t < end and payload.get("started_at") is not None and payload.get("completed_at") is not None:
                a, b = timestamp(payload["started_at"]), timestamp(payload["completed_at"])
                if start <= a <= b <= end:
                    spans.append((a, b))
            continue
        info = payload.get("info") or {}
        total, last = info.get("total_token_usage"), info.get("last_token_usage")
        if not total:
            continue
        current = {k: numeric(total, k) for k in KEYS}
        if previous is None:
            delta = {k: numeric(last, k) for k in KEYS} if last else None
        elif any(current[k] < previous[k] for k in KEYS):
            delta = {k: numeric(last, k) for k in KEYS} if last else None
            if start <= t < end:
                warnings.add("Codex cumulative counters reset; only the reported last call was included.")
        else:
            delta = {k: current[k] - previous[k] for k in KEYS}
        previous = current
        if not start <= t < end:
            continue
        if delta is None:
            warnings.add("Codex's first counter has no last-call baseline; it was excluded.")
            continue
        # Repeated cumulative snapshots contribute zero; reasoning/cache reads are subsets.
        key = ("codex", source["session_id"], event["timestamp"], tuple(current.values()))
        if sum(delta.values()):
            samples[key] = delta


def claude(source, samples, spans, warnings):
    start, end = timestamp(source["since"]), timestamp(source["until"])
    for event in events(source["path"], warnings):
        message = event.get("message") or {}
        if event.get("type") != "assistant" or not isinstance(message, dict) or not message.get("usage"):
            continue
        if not event.get("timestamp") or not message.get("id"):
            warnings.add("A Claude usage record has no timestamp/message ID; excluded.")
            continue
        if not start <= timestamp(event["timestamp"]) < end:
            continue
        usage = message["usage"]
        read = numeric(usage, "cache_read_input_tokens")
        write = numeric(usage, "cache_creation_input_tokens")
        value = {"input_tokens": numeric(usage, "input_tokens") + read + write,
                 "cached_input_tokens": read, "cache_write_input_tokens": write,
                 "output_tokens": numeric(usage, "output_tokens")}
        key = ("claude", source["session_id"], event.get("requestId"), message["id"])
        # Streaming records can repeat the message with increasing final usage.
        previous = samples.get(key, {})
        samples[key] = {k: max(previous.get(k, 0), value[k]) for k in KEYS}


def union_seconds(spans):
    if not spans:
        return None
    merged = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return round(sum((b - a).total_seconds() for a, b in merged), 3)


def collect(sources):
    if not sources:
        raise ValueError("Attach an explicitly attributed session interval with usage --file <path> --tool <tool> first.")
    samples, spans, warnings = {}, [], set()
    for source in sources:
        if source_identity(source["path"], source["tool"]) != source["session_id"]:
            raise ValueError("A source file's session identity changed; reattach the correct file.")
        (codex if source["tool"] == "codex" else claude)(source, samples, spans, warnings)
    totals = {k: sum(s[k] for s in samples.values()) for k in KEYS}
    return {**totals, "total_tokens": totals["input_tokens"] + totals["output_tokens"],
            "usage_records": len(samples), "collected_at": now(),
            "turn_wall_seconds": union_seconds(spans), "warnings": sorted(warnings),
            "time_scope": "Complete Codex turns within the intervals, unioned across overlap; includes tool waits. "
                          "Claude turn time and partial turns are not measured. Do not treat this as human effort.",
            "scope": "Only explicitly attached intervals; no billing or human-effort estimate."}


def input_prompts(sources):
    """Collect candidate human inputs privately; do not claim automatic redaction."""
    result, warnings = {}, set()
    for source in sources:
        start, end = timestamp(source["since"]), timestamp(source["until"])
        for event in events(source["path"], warnings):
            if not event.get("timestamp") or not start <= timestamp(event["timestamp"]) < end:
                continue
            text = None
            if source["tool"] == "codex" and event.get("type") == "event_msg":
                payload = event.get("payload", {})
                if payload.get("type") == "user_message":
                    text = payload.get("message")
            elif source["tool"] == "claude" and event.get("type") == "user" and not (event.get("isMeta") or event.get("isCompactSummary")):
                content = (event.get("message") or {}).get("content")
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    parts = [c["text"] for c in content if c.get("type") == "text"]
                    if parts:
                        text = "\n".join(parts)
            if not isinstance(text, str) or not text:
                continue
            digest = hashlib.sha256(text.encode()).hexdigest()
            key = (source["tool"], source["session_id"], event["timestamp"], digest)
            result[key] = {"tool": source["tool"], "session_id": source["session_id"],
                           "timestamp": event["timestamp"], "text": text}
    return {"prompts": sorted(result.values(), key=lambda r: r["timestamp"]), "warnings": sorted(warnings),
            "review_required": "Private, unredacted candidates. Check missing prompts, generated wrappers, "
                               "attachments and secrets against the original interaction history before publication."}
