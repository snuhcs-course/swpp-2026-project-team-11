"""Opt-in, privacy-limited interaction events in daily JSONL files.

Only server-generated step data and validated answer IDs are recorded. The log
uses a random identifier distinct from the session's API bearer and never stores
client IPs, device identifiers, or question/reason text. Validated location and
allergy selections are stored once at session start.
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import re
import threading
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)
_NAME = re.compile(r"^interactions-(\d{4}-\d{2}-\d{2})\.jsonl$")
_LOCK = threading.RLock()
_STARTED = False


def _root():
    value = getattr(settings, "INTERACTION_LOG_DIR", "")
    return Path(value).expanduser() if value else None


def prune(root: Path, today: datetime.date | None = None) -> None:
    """Keep the current UTC calendar day and preceding 29 days only."""
    today = today or datetime.datetime.now(datetime.timezone.utc).date()
    cutoff = today - datetime.timedelta(days=29)
    with _LOCK:
        if not root.is_dir():
            return
        for path in root.iterdir():
            match = _NAME.fullmatch(path.name)
            if not match or path.is_symlink() or not path.is_file():
                continue
            try:
                day = datetime.date.fromisoformat(match.group(1))
            except ValueError:
                continue
            if day < cutoff:
                path.unlink()


def start_retention() -> None:
    """Prune at process startup and hourly, including when no sessions are active."""
    global _STARTED
    root = _root()
    if root is None:
        return
    with _LOCK:
        if _STARTED:
            return
        _STARTED = True

    def worker():
        while True:
            try:
                prune(root)
            except OSError:
                logger.warning("Could not prune interaction logs", exc_info=True)
            threading.Event().wait(3600)

    threading.Thread(target=worker, name="interaction-log-retention", daemon=True).start()


def _step(step):
    """A small, server-produced representation of the shown step."""
    if not isinstance(step, dict):
        return None
    kind = step.get("type")
    result = {"type": kind, "question_count": step.get("question_count")}
    if kind == "question":
        result["question_id"] = step.get("question_id")
    elif kind in ("guess", "recommendation"):
        food = step.get("food") or {}
        result["food_id"] = food.get("food_id")
        result["display_name"] = food.get("display_name")
        offers = food.get("offers") or []
        result["restaurants"] = list(dict.fromkeys(
            o.get("restaurant") for o in offers if isinstance(o, dict) and o.get("restaurant")
        ))[:10]
        result["restaurant_count"] = len({o.get("restaurant") for o in offers
                                          if isinstance(o, dict) and o.get("restaurant")})
    elif kind == "unavailable":
        result["reason"] = step.get("reason")
    return result


def record(session, event: str, *, before=None, after=None, answer_id=None,
           accepted=None, outcome="ok") -> None:
    """Best-effort append: a disk failure must never fail the user's request."""
    root = _root()
    if root is None:
        return
    try:
        now = datetime.datetime.now(datetime.timezone.utc)
        data = {
            "version": 1,
            "timestamp": now.isoformat().replace("+00:00", "Z"),
            "session": session.interaction_id,
            "event": event,
            "outcome": outcome,
            "engine": session.engine_name,
            "meal": session.meal,
            "menu_date": session.date.isoformat(),
            "source": session.source,
            "distance_scope": session.distance_scope,
            "location_available": session.location_available,
            "candidates_before_distance": session.candidates_before_distance,
            "candidate_count": session.candidate_count,
            "before": _step(before),
            "after": _step(after),
        }
        if event == "start":
            data["allergies"] = session.logged_allergies
            data["location"] = session.logged_location
        if answer_id is not None:
            data["answer_id"] = answer_id
        if accepted is not None:
            data["accepted"] = accepted
        raw = (json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        with _LOCK:
            root.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(root / f"interactions-{now.date().isoformat()}.jsonl",
                         os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
    except Exception:
        logger.warning("Could not write interaction log", exc_info=True)
