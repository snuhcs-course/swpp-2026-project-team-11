"""HTTP glue between the Android client and the question engine.

    POST /api/sessions/                      {"date"?, "meal"?}            -> 201 state
    GET  /api/sessions/<id>/                                               -> state
    POST /api/sessions/<id>/answer/          {"question_id", "answer_id"}  -> state
    POST /api/sessions/<id>/feedback/        {"guess_id", "accepted"}      -> state
    POST /api/sessions/<id>/recommend-now/                                 -> state
    POST /api/sessions/<id>/undo/                                          -> state

Every success returns the same session state (see `RecommendSession.public_state`),
so the client always redraws from one shape. Errors are
`{"error": {"code", "message"}}`; a 409 `stale_step` also carries the current
`state`, so a double tap redraws instead of failing.
"""

from __future__ import annotations

import datetime
import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from . import sessions

MEALS = ("BR", "LU", "DN")


def _error(status: int, code: str, message: str, **extra) -> JsonResponse:
    return JsonResponse({"error": {"code": code, "message": message}, **extra}, status=status)


def _body(request) -> dict:
    if not request.body:
        return {}
    payload = json.loads(request.body)
    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object body.")
    return payload


@csrf_exempt
@require_POST
def create_session(request):
    try:
        payload = _body(request)
        date = payload.get("date")
        if date is not None:
            if not isinstance(date, str):
                raise ValueError("date must be an ISO date string such as 2026-09-29.")
            date = datetime.date.fromisoformat(date)
        meal = payload.get("meal")
        if meal is not None and meal not in MEALS:
            raise ValueError("meal must be one of BR, LU, DN.")
    except ValueError as error:  # includes json.JSONDecodeError
        return _error(400, "invalid_request", str(error))
    return JsonResponse(sessions.create(date, meal).public_state(), status=201)


@require_GET
def session_state(request, session_id: str):
    session = sessions.get(session_id)
    if session is None:
        return _error(404, "session_not_found", "No such session. Start a new one.")
    with session.lock:
        return JsonResponse(session.public_state())


def _action(request, session_id: str, apply):
    """Run one engine action under the session lock and return the new state."""
    session = sessions.get(session_id)
    if session is None:
        return _error(404, "session_not_found", "No such session. Start a new one.")
    with session.lock:
        try:
            apply(session, _body(request))
        except sessions.StaleStep as error:
            return _error(409, "stale_step", str(error), state=session.public_state())
        except KeyError as error:
            return _error(400, "invalid_request", f"Missing field: {error.args[0]}")
        except ValueError as error:
            return _error(400, "invalid_request", str(error))
        return JsonResponse(session.public_state())


@csrf_exempt
@require_POST
def answer(request, session_id: str):
    return _action(request, session_id,
                   lambda s, body: s.answer(body["question_id"], body["answer_id"]))


@csrf_exempt
@require_POST
def feedback(request, session_id: str):
    def apply(session, body):
        if type(body["accepted"]) is not bool:
            raise ValueError("accepted must be true or false.")
        session.feedback(body["guess_id"], body["accepted"])
    return _action(request, session_id, apply)


@csrf_exempt
@require_POST
def recommend_now(request, session_id: str):
    return _action(request, session_id, lambda s, body: s.recommend_now())


@csrf_exempt
@require_POST
def undo(request, session_id: str):
    return _action(request, session_id, lambda s, body: s.undo())
