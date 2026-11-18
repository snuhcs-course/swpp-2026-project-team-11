"""Publish staged menu tables without replacing accounts or authentication tokens."""
import sqlite3
from contextlib import closing


def publish_menus(stage, live):
    with closing(sqlite3.connect(live, timeout=30)) as db:
        # Validate the complete replacement before commit; no partial menu state is visible.
        db.execute('PRAGMA foreign_keys=OFF')
        db.execute('ATTACH DATABASE ? AS staged', (str(stage),))
        try:
            db.execute('BEGIN IMMEDIATE')
            db.execute('PRAGMA defer_foreign_keys=ON')
            names = [r[0] for r in db.execute("SELECT name FROM main.sqlite_master WHERE type='table' AND name GLOB 'menus_*'")]
            staged = {r[0] for r in db.execute("SELECT name FROM staged.sqlite_master WHERE type='table' AND name GLOB 'menus_*'")}
            if set(names) != staged:
                raise RuntimeError('Migrate both live and staged menu schemas before publication')
            for name in names:
                quoted = '"' + name.replace('"', '""') + '"'
                db.execute(f'DELETE FROM main.{quoted}')
                db.execute(f'INSERT INTO main.{quoted} SELECT * FROM staged.{quoted}')
                db.execute('DELETE FROM main.sqlite_sequence WHERE name=?', (name,))
                db.execute('INSERT INTO main.sqlite_sequence SELECT * FROM staged.sqlite_sequence WHERE name=?', (name,))
            if db.execute('PRAGMA main.foreign_key_check').fetchall():
                raise RuntimeError('Menu publication violates foreign keys')
            db.commit()
        except BaseException:
            db.rollback()
            raise
