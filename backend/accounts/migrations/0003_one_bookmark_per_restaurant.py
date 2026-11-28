"""Collapse the dish bookmarks to one per user and restaurant before 0004 drops the dish fields.

The row kept is the earliest saved (by created_at, then id), so a restaurant keeps the date it was
first bookmarked. Going back keeps the rows as they are: the removed duplicates are not restored.
"""

from django.db import migrations


def keep_the_earliest(apps, schema_editor):
    Bookmark = apps.get_model("accounts", "Bookmark")
    rows = Bookmark.objects.using(schema_editor.connection.alias)
    seen, extra = set(), []
    for pk, user_id, restaurant in rows.order_by("created_at", "id").values_list("id", "user_id", "restaurant"):
        if (user_id, restaurant) in seen:
            extra.append(pk)
        seen.add((user_id, restaurant))
    rows.filter(pk__in=extra).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_bookmarks_history'),
    ]

    operations = [
        migrations.RunPython(keep_the_earliest, migrations.RunPython.noop),
    ]
