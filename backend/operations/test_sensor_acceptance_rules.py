from datetime import timedelta
from django.contrib.auth.models import User
from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from .hardware_live import INVENTORY
from .hardware_alarm_config import RULES, RULE_KEYS, policy
from .management.commands.prepare_sensor_acceptance import install_rules
from .models import Alert, Asset, AuditLog, HardwareBinding, Profile, Telemetry, Threshold, WorkOrder
from .telemetry_rules import evaluate_threshold


class AcceptanceRuleConfigurationTests(TestCase):
    def test_idempotent_configuration_covers_28_sensors_and_explicitly_blocks_uncalibrated_oxygen(self):
        self.assertEqual(len(install_rules()), 7)
        self.assertEqual(install_rules(), [])
        self.assertEqual(Threshold.objects.count(), 7)
        self.assertEqual(AuditLog.objects.count(), 7)
        self.assertFalse(Telemetry.objects.exists())
        result = policy()
        self.assertEqual(len(result['sensors']), 31)
        self.assertEqual(sum(s['status']=='threshold_configured' for s in result['sensors']), 28)
        blocked = [s for s in result['sensors'] if s['status']=='blocked_calibration']
        self.assertEqual(len(blocked), 3)
        self.assertTrue(all(not s['ruleKeys'] and s['reason'] for s in blocked))
        self.assertFalse(Threshold.objects.filter(key__startswith='oxygen.').exists())

    def test_conflicting_existing_rules_abort_without_partial_configuration(self):
        Threshold.objects.create(key='co.raw', label='manual', warning=2000, alarm=2500, unit='adc')
        with self.assertRaises(CommandError): install_rules()
        self.assertEqual(Threshold.objects.count(), 1)
        self.assertFalse(AuditLog.objects.exists())

    def test_command_cannot_write_business_or_test_database(self):
        with self.assertRaises(CommandError): call_command('prepare_sensor_acceptance')
        self.assertFalse(Threshold.objects.exists())


@override_settings(HARDWARE_LIVE_MODE=True, CONTROLLER_COMMAND_PROTOCOL='four-controller-v2')
class AcceptanceRuleEndToEndTests(TestCase):
    def setUp(self):
        install_rules()
        user = User.objects.create_user('rule-ingest')
        Profile.objects.create(user=user, role='ingest')
        self.client = APIClient(); self.client.force_authenticate(user)
        self.user = user
        self.bindings = {b['assetCode']: b for b in INVENTORY['bindings']}
        for b in self.bindings.values():
            asset = Asset.objects.create(code=b['assetCode'], name=b['physicalTag'], asset_type='sensor', zone=b['stationId'])
            HardwareBinding.objects.create(asset=asset, protocol='mqtt', device_identifier='test:'+asset.code,
                endpoint=f'ut/v1/{b["controllerId"]}/telemetry', expected_interval_seconds=2)
        self.seq = 0

    def send(self, code, metric, value, quality='good', age=0):
        rule = next((r for r in RULES if r['key']==metric), None)
        self.seq += 1
        frame = timezone.now()-timedelta(seconds=age, milliseconds=100)
        item = {'assetCode':code,'metricKey':metric,'metric':metric,'unit':rule['unit'] if rule else 'adc',
            'value':value,'quality':quality,'eventId':f'rule-test:{self.seq}',
            'recordedAt':(frame-timedelta(milliseconds=100)).isoformat(),
            'provenance':{'source':'four-controller-rtu-v2', 'controllerId':self.bindings[code]['controllerId'],
                'frameId':f'bench:{self.seq}', 'seq':self.seq, 'layoutVersion':INVENTORY['revision'], 'rawOnly':True,
                'clockSource':'gateway-ntp', 'sampleAgeMs':100, 'frameTimestamp':frame.isoformat()}}
        response = self.client.post('/api/telemetry/', {'readings':[item]}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def test_all_28_supported_physical_channels_trigger_their_own_alarm_and_recover(self):
        from .hardware_live import SPECS
        for code in self.bindings:
            for metric in SPECS[code]:
                if metric not in RULE_KEYS: continue
                rule = next(r for r in RULES if r['key']==metric)
                self.send(code, metric, rule['alarm'])
                alert = Alert.objects.get(asset__code=code, rule_key=metric)
                self.assertEqual((alert.status,alert.severity),('open','critical'))
                self.send(code, metric, 0 if rule['unit']=='bool' else rule['warning']-1)
                alert.refresh_from_db(); self.assertEqual(alert.status,'resolved')
        self.assertEqual(Alert.objects.values('asset_id').distinct().count(), 28)
        self.assertEqual(WorkOrder.objects.count(), 0)

    def test_analog_warning_escalation_and_new_valid_recovery(self):
        for code,metric in [('ENV-01','temperature'),('ENV-01','humidity'),('MQ4-05','methane.raw'),('CO-05','co.raw')]:
            rule = next(r for r in RULES if r['key']==metric)
            self.send(code,metric,rule['warning'])
            alert=Alert.objects.get(asset__code=code,rule_key=metric)
            self.assertEqual(alert.severity,'warning')
            self.send(code,metric,rule['alarm']);alert.refresh_from_db();self.assertEqual(alert.severity,'critical')
            self.send(code,metric,0,quality='bad');alert.refresh_from_db();self.assertEqual(alert.status,'open')
            self.send(code,metric,0,age=60);alert.refresh_from_db();self.assertEqual(alert.status,'open')
            self.send(code,metric,0);alert.refresh_from_db();self.assertEqual(alert.status,'resolved')

    def test_uncalibrated_oxygen_is_stored_as_suspect_without_concentration_alarm(self):
        self.send('GAS-O2-01','oxygen.raw',1000,quality='suspect')
        self.assertFalse(Alert.objects.exists())
        self.assertEqual(Telemetry.objects.get().quality, 'suspect')

    def test_threshold_with_wrong_unit_cannot_create_or_clear_alarm(self):
        asset=Asset.objects.get(code='ENV-01')
        threshold=Threshold.objects.get(key='temperature')
        row=Telemetry.objects.create(asset=asset,metric='temperature',metric_key='temperature',unit='adc',
            value=4095,quality='good',recorded_at=timezone.now())
        self.assertEqual(evaluate_threshold(row,threshold,self.user,'unit-test').action,'skipped_unit')
        self.assertFalse(Alert.objects.exists())
        self.send('ENV-01','temperature',32)
        row.value = 0
        row.save(update_fields=['value'])
        self.assertEqual(evaluate_threshold(row,threshold,self.user,'unit-test').action,'skipped_unit')
        self.assertEqual(Alert.objects.get(rule_key='temperature').status,'open')
