"""Pure stub service tests. Run with unittest; no torch/model import required."""
import copy
import importlib.util
import json
from pathlib import Path
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen


spec = importlib.util.spec_from_file_location('router_service', Path(__file__).with_name('router_service.py'))
router = importlib.util.module_from_spec(spec)
spec.loader.exec_module(router)
TOKEN = 'TEST_STUB_TOKEN_NOT_REAL_1234567890123456789'
OPTIONS = [{'id': 'snapshot', 'label': '读取快照', 'description': ''},
           {'id': 'uncertain', 'label': '无法判定', 'description': ''}]
REQUEST = {'requestId': 'test-request', 'state': {'station': 'P5', 'source': 'SIMULATED_TEST'}, 'options': OPTIONS}


class StubEngine:
    source = 'TEST_STUB'
    ready = True
    metadata = {'testOnly': True}

    def decide(self, request):
        return router.distribution_reply(request, {'snapshot': 0.9, 'uncertain': 0.1})


class ContractTests(unittest.TestCase):
    def test_closed_options_and_fields(self):
        self.assertEqual(router.validate_request(REQUEST), REQUEST)
        for key, value in [('model', 'untrusted'), ('tool', 'publish'), ('path', 'c:/secret')]:
            with self.subTest(key=key), self.assertRaises(router.Rejected):
                router.validate_request({**REQUEST, key: value})
        for options in (OPTIONS * 5, OPTIONS[:1], [{**OPTIONS[0], 'id': 'uncertain'}, OPTIONS[1]],
                        [{**OPTIONS[0], 'parameters': {'command': 'x'}}, OPTIONS[1]]):
            with self.assertRaises(router.Rejected):
                router.validate_request({**REQUEST, 'options': options})

    def test_nan_and_oversized_state_are_rejected(self):
        for state in ({'number': float('nan')}, {'text': 'x' * 70000}):
            with self.assertRaises(router.Rejected):
                router.validate_request({**REQUEST, 'state': state})

    def test_rules_derive_gap_and_uncertainty_not_safety_probability(self):
        low = router.distribution_reply(REQUEST, {'snapshot': 0.55, 'uncertain': 0.45})
        self.assertEqual(low['fallbackReason'], 'low_margin')
        uncertain = router.distribution_reply(REQUEST, {'snapshot': 0.1, 'uncertain': 0.9})
        self.assertEqual(uncertain['fallbackReason'], 'uncertain')
        self.assertFalse(uncertain['probabilitiesCalibratedForProject'])
        selected = router.distribution_reply(REQUEST, {'snapshot': 1.0, 'uncertain': 0.0})
        self.assertIsNone(selected['logProbabilityGap'])  # JSON finite representation of an infinite gap.

    def test_bind_and_token_are_required(self):
        with self.assertRaises(ValueError): router.LocalServer(('0.0.0.0', 0), TOKEN, StubEngine())
        with self.assertRaises(ValueError): router.LocalServer(('127.0.0.1', 0), '', StubEngine())


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.server = router.LocalServer(('127.0.0.1', 0), TOKEN, StubEngine())
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True)
        self.thread.start()
        self.url = 'http://127.0.0.1:' + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=2)

    def send(self, path='/v1/decide', data=REQUEST, token=TOKEN, method='POST'):
        req = Request(self.url + path, data=json.dumps(data).encode() if method == 'POST' else None,
                      headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token}, method=method)
        with urlopen(req, timeout=2) as response:
            return response.status, json.load(response)

    def test_authenticated_response_bound_to_state_and_explicit_stub(self):
        status, data = self.send()
        self.assertEqual(status, 200)
        self.assertEqual(data['inputHash'], router.digest(REQUEST['state']))
        self.assertEqual(data['optionsHash'], router.digest(OPTIONS))
        self.assertEqual(data['executionSource'], 'TEST_STUB')
        self.assertEqual(data['authority'], 'READ_ONLY_ROUTING')
        _, health = self.send('/health', method='GET')
        self.assertEqual(health['source'], 'TEST_STUB')

    def test_auth_and_unknown_fields(self):
        for kwargs, code in [({'token': 'wrong'}, 401), ({'data': {**REQUEST, 'model': 'other'}}, 400),
                             ({'path': '/run-code'}, 404)]:
            with self.subTest(kwargs=kwargs), self.assertRaises(HTTPError) as exc:
                self.send(**kwargs)
            self.assertEqual(exc.exception.code, code)

    def test_single_inference_busy_and_unavailable_fail_closed(self):
        self.server.inference_lock.acquire()
        try:
            with self.assertRaises(HTTPError) as exc: self.send()
            self.assertEqual(exc.exception.code, 429)
        finally:
            self.server.inference_lock.release()
        self.server.engine.ready = False
        with self.assertRaises(HTTPError) as exc: self.send()
        self.assertEqual(exc.exception.code, 503)


if __name__ == '__main__':
    unittest.main()
