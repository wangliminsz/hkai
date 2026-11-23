# -*- coding: utf-8 -*-
from __future__ import annotations

from dvadmin.proposal.permissions import is_internal


def role_keys(user) -> set[str]:
    try:
        return set(user.role.values_list("key", flat=True))
    except Exception:  # noqa: BLE001
        return set()


def is_superuser(user) -> bool:
    return bool(user and getattr(user, "is_authenticated", False) and getattr(user, "is_superuser", False))


def is_manager(user) -> bool:
    return is_superuser(user) or "tenant_manager" in role_keys(user)


def user_tenant_id(user) -> int | None:
    tid = getattr(user, "tenant_id", None)
    return tid or None


def normalize_scope(value) -> int | None:
    """把请求里的 tenant_id 归一化：'platform'/''/None -> None。"""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in ("platform", "global", "null", "none", "0"):
        return None
    try:
        return int(text) or None
    except (TypeError, ValueError):
        return None


def can_read(user, tenant_id: int | None) -> bool:
    if not (user and getattr(user, "is_authenticated", False)):
        return False
    if is_superuser(user):
        return True
    if is_internal(user):
        return True
    own = user_tenant_id(user)
    return bool(own and tenant_id == own)


def can_write(user, tenant_id: int | None) -> bool:
    if not (user and getattr(user, "is_authenticated", False)):
        return False
    if is_superuser(user):
        return True
    # 双重角色（tenant_manager + internal）应能管理自己渠道的 Key；
    # internal 只限制“写平台池/其他渠道”，不限制自己的 tenant。
    own = user_tenant_id(user)
    if own and tenant_id == own and is_manager(user):
        return True
    if is_internal(user):
        return False
    return False
