# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
from datetime import datetime, time
from decimal import Decimal

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.translation import gettext_lazy as _
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from dvadmin.utils.json_response import ErrorResponse, SuccessResponse

from . import permissions as perms
from . import resolver, services
from .models import (
    DEFAULT_BASE_URLS,
    MULTI_KEY_PROVIDERS,
    PROVIDER_CHOICES,
    PROVIDER_QVERIS,
    AiKeySetting,
    ApiKey,
)

logger = logging.getLogger(__name__)

_PROVIDER_LABELS = dict(PROVIDER_CHOICES)
_BALANCE_TTL = int(getattr(settings, "AI_KEY_BALANCE_TTL", 900) or 900)


def _fmt(dt) -> str | None:
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None


def _serialize(obj: ApiKey) -> dict:
    return {
        "id": obj.id,
        "provider": obj.provider,
        "provider_label": _PROVIDER_LABELS.get(obj.provider, obj.provider),
        "tenant_id": obj.tenant_id,
        "tenant_name": obj.tenant.name if obj.tenant_id and obj.tenant else "平台",
        "scope": obj.scope,
        "name": obj.name,
        "key_mask": obj.key_mask,
        "base_url": obj.base_url,
        "effective_base_url": obj.effective_base_url(),
        "model": obj.model,
        "extra": obj.extra or {},
        "priority": obj.priority,
        "is_active": obj.is_active,
        "remain_credit": float(obj.remain_credit) if obj.remain_credit is not None else None,
        "last_checked_at": _fmt(obj.last_checked_at),
        "last_used_at": _fmt(obj.last_used_at),
        "expires_at": _fmt(obj.expires_at),
        "used_count": obj.used_count,
        "fail_count": obj.fail_count,
        "last_error": obj.last_error,
        "remark": obj.remark,
        "created_at": _fmt(obj.create_datetime),
    }


