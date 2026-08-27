from datetime import timedelta
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone
from operations.models import Alert, Asset, Profile, Telemetry, Threshold, WorkOrder


class Command(BaseCommand):
    help = 'Create deterministic local demonstration data for the Vue 3 + Django stack.'

    def handle(self, *args, **options):
        users = [
            ('admin@example.com', '管理员', Profile.Role.ADMINISTRATOR),
            ('operator@example.com', '运维员', Profile.Role.OPERATOR),
            ('viewer@example.com', '查看者', Profile.Role.VIEWER),
        ]
        created_users = {}
        for email, display_name, role in users:
            user, _ = User.objects.get_or_create(username=email, defaults={'email': email, 'first_name': display_name})
            user.email = email
            user.set_password('demo-password-2026')
            user.save()
            Profile.objects.update_or_create(user=user, defaults={'display_name': display_name, 'role': role})
            created_users[role] = user

        now = timezone.now()
        assets = [
            ('CTRL-01', '现场控制器', 'UT-ZA', '控制器', Asset.Status.NORMAL, 'MESH_CTRL_01', {'x': 20, 'y': 50, 'z': 0}),
            ('FAN-01', '送风机 #01', 'UT-ZB', '执行器', Asset.Status.NORMAL, 'MESH_FAN_01', {'x': 52, 'y': 38, 'z': 0}),
            ('SEEP-W01', '渗水监测点', 'UT-ZB', '测点', Asset.Status.WARNING, 'MESH_SEEP_W01', {'x': 70, 'y': 68, 'z': 0}),
            ('GAS-01', '甲烷监测节点', 'UT-ZC', '测点', Asset.Status.NORMAL, 'MESH_GAS_01', {'x': 84, 'y': 44, 'z': 0}),
        ]
        asset_by_code = {}
        for code, name, zone, asset_type, status, mesh, position in assets:
            asset, _ = Asset.objects.update_or_create(code=code, defaults={'name': name, 'zone': zone, 'asset_type': asset_type, 'status': status, 'mesh': mesh, 'last_seen_at': now, 'position': position})
            asset_by_code[code] = asset

        alert_specs = [
            ('ALM-260826-003', 'SEEP-W01', Alert.Severity.WARNING, '水浸趋势', Alert.Status.OPEN, '水浸趋势异常', '渗水趋势上升，需确认现场情况并安排巡检。'),
            ('ALM-260826-002', 'FAN-01', Alert.Severity.CRITICAL, '设备反馈', Alert.Status.ACKNOWLEDGED, '风机反馈丢失', '执行反馈暂未返回，正在等待工单复核。'),
            ('ALM-260826-001', 'CTRL-01', Alert.Severity.WARNING, '通信质量', Alert.Status.OPEN, '控制器通信质量波动', '控制器出现短时延迟抖动，建议建立巡检工单并观察后续遥测。'),
        ]
        alert_by_code = {}
        for code, asset_code, severity, category, alert_status, title, detail in alert_specs:
            alert, _ = Alert.objects.update_or_create(code=code, defaults={'asset': asset_by_code[asset_code], 'severity': severity, 'category': category, 'status': alert_status, 'title': title, 'detail': detail, 'opened_at': now, 'acknowledged_by': created_users[Profile.Role.OPERATOR] if alert_status == Alert.Status.ACKNOWLEDGED else None, 'acknowledged_at': now if alert_status == Alert.Status.ACKNOWLEDGED else None})
            alert_by_code[code] = alert

        WorkOrder.objects.update_or_create(code='WO-260826-08', defaults={'source_alert': alert_by_code['ALM-260826-003'], 'asset': asset_by_code['SEEP-W01'], 'title': '检查 UT-ZB 接水盘与水位探针', 'priority': WorkOrder.Priority.HIGH, 'status': WorkOrder.Status.OPEN, 'created_by': created_users[Profile.Role.OPERATOR], 'due_at': now + timedelta(hours=6)})
        WorkOrder.objects.update_or_create(code='WO-260826-06', defaults={'source_alert': alert_by_code['ALM-260826-002'], 'asset': asset_by_code['FAN-01'], 'title': '复核风机反馈与现场状态', 'priority': WorkOrder.Priority.URGENT, 'status': WorkOrder.Status.IN_PROGRESS, 'assignee': created_users[Profile.Role.OPERATOR], 'created_by': created_users[Profile.Role.OPERATOR], 'due_at': now + timedelta(hours=8)})

        for asset_code, metric, value, unit, quality in [('FAN-01', '风机转速', 1248, 'rpm', Telemetry.Quality.GOOD), ('SEEP-W01', '积水趋势', 68, '%', Telemetry.Quality.SUSPECT), ('GAS-01', '甲烷浓度', 0.03, '%LEL', Telemetry.Quality.GOOD), ('CTRL-01', '通信延迟', 132, 'ms', Telemetry.Quality.GOOD)]:
            Telemetry.objects.update_or_create(asset=asset_by_code[asset_code], metric=metric, defaults={'value': value, 'unit': unit, 'quality': quality, 'recorded_at': now})

        for key, label, warning, alarm, unit in [('temperature', '环境温度', 28, 32, '°C'), ('humidity', '环境湿度', 75, 85, '%RH'), ('water', '水浸趋势', 20, 45, '秒')]:
            Threshold.objects.update_or_create(key=key, defaults={'label': label, 'warning': warning, 'alarm': alarm, 'unit': unit})
        self.stdout.write(self.style.SUCCESS('Django demo data seeded. Users share password: demo-password-2026'))
