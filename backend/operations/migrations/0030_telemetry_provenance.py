from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('operations', '0029_reviewed_experience')]
    operations = [migrations.AddField(model_name='telemetry', name='provenance',
        field=models.JSONField(blank=True, default=dict))]
