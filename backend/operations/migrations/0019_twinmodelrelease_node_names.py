from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('operations', '0018_merge_model_validation_and_v34')]

    operations = [
        migrations.AddField(
            model_name='twinmodelrelease',
            name='node_names',
            field=models.JSONField(blank=True, default=list, editable=False),
        ),
    ]
