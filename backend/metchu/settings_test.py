# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""Settings for pytest (pytest.ini): the app's settings, always on local SQLite.

pytest reads these before any conftest.py runs, so this is the one place that
can keep a test run off a database named in the environment, such as a shared
one. Django creates its own throwaway test database from this entry.
"""

from .settings import *  # noqa: F401,F403
from .settings import BASE_DIR

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}
