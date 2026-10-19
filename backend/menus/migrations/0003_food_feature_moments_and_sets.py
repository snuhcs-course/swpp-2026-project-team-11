# AI-generated: written with Codex (OpenAI) and reviewed by the team.
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("menus", "0002_menu_lines_and_dish_items")]
    operations = [
        migrations.AddField(model_name="food", name="is_set",
                            field=models.BooleanField(default=False)),
        migrations.AddField(model_name="food", name="feature_std",
                            field=models.JSONField(blank=True, default=dict)),
        migrations.AlterField(model_name="food", name="name",
                              field=models.CharField(max_length=300)),
        migrations.AddConstraint(model_name="food", constraint=models.UniqueConstraint(
            fields=("name", "is_set"), name="unique_food_name_and_set")),
    ]
