from django.conf import settings
from django.db import migrations, models
from django.db.migrations.exceptions import IrreversibleError


def refuse_while_bookmarked(apps, schema_editor):
    if apps.get_model("accounts", "Bookmark").objects.using(schema_editor.connection.alias).exists():
        raise IrreversibleError(
            "Bookmarks are saved per restaurant and the dish fields are gone, so they cannot go back to "
            "0002. Restore a database backup taken before accounts 0003 instead."
        )


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_one_bookmark_per_restaurant'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='bookmark',
            name='unique_bookmark_per_user',
        ),
        migrations.RemoveField(
            model_name='bookmark',
            name='display_name',
        ),
        migrations.RemoveField(
            model_name='bookmark',
            name='food_id',
        ),
        migrations.AddConstraint(
            model_name='bookmark',
            constraint=models.UniqueConstraint(fields=('user', 'restaurant'), name='unique_bookmark_per_restaurant'),
        ),
        migrations.RunPython(migrations.RunPython.noop, refuse_while_bookmarked),
    ]