def _as_bool(value, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on", "open", "启用")


def _as_int(value, default: int = 10) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_dt(value):
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    dt = parse_datetime(text)
    if dt is None:
        day = parse_date(text)
        if day is not None:
            dt = datetime.combine(day, time.min)
    if dt is None:
        raise ValueError("时间格式不正确")
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    return dt


def _body(request) -> dict:
    data = getattr(request, "data", None)
    return data if isinstance(data, dict) else {}


def _requested_scope(request, data: dict | None = None):
    """返回 (scope, tenant_id, all_flag)。

    - ``scope=tenant``：强制当前用户自己的渠道（渠道页使用）。
    - ``scope=all``：仅超管/内部，返回全部（管理概览）。
    - ``tenant_id=platform/数字``：显式指定平台池或某个渠道（超管/内部使用）。
    - 不传：超管 -> 全部；有 tenant 的用户（含双重角色）-> 自己的渠道；纯 internal -> 全部。
    """
    user = request.user
    own = perms.user_tenant_id(user)

    raw_scope = None
    if data and data.get("scope") is not None:
        raw_scope = data.get("scope")
    elif request.query_params.get("scope") is not None:
        raw_scope = request.query_params.get("scope")
    raw_scope = str(raw_scope).strip().lower() if raw_scope is not None else ""

    if raw_scope == "tenant":
        return "scope", own, False
    if raw_scope == "all":
        if perms.is_superuser(user) or perms.is_internal(user):
            return "all", None, True
        return "scope", own, False

    raw = None
    if data and "tenant_id" in data:
        raw = data.get("tenant_id")
    elif request.query_params.get("tenant_id") is not None:
        raw = request.query_params.get("tenant_id")
    if raw is not None:
        return "scope", perms.normalize_scope(raw), False

    if perms.is_superuser(user):
        return "all", None, True
    if own:
        return "scope", own, False
    if perms.is_internal(user):
        return "all", None, True
    return "scope", None, False


def _can_view(user, tenant_id) -> bool:
    return perms.can_read(user, tenant_id)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def keys(request):
    if request.method == "GET":
        scope, tenant_id, all_flag = _requested_scope(request)
        qs = ApiKey.objects.all()
        provider = str(request.query_params.get("provider") or "").strip()
        if provider:
            qs = qs.filter(provider=provider)
        if all_flag:
            if not (perms.is_superuser(request.user) or perms.is_internal(request.user)):
                return ErrorResponse(msg=_("无权限"), code=403)
        else:
            if not _can_view(request.user, tenant_id):
                return ErrorResponse(msg=_("无权限"), code=403)
            qs = qs.filter(tenant__isnull=True) if tenant_id is None else qs.filter(tenant_id=tenant_id)
        qs = qs.select_related("tenant").order_by("tenant_id", "provider", "priority", "id")
        return SuccessResponse(data=[_serialize(obj) for obj in qs])

    # POST
    data = _body(request)
    scope, tenant_id, _all = _requested_scope(request, data)
    if scope == "all":
        tenant_id = None
    if not perms.can_write(request.user, tenant_id):
        return ErrorResponse(msg=_("无权限管理该范围的 Key"), code=403)

    provider = str(data.get("provider") or PROVIDER_QVERIS).strip() or PROVIDER_QVERIS
    if provider not in _PROVIDER_LABELS:
        return ErrorResponse(msg=_("不支持的 provider"))
    raw_key = str(data.get("api_key") or data.get("key") or "").strip()
    if not raw_key:
        return ErrorResponse(msg=_("请填写 API Key"))

    try:
        expires_at = _parse_dt(data.get("expires_at"))
    except ValueError as exc:
        return ErrorResponse(msg=str(exc))

    name = str(data.get("name") or "").strip() or (
        f"QVeris {ApiKey.objects.filter(provider=provider, tenant_id=tenant_id).count() + 1}"
        if provider == PROVIDER_QVERIS else _PROVIDER_LABELS[provider]
    )
    base_url = str(data.get("base_url") or "").strip() or DEFAULT_BASE_URLS.get(provider, "")
    model = str(data.get("model") or "").strip()
    extra = data.get("extra") if isinstance(data.get("extra"), dict) else {}

    # 非 QVeris：每个 tenant + provider 只保留一条，编辑即 upsert
    if provider not in MULTI_KEY_PROVIDERS:
        obj = ApiKey.objects.filter(provider=provider, tenant_id=tenant_id).order_by("id").first()
        if obj is None:
            obj = ApiKey(provider=provider, tenant_id=tenant_id)
        obj.name = name
        obj.set_secret(raw_key)
        obj.base_url = base_url
        obj.model = model
        obj.extra = extra
        obj.priority = _as_int(data.get("priority"), obj.priority)
        obj.is_active = _as_bool(data.get("is_active"), True)
        obj.expires_at = expires_at
        obj.remark = str(data.get("remark") or "")
        obj.last_error = ""
        obj.save()
        return SuccessResponse(data=_serialize(obj), msg=_("已保存"))

    obj = ApiKey(
        provider=provider, tenant_id=tenant_id, name=name,
        base_url=base_url, model=model, extra=extra,
        priority=_as_int(data.get("priority"), 10),
        is_active=_as_bool(data.get("is_active"), True),
        expires_at=expires_at,
        remark=str(data.get("remark") or ""),
    )
    obj.set_secret(raw_key)
    obj.save()
    return SuccessResponse(data=_serialize(obj), msg=_("已添加"))


@api_view(["GET", "PATCH", "PUT", "DELETE"])
@permission_classes([IsAuthenticated])
def key_detail(request, pk: int):
    obj = ApiKey.objects.select_related("tenant").filter(id=pk).first()
    if obj is None:
        return ErrorResponse(msg=_("Key 不存在"), code=404)

    if request.method == "GET":
        if not _can_view(request.user, obj.tenant_id):
            return ErrorResponse(msg=_("无权限"), code=403)
        return SuccessResponse(data=_serialize(obj))

    if not perms.can_write(request.user, obj.tenant_id):
        return ErrorResponse(msg=_("无权限管理该 Key"), code=403)

    if request.method == "DELETE":
        obj.delete()
        return SuccessResponse(msg=_("已删除"))

    data = _body(request)
    raw_key = str(data.get("api_key") or data.get("key") or "").strip()
    if raw_key:
        obj.set_secret(raw_key)
        obj.is_active = True
        obj.last_error = ""
    if "name" in data:
        obj.name = str(data.get("name") or "").strip() or obj.name
    if "base_url" in data:
        obj.base_url = str(data.get("base_url") or "").strip()
    if "model" in data:
        obj.model = str(data.get("model") or "").strip()
    if "extra" in data and isinstance(data.get("extra"), dict):
        obj.extra = data.get("extra")
    if "priority" in data:
        obj.priority = _as_int(data.get("priority"), obj.priority)
    if "is_active" in data:
        obj.is_active = _as_bool(data.get("is_active"), obj.is_active)
    if "remark" in data:
        obj.remark = str(data.get("remark") or "")
    if "expires_at" in data:
        try:
            obj.expires_at = _parse_dt(data.get("expires_at"))
        except ValueError as exc:
            return ErrorResponse(msg=str(exc))
    obj.save()
    return SuccessResponse(data=_serialize(obj), msg=_("已保存"))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def key_test(request, pk: int):
    obj = ApiKey.objects.select_related("tenant").filter(id=pk).first()
    if obj is None:
        return ErrorResponse(msg=_("Key 不存在"), code=404)
    if not perms.can_write(request.user, obj.tenant_id):
        return ErrorResponse(msg=_("无权限操作该 Key"), code=403)
    if obj.provider != PROVIDER_QVERIS:
        return ErrorResponse(msg=_("该 provider 暂不支持在线测试"))
    ok, balance, error = services.refresh_key(obj)
    obj.refresh_from_db()
    if not ok:
        return ErrorResponse(data={"balance": None, "error": error}, msg=f"测试失败: {error}")
    return SuccessResponse(data={"balance": balance, "key": _serialize(obj)}, msg=_("连接成功"))


def _maybe_refresh(rows: list[ApiKey], force: bool) -> None:
    now = timezone.now()
    for obj in rows:
        if obj.provider != PROVIDER_QVERIS:
            continue
        stale = (
            force
            or obj.last_checked_at is None
            or (now - obj.last_checked_at).total_seconds() > _BALANCE_TTL
        )
        if not stale:
            continue
        try:
            services.refresh_key(obj)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[AIKEY] refresh %s failed: %s", obj.id, exc)


def _credits_summary(rows: list[ApiKey], can_write: bool = False) -> dict:
    values = [float(r.remain_credit) for r in rows if r.remain_credit is not None]
    total = round(sum(values), 4) if values else 0
    lowest = min(values) if values else None
    return {
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(rows),
        "active_count": sum(1 for r in rows if r.is_active),
        "total": total,
        "lowest": lowest,
        "can_write": can_write,
        "fallback_to_global": resolver.fallback_enabled(),
        "items": [_serialize(r) for r in rows],
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def credits(request):
    scope, tenant_id, all_flag = _requested_scope(request)
    if all_flag and not (perms.is_superuser(request.user) or perms.is_internal(request.user)):
        return ErrorResponse(msg=_("无权限"), code=403)
    if not all_flag and not _can_view(request.user, tenant_id):
        return ErrorResponse(msg=_("无权限"), code=403)

    qs = ApiKey.objects.select_related("tenant").filter(provider=PROVIDER_QVERIS)
    if not all_flag:
        qs = qs.filter(tenant__isnull=True) if tenant_id is None else qs.filter(tenant_id=tenant_id)
    rows = list(qs.order_by("tenant_id", "priority", "id"))
    force = str(request.query_params.get("refresh") or "").lower() in ("1", "true", "yes")
    _maybe_refresh(rows, force)
    rows = list(qs.order_by("tenant_id", "priority", "id"))
    writable = perms.can_write(request.user, tenant_id) if not all_flag else perms.is_superuser(request.user)
    return SuccessResponse(data=_credits_summary(rows, can_write=writable))


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def settings_view(request):
    """全局 AI Key 策略：读取（内部）/切换 fallback（仅超管）。"""
    if not (perms.is_superuser(request.user) or perms.is_internal(request.user)):
        return ErrorResponse(msg=_("无权限"), code=403)
    obj = AiKeySetting.load()
    if request.method == "PATCH":
        if not perms.is_superuser(request.user):
            return ErrorResponse(msg=_("仅超级管理员可修改"), code=403)
        data = _body(request)
        if "fallback_to_global" in data:
            obj.fallback_to_global = _as_bool(data.get("fallback_to_global"), obj.fallback_to_global)
            obj.save(update_fields=["fallback_to_global"])
    return SuccessResponse(data={"fallback_to_global": obj.fallback_to_global})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def overview(request):
    if not (perms.is_superuser(request.user) or perms.is_internal(request.user)):
        return ErrorResponse(msg=_("无权限"), code=403)
    rows = list(ApiKey.objects.select_related("tenant").filter(provider=PROVIDER_QVERIS))
    groups: dict = {}
    for obj in rows:
        key = obj.tenant_id or 0
        item = groups.setdefault(key, {
            "tenant_id": obj.tenant_id,
            "tenant_name": obj.tenant.name if obj.tenant_id and obj.tenant else "平台",
            "count": 0,
            "active_count": 0,
            "total": Decimal("0"),
        })
        item["count"] += 1
        if obj.is_active:
            item["active_count"] += 1
        if obj.remain_credit is not None:
            item["total"] += obj.remain_credit
    data = []
    for item in groups.values():
        item["total"] = float(round(item["total"], 4))
        data.append(item)
    return SuccessResponse(data=data)
