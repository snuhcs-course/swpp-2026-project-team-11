"""Accounts for the app: an own username and password, a Google account, or both.

    POST /api/auth/signup/       {"username", "password"}        -> 201 {"token", "user"}
    POST /api/auth/login/        {"username", "password"}        -> {"token", "user"}
    POST /api/auth/google/       {"id_token"}                    -> {"token", "user", "created"}
    POST /api/auth/google/link/  {"id_token"}        (signed in) -> {"user"}
    GET  /api/auth/me/                               (signed in) -> {"user"}
    POST /api/auth/logout/                           (signed in) -> 204

"Signed in" means an `Authorization: Token <token>` header carrying a token from one of
the first three (accounts/tokens.py). `user` is {"username", "google_email",
"has_password"}: `google_email` is null with no Google account linked, and "" when
Google shared no verified address. Errors are `{"error": {"code", "message"}}`, as in
recommend/views.py.

Signing in is optional; the recommendation API does not read the token. Usernames are
3 to 30 letters, digits or . @ + - _, unique ignoring case, and log in in any case.
Passwords must pass settings.AUTH_PASSWORD_VALIDATORS (400 `weak_password`). A wrong
username and a wrong password get the same 401 `invalid_credentials`.

`google` signs in with the user a Google account is linked to, or creates one named after
its email (201, `created` true) with no password. `google/link` links a Google account
to the signed-in user, so that either way of signing in reaches the same account; a
Google account belongs to one user only (409 `google_in_use`), and a user has one
Google account (409 `already_linked`). Without METCHU_GOOGLE_CLIENT_ID both are 503
`google_unavailable` (accounts/google.py).
"""

from __future__ import annotations

import json
import re

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from . import google, tokens
from .models import GoogleIdentity

User = get_user_model()
USERNAME = re.compile(r"[\w.@+-]{3,30}")


def _error(status: int, code: str, message: str) -> JsonResponse:
    return JsonResponse({"error": {"code": code, "message": message}}, status=status)


def _body(request) -> dict:
    if not request.body:
        return {}
    payload = json.loads(request.body)
    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object body.")
    return payload


def _text(payload: dict, field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required.")
    return value


def _not_signed_in() -> JsonResponse:
    return _error(401, "not_authenticated", "Sign in first.")


def _google_of(user) -> GoogleIdentity | None:
    try:
        return user.google
    except GoogleIdentity.DoesNotExist:
        return None


def _user(user) -> dict:
    identity = _google_of(user)
    return {"username": user.username, "google_email": identity.email if identity else None,
            "has_password": user.has_usable_password()}


def _signed_in(user, status: int = 200, **extra) -> JsonResponse:
    return JsonResponse({"token": tokens.issue(user), "user": _user(user), **extra}, status=status)


def _google_account(request) -> google.GoogleAccount | JsonResponse:
    """The checked Google account of the request's `id_token`, or the error to return."""
    try:
        return google.verify(_text(_body(request), "id_token"))
    except ValueError as error:  # includes json.JSONDecodeError
        return _error(400, "invalid_request", str(error))
    except google.GoogleUnavailable as error:
        return _error(503, "google_unavailable", str(error))
    except google.InvalidGoogleToken:
        return _error(401, "invalid_google_token", "Google could not confirm this sign-in.")


def _free_username(email: str) -> str:
    base = re.sub(r"[^\w.+-]", "", email.partition("@")[0])[:26]
    base = base if len(base) >= 3 else "google"
    name, number = base, 1
    while User.objects.filter(username__iexact=name).exists():
        number += 1
        name = f"{base}{number}"
    return name


@csrf_exempt
@require_POST
def sign_up(request):
    try:
        payload = _body(request)
        username, password = _text(payload, "username").strip(), _text(payload, "password")
    except ValueError as error:
        return _error(400, "invalid_request", str(error))
    if not USERNAME.fullmatch(username):
        return _error(400, "invalid_username", "Use 3 to 30 letters, digits or . @ + - _.")
    if User.objects.filter(username__iexact=username).exists():
        return _error(409, "username_taken", "That username is taken.")
    try:
        validate_password(password, User(username=username))
    except ValidationError as error:
        return _error(400, "weak_password", " ".join(error.messages))
    try:
        with transaction.atomic():
            user = User.objects.create_user(username=username, password=password)
    except IntegrityError:
        return _error(409, "username_taken", "That username is taken.")
    return _signed_in(user, 201)


@csrf_exempt
@require_POST
def log_in(request):
    try:
        payload = _body(request)
        username, password = _text(payload, "username").strip(), _text(payload, "password")
    except ValueError as error:
        return _error(400, "invalid_request", str(error))
    stored = User.objects.filter(username__iexact=username).values_list("username", flat=True).first()
    # authenticate() hashes the password even for an unknown user, so timing does not tell.
    user = authenticate(request, username=stored or username, password=password)
    if user is None:
        return _error(401, "invalid_credentials", "Wrong username or password.")
    return _signed_in(user)


@csrf_exempt
@require_POST
def google_sign_in(request):
    account = _google_account(request)
    if isinstance(account, JsonResponse):
        return account
    identity = GoogleIdentity.objects.select_related("user").filter(subject=account.subject).first()
    if identity is None:
        try:
            with transaction.atomic():
                user = User.objects.create_user(username=_free_username(account.email))
                GoogleIdentity.objects.create(user=user, subject=account.subject, email=account.email)
            return _signed_in(user, 201, created=True)
        except IntegrityError:  # the same account signing in twice at once
            identity = GoogleIdentity.objects.select_related("user").get(subject=account.subject)
    if not identity.user.is_active:
        return _error(401, "invalid_credentials", "This account is disabled.")
    if account.email and identity.email != account.email:
        identity.email = account.email
        identity.save(update_fields=["email"])
    return _signed_in(identity.user, created=False)


@csrf_exempt
@require_POST
def link_google(request):
    user = tokens.user_for(request)
    if user is None:
        return _not_signed_in()
    account = _google_account(request)
    if isinstance(account, JsonResponse):
        return account
    owner = GoogleIdentity.objects.filter(subject=account.subject).first()
    if owner is not None and owner.user_id != user.pk:
        return _error(409, "google_in_use", "This Google account is linked to another account.")
    current = _google_of(user)
    if current is not None and current.subject != account.subject:
        return _error(409, "already_linked", "This account is linked to another Google account.")
    if current is None:
        try:
            with transaction.atomic():
                GoogleIdentity.objects.create(user=user, subject=account.subject, email=account.email)
        except IntegrityError:
            return _error(409, "google_in_use", "This Google account is linked to another account.")
    elif account.email and current.email != account.email:
        current.email = account.email
        current.save(update_fields=["email"])
    user.refresh_from_db()
    return JsonResponse({"user": _user(user)})


@require_GET
def me(request):
    user = tokens.user_for(request)
    if user is None:
        return _not_signed_in()
    return JsonResponse({"user": _user(user)})


@csrf_exempt
@require_POST
def log_out(request):
    record = tokens.token_for(request)
    if record is None:
        return _not_signed_in()
    record.delete()
    return HttpResponse(status=204)
