import re
import logging
from time import perf_counter
from uuid import uuid4


REQUEST_ID_PATTERN = re.compile(r'^[A-Za-z0-9._:-]{1,80}$')
request_logger = logging.getLogger('operations.request')


class RequestIdMiddleware:
    """Propagate a bounded request id for support diagnostics and audit correlation."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started = perf_counter()
        supplied = request.headers.get('X-Request-Id', '')
        request.request_id = supplied if REQUEST_ID_PATTERN.fullmatch(supplied) else uuid4().hex
        response = self.get_response(request)
        response['X-Request-Id'] = request.request_id
        response.setdefault('Cache-Control', 'no-store')
        response.setdefault('Permissions-Policy', 'geolocation=(), microphone=(), camera=()')
        request_logger.info('http_request', extra={
            'request_id': request.request_id,
            'method': request.method,
            'path': request.path,
            'status_code': response.status_code,
            'duration_ms': round((perf_counter() - started) * 1000, 2),
        })
        return response
