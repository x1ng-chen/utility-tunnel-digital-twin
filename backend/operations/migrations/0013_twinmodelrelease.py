import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import operations.models


class Migration(migrations.Migration):
    dependencies = [
        ('operations', '0012_asset_mesh_name_unique_ci'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='TwinModelRelease',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('version', models.CharField(max_length=40, unique=True)),
                ('model_file', models.FileField(max_length=180, upload_to=operations.models.twin_model_upload_path)),
                ('original_name', models.CharField(max_length=180)),
                ('sha256', models.CharField(editable=False, max_length=64, unique=True)),
                ('size_bytes', models.PositiveBigIntegerField(editable=False)),
                ('notes', models.CharField(blank=True, max_length=500)),
                ('status', models.CharField(choices=[('draft', '待启用'), ('active', '使用中'), ('retired', '历史版本')], default='draft', max_length=20)),
                ('activated_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('activated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='activated_twin_models', to=settings.AUTH_USER_MODEL)),
                ('uploaded_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='uploaded_twin_models', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['status', '-created_at'], name='twin_release_status_idx')],
                'constraints': [
                    models.UniqueConstraint(condition=models.Q(status='active'), fields=('status',), name='twin_single_active_release'),
                    models.CheckConstraint(check=models.Q(size_bytes__gt=0), name='twin_release_size_positive'),
                ],
            },
        ),
    ]
