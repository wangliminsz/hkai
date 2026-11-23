# -*- coding: utf-8 -*-
from __future__ import annotations

import logging

from celery import shared_task

from . import resolver, services
from .models import PROVIDER_QVERIS, ApiKey

logger = logging.getLogger(__name__)


@shared_task(name="dvadmin.aikeys.sync_qveris_credits")
def sync_qveris_credits(tenant_id=None):
    """刷新 QVeris Key 余额；tenant_id 为空只刷新平台池，'all' 刷新全部。"""
    qs = ApiKey.objects.filter(provider=PROVIDER_QVERIS, is_active=True)
    if tenant_id == "all":
        pass
    elif tenant_id in (None, "", "platform"):
        qs = qs.filter(tenant__isnull=True)
    else:
        tid = resolver.normalize_tenant_id(tenant_id)
        qs = qs.filter(tenant_id=tid) if tid else qs.filter(tenant__isnull=True)

    ok = fail = 0
    for key in qs.order_by("tenant_id", "priority", "id"):
        good, _balance, error = services.refresh_key(key)
        if good:
            ok += 1
        else:
            fail += 1
            logger.warning("[AIKEY] sync %s failed: %s", key.id, error)
    logger.info("[AIKEY] sync done: ok=%s fail=%s", ok, fail)
    return {"ok": ok, "fail": fail}
