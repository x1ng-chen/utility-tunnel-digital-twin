"""Permit authentication and analysis without exposing business mutations."""
import re

from django.http import JsonResponse


class ReviewPermissions:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info
        if path.startswith(("/admin/", "/api/admin/", "/api/internal/", "/api/auth/registration-requests/")):
            return JsonResponse({"message": "评审环境未开放此入口。"}, status=404)
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return self.get_response(request)
        analysis = path in {
            "/api/auth/login/", "/api/auth/logout/", "/api/assistant/runs/",
        } or re.fullmatch(r"/api/assistant/runs/[0-9a-f-]{36}/", path)
        if request.method == "POST" and analysis:
            return self.get_response(request)
        return JsonResponse({"message": "评审环境只允许查询和分析。"}, status=403)
