# -*- coding: utf-8 -*-
from __future__ import annotations

from .context import reset_current_tenant_id, set_current_tenant_id


class TenantContextMiddleware:
    """已停用：DRF JWT 在中间件之后才认证，无法取得真实 tenant_id。请勿重新注册。"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        tenant_id = getattr(user, "tenant_id", None) if getattr(user, "is_authenticated", False) else None
        token = set_current_tenant_id(tenant_id)
        try:
            return self.get_response(request)
        finally:
            reset_current_tenant_id(token)
