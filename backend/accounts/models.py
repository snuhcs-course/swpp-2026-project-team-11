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


class Bookmark(models.Model):
    """A dish a user saved, by the restaurant and dish name the phone showed. `food_id` is the
    result's ID when last saved; it is not the key, since it can change from day to day."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bookmarks")
    food_id = models.BigIntegerField()
    display_name = models.CharField(max_length=500)  # as long as a menu name
    restaurant = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "restaurant", "display_name"],
                                               name="unique_bookmark_per_user")]


class HistoryEntry(models.Model):
    """A dish a solo session proposed to a signed-in user, once per session (accounts/history.py)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="history")
    session_id = models.CharField(max_length=32)
    date = models.DateField()
    meal = models.CharField(max_length=2, null=True)  # null: the whole day
    food_id = models.BigIntegerField()
    display_name = models.CharField(max_length=500)  # as long as a menu name
    restaurant = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "session_id", "food_id"],
                                               name="unique_history_per_session_dish")]
