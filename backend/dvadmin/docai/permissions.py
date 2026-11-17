# -*- coding: utf-8 -*-
"""AI 文件分析权限: 超管 / 内部用户 / 渠道经理 / 渠道成员(按设置开关)。"""
from __future__ import annotations

from rest_framework.permissions import BasePermission

from .models import DocAiSetting


def role_keys(user) -> set[str]:
    try:
        return set(user.role.values_list("key", flat=True))
    except Exception:  # noqa: BLE001
        return set()


def access_info(user) -> dict:
    """Return {'allowed': bool, 'reason': str, 'tier': str} for a user."""
    if not (user and getattr(user, "is_authenticated", False)):
        return {"allowed": False, "reason": "未登录", "tier": ""}
    if user.is_superuser:
        return {"allowed": True, "reason": "superadmin", "tier": "superadmin"}

    cfg = DocAiSetting.load()
    keys = role_keys(user)
    if "internal" in keys:
        return {"allowed": cfg.allow_internal, "reason": "" if cfg.allow_internal else "内部用户未开通", "tier": "internal"}
    if "tenant_manager" in keys:
        return {"allowed": cfg.allow_manager, "reason": "" if cfg.allow_manager else "渠道经理未开通", "tier": "manager"}
    if getattr(user, "tenant_id", None):
        return {"allowed": cfg.allow_member, "reason": "" if cfg.allow_member else "渠道成员未开通", "tier": "member"}
    return {"allowed": False, "reason": "无权限", "tier": ""}


class DocAiPermission(BasePermission):
    message = "未开通 AI 文件分析权限"

    def has_permission(self, request, view):
        return access_info(getattr(request, "user", None))["allowed"]
