"""Read-only ASR-text bridge. Audio and device credentials stay outside Django."""
from dataclasses import dataclass, field
import ipaddress
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from datetime import datetime, timezone
from .speech_input import normalize_business_text
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

MAX_RESPONSE_BYTES = 512 * 1024


class VoiceBridgeError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise VoiceBridgeError('redirect_rejected', '管廊接口发生重定向，请核对服务地址。')


@dataclass(frozen=True)
class BridgeConfig:
    base_url: str
    token: str = field(repr=False)
    timeout: int = 65

    def __post_init__(self):
        try:
            parsed = urlsplit(self.base_url)
            port = parsed.port
        except (ValueError, TypeError):
            raise VoiceBridgeError('invalid_url', '管廊 API 地址无效。') from None
        if (parsed.scheme not in {'http', 'https'} or not parsed.hostname
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path.rstrip('/') != '/api' or any(c.isspace() for c in self.base_url)):
            raise VoiceBridgeError('invalid_url', '请配置不含凭据的管廊 API 根地址，以 /api 结尾。')
        local = parsed.hostname.lower() == 'localhost'
        try:
            local = local or ipaddress.ip_address(parsed.hostname).is_loopback
        except ValueError:
            pass
        if parsed.scheme == 'http' and not local:
            raise VoiceBridgeError('https_required', '非本机的管廊 API 必须使用 HTTPS。')
        if not isinstance(self.token, str) or not re.fullmatch(r'[a-fA-F0-9]{40}', self.token):
            raise VoiceBridgeError('token_missing', '请在语音服务器环境中配置查看者的临时访问令牌。')
        if isinstance(self.timeout, bool) or not isinstance(self.timeout, int) or not 60 <= self.timeout <= 90:
            raise VoiceBridgeError('invalid_timeout', '管廊查询超时必须为 60 至 90 秒。')
        object.__setattr__(self, 'base_url', self.base_url.rstrip('/'))

    @classmethod
    def from_environment(cls, config):
        return cls(
            base_url=os.environ.get('UT_VOICE_API_URL', config.get('platform_url', 'http://127.0.0.1:8000/api')),
            token=os.environ.get('UT_VOICE_API_TOKEN', ''),
            timeout=config.get('request_timeout_seconds', 65),
        )


def prepare_history(dialogue):
    if not isinstance(dialogue, list) or len(dialogue) > 100:
        raise VoiceBridgeError('invalid_dialogue', '本轮对话无效，请重新说出问题。')
    messages = []
    for item in dialogue:
        if not isinstance(item, dict) or item.get('role') not in {'user', 'assistant'}:
            continue
        content = item.get('content')
        if not isinstance(content, str) or not content.strip():
            continue
        content = content.strip()
        if len(content) > 2000:
            raise VoiceBridgeError('question_too_long', '问题过长，请缩短后重新说。')
        messages.append({'role': item['role'], 'content': content})
    if not messages or messages[-1]['role'] != 'user':
        raise VoiceBridgeError('user_turn_required', '请先说出完整的问题。')
    messages = messages[-12:]
    while sum(len(m['content']) for m in messages) > 8000:
        messages.pop(0)
    return messages


@dataclass(frozen=True)
class VoiceReply:
    text: str
    mode: str
    queried_at: str


