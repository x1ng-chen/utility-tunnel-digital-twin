from django.db import migrations, models


def mark_legacy_exports_unavailable(apps, schema_editor):
    ReportExport = apps.get_model('operations', 'ReportExport')
    ReportExport.objects.update(status='failed')


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0015_registrationrequest_setup_token_hash_index'),
    ]

    operations = [
        migrations.AddField(
            model_name='reportexport',
            name='content',
            field=models.BinaryField(default=b'', editable=False),
        ),
        migrations.AddField(
            model_name='reportexport',
            name='content_sha256',
            field=models.CharField(blank=True, editable=False, max_length=64),
        ),
        migrations.AddField(
            model_name='reportexport',
            name='row_count',
            field=models.PositiveIntegerField(default=0, editable=False),
        ),
        migrations.RunPython(mark_legacy_exports_unavailable, migrations.RunPython.noop),
    ]
