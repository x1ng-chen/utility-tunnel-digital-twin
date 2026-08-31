from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('operations', '0019_twinmodelrelease_node_names'),
    ]

    operations = [
        migrations.AddField(
            model_name='twinmodelrelease',
            name='node_inventory_available',
            field=models.BooleanField(default=False, editable=False),
        ),
    ]
