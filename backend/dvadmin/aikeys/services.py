# -*- coding: utf-8 -*-
"""QVeris 余额查询 / 连通性测试。"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from . import resolver
from .models import ApiKey, PROVIDER_QVERIS

logger = logging.getLogger(__name__)

_BALANCE_KEYS = (
    "remaining_credits", "remaining_credit", "remaining",
    "balance", "credits", "total_credits", "available_credits",
)


def _as_float(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sum_remaining(balance: Any) -> tuple[float, bool]:
    """递归累加 balance 对象里所有 ``remaining`` 字段（QVeris 的余额结构按桶分层）。"""
    if not isinstance(balance, dict):
        return 0.0, False
    total = 0.0
    found = False
    for value in balance.values():
        if not isinstance(value, dict):
            continue
        remaining = value.get("remaining")
        if remaining is not None and not isinstance(remaining, bool):
            try:
                total += float(remaining)
                found = True
                continue
            except (TypeError, ValueError):
                pass
        sub_total, sub_found = _sum_remaining(value)
        total += sub_total
        found = found or sub_found
    return total, found


def _extract_balance(payload: Any) -> float | None:
    """从 ledger 最新一条记录里提取当前余额（优先 balance_after）。"""
    if payload is None:
        return None
    items = getattr(payload, "items", None) or []
    for item in items:
        for attr in ("balance_after", "balance_before"):
            total, found = _sum_remaining(getattr(item, attr, None))
            if found:
                return round(total, 4)
    summary = getattr(payload, "summary", None)
    if isinstance(summary, dict):
        for key in _BALANCE_KEYS:
            val = _as_float(summary.get(key))
            if val is not None:
                return val
    return None


def fetch_qveris_balance(api_key: str, base_url: str | None = None) -> float | None:
    from qveris import QverisClient, QverisConfig

    cfg = QverisConfig(
        api_key=api_key,
        base_url=(base_url or "https://qveris.ai/api/v1").rstrip("/"),
    )

    async def _run():
        client = QverisClient(cfg)
        try:
            result = await client.ledger(page_size=1, summary=False)
            return _extract_balance(result)
        finally:
            await client.close()

    return asyncio.run(_run())


def refresh_key(key: ApiKey) -> tuple[bool, float | None, str]:
    """查询并落库余额；返回 (ok, balance, error)。"""
    try:
        balance = fetch_qveris_balance(key.get_secret(), key.effective_base_url())
    except Exception as exc:  # noqa: BLE001
        status = getattr(exc, "status", None)
        error = f"{type(exc).__name__}: {exc}"
        if status in (401, 403):
            resolver.mark_invalid(key, error)
        else:
            resolver.mark_failed(key.id, status=status, error=error)
        return False, None, error
    resolver.refresh_credit(key, balance)
    return True, balance, ""


def refresh_tenant(tenant_id, provider: str = PROVIDER_QVERIS) -> dict:
    rows = list(ApiKey.objects.filter(provider=provider, is_active=True))
    tid = resolver.normalize_tenant_id(tenant_id)
    if tid is None:
        rows = [r for r in rows if r.tenant_id is None]
    else:
        rows = [r for r in rows if r.tenant_id == tid]
    ok = fail = 0
    errors: list[str] = []
    for key in rows:
        good, _balance, error = refresh_key(key)
        if good:
            ok += 1
        else:
            fail += 1
            errors.append(f"{key.name}: {error}")
    return {"ok": ok, "fail": fail, "errors": errors}
