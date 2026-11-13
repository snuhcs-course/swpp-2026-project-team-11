"""App sign-in tokens, sent as `Authorization: Token <token>`.

A token is made at sign-up or sign-in and returned once. The database keeps only its
SHA-256, so a copy of the database signs no one in. Each device holds its own token,
and signing out deletes that one only.
"""

from __future__ import annotations

import hashlib
import secrets

from .models import AuthToken

SCHEME = "Token "


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue(user) -> str:
    token = secrets.token_urlsafe(32)
    AuthToken.objects.create(user=user, key_hash=_digest(token))
    return token


def token_for(request) -> AuthToken | None:
    """The request's token record, or None without a valid token of an active user."""
    header = request.headers.get("Authorization", "")
    token = header[len(SCHEME):].strip() if header.startswith(SCHEME) else ""
    if not token:
        return None
    return (AuthToken.objects.select_related("user")
            .filter(key_hash=_digest(token), user__is_active=True).first())


def user_for(request):
    """The signed-in user of the request, or None."""
    record = token_for(request)
    return record.user if record else None
