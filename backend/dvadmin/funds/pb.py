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


def get_qveris_keys() -> list[dict]:
    """Read qveris.ai API keys + remaining credit from PocketBase.

    Only the masked key is returned; api_key itself never leaves the server.
    Sorted ascending by remain_credit so the lowest-credit key comes first.
    """
    token = admin_token()
    data = get_records("qveris_keys", token, perPage=200)
    rows = []
    for r in data.get("items", []):
        try:
            credit = round(float(r.get("remain_credit") or 0), 2)
        except (TypeError, ValueError):
            credit = 0.0
        rows.append({
            "id": r.get("id"),
            "key_env": r.get("key_env") or "",
            "login_name": r.get("login_name") or "",
            "masked_key": r.get("masked_key") or "",
            "remain_credit": credit,
        })
    rows.sort(key=lambda x: x["remain_credit"])
    return rows


def get_qveris_api_key() -> str:
    """Return the qveris.ai api_key with the highest remaining credit.

    api_key stays server-side; callers must never log it. Falls back to the
    QVERIS_API_KEY setting when PocketBase has no usable key.
    """
    try:
        token = admin_token()
        data = get_records("qveris_keys", token, perPage=200)
        best = None
        for r in data.get("items", []):
            key = (r.get("api_key") or "").strip()
            if not key:
                continue
            try:
                credit = float(r.get("remain_credit") or 0)
            except (TypeError, ValueError):
                credit = 0.0
            if best is None or credit > best[0]:
                best = (credit, key)
        if best:
            return best[1]
    except Exception:  # noqa: BLE001 - fall through to setting
        pass
    return _opt("QVERIS_API_KEY", "") or ""
