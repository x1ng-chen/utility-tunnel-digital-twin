# Generated manually for the short-lived controller-command confirmation record.

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('operations', '0023_add_verified_level_l01'),
    ]

    operations = [
        migrations.CreateModel(
            name='ControllerCommandConfirmation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('token_hash', models.CharField(editable=False, max_length=64, unique=True)),
                ('asset_code', models.CharField(max_length=40)),
                ('action', models.CharField(max_length=20)),
                ('duty_percent', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('expires_at', models.DateTimeField()),
                ('consumed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='controller_command_confirmations', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddIndex(
            model_name='controllercommandconfirmation',
            index=models.Index(fields=['expires_at'], name='controller_confirm_expires_idx'),
        ),
    ]
