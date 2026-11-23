# -*- coding: utf-8 -*-
"""按 tenant/provider 解析可用的 API Key。

规则：
- ``tenant_id`` 有值 -> 只使用该渠道自己的池；池为空直接拒绝（绝不回退平台池）。
- ``tenant_id`` 为空 -> 使用平台池（全局任务 / 无 tenant 的内部用户）。
- 默认 LRU（最久未使用优先），可通过 ``AI_KEY_STRATEGY`` 切换 random / highest_credit。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from django.conf import settings
from django.db.models import F, Q
from django.utils import timezone

from . import crypto
from .context import get_current_tenant_id
from .models import (
    DEFAULT_BASE_URLS,
    DEFAULT_MODELS,
    AiKeySetting,
    ApiKey,
    PROVIDER_CHOICES,
    PROVIDER_DEEPSEEK,
    PROVIDER_PAGEINDEX,
    PROVIDER_QVERIS,
    PROVIDER_VLLM,
)

STRATEGIES = ("lru", "random", "highest_credit")
DEFAULT_STRATEGY = "lru"


class NoAvailableKey(Exception):
    """当前范围内没有可用 Key。"""


@dataclass
class Credential:
    id: int
    tenant_id: int | None
    provider: str
    name: str
    key_mask: str
    api_key: str
    base_url: str
    model: str
    extra: dict = field(default_factory=dict)
    source: str = "db"  # db / env


def normalize_tenant_id(tenant_id) -> int | None:
    try:
        value = int(tenant_id)
    except (TypeError, ValueError):
        return None
    return value or None


def strategy_for(provider: str | None = None) -> str:
    raw = (getattr(settings, "AI_KEY_STRATEGY", "") or DEFAULT_STRATEGY).strip().lower()
    return raw if raw in STRATEGIES else DEFAULT_STRATEGY


def _pool(tenant_id, provider: str):
    qs = ApiKey.objects.filter(provider=provider, is_active=True)
    tid = normalize_tenant_id(tenant_id)
    if tid is None:
        qs = qs.filter(tenant__isnull=True)
    else:
        qs = qs.filter(tenant_id=tid)
    now = timezone.now()
    qs = qs.filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
    return qs


def _order(qs, strategy: str):
    if strategy == "random":
        return qs.order_by("?")
    if strategy == "highest_credit":
        return qs.order_by(
            F("remain_credit").desc(nulls_last=True),
            F("last_used_at").asc(nulls_first=True),
            "priority", "id",
        )
    # lru
    return qs.order_by(
        F("last_used_at").asc(nulls_first=True),
        "priority", "id",
    )


def candidates(tenant_id, provider: str = PROVIDER_QVERIS, strategy: str | None = None) -> list[ApiKey]:
    """按策略返回候选 Key（已过滤停用/过期/余额为 0）。"""
    qs = _pool(tenant_id, provider).filter(
        Q(remain_credit__isnull=True) | Q(remain_credit__gt=0)
    )
    return list(_order(qs, strategy or strategy_for(provider)))


def to_credential(obj: ApiKey) -> Credential:
    return Credential(
        id=obj.id,
        tenant_id=obj.tenant_id,
        provider=obj.provider,
        name=obj.name,
        key_mask=obj.key_mask,
        api_key=obj.get_secret(),
        base_url=obj.effective_base_url(),
        model=obj.effective_model(),
        extra=obj.extra or {},
        source="db",
    )


def first_credential(tenant_id, provider: str = PROVIDER_QVERIS, strategy: str | None = None) -> Credential:
    rows = candidates(tenant_id, provider, strategy)
    if not rows:
        raise NoAvailableKey(empty_message(tenant_id, provider))
    return to_credential(rows[0])


def mark_used(key_id: int) -> None:
    ApiKey.objects.filter(id=key_id).update(
        last_used_at=timezone.now(),
        used_count=F("used_count") + 1,
    )


def mark_failed(key_id: int, status: int | None = None, error: str = "") -> None:
    """记录失败；402/401/403 时停用该 Key，便于下一次换下一个。"""
    fields: dict = {
        "fail_count": F("fail_count") + 1,
        "last_error": (error or "")[:1000],
    }
    if status == 402:
        fields.update(is_active=False, remain_credit=0)
    elif status in (401, 403):
        fields.update(is_active=False)
    ApiKey.objects.filter(id=key_id).update(**fields)


def refresh_credit(key: ApiKey, amount) -> None:
    fields = {"last_checked_at": timezone.now()}
    if amount is not None:
        fields["remain_credit"] = amount
    ApiKey.objects.filter(id=key.id).update(**fields)


def mark_invalid(key: ApiKey, error: str = "invalid key") -> None:
    ApiKey.objects.filter(id=key.id).update(
        is_active=False,
        last_error=(error or "")[:1000],
        fail_count=F("fail_count") + 1,
    )


def empty_message(tenant_id, provider: str) -> str:
    label = dict(PROVIDER_CHOICES).get(provider, provider)
    tid = normalize_tenant_id(tenant_id)
    if tid is None:
        return f"平台未配置可用的 {label} Key"
    return f"当前渠道未配置可用的 {label} Key，请先在 AI 配置中添加"


# ---------------------------------------------------------------------------
# 单 Key provider（deepseek / vllm / pageindex）
# ---------------------------------------------------------------------------

_ENV_FIELDS = {
    PROVIDER_DEEPSEEK: ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE", "DEEPSEEK_MODEL"),
    PROVIDER_VLLM: ("VLLM_API_KEY", "VLLM_BASE", "VLLM_MODEL"),
}


def _env_value(*names) -> str:
    for name in names:
        val = getattr(settings, name, None) or os.getenv(name)
        if val:
            return str(val).strip()
    return ""


def env_credential(provider: str) -> Credential | None:
    """平台没有 DB Key 时，回退到 conf/env.py 的全局 Key。"""
    if provider == PROVIDER_PAGEINDEX:
        api_key = _env_value("PI_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY")
        base_url = _env_value("PI_BASE_URL", "OPENAI_BASE_URL", "DEEPSEEK_BASE") or DEFAULT_BASE_URLS.get(provider, "")
        model = _env_value("PI_CHAT_MODEL", "DEEPSEEK_MODEL") or DEFAULT_MODELS.get(provider, "")
        index_model = _env_value("PI_INDEX_MODEL") or model
    else:
        fields = _ENV_FIELDS.get(provider)
        if not fields:
            return None
        key_name, base_name, model_name = fields
        api_key = _env_value(key_name)
        base_url = _env_value(base_name) or DEFAULT_BASE_URLS.get(provider, "")
        model = _env_value(model_name) or DEFAULT_MODELS.get(provider, "")
        index_model = ""
    if not api_key:
        return None
    extra = {"index_model": index_model} if index_model else {}
    return Credential(
        id=0,
        tenant_id=None,
        provider=provider,
        name="env",
        key_mask=crypto.mask(api_key),
        api_key=api_key,
        base_url=base_url,
        model=model,
        extra=extra,
        source="env",
    )


def fallback_enabled() -> bool:
    try:
        return bool(AiKeySetting.load().fallback_to_global)
    except Exception:  # noqa: BLE001 - DB 未迁移时退回 env 默认
        return bool(getattr(settings, "AI_KEY_FALLBACK_TO_GLOBAL", True))


def _single_row(tenant_id, provider: str) -> ApiKey | None:
    return _pool(tenant_id, provider).order_by("priority", "id").first()


def _use(cred: Credential | None) -> Credential | None:
    """记录 DB Key 的使用时间/次数（env Key 无 id，不记录）。"""
    if cred is not None and cred.source == "db" and cred.id:
        mark_used(cred.id)
    return cred


def platform_credential(provider: str) -> Credential | None:
    row = _single_row(None, provider)
    if row is not None:
        return to_credential(row)
    return env_credential(provider)


def get_single(
    tenant_id=None,
    provider: str = PROVIDER_DEEPSEEK,
    *,
    require: bool = True,
    fallback: bool | None = None,
    use_context: bool = False,
) -> Credential | None:
    """解析单 Key provider 的凭据。

    - ``tenant_id`` 显式给值优先；``use_context=True`` 时才会读 Celery ContextVar。
    - 渠道有 Key -> 用渠道的。
    - 渠道没 Key -> 根据 fallback 开关回退平台 DB/env；关闭则拒绝。
    - 平台（tenant=None）-> 平台 DB Key，没有则 env。
    """
    tid = normalize_tenant_id(tenant_id)
    if tid is None and use_context:
        tid = get_current_tenant_id()

    allow_fallback = fallback_enabled() if fallback is None else bool(fallback)

    if tid is not None:
        row = _single_row(tid, provider)
        if row is not None:
            return _use(to_credential(row))
        if not allow_fallback:
            if require:
                raise NoAvailableKey(empty_message(tid, provider))
            return None

    cred = platform_credential(provider)
    if cred is not None:
        return _use(cred)
    if require:
        raise NoAvailableKey(empty_message(None, provider))
    return None
