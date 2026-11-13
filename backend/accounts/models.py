"""What the server keeps about an account besides Django's own user: app tokens and Google."""

from django.conf import settings
from django.db import models


class AuthToken(models.Model):
    """One signed-in device. Only the SHA-256 of the token is stored (accounts/tokens.py)."""

    key_hash = models.CharField(max_length=64, unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="auth_tokens")
    created_at = models.DateTimeField(auto_now_add=True)


class GoogleIdentity(models.Model):
    """The Google account linked to a user, by Google's stable subject ID (the token's `sub`)."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="google")
    subject = models.CharField(max_length=255, unique=True)
    email = models.EmailField(blank=True)  # only when Google verified it
    linked_at = models.DateTimeField(auto_now_add=True)
