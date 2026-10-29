"""Presentation-aware experience approval; model and diagnostic results are stubs."""
from copy import deepcopy
from django.test import TestCase, override_settings
from . import test_reviewed_experience as fixtures
from .agent_experience import hash_content, matching, transition
from .models import Asset, TwinModelRelease
from .twin_presentation import V20, V24


@override_settings(DEEPSEEK_API_KEY='EXPLICIT_OFFLINE_STUB', AGENT_EVALUATION_MODE=True,
    AGENT_EXPERIENCE_ENABLED=True, AGENT_EXPERIENCE_TEST_APPROVAL=True, ANYJEV_ENABLED=False,
    ALLOWED_HOSTS=['testserver', '127.0.0.1'], CONTROLLER_COMMAND_PROTOCOL='four-controller-v2')
class ExperiencePresentationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.ExperienceTests.setUpTestData.__func__(cls)

    client_for = fixtures.ExperienceTests.client_for
    candidate = fixtures.ExperienceTests.candidate
    approve = fixtures.ExperienceTests.approve

    def activate_v24_fixture(self):
        # Unit-test metadata only; actual GLB verification is a separate suite.
        assets = {asset.code: asset for asset in Asset.objects.filter(asset_type='sensor')}
        Asset.objects.filter(pk__in=[asset.pk for asset in assets.values()]).update(mesh='')
        for code, asset in assets.items():
            asset.mesh = V24['sensorMeshes'][code]
            asset.zone = V24['sensorStations'][code]
            asset.save(update_fields=['mesh', 'zone'])
        return TwinModelRelease.objects.create(version='EXPLICIT_V24_METADATA_FIXTURE',
            model_file='NOT_A_REAL_MODEL.glb', original_name='fixture.glb', sha256=V24['modelSha256'],
            size_bytes=1, node_count=len(assets), node_inventory_available=True,
            node_names=list(Asset.objects.values_list('mesh', flat=True)),
            status='active', uploaded_by=self.admin, is_compatible=True)

    def post_approval(self, item):
        return self.client_for(self.admin).post(f'/api/assistant/experiences/{item.pk}/',
            {'action': 'approve', 'revision': item.revision}, format='json')

    def test_v24_candidate_can_be_approved_shared_and_retired(self):
        self.activate_v24_fixture()
        item, run = self.candidate()
        self.assertTrue(item.layout_version.endswith(':' + V24['revision']))
        self.assertEqual(run.snapshot['presentationVersion'], V24['revision'] + ':' + V24['modelSha256'])
        response = self.post_approval(item)
        self.assertEqual(response.status_code, 200, response.data)
        item.refresh_from_db()
        loaded = matching(run.snapshot, run.input, self.other)['items']
        self.assertEqual([entry['id'] for entry in loaded], [str(item.pk)])
        self.assertEqual(loaded[0]['originSnapshotHash'], run.snapshot['sha256'])
        self.assertEqual(self.client_for(self.other).get(f'/api/assistant/runs/{run.pk}/').status_code, 404)
        transition(self.admin, item.pk, {'action': 'retire', 'revision': item.revision})
        self.assertEqual(matching(run.snapshot, run.input, self.other)['items'], [])

    def test_switch_to_another_recognised_presentation_refuses_old_candidate(self):
        release = self.activate_v24_fixture()
        item, _ = self.candidate()
        release.sha256 = V20['modelSha256']
        release.save(update_fields=['sha256'])
        self.assertEqual(self.post_approval(item).status_code, 409)
        item.refresh_from_db()
        self.assertEqual(item.status, 'candidate')

    def test_unknown_active_model_cannot_reuse_legacy_unversioned_scope(self):
        item, run = self.candidate()
        release = self.activate_v24_fixture()
        release.sha256 = 'f' * 64
        release.save(update_fields=['sha256'])
        self.assertEqual(self.post_approval(item).status_code, 409)
        legacy = deepcopy(run.snapshot)
        legacy['presentationVersion'] = ':' + release.sha256
        item.status = 'approved'
        item.save(update_fields=['status'])  # Deliberate old-record fixture, never API approval.
        self.assertEqual(matching(legacy, run.input, self.other)['items'], [])

    def test_legacy_no_model_context_remains_reviewable(self):
        item, run = self.candidate()
        self.assertEqual(run.snapshot.get('presentationVersion'), '')
        self.assertEqual(self.post_approval(item).status_code, 200)

    def test_source_run_model_hash_must_match_current_exact_identity(self):
        self.activate_v24_fixture()
        item, run = self.candidate()
        run.snapshot['presentationVersion'] = V24['revision'] + ':' + '0' * 64
        run.save(update_fields=['snapshot'])
        self.assertEqual(self.post_approval(item).status_code, 409)

    def test_reference_snapshot_hash_is_still_verified(self):
        self.activate_v24_fixture()
        item, _ = self.candidate()
        item.source_refs[0]['snapshotHash'] = '0' * 64
        item.save(update_fields=['source_refs'])
        self.assertEqual(self.post_approval(item).status_code, 409)

    def test_source_scope_cannot_be_reclassified_into_current_environment(self):
        self.activate_v24_fixture()
        item, run = self.candidate()
        item.source_scope = 'database_observation'
        run.snapshot['source']['mode'] = 'database_observation'
        run.save(update_fields=['snapshot'])
        fields = {key: getattr(item, key) for key in ('station_id', 'asset_code', 'asset_kind',
            'metric_key', 'category', 'lesson', 'source_scope', 'layout_version', 'knowledge_version', 'rule_version')}
        item.content_hash = hash_content(fields)
        item.save(update_fields=['source_scope', 'content_hash'])
        self.assertEqual(self.post_approval(item).status_code, 409)
