"""What a signed-in user was recommended: one HistoryEntry per dish a solo session proposes.

recommend/views.py calls `record` after every session request that succeeds. A session
started with a token belongs to that user; each guess or recommendation it shows is kept
once, however often the same dish comes back in the session (undo, a lost reply sent again).
The restaurant is the offer nearest the session's location, else the first, as the result
screen lists them. Only the newest LIMIT entries of a user are kept. A failure is logged and
never fails the session request, which has already moved the session on.
"""

from __future__ import annotations

import logging

from .models import HistoryEntry

logger = logging.getLogger(__name__)

LIMIT = 100


def _restaurant(offers: list[dict]) -> str:
    if not offers:
        return ""
    return min(offers, key=lambda o: (o.get("distance_m") is None, o.get("distance_m") or 0))["restaurant"]


def record(session, step: dict) -> None:
    if session.user_id is None or step["type"] not in ("guess", "recommendation"):
        return
    try:
        _record(session, step)
    except Exception:
        logger.warning("Could not record history", exc_info=True)


def _record(session, step: dict) -> None:
    food = step["food"]
    _, created = HistoryEntry.objects.get_or_create(
        user_id=session.user_id, session_id=session.session_id, food_id=food["food_id"],
        defaults={"date": session.date, "meal": session.meal, "display_name": food["display_name"],
                  "restaurant": _restaurant(food["offers"])})
    if created:
        old = HistoryEntry.objects.filter(user_id=session.user_id).order_by("-id").values_list("id", flat=True)[LIMIT:]
        HistoryEntry.objects.filter(id__in=list(old)).delete()

