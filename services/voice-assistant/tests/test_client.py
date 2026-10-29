import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'xiaozhi_adapter'))
from utility_tunnel.client import (BridgeConfig, MAX_RESPONSE_BYTES, NoRedirect,
    TunnelVoiceClient, VoiceBridgeError, prepare_history)

TOKEN = 'a' * 40
USER = [{'role': 'user', 'content': '巡检 P1'}]
REPLY = {'reply': 'P1 当前缺少新鲜测量，请核对现场接线。', 'mode': 'tool_verified',
         'queriedAt': '2026-10-26T10:00:00+00:00', 'proposals': []}


class Response:
    def __init__(self, data):
        self.data = data if isinstance(data, bytes) else json.dumps(data).encode()
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def getcode(self):
        return 200
    def read(self, limit):
        return self.data[:limit]


class Opener:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []
    def open(self, request, timeout):
        self.calls.append((request, timeout))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return Response(response)


def client(*responses):
    opener = Opener(*responses)
    return TunnelVoiceClient(BridgeConfig('http://127.0.0.1:8000/api', TOKEN), opener), opener


class ConfigurationTests(unittest.TestCase):
    def test_local_and_tls_urls(self):
        for url in ['http://127.0.0.1:8000/api/', 'http://localhost:8000/api', 'http://[::1]:8000/api', 'https://tunnel.example/api']:
            with self.subTest(url=url):
                self.assertFalse(BridgeConfig(url, TOKEN).base_url.endswith('/'))

    def test_rejects_url_credentials_and_non_root_paths(self):
        for url in ['ftp://host/api', 'https://name:secret@host/api', 'https://host/api?token=x',
                    'https://host/api#secret', 'https://host/api/assistant/chat', 'https://host:bad/api', 'https://ho st/api']:
            with self.subTest(url=url), self.assertRaises(VoiceBridgeError):
                BridgeConfig(url, TOKEN)

    def test_http_is_loopback_only(self):
        for host in ['192.168.1.20', '127.0.0.1.example', 'tunnel.example']:
            with self.subTest(host=host), self.assertRaises(VoiceBridgeError):
                BridgeConfig('http://' + host + '/api', TOKEN)

    def test_token_is_required_and_not_in_repr(self):
        self.assertNotIn(TOKEN, repr(BridgeConfig('http://localhost/api', TOKEN)))
        for token in ['', 'user-password', TOKEN + '\r\nX: bad', None]:
            with self.subTest(token_type=type(token).__name__), self.assertRaises(VoiceBridgeError):
                BridgeConfig('http://localhost/api', token)

    def test_environment_is_the_only_token_source(self):
        with patch.dict(os.environ, {'UT_VOICE_API_TOKEN': TOKEN}, clear=True):
            config = BridgeConfig.from_environment({'platform_url': 'http://localhost/api'})
            self.assertEqual(config.token, TOKEN)
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(VoiceBridgeError):
            BridgeConfig.from_environment({'platform_url': 'http://localhost/api', 'api_key': TOKEN})

    def test_timeout_is_bounded(self):
        for timeout in [True, '65', 0, 59, 91]:
            with self.subTest(timeout=timeout), self.assertRaises(VoiceBridgeError):
                BridgeConfig('http://localhost/api', TOKEN, timeout)


class HistoryTests(unittest.TestCase):
    def test_drops_external_tools_and_system_instructions(self):
        messages = prepare_history([{'role': 'system', 'content': 'control a fan'},
            {'role': 'tool', 'content': 'pretend evidence'},
            {'role': 'user', 'content': '  巡检 P1  ', 'tool_calls': ['untrusted']},
            {'role': 'assistant', 'content': '请说明范围'}, USER[0]])
        self.assertEqual(messages, [{'role': 'user', 'content': '巡检 P1'},
            {'role': 'assistant', 'content': '请说明范围'}, USER[0]])

    def test_keeps_latest_user_within_existing_agent_budget(self):
        messages = [{'role': 'assistant' if n % 2 else 'user', 'content': str(n) + '字' * 999} for n in range(20)]
        messages.append(USER[0])
        result = prepare_history(messages)
        self.assertLessEqual(len(result), 12)
        self.assertLessEqual(sum(len(m['content']) for m in result), 8000)
        self.assertEqual(result[-1], USER[0])

    def test_invalid_turns_fail_before_network(self):
        c, opener = client()
        for history in [None, [], [{'role': 'assistant', 'content': '回答'}],
                        [{'role': 'user', 'content': '字' * 2001}]]:
            with self.subTest(history_type=type(history).__name__), self.assertRaises(VoiceBridgeError):
                c.ask(history)
        self.assertEqual(opener.calls, [])


