"""Shared API error handling for the Django REST surface.

Keeping the envelope stable means the Vue client can render validation,
authentication and routing failures without having to know DRF internals.
"""

from rest_framework.views import exception_handler
from django.http import JsonResponse


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
    return response


def api_handler404(request, exception):
    if request.path.startswith('/api/'):
        return JsonResponse({'error': 'not_found', 'message': '请求的 API 资源不存在。', 'details': {}}, status=404)
    return JsonResponse({'error': 'not_found', 'message': '请求的资源不存在。', 'details': {}}, status=404)


def api_handler500(request):
    return JsonResponse({'error': 'internal_error', 'message': '服务暂时不可用，请稍后重试。', 'details': {}}, status=500)
