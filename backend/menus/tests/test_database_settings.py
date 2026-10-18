# AI-generated: written with Claude (Anthropic) and reviewed by the team.
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from metchu.database import database_config

BASE = Path("/srv/metchu/backend")
SUPABASE = "postgresql://postgres.abcdref:secret@aws-0-ap-northeast-2.pooler.supabase.com:5432/postgres"


class DatabaseConfigTests(SimpleTestCase):
    def test_no_url_means_local_sqlite(self):
        db = database_config({}, ["manage.py", "runserver"], BASE)["default"]
        self.assertEqual((db["ENGINE"], db["NAME"]), ("django.db.backends.sqlite3", BASE / "db.sqlite3"))

    def test_supabase_url_means_postgres_over_ssl(self):
        db = database_config({"DATABASE_URL": SUPABASE}, ["manage.py", "runserver"], BASE)["default"]
        self.assertEqual(db["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual((db["HOST"], db["PORT"], db["USER"]),
                         ("aws-0-ap-northeast-2.pooler.supabase.com", 5432, "postgres.abcdref"))
        self.assertEqual(db["OPTIONS"], {"sslmode": "require"})
        self.assertEqual(db["CONN_MAX_AGE"], 0)

    def test_a_sqlite_url_gets_no_ssl_option(self):
        db = database_config({"DATABASE_URL": "sqlite:///db.sqlite3"}, ["manage.py", "dumpdata"], BASE)["default"]
        self.assertEqual(db["ENGINE"], "django.db.backends.sqlite3")
        self.assertNotIn("sslmode", db.get("OPTIONS", {}))

    def test_tests_never_use_the_shared_database(self):
        db = database_config({"DATABASE_URL": SUPABASE}, ["manage.py", "test", "menus"], BASE)["default"]
        self.assertEqual(db["ENGINE"], "django.db.backends.sqlite3")

    def test_this_test_run_is_on_sqlite(self):
        self.assertEqual(settings.DATABASES["default"]["ENGINE"], "django.db.backends.sqlite3")
