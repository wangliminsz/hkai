from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("funds", "0002_fundbroadcast_edition_fundbroadcast_kind_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="fundbroadcast",
            name="kind",
            field=models.CharField(
                default="fund",
                help_text="fund / news / analysis",
                max_length=16,
                verbose_name="类型",
            ),
        ),
    ]