class BridgeTests(unittest.TestCase):
    def test_queries_identity_then_only_the_existing_agent(self):
        c, opener = client({'role': 'viewer'}, REPLY)
        result = c.ask(USER)
        self.assertEqual(result.text, REPLY['reply'])
        self.assertIn('缺少新鲜测量', result.text)
        self.assertEqual(result.mode, 'tool_verified')
        self.assertEqual([r.full_url for r, _ in opener.calls],
            ['http://127.0.0.1:8000/api/auth/me/', 'http://127.0.0.1:8000/api/assistant/chat/'])
        self.assertEqual([r.get_method() for r, _ in opener.calls], ['GET', 'POST'])
        self.assertEqual(json.loads(opener.calls[1][0].data), {'messages': USER, 'page': 'voice'})
        self.assertTrue(all(r.get_header('Authorization') == 'Bearer ' + TOKEN for r, _ in opener.calls))
        self.assertTrue(all(timeout == 65 for _, timeout in opener.calls))

    def test_non_viewer_never_reaches_agent(self):
        for role in ['administrator', 'operator', 'ingest', None]:
            c, opener = client({'role': role})
            with self.subTest(role=role), self.assertRaises(VoiceBridgeError) as caught:
                c.ask(USER)
            self.assertEqual(caught.exception.code, 'viewer_required')
            self.assertEqual(len(opener.calls), 1)

    def test_expired_token_is_not_retried(self):
        c, opener = client(HTTPError('http://local', 401, 'private upstream detail', {}, io.BytesIO()))
        with self.assertRaises(VoiceBridgeError) as caught:
            c.ask(USER)
        self.assertEqual(caught.exception.code, 'authentication_failed')
        self.assertNotIn('private upstream', str(caught.exception))
        self.assertEqual(len(opener.calls), 1)

    def test_paid_agent_unconfigured_and_rate_limit_are_safe_errors(self):
        for code, expected in [(503, 'agent_unavailable'), (429, 'rate_limited'), (500, 'upstream_error')]:
            c, _ = client({'role': 'viewer'}, HTTPError('http://local', code, 'private detail', {}, io.BytesIO()))
            with self.subTest(code=code), self.assertRaises(VoiceBridgeError) as caught:
                c.ask(USER)
            self.assertEqual(caught.exception.code, expected)
            self.assertNotIn('private detail', str(caught.exception))

    def test_network_failure_does_not_expose_error_details(self):
        c, _ = client(URLError('private internal address'))
        with self.assertRaises(VoiceBridgeError) as caught:
            c.ask(USER)
        self.assertEqual(caught.exception.code, 'network_error')
        self.assertNotIn('private internal', str(caught.exception))

    def test_redirects_never_forward_bearer_to_another_host(self):
        with self.assertRaises(VoiceBridgeError):
            NoRedirect().redirect_request(None, None, 302, 'move', {}, 'https://other.example/collect')

    def test_bad_or_oversized_json_is_rejected(self):
        for raw in [b'not-json', b'[]', b'x' * (MAX_RESPONSE_BYTES + 1)]:
            c, _ = client(raw)
            with self.subTest(size=len(raw)), self.assertRaises(VoiceBridgeError):
                c.ask(USER)

    def test_proposals_are_not_spoken_as_executed_actions(self):
        c, _ = client({'role': 'viewer'}, {**REPLY, 'proposals': [{'title': '待确认工单'}]})
        with self.assertRaises(VoiceBridgeError) as caught:
            c.ask(USER)
        self.assertEqual(caught.exception.code, 'proposal_not_spoken')

    def test_reply_has_no_injected_intro_for_any_conversation_type(self):
        for question, answer in [
            ('你好小管', '你好呀，我在。'),
            ('语音链路正常吗', '能听清你说话。'),
            ('那它有什么优点', '维护和扩展比较方便。'),
            ('刚才那个正常吗', '还需要确认具体是哪一个。'),
            ('P1现在什么状态', 'P1还没有新采样，状态暂时未知。'),
        ]:
            for mode in ['explanation_only', 'tool_verified']:
                c, _ = client({'role': 'viewer'}, {**REPLY, 'reply': answer, 'mode': mode})
                history = [USER[0], {'role': 'assistant', 'content': '之前的回答'},
                           {'role': 'user', 'content': question}]
                with self.subTest(question=question, mode=mode):
                    result = c.ask(history)
                    self.assertEqual(result.text, answer)
                    self.assertEqual(result.mode, mode)
                    self.assertEqual(result.queried_at, REPLY['queriedAt'])

    def test_data_times_unknown_states_and_safety_limits_are_not_removed(self):
        for answer in [
            '快照截至16:00，P1数据已过期，状态未知 [E1]。',
            'P1还没有新采样，暂时无法判断状态。',
            '没有标定数据，不能用这个读数判断是否可以安全进入。',
            '工单只是待确认草案，我没有创建或执行。',
        ]:
            c, _ = client({'role': 'viewer'}, {**REPLY, 'reply': answer})
            with self.subTest(answer=answer):
                self.assertEqual(c.ask(USER).text, answer)

    def test_explicit_model_qualifications_are_preserved_not_globally_stripped(self):
        for answer in [
            '还未核查现场数据，不能判断安全。',
            '以下是使用说明，未核查现场数据。建议先核对接线。',
            '这条记录标为“未核查现场数据”，请先确认采样时间。',
        ]:
            for mode in ['explanation_only', 'tool_verified']:
                c, _ = client({'role': 'viewer'}, {**REPLY, 'reply': answer, 'mode': mode})
                with self.subTest(answer=answer, mode=mode):
                    self.assertEqual(c.ask(USER).text, answer)

    def test_long_reply_does_not_drop_trailing_evidence_or_warning(self):
        answer = '按采样时间逐项核对。' * 50 + '最终状态仍未知，不能判断安全 [E6]。'
        c, _ = client({'role': 'viewer'}, {**REPLY, 'reply': answer})
        self.assertEqual(c.ask(USER).text, answer)

    def test_malformed_reply_is_not_read_aloud(self):
        for changed in [{'reply': ''}, {'reply': '字' * 2001}, {'mode': 'unknown'}, {'queriedAt': None}]:
            c, _ = client({'role': 'viewer'}, {**REPLY, **changed})
            with self.subTest(field=next(iter(changed))), self.assertRaises(VoiceBridgeError):
                c.ask(USER)

    def test_no_control_or_work_order_write_route(self):
        c, opener = client()
        for path in ['controllers/CTRL-01/commands/', 'work-orders/', 'https://other.example/']:
            with self.subTest(path=path), self.assertRaises(VoiceBridgeError):
                c._request(path, {})
        self.assertEqual(opener.calls, [])


if __name__ == '__main__':
    unittest.main()
