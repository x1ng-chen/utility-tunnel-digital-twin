"""Shared API error handling for the Django REST surface.

Keeping the envelope stable means the Vue client can render validation,
authentication and routing failures without having to know DRF internals.
"""

import re

from rest_framework.views import exception_handler
from django.http import JsonResponse


REQUEST_ID_PATTERN = re.compile(r'^[A-Za-z0-9._:-]{1,80}$')


def _request_id(request) -> str:
    request_id = getattr(request, 'request_id', '') or request.headers.get('X-Request-Id', '')
    return request_id if REQUEST_ID_PATTERN.fullmatch(request_id) else ''


def _json_error(request, message: str, status: int) -> JsonResponse:
    response = JsonResponse({'error': 'not_found' if status == 404 else 'internal_error', 'message': message, 'details': {}}, status=status)
    request_id = _request_id(request)
    if request_id:
        response['X-Request-Id'] = request_id
    return response


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return response

    payload = response.data
    code = getattr(exc, 'default_code', 'api_error')
    message = '请求参数无效。'
    details = payload
    if isinstance(payload, dict) and 'detail' in payload:
        detail = payload.get('detail')
        message = str(detail)
        details = {key: value for key, value in payload.items() if key != 'detail'}
    elif isinstance(payload, list):
        details = {'errors': payload}

    response.data = {
        'error': str(code),
        'message': message,
        'details': details or {},
    }
    request = context.get('request')
    if request is not None:
        request_id = _request_id(request)
        if request_id:
            response['X-Request-Id'] = request_id
    return response


def api_handler404(request, exception):
    if request.path.startswith('/api/'):
        return _json_error(request, '请求的 API 资源不存在。', 404)
    return _json_error(request, '请求的资源不存在。', 404)


def api_handler500(request):
    response = _json_error(request, '服务暂时不可用，请稍后重试。', 500)
    response['Cache-Control'] = 'no-store'
    return response
