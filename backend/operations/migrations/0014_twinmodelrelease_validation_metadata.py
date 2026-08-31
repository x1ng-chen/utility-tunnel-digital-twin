from django.db import migrations, models


def trust_previously_validated_releases(apps, schema_editor):
    # Releases created before this migration already passed the strict GLB 2.0
    # container validation. Keep them usable; new uploads receive full node
    # coverage metadata from the API.
    apps.get_model('operations', 'TwinModelRelease').objects.update(is_compatible=True)


class Migration(migrations.Migration):
    dependencies = [('operations', '0013_twinmodelrelease')]

    operations = [
        migrations.AddField(model_name='twinmodelrelease', name='node_count', field=models.PositiveIntegerField(default=0, editable=False)),
        migrations.AddField(model_name='twinmodelrelease', name='mesh_count', field=models.PositiveIntegerField(default=0, editable=False)),
        migrations.AddField(model_name='twinmodelrelease', name='named_node_count', field=models.PositiveIntegerField(default=0, editable=False)),
        migrations.AddField(model_name='twinmodelrelease', name='duplicate_node_names', field=models.JSONField(blank=True, default=list, editable=False)),
        migrations.AddField(model_name='twinmodelrelease', name='missing_asset_codes', field=models.JSONField(blank=True, default=list, editable=False)),
        migrations.AddField(model_name='twinmodelrelease', name='is_compatible', field=models.BooleanField(default=False, editable=False)),
        migrations.RunPython(trust_previously_validated_releases, migrations.RunPython.noop),
    ]
