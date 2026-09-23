from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('operations', '0020_twinmodelrelease_node_inventory_available'),
    ]

    operations = [
        migrations.CreateModel(
            name='WorkOrderEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('event_type', models.CharField(choices=[('created', '已创建'), ('transition', '状态变更')], max_length=20)),
                ('from_status', models.CharField(blank=True, choices=[('draft', '草稿'), ('open', '待分派'), ('assigned', '已分派'), ('in_progress', '处理中'), ('pending_review', '待复核'), ('completed', '已完成'), ('cancelled', '已取消')], max_length=20)),
                ('to_status', models.CharField(blank=True, choices=[('draft', '草稿'), ('open', '待分派'), ('assigned', '已分派'), ('in_progress', '处理中'), ('pending_review', '待复核'), ('completed', '已完成'), ('cancelled', '已取消')], max_length=20)),
                ('note', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('actor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='work_order_events', to=settings.AUTH_USER_MODEL)),
                ('work_order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='events', to='operations.workorder')),
            ],
            options={
                'ordering': ['-created_at', '-id'],
                'indexes': [models.Index(fields=['work_order', '-created_at'], name='wo_event_order_time_idx')],
            },
        ),
    ]
