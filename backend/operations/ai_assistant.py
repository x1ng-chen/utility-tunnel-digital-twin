"""Server-side DeepSeek gateway for the authenticated page assistant."""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings


DEEPSEEK_CHAT_URL = 'https://api.deepseek.com/chat/completions'
SYSTEM_PROMPT = (
    '你是综合管廊数字孪生运维平台的页面助手。用简洁、清楚的中文回答。'
    '你可以解释设备台账、告警、工单、GIS、三维孪生和遥测页面的常见用法。'
    '你没有直接读取实时设备、数据库或操作控制器的权限；不要声称已经查看现场状态、'
    '完成操作或验证安全状态。若问题需要实时数据，请引导用户到相应页面核对。'
    '不要把演示坐标或未标定的传感器原始量说成精确测绘或可信浓度。'
)


class AssistantServiceError(Exception):
    def __init__(self, code, message, status_code):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def ask_deepseek(messages, page=''):
    api_key = settings.DEEPSEEK_API_KEY
    if not api_key:
        raise AssistantServiceError('assistant_not_configured', 'AI 助手尚未配置，请联系管理员。', 503)

    system_content = SYSTEM_PROMPT + (f'用户当前页面：{page}。' if page else '')
    payload = json.dumps({
        'model': settings.DEEPSEEK_MODEL,
        'messages': [{'role': 'system', 'content': system_content}, *messages],
        'thinking': {'type': 'disabled'},
        'max_tokens': 700,
        'stream': False,
    }, ensure_ascii=False).encode('utf-8')
    request = Request(
        DEEPSEEK_CHAT_URL,
        data=payload,
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urlopen(request, timeout=30) as response:
            result = json.loads(response.read(256 * 1024))
    except HTTPError as exc:
        if exc.code == 429:
            raise AssistantServiceError('assistant_busy', 'AI 服务请求过多，请稍后重试。', 429) from exc
        raise AssistantServiceError('assistant_upstream_error', 'AI 服务暂不可用，请稍后重试。', 502) from exc
    except (URLError, TimeoutError) as exc:
        raise AssistantServiceError('assistant_unreachable', '连接 AI 服务超时，请稍后重试。', 504) from exc
    except (ValueError, UnicodeError) as exc:
        raise AssistantServiceError('assistant_invalid_response', 'AI 服务返回了无效响应。', 502) from exc

    choices = result.get('choices') if isinstance(result, dict) else None
    message = choices[0].get('message') if isinstance(choices, list) and choices and isinstance(choices[0], dict) else None
    reply = message.get('content') if isinstance(message, dict) else None
    if not isinstance(reply, str) or not reply.strip():
        raise AssistantServiceError('assistant_empty_response', 'AI 服务未返回可显示的回答。', 502)
    return reply.strip()
