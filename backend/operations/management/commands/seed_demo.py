from datetime import timedelta
import os
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from operations.models import Alert, Asset, HardwareBinding, Profile, Telemetry, Threshold, WorkOrder
from operations.release_hygiene import clean_release_test_data


class Command(BaseCommand):
    help = 'Create deterministic local demonstration data for the Vue 3 + Django stack.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clean-e2e-data',
            action='store_true',
            help='Remove only records created by the browser regression suite before seeding demo data.',
        )

    def handle(self, *args, **options):
        if settings.IS_PRODUCTION:
            raise CommandError('seed_demo is disabled in production environments.')
        admin_account = os.getenv('SEED_ADMIN_EMAIL', 'admin').strip() or 'admin'
        admin_password = '123'
        if options['clean_e2e_data']:
            clean_release_test_data()
        users = [
            (admin_account, '管理员', Profile.Role.ADMINISTRATOR, admin_password),
            ('operator@example.com', '运维员', Profile.Role.OPERATOR, 'demo-password-2026'),
            ('viewer@example.com', '查看者', Profile.Role.VIEWER, 'demo-password-2026'),
        ]
        created_users = {}
        for username, display_name, role, password in users:
            legacy_username = 'admin@example.com' if username == 'admin' else username
            user = User.objects.filter(username=username).first() or User.objects.filter(username=legacy_username).first()
            if user is None:
                user = User(username=username)
            user.username = username
            user.email = username
            user.first_name = display_name
            user.set_password(password)
            user.save()
            Profile.objects.update_or_create(user=user, defaults={'display_name': display_name, 'role': role})
            created_users[role] = user

        now = timezone.now()
        # Coordinates use a clearly identified demonstration anchor. They are
        # not represented as surveyed/GPS locations until site data is entered.
        assets = [
            {'code': 'CTRL-01', 'hardware_code': 'H-01', 'name': 'STM32F103RCT6 主控板', 'zone': 'CTRL', 'asset_type': '控制器', 'status': Asset.Status.NORMAL, 'integration_status': Asset.IntegrationStatus.VERIFIED, 'interface': '板载 GPIO / ADC / EXTI', 'capabilities': ['系统调度', '数据采集', '本地状态输出'], 'mesh': 'CTRL-01', 'position': {'x': 15, 'y': 52, 'z': 0}, 'latitude': 31.230400, 'longitude': 121.473700, 'installation_note': '实物主控板；当前固件入口与调度逻辑已验证。'},
            {'code': 'LED-01', 'hardware_code': 'H-02', 'name': '5V RGB 灯带', 'zone': 'UT-ZA', 'asset_type': '执行器', 'status': Asset.Status.UNKNOWN, 'integration_status': Asset.IntegrationStatus.PENDING_VERIFICATION, 'interface': '5V 单总线（待确认）', 'capabilities': ['状态灯效', '告警联动'], 'mesh': 'MESH_LED_01', 'position': {'x': 24, 'y': 32, 'z': 0}, 'latitude': 31.230455, 'longitude': 121.473760, 'installation_note': '实物已到位；供电能力和时序尚未验证，当前固件未接入。'},
            {'code': 'DISP-01', 'hardware_code': 'H-03', 'name': 'ST7735S TFT 显示屏', 'zone': 'CTRL', 'asset_type': '显示模块', 'status': Asset.Status.NORMAL, 'integration_status': Asset.IntegrationStatus.VERIFIED, 'interface': 'PB4-PB9 软件 SPI', 'capabilities': ['温湿度显示', '水位显示', '振动状态显示'], 'mesh': 'MESH_DISP_01', 'position': {'x': 20, 'y': 62, 'z': 0}, 'latitude': 31.230415, 'longitude': 121.473715, 'installation_note': '实物与当前固件已验证。'},
            {'code': 'SEEP-W01', 'hardware_code': 'H-04', 'name': '水位传感器', 'zone': 'UT-ZB', 'asset_type': '测点', 'status': Asset.Status.WARNING, 'integration_status': Asset.IntegrationStatus.CALIBRATION_REQUIRED, 'interface': 'PC0 / ADC1_IN10', 'capabilities': ['8 次采样平均', '水位趋势', '阈值告警'], 'mesh': 'MESH_SEEP_W01', 'position': {'x': 58, 'y': 70, 'z': 0}, 'latitude': 31.230505, 'longitude': 121.473910, 'installation_note': '固件已接入；阈值 1000 为临时值，需完成现场标定。'},
            {'code': 'MOIST-01', 'hardware_code': 'H-05', 'name': '土壤湿度传感器', 'zone': 'UT-ZB', 'asset_type': '辅助测点', 'status': Asset.Status.UNKNOWN, 'integration_status': Asset.IntegrationStatus.OPTIONAL, 'interface': '模拟量（待分配）', 'capabilities': ['辅助湿度趋势'], 'mesh': 'MESH_MOIST_01', 'position': {'x': 64, 'y': 64, 'z': 0}, 'latitude': 31.230535, 'longitude': 121.473955, 'installation_note': '仅作辅助展示，不用于安全联锁，当前固件未接入。'},
            {'code': 'ENV-01', 'hardware_code': 'H-06', 'name': 'DHT11 温湿度传感器', 'zone': 'UT-ZA', 'asset_type': '环境测点', 'status': Asset.Status.NORMAL, 'integration_status': Asset.IntegrationStatus.VERIFIED, 'interface': 'PA1 单总线', 'capabilities': ['环境温度', '环境湿度', '约 2 秒采样'], 'mesh': 'ENV-01', 'position': {'x': 34, 'y': 44, 'z': 0}, 'latitude': 31.230475, 'longitude': 121.473815, 'installation_note': '实物与当前固件已验证。'},
            {'code': 'GAS-01', 'hardware_code': 'H-12', 'name': '气体监测节点', 'zone': 'UT-ZC', 'asset_type': '环境测点', 'status': Asset.Status.UNKNOWN, 'integration_status': Asset.IntegrationStatus.PENDING_VERIFICATION, 'interface': '采集接口待分配', 'capabilities': ['氧气安装位', '一氧化碳安装位', '甲烷安装位'], 'mesh': 'MESH_GAS_SAMPLE_MANIFOLD_01', 'position': {'x': 80, 'y': 45, 'z': 0}, 'latitude': 31.230610, 'longitude': 121.474095, 'installation_note': '三合一采样歧管已纳入实体模型；传感器型号、接口和标定状态需由硬件组确认后接入。'},
            {'code': 'VIB-01', 'hardware_code': 'H-07', 'name': 'SW-420 振动传感器', 'zone': 'UT-ZC', 'asset_type': '安全测点', 'status': Asset.Status.WARNING, 'integration_status': Asset.IntegrationStatus.FIRMWARE_CONNECTED, 'interface': 'PA4 / EXTI4 双边沿', 'capabilities': ['振动事件', '5 秒状态锁存'], 'mesh': 'MESH_VIB_01', 'position': {'x': 76, 'y': 44, 'z': 0}, 'latitude': 31.230590, 'longitude': 121.474070, 'installation_note': '固件已接入，等待实体振动场景复核。'},
            {'code': 'BUZZ-01', 'hardware_code': 'H-08', 'name': '有源蜂鸣器', 'zone': 'CTRL', 'asset_type': '声光执行器', 'status': Asset.Status.UNKNOWN, 'integration_status': Asset.IntegrationStatus.PENDING_VERIFICATION, 'interface': 'GPIO（待分配）', 'capabilities': ['本地声报警'], 'mesh': 'MESH_BUZZ_01', 'position': {'x': 26, 'y': 58, 'z': 0}, 'latitude': 31.230430, 'longitude': 121.473730, 'installation_note': '实物已到位；电平与工作电压待确认，当前固件未接入。'},
            {'code': 'RELAY-01', 'hardware_code': 'H-09', 'name': '5V 继电器模块', 'zone': 'CTRL', 'asset_type': '控制执行器', 'status': Asset.Status.UNKNOWN, 'integration_status': Asset.IntegrationStatus.PENDING_VERIFICATION, 'interface': 'GPIO（待分配）', 'capabilities': ['隔离开关控制'], 'mesh': 'MESH_RELAY_01', 'position': {'x': 31, 'y': 62, 'z': 0}, 'latitude': 31.230445, 'longitude': 121.473745, 'installation_note': '实物已到位；触发电平待确认，当前固件未接入。'},
            {'code': 'FAN-01', 'hardware_code': 'H-10', 'name': '小风扇与 IN-A/IN-B 驱动', 'zone': 'UT-ZC', 'asset_type': '通风执行器', 'status': Asset.Status.UNKNOWN, 'integration_status': Asset.IntegrationStatus.PENDING_VERIFICATION, 'interface': '双路 GPIO（待分配）', 'capabilities': ['启停控制', '通风联动'], 'mesh': 'FAN-01', 'position': {'x': 84, 'y': 34, 'z': 0}, 'latitude': 31.230630, 'longitude': 121.474125, 'installation_note': '实物已到位；电压、电流、驱动与反馈链路待验证，当前固件未接入。'},
            {'code': 'NET-01', 'hardware_code': 'H-11', 'name': 'ESP8266-01S 通信模块', 'zone': 'CTRL', 'asset_type': '无线通信模块', 'status': Asset.Status.NORMAL, 'integration_status': Asset.IntegrationStatus.VERIFIED, 'interface': 'USART2 9600 bit/s / MQTT', 'capabilities': ['Wi-Fi 联网', 'MQTT 上报', '断线重连'], 'mesh': 'MESH_ESP01S_01', 'position': {'x': 36, 'y': 56, 'z': 0}, 'latitude': 31.230460, 'longitude': 121.473760, 'installation_note': '唯一无线通信链路；已完成 STM32 真机连接与 IoTDA 数据上行。'},
            {'code': 'PCB-01', 'hardware_code': 'H-25', 'name': '洞洞板', 'zone': 'CTRL', 'asset_type': '施工辅材', 'status': Asset.Status.UNKNOWN, 'integration_status': Asset.IntegrationStatus.NON_OPERATIONAL, 'interface': '无', 'capabilities': ['转接与固定'], 'mesh': 'MESH_PCB_01', 'position': {'x': 41, 'y': 63, 'z': 0}, 'latitude': 31.230475, 'longitude': 121.473775, 'installation_note': '非运行资产，仅用于电气转接和实体安装。'},
        ]
        # Migrate the discontinued Bluetooth placeholder in local demo
        # databases without creating a second communication asset. Production
        # databases receive the same guarded transition through migration 0022.
        legacy_network = Asset.objects.filter(code='BT-01').first()
        if legacy_network and not Asset.objects.filter(code='NET-01').exists():
            legacy_network.code = 'NET-01'
            legacy_network.save(update_fields=['code'])

        asset_by_code = {}
        for spec in assets:
            code = spec['code']
            defaults = {key: value for key, value in spec.items() if key != 'code'}
            defaults.update({'location_source': Asset.LocationSource.DEMO_ANCHOR, 'last_seen_at': now if spec['integration_status'] in {Asset.IntegrationStatus.VERIFIED, Asset.IntegrationStatus.FIRMWARE_CONNECTED, Asset.IntegrationStatus.CALIBRATION_REQUIRED} else None, 'is_active': True, 'version': 1})
            asset, _ = Asset.objects.update_or_create(code=code, defaults=defaults)
            asset_by_code[code] = asset

        # These are integration contracts only. They reserve stable identifiers
        # for future gateways and never claim that an unconnected module is online.
        for code, asset in asset_by_code.items():
            HardwareBinding.objects.update_or_create(
                asset=asset,
                defaults={
                    'protocol': HardwareBinding.Protocol.MQTT,
                    'device_identifier': f'ut-demo-{code.lower()}',
                    'endpoint': f'ut/v1/{code.lower()}/telemetry',
                    'expected_interval_seconds': 60,
                    'status': HardwareBinding.Status.RESERVED,
                    'last_heartbeat_at': None,
                    'version': 1,
                },
            )

        alert_specs = [
            ('ALM-260826-003', 'SEEP-W01', Alert.Severity.WARNING, '水浸趋势', Alert.Status.OPEN, '水浸趋势异常', '渗水趋势上升，需确认现场情况并安排巡检。'),
            ('ALM-260826-002', 'FAN-01', Alert.Severity.CRITICAL, '设备反馈', Alert.Status.ACKNOWLEDGED, '风机反馈丢失', '执行反馈暂未返回，正在等待工单复核。'),
            ('ALM-260826-001', 'CTRL-01', Alert.Severity.WARNING, '通信质量', Alert.Status.OPEN, '控制器通信质量波动', '控制器出现短时延迟抖动，建议建立巡检工单并观察后续遥测。'),
        ]
        alert_by_code = {}
        for code, asset_code, severity, category, alert_status, title, detail in alert_specs:
            alert, _ = Alert.objects.update_or_create(code=code, defaults={'asset': asset_by_code[asset_code], 'severity': severity, 'category': category, 'status': alert_status, 'title': title, 'detail': detail, 'opened_at': now, 'acknowledged_by': created_users[Profile.Role.OPERATOR] if alert_status == Alert.Status.ACKNOWLEDGED else None, 'acknowledged_at': now if alert_status == Alert.Status.ACKNOWLEDGED else None, 'resolved_at': None})
            alert_by_code[code] = alert

        WorkOrder.objects.update_or_create(code='WO-260826-08', defaults={'source_alert': alert_by_code['ALM-260826-003'], 'asset': asset_by_code['SEEP-W01'], 'title': '检查 UT-ZB 接水盘与水位探针', 'priority': WorkOrder.Priority.HIGH, 'status': WorkOrder.Status.OPEN, 'assignee': None, 'created_by': created_users[Profile.Role.OPERATOR], 'due_at': now + timedelta(hours=6), 'completed_at': None, 'reviewed_by': None, 'version': 1})
        WorkOrder.objects.update_or_create(code='WO-260826-06', defaults={'source_alert': alert_by_code['ALM-260826-002'], 'asset': asset_by_code['FAN-01'], 'title': '复核风机反馈与现场状态', 'priority': WorkOrder.Priority.URGENT, 'status': WorkOrder.Status.IN_PROGRESS, 'assignee': created_users[Profile.Role.OPERATOR], 'created_by': created_users[Profile.Role.OPERATOR], 'due_at': now + timedelta(hours=8), 'completed_at': None, 'reviewed_by': None, 'version': 1})

        for asset_code, metric_key, metric, value, unit, quality in [('ENV-01', 'temperature', '环境温度', 26.4, '°C', Telemetry.Quality.GOOD), ('SEEP-W01', 'water_adc', '水位 ADC', 684, 'ADC', Telemetry.Quality.SUSPECT), ('VIB-01', 'vibration', '振动锁存', 0, 'bool', Telemetry.Quality.GOOD), ('CTRL-01', 'sample_period', '采集周期', 2.0, 's', Telemetry.Quality.GOOD)]:
            Telemetry.objects.update_or_create(asset=asset_by_code[asset_code], metric=metric, defaults={'event_id': f'demo:{asset_code}:{metric_key}', 'metric_key': metric_key, 'value': value, 'unit': unit, 'quality': quality, 'recorded_at': now})

        for key, label, warning, alarm, unit in [('temperature', '环境温度', 28, 32, '°C'), ('humidity', '环境湿度', 75, 85, '%RH'), ('water', '水浸趋势', 20, 45, '秒')]:
            Threshold.objects.update_or_create(key=key, defaults={'label': label, 'warning': warning, 'alarm': alarm, 'unit': unit})
        self.stdout.write(self.style.SUCCESS(f'Django demo data seeded. Local administrator: {admin_account}; fixed password: 123.'))