class TunnelVoiceClient:
    def __init__(self, config, opener=None):
        self.config = config
        # Do not forward bearer credentials through ambient proxies or redirects.
        self.opener = opener if opener is not None else build_opener(ProxyHandler({}), NoRedirect())

    def _request(self, route, payload=None):
        inspection = re.fullmatch(r'assistant/inspection/\?station=(?:P[1-5]|all)', route)
        if route not in {'auth/me/', 'assistant/chat/'} and not (inspection and payload is None):
            raise VoiceBridgeError('route_rejected', '语音适配器未开放此操作。')
        body = None if payload is None else json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8')
        request = Request(self.config.base_url + '/' + route, data=body,
            headers={'Authorization': 'Bearer ' + self.config.token,
                     'Accept': 'application/json', 'Content-Type': 'application/json'},
            method='GET' if payload is None else 'POST')
        try:
            with self.opener.open(request, timeout=self.config.timeout) as response:
                if response.getcode() != 200:
                    raise VoiceBridgeError('upstream_status', '管廊查询暂不可用，请稍后重试。')
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise VoiceBridgeError('response_too_large', '管廊返回数据过大，请缩小查询范围。')
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError('not an object')
            return data
        except HTTPError as exc:
            if exc.code in {401, 403}:
                raise VoiceBridgeError('authentication_failed', '语音查询凭据已失效或无权限，请在服务器更新。') from None
            if exc.code == 429:
                raise VoiceBridgeError('rate_limited', '语音查询次数已达限制，请稍后重试。') from None
            if exc.code == 503:
                raise VoiceBridgeError('agent_unavailable', '管廊智能体尚未就绪，请检查服务端模型配置。') from None
            raise VoiceBridgeError('upstream_error', '管廊查询失败，请稍后重试。') from None
        except (URLError, TimeoutError, OSError):
            raise VoiceBridgeError('network_error', '暂时连接不上管廊服务，请稍后重试。') from None
        except (ValueError, UnicodeError, TypeError):
            raise VoiceBridgeError('invalid_response', '管廊返回内容无效，请稍后重试。') from None

    def inspect(self, station, *, alarm_only=False):
        station_id = 'all' if station == '五站' else station
        data = self._request(f'assistant/inspection/?station={station_id}')
        try:
            source = data['runtime']['dataContext']
            snapshot = data['evidence'][0]['data']
            queried_at = snapshot['queried_at']
            if snapshot['station_id'] != station_id:
                raise ValueError('station mismatch')
            when = datetime.fromisoformat(queried_at).astimezone(timezone.utc).strftime('%H点%M分%S秒')
            observed = [datetime.fromisoformat(row['sampled_at'])
                        for item in snapshot.get('items', [])
                        for row in (item.get('snapshot') or {}).get('readings', [])
                        if row.get('usable') or row.get('scenario_usable')]
            latest = max(observed).astimezone(timezone.utc).strftime('%H点%M分%S秒') if observed else None
            expected = snapshot['expected_sensor_count']
            usable = snapshot['usable_observation_sensor_count']
            if not (type(expected) is int and type(usable) is int and 0 <= usable <= expected):
                raise ValueError('invalid counts')
            issues = [code for fact in snapshot['station_facts'].values()
                      for code in fact['data_issue_asset_codes']]
            alerts = [code for fact in snapshot['station_facts'].values()
                      for code in fact['alert_asset_codes']]
        except (AttributeError, IndexError, KeyError, TypeError, ValueError):
            raise VoiceBridgeError('invalid_reply', '巡检结果格式无效，请到网页查看。') from None
        label = '模拟巡检' if source.get('mode') == 'simulated_test' else (
            '实物平台巡检' if source.get('hardwareLive') is True else '数据库巡检')
        alert_text = ('平台记录的活动告警涉及' + '、'.join(alerts[:5]) if alerts
                      else '平台当前未列出活动告警')
        if alarm_only:
            text = f'{station}，{label}于世界时{when}查询，{alert_text}。'
        else:
            text = f'{station}，{label}于世界时{when}查询。{expected}路中有{usable}路观测新鲜且质量良好。'
            if latest:
                text += f'最新可用采样为世界时{latest}。'
            if issues:
                text += '待核查点位包括' + '、'.join(issues[:5]) + '。'
            text += alert_text + '。'
        if usable < expected:
            text += '有点位观测缺失或不可用。'
        return VoiceReply(text, 'tool_verified', queried_at)

    def ask(self, dialogue):
        messages = prepare_history(dialogue)
        identity = self._request('auth/me/')
        if identity.get('role') != 'viewer':
            raise VoiceBridgeError('viewer_required', '语音查询需要独立的查看者账号，请勿配置管理员或运维员凭据。')
        command = normalize_business_text(messages[-1]['content'])
        match = re.fullmatch(r'(?:你好[，, ]*小管[，, ]*|小管[，, ]*)?(?:请)?'
                             r'(?:(?:巡检|零检)\s*(P[1-5]|五站)(?:站|检测点)?|(P[1-5])\s*(?:站)?(?:的)?(?:当前)?告警(?:状态)?)'
                             r'[。！？?!\s]*', command)
        if match:
            return self.inspect(match[1] or match[2], alarm_only=bool(match[2]))
        data = self._request('assistant/chat/', {'messages': messages, 'page': 'voice'})
        reply, mode, queried_at = data.get('reply'), data.get('mode'), data.get('queriedAt')
        if (not isinstance(reply, str) or not reply.strip() or len(reply) > 2000
                or mode not in {'tool_verified', 'explanation_only'} or not isinstance(queried_at, str) or not queried_at):
            raise VoiceBridgeError('invalid_reply', '管廊回答格式无效，请稍后重试。')
        if data.get('proposals'):
            raise VoiceBridgeError('proposal_not_spoken', '需要处置工单时，请到管廊网页审阅并确认。')
        # The backend owns the answer and any specific data limitations.
        # Keep verification metadata separate; do not inject spoken boilerplate.
        return VoiceReply(reply.strip(), mode, queried_at)
