# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""Which database Django uses.

- DATABASE_URL set: that database. For the team this is the shared Supabase
  Postgres (Session pooler URL, see backend/README.md), always over SSL.
- DATABASE_URL unset: local SQLite at backend/db.sqlite3, as before.
- `manage.py test`: always local SQLite, so tests never touch the shared database.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import dj_database_url


def database_config(env: Mapping[str, str], argv: Sequence[str], base_dir: Path) -> dict:
    sqlite = {"ENGINE": "django.db.backends.sqlite3", "NAME": base_dir / "db.sqlite3"}
    url = (env.get("DATABASE_URL") or "").strip()
    if not url or list(argv[1:2]) == ["test"]:
        return {"default": sqlite}
    is_postgres = url.startswith(("postgres://", "postgresql://"))
    # dj-database-url adds sslmode even to SQLite when asked, so only ask for Postgres.
    # conn_max_age=0: runserver uses a thread per request, so Django advises against
    # persistent connections in development.
    return {"default": dj_database_url.parse(url, conn_max_age=0, ssl_require=is_postgres)}
