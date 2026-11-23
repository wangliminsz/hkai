"""Read-only PocketBase client for the HK fund database (refer-04)."""
from __future__ import annotations

import requests
from django.conf import settings


class PBError(Exception):
    pass


def _opt(name, default=None):
    return getattr(settings, name, None) or default


def admin_token() -> str:
    base = _opt("HKFUND_PB_URL")
    email = _opt("HKFUND_PB_EMAIL")
    password = _opt("HKFUND_PB_PASSWORD")
    if not (base and email and password):
        raise PBError("基金 PocketBase 未配置（HKFUND_PB_*）")
    r = requests.post(
        f"{base.rstrip('/')}/api/collections/_superusers/auth-with-password",
        json={"identity": email, "password": password}, timeout=15,
    )
    r.raise_for_status()
    return r.json()["token"]


def get_records(collection: str, token: str, **params) -> dict:
    base = _opt("HKFUND_PB_URL")
    if not base:
        raise PBError("基金 PocketBase 未配置（HKFUND_PB_URL）")
    r = requests.get(
        f"{base.rstrip('/')}/api/collections/{collection}/records",
        headers={"Authorization": token}, params=params, timeout=20,
    )
    r.raise_for_status()
    return r.json()


# QVeris Key 已迁移到 Django DB（dvadmin.ai_key / dvadmin.aikeys），
# PocketBase 仅保留港股基金数据（read-only）。
