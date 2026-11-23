# -*- coding: utf-8 -*-
"""Celery 任务级别的当前 tenant 上下文。

仅用于后台任务中不方便层层传参的深层调用（Proposal engine）。
HTTP 请求路径不要依赖此上下文：DRF JWT 在视图内部才完成认证，
Django 中间件阶段拿不到真实 tenant_id；请显式传 ``request.user.tenant_id``。
"""
from __future__ import annotations

from contextvars import ContextVar, Token

_current_tenant_id: ContextVar[int | None] = ContextVar("aikeys_tenant_id", default=None)


def _normalize(tenant_id) -> int | None:
    try:
        value = int(tenant_id)
    except (TypeError, ValueError):
        return None
    return value or None


def get_current_tenant_id() -> int | None:
    return _current_tenant_id.get()


def set_current_tenant_id(tenant_id) -> Token:
    return _current_tenant_id.set(_normalize(tenant_id))


def reset_current_tenant_id(token: Token) -> None:
    try:
        _current_tenant_id.reset(token)
    except (ValueError, RuntimeError):
        _current_tenant_id.set(None)
