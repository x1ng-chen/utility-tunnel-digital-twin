from django.db import migrations


MESH_UPDATES = {
    'CTRL-01': ('MESH_CTRL_01', 'CTRL-01'),
    'ENV-01': ('MESH_ENV_01', 'ENV-01'),
    'FAN-01': ('MESH_FAN_01', 'FAN-01'),
}


def align_assets(apps, schema_editor):
    Asset = apps.get_model('operations', 'Asset')

    for code, (old_mesh, new_mesh) in MESH_UPDATES.items():
        Asset.objects.filter(code=code, mesh=old_mesh).update(mesh=new_mesh)

    legacy = Asset.objects.filter(code='BT-01').first()
    current = Asset.objects.filter(code='NET-01').first()
    if legacy and not current:
        legacy.code = 'NET-01'
        legacy.hardware_code = 'H-11'
        legacy.name = 'ESP8266-01S 通信模块'
        legacy.asset_type = '无线通信模块'
        legacy.status = 'normal'
        legacy.integration_status = 'verified'
        legacy.interface = 'USART2 9600 bit/s / MQTT'
        legacy.capabilities = ['Wi-Fi 联网', 'MQTT 上报', '断线重连']
        legacy.mesh = 'MESH_ESP01S_01'
        legacy.installation_note = '唯一无线通信链路；已完成 STM32 真机连接与 IoTDA 数据上行。'
        legacy.save()
    elif legacy and current:
        legacy.is_active = False
        legacy.save(update_fields=['is_active'])


def restore_legacy_names(apps, schema_editor):
    Asset = apps.get_model('operations', 'Asset')

    for code, (old_mesh, new_mesh) in MESH_UPDATES.items():
        Asset.objects.filter(code=code, mesh=new_mesh).update(mesh=old_mesh)

    network = Asset.objects.filter(code='NET-01').first()
    if network:
        network.code = 'BT-01'
        network.name = 'HC-05 蓝牙模块'
        network.asset_type = '可选通信模块'
        network.status = 'unknown'
        network.integration_status = 'optional'
        network.interface = 'UART（待分配）'
        network.capabilities = ['近场调试通信']
        network.mesh = 'MESH_BT_01'
        network.installation_note = '可选模块，不属于核心数据链路，当前固件未接入。'
        network.save()


class Migration(migrations.Migration):
    dependencies = [('operations', '0021_workorderevent')]

    operations = [migrations.RunPython(align_assets, restore_legacy_names)]
