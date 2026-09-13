from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0024_controllercommandconfirmation'),
    ]

    operations = [
        migrations.AddField(
            model_name='reportexport',
            name='filters',
            field=models.JSONField(blank=True, default=dict, editable=False),
        ),
    ]
