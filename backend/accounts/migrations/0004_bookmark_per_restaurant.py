from django.conf import settings
from django.db import migrations, models


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
    ]
