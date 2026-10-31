"""The new sandbox can sample; business and older evaluation DBs cannot."""
from unittest.mock import patch
from django.conf import settings
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings
from .sprint_demo import guard


class CapabilityDemoGuardTests(SimpleTestCase):
    @override_settings(AGENT_DEMO_MODE=True)
    def test_only_both_dedicated_demo_roots_pass_after_database_validation(self):
        for name in ('.agent-demo', '.agent-capabilities'):
            root = (settings.BASE_DIR.parent / name).resolve()
            with self.subTest(name=name), patch('operations.sprint_demo.require_evaluation_database', return_value=root):
                self.assertEqual(guard(), root)
        for name in ('.hardware-live', '.agent-eval', 'business', '.agent-capabilities-other'):
            with self.subTest(name=name), patch('operations.sprint_demo.require_evaluation_database',
                    return_value=settings.BASE_DIR.parent / name):
                with self.assertRaises(CommandError):
                    guard()

    @override_settings(AGENT_DEMO_MODE=False)
    def test_demo_flag_is_required_even_with_valid_root(self):
        with patch('operations.sprint_demo.require_evaluation_database',
                return_value=settings.BASE_DIR.parent / '.agent-capabilities'):
            with self.assertRaises(CommandError):
                guard()

    def test_underlying_database_mismatch_is_not_bypassed(self):
        with patch('operations.sprint_demo.require_evaluation_database', side_effect=CommandError('database mismatch')):
            with self.assertRaisesMessage(CommandError, 'database mismatch'):
                guard()
