"""Checking the Google ID token the app gets from "Sign in with Google".

The app asks Google for an ID token addressed to the team's web OAuth client
(settings.GOOGLE_OAUTH_CLIENT_ID, from METCHU_GOOGLE_CLIENT_ID). google-auth checks
its signature against Google's public keys, its expiry, its issuer and that audience.
Tests patch `id_token.verify_oauth2_token`, so they make no network call.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from google.auth.exceptions import TransportError
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token


class GoogleUnavailable(Exception):
    """The server has no Google client ID, or cannot reach Google for its keys."""


class InvalidGoogleToken(Exception):
    """Not a valid, current Google ID token for this app."""


@dataclass(frozen=True)
class GoogleAccount:
    subject: str
    email: str  # "" unless Google verified it


def verify(token: str) -> GoogleAccount:
    client_id = settings.GOOGLE_OAUTH_CLIENT_ID
    if not client_id:
        raise GoogleUnavailable("Google sign-in is not set up on this server.")
    try:
        claims = id_token.verify_oauth2_token(token, google_requests.Request(), client_id)
    except TransportError as error:
        raise GoogleUnavailable("Could not reach Google to check the sign-in.") from error
    except ValueError as error:  # bad signature, expired, another audience or issuer
        raise InvalidGoogleToken(str(error)) from error
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise InvalidGoogleToken("The token names no Google account.")
    email = claims.get("email") if claims.get("email_verified") is True else ""
    return GoogleAccount(subject, email if isinstance(email, str) else "")
