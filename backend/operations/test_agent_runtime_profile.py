from django.conf import settings
from django.test import TestCase, override_settings
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from unittest.mock import patch
from .agent_context import data_context, runtime_profile


class AgentRuntimeProfileTests(TestCase):
    @override_settings(AGENT_EVALUATION_MODE=True, AGENT_DEMO_MODE=True, IS_PRODUCTION=False)
    def test_dedicated_software_profile_is_discoverable_without_secrets(self):
        for folder, profile in (('.agent-capabilities', 'agent-capabilities'), ('.agent-demo', 'agent-demo')):
            with self.subTest(profile=profile), override_settings(AGENT_EVAL_ROOT=settings.BASE_DIR.parent / folder):
                response = self.client.get('/api/ready/')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['profile'], profile)
                self.assertNotIn('DEEPSEEK_API_KEY', response.content.decode())

    @override_settings(AGENT_EVALUATION_MODE=True, AGENT_DEMO_MODE=False, IS_PRODUCTION=False, DEEPSEEK_API_KEY='')
    def test_unconfigured_model_is_explicitly_disabled_in_simulated_context(self):
        self.assertTrue(data_context()['modelCallsDisabled'])
        self.assertEqual(runtime_profile(), 'agent-evaluation')

    @override_settings(HARDWARE_LIVE_MODE=True, AGENT_EVALUATION_MODE=False, DEEPSEEK_API_KEY='not-a-real-key')
    def test_hardware_remains_disabled_even_with_a_key(self):
        self.assertEqual(runtime_profile(), 'hardware-live')
        self.assertTrue(data_context()['modelCallsDisabled'])

    @override_settings(AGENT_EVALUATION_MODE=True, AGENT_DEMO_MODE=False, IS_PRODUCTION=False, DEEPSEEK_API_KEY='EXPLICIT_TEST_STUB')
    def test_explicit_test_or_live_model_transport_is_reported_as_configured(self):
        self.assertFalse(data_context()['modelCallsDisabled'])

    @override_settings(DEEPSEEK_API_KEY='', HARDWARE_LIVE_MODE=False)
    def test_disabled_transport_rejects_direct_requests_before_creating_a_job(self):
        from .models import Profile
        from .sprint_models import AgentRun
        user = User.objects.create_user('profile-operator')
        Profile.objects.create(user=user, role='operator')
        client = APIClient(); client.force_authenticate(user)
        with patch('operations.ai_assistant._completion') as completion:
            response = client.post('/api/assistant/runs/', {'kind':'inspection','station_id':'all'}, format='json')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(AgentRun.objects.count(), 0)
        completion.assert_not_called()
