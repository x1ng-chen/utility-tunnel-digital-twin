"""Offline adapter contract tests. No model packages, downloads, or paid calls."""
import copy
import io
import json
import socket
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from django.test import SimpleTestCase, override_settings

from . import decision_router as router


TOKEN = 'UNIT_TEST_ONLY_NOT_A_REAL_TOKEN_123456789'
OPTIONS = [{'id': 'snapshot', 'label': '读取本站快照'}, {'id': 'uncertain', 'label': '证据不足，交由原流程'}]
STATE = {'station': 'P5', 'source': 'SIMULATED_TEST', 'missing': ['rpm']}


class Reply:
    status = 200

    def __init__(self, body):
        self.body = body if isinstance(body, bytes) else json.dumps(body).encode('utf-8')

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, n):
        return self.body[:n]


def answer(request, **updates):
    payload = json.loads(request.data)
    return {
        'requestId': payload['requestId'], 'inputHash': router._hash(payload['state']),
        'optionsHash': router._hash(payload['options']), 'model': router.MODEL,
        'modelRevision': router.MODEL_REVISION, 'anyjevCommit': router.ANYJEV_COMMIT,
        'authority': 'READ_ONLY_ROUTING', 'executionSource': 'LOCAL_MODEL',
        'status': 'selected', 'selectedOption': 'snapshot',
        'probabilities': {'snapshot': 0.9, 'uncertain': 0.1},
        'usage': {'prompt_tokens': 83, 'completion_tokens': 0, 'total_tokens': 83},
        **updates,
    }


