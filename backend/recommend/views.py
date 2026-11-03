"""HTTP glue between the Android client and the question engine.

    POST /api/sessions/  {"date"?, "meal"?, "engine"?, "location"?, "allergies"?, "source"?, "distance_scope"?,
                          "language"?}                                       -> 201 state
    GET  /api/sessions/<id>/                                               -> state
    POST /api/sessions/<id>/answer/          {"question_id", "answer_id"}  -> state
    POST /api/sessions/<id>/feedback/        {"guess_id", "accepted"}      -> state
    POST /api/sessions/<id>/recommend-now/                                 -> state
    POST /api/sessions/<id>/undo/                                          -> state
    POST /api/sessions/<id>/ban/  {"food_id" | "food_group", "banned"}     -> state
    GET  /api/sessions/<id>/reason/              -> {"food_id", "reason", "source"}
    GET  /api/sessions/<id>/menu/?restaurant=<name>  -> {"restaurant", "dishes"}
    GET  /api/health/                                                      -> {"status": "ok"}

Every success returns the same session state (see `RecommendSession.public_state`),
so the client always redraws from one shape. Errors are
`{"error": {"code", "message"}}`; a 409 `stale_step` also carries the current
`state`, so a double tap redraws instead of failing.

`reason` explains the dish of the current guess or recommendation in one or two
sentences of the session's language (recommend/reasons.py). The phone asks for it
after drawing the result, as it can take an LLM call; `source` is "llm", or
"template" when the server has no key or the LLM failed. With no dish on screen
it is a 409 `stale_step` with the state.

`menu` lists what one restaurant serves among the session's dishes, for the result
screen: each dish is {"food_id", "display_name", "meal", "price"}, breakfast first and
by name within a meal. A restaurant the session does not know has no dishes; a
missing `restaurant` is a 400.

`ban` keeps one dish (`food_id`) or every dish of a `food_group` out of the rest of the
session (`banned` true), or lets it back (false). The step on screen does not change;
the next action that would show a banned dish skips it, and an undo that would goes
back further (recommend/sessions.py).

`health` touches nothing; it is for checking from a browser that the server can
be reached, for example through the tunnel of `manage.py serve_public`.

`engine` can be "decision_tree", "rl" or "llm". RL requires v2 features for a nonempty
catalogue. Missing RL features or unavailable LLM configuration return 503
`engine_unavailable`. `location` is the user's `{"lat", "lng"}`; it
adds each cafeteria's `distance_m` to the offers (see recommend/distance.py).

`allergies` lists keys of menus/allergens.py ALLERGEN_KEYS, as the phone stores
them; no dish that may contain one is proposed. `language` is "en" (default) or "ko":
every text the session sends is in it, except dish and cafeteria names, which stay Korean.

`source` is "cafeteria" (default), the day's SNU cafeteria menu, or "general", the
restaurants near 서울대입구역 and 낙성대역, or "all" for both. General and all
sessions support "decision_tree" and "rl"; asking for "llm" is a 400. An omitted engine
uses the server default, falling back to the decision tree for a general session
if that default is "llm".
"""

from __future__ import annotations

import datetime
import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from menus.allergens import ALLERGEN_KEYS
from question_engines.decision_tree.contracts import LANGUAGES

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


def _location(value) -> tuple[float, float] | None:
    if value is None:
        return None
    try:
        lat, lng = value["lat"], value["lng"]
    except (TypeError, KeyError):
        raise ValueError("location must be {\"lat\": ..., \"lng\": ...}.") from None
    if not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in (lat, lng)) \
            or not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise ValueError("location lat and lng must be numbers within -90..90 and -180..180.")
    return float(lat), float(lng)


@require_GET
def health(request):
    return JsonResponse({"status": "ok"})


@csrf_exempt
@require_POST
def create_session(request):
    try:
        payload = _body(request)
        date = payload.get("date")
        if date is not None:
            if not isinstance(date, str):
                raise ValueError("date must be an ISO date string such as 2026-11-02.")
            date = datetime.date.fromisoformat(date)
        meal = payload.get("meal")
        if meal is not None and meal not in MEALS:
            raise ValueError("meal must be one of BR, LU, DN.")
        engine = payload.get("engine")
        if engine is not None and engine not in sessions.ENGINES:
            raise ValueError(f"engine must be one of {', '.join(sessions.ENGINES)}.")
        location = _location(payload.get("location"))
        allergies = payload.get("allergies")
        if allergies is not None and (not isinstance(allergies, list)
                                      or any(key not in ALLERGEN_KEYS for key in allergies)):
            raise ValueError(f"allergies must be a list of {', '.join(ALLERGEN_KEYS)}.")
        source = payload.get("source")
        if source is not None and source not in sessions.SOURCES:
            raise ValueError(f"source must be one of {', '.join(sessions.SOURCES)}.")
        if source == "general" and engine == "llm":
            raise ValueError("The general source supports the decision_tree and rl engines.")
        distance_scope = payload.get("distance_scope")
        if distance_scope is not None and distance_scope not in ("near", "any"):
            raise ValueError("distance_scope must be near or any.")
        language = payload.get("language", "en")
        if language not in LANGUAGES:
            raise ValueError(f"language must be one of {', '.join(LANGUAGES)}.")
    except ValueError as error:  # includes json.JSONDecodeError
        return _error(400, "invalid_request", str(error))
    if source == "all" and engine == "llm":
        return _error(400, "all_source_llm_unsupported", "All restaurants supports the decision tree and RL engines.")
    try:
        session = sessions.create(date, meal, engine, location, frozenset(allergies or ()), source, language, distance_scope)
    except sessions.EngineUnavailable as error:
        return _error(503, "engine_unavailable", str(error))
    return JsonResponse(session.public_state(), status=201)


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


@require_GET
def reason(request, session_id: str):
    session = sessions.get(session_id)
    if session is None:
        return _error(404, "session_not_found", "No such session. Start a new one.")
    try:
        return JsonResponse(session.reason())
    except sessions.StaleStep as error:
        with session.lock:
            return _error(409, "stale_step", str(error), state=session.public_state())


@require_GET
def menu(request, session_id: str):
    session = sessions.get(session_id)
    if session is None:
        return _error(404, "session_not_found", "No such session. Start a new one.")
    restaurant = request.GET.get("restaurant")
    if not restaurant:
        return _error(400, "invalid_request", "Missing parameter: restaurant")
    return JsonResponse(session.menu(restaurant))


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


@csrf_exempt
@require_POST
def ban(request, session_id: str):
    return _action(request, session_id,
                   lambda s, body: s.ban(body.get("food_id"), body.get("food_group"), body["banned"]))