@override_settings(ANYJEV_ENABLED=True, ANYJEV_URL='http://127.0.0.1:8100', ANYJEV_TOKEN=TOKEN)
class LocalDecisionAdapterTests(SimpleTestCase):
    def route(self, *, updates=None, body=None):
        opener = Mock()
        opener.open.side_effect = lambda request, timeout: Reply(body if body is not None else answer(request, **(updates or {})))
        with patch.object(router, 'build_opener', return_value=opener):
            result = router.route_decision(STATE, OPTIONS)
        return result, opener

    @override_settings(ANYJEV_ENABLED=False)
    def test_disabled_has_no_http_or_inference(self):
        with patch.object(router, 'build_opener') as http:
            result = router.route_decision(STATE, OPTIONS)
        self.assertEqual(result['fallbackReason'], 'not_enabled')
        self.assertFalse(result['attempted'])
        http.assert_not_called()

    def test_valid_distribution_selects_only_whitelisted_id(self):
        result, opener = self.route()
        self.assertEqual(result['selectedOption'], 'snapshot')
        self.assertEqual(result['status'], 'selected')
        self.assertTrue(result['attempted'])
        self.assertFalse(result['probabilitiesCalibratedForProject'])
        self.assertIsNone(result['cost'])
        self.assertEqual(result['usage']['total_tokens'], 83)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_header('Authorization'), 'Bearer ' + TOKEN)
        self.assertLessEqual(opener.open.call_args.kwargs['timeout'], 5)

    def test_invalid_options_or_nan_state_never_reach_service(self):
        bad = [[], OPTIONS * 5, [{'id': 'x', 'label': 'x'}, {'id': 'x', 'label': 'x'}],
               [{'id': 'x', 'label': 'x'}, {'id': 'y', 'label': 'y'}],
               [{**OPTIONS[0], 'tool': 'publish_command'}, OPTIONS[1]]]
        with patch.object(router, 'build_opener') as http:
            for options in bad:
                self.assertFalse(router.route_decision(STATE, options)['attempted'])
            self.assertFalse(router.route_decision({'power': float('nan')}, OPTIONS)['attempted'])
        http.assert_not_called()

    def test_input_size_and_deadline_rejected_before_network(self):
        with patch.object(router, 'build_opener') as http:
            self.assertFalse(router.route_decision({'x': 'x' * 70000}, OPTIONS)['attempted'])
            for timeout in (0, -1, True, float('inf')):
                self.assertFalse(router.route_decision(STATE, OPTIONS, timeout=timeout)['attempted'])
        http.assert_not_called()

    def test_service_configuration_cannot_target_remote_or_redirect_path(self):
        for url in ('https://127.0.0.1:8100', 'http://example.com:8100', 'http://127.0.0.1:8100/a',
                    'http://a:b@127.0.0.1:8100', 'http://127.0.0.1:8100/?x=1', 'file:///tmp/model'):
            with self.subTest(url=url), override_settings(ANYJEV_URL=url), patch.object(router, 'build_opener') as http:
                self.assertFalse(router.route_decision(STATE, OPTIONS)['attempted'])
                http.assert_not_called()
        self.assertIsNone(router._NoRedirect().redirect_request(None, None, 302, '', {}, 'http://example.com'))

    def test_uncertain_and_low_margin_preserve_actual_distribution(self):
        for probability, reason in (({'snapshot': 0.1, 'uncertain': 0.9}, 'uncertain'),
                                    ({'snapshot': 0.55, 'uncertain': 0.45}, 'low_margin')):
            result, _ = self.route(updates={'status': 'fallback', 'selectedOption': None,
                                            'probabilities': probability, 'fallbackReason': reason})
            self.assertEqual(result['status'], 'fallback')
            self.assertEqual(result['fallbackReason'], reason)
            self.assertEqual(result['probabilities'], probability)
            self.assertEqual(result['usage']['total_tokens'], 83)

    def test_fake_confidence_cannot_override_recomputed_gap(self):
        result, _ = self.route(updates={'probabilities': {'snapshot': 0.51, 'uncertain': 0.49},
                                        'confidence': 1, 'logProbabilityGap': 100})
        self.assertEqual(result['fallbackReason'], 'low_margin')

    def test_wrong_request_model_hash_or_stub_source_is_rejected(self):
        for update in ({'modelRevision': 'wrong'}, {'requestId': 'other'}, {'inputHash': 'wrong'},
                       {'optionsHash': 'wrong'}, {'anyjevCommit': 'wrong'}, {'executionSource': 'TEST_STUB'},
                       {'authority': 'CONTROL_ALLOWED'}):
            result, _ = self.route(updates=update)
            self.assertEqual(result['fallbackReason'], 'invalid_response')
            self.assertTrue(result['attempted'])

    def test_invented_selection_malformed_and_nonfinite_distributions_rejected(self):
        updates = [{'selectedOption': 'publish_mqtt'}, {'selectedOption': 'uncertain'},
                   {'probabilities': {'snapshot': 0.9}},
                   {'probabilities': {'snapshot': 0.9, 'uncertain': 0.9}},
                   {'probabilities': {'snapshot': True, 'uncertain': 0.0}},
                   {'probabilities': {'snapshot': float('nan'), 'uncertain': 0.1}},
                   {'probabilities': {'snapshot': 1.1, 'uncertain': -0.1}}]
        for update in updates:
            with self.subTest(update=update):
                self.assertEqual(self.route(updates=update)[0]['fallbackReason'], 'invalid_response')

    def test_missing_usage_is_unknown_not_fabricated(self):
        result, _ = self.route(updates={'usage': None})
        self.assertIsNone(result['usage'])
        result, _ = self.route(updates={'usage': {'prompt_tokens': 1, 'completion_tokens': 20, 'total_tokens': 21}})
        self.assertIsNone(result['usage'])

    def test_response_size_and_json_shape_rejected(self):
        for body in (b'[]', b'not-json', b'x' * 40000):
            self.assertEqual(self.route(body=body)[0]['fallbackReason'], 'invalid_response')

    def test_http_timeout_and_connection_failure_are_observable_counted_attempts(self):
        errors = [(socket.timeout(), 'timeout'), (URLError('unreachable'), 'service_unavailable'),
                  (HTTPError('http://127.0.0.1', 429, 'busy', {}, io.BytesIO()), 'busy'),
                  (HTTPError('http://127.0.0.1', 401, 'no', {}, io.BytesIO()), 'http_error')]
        for exc, reason in errors:
            opener = Mock(); opener.open.side_effect = exc
            with self.subTest(reason=reason), patch.object(router, 'build_opener', return_value=opener):
                result = router.route_decision(STATE, OPTIONS)
                self.assertTrue(result['attempted'])
                self.assertEqual(result['fallbackReason'], reason)

    def test_raw_service_text_and_secrets_are_not_echoed(self):
        result, _ = self.route(body=b'{"error":"SECRET_TOKEN_AND_PRIVATE_PROMPT"}')
        serialized = json.dumps(result)
        self.assertNotIn(TOKEN, serialized)
        self.assertNotIn('SECRET_TOKEN_AND_PRIVATE_PROMPT', serialized)
