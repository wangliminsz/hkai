# -*- coding: utf-8 -*-
"""API Key 加密/脱敏工具。

生产环境请设置 ``AI_KEY_ENCRYPTION_KEY``（Fernet key，可用
``python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`` 生成）。
未配置时回退到由 ``SECRET_KEY`` 派生的密钥，仅适合开发/测试。
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

logger = logging.getLogger(__name__)

_warned = False


class DecryptError(Exception):
    pass


def _fernet() -> Fernet:
    global _warned
    raw = getattr(settings, "AI_KEY_ENCRYPTION_KEY", "") or os.getenv("AI_KEY_ENCRYPTION_KEY", "")
    if not raw:
        if not _warned:
            logger.warning(
                "AI_KEY_ENCRYPTION_KEY 未配置，暂用 SECRET_KEY 派生密钥；生产环境请显式配置。"
            )
            _warned = True
        secret = getattr(settings, "SECRET_KEY", "dvadmin-insecure-secret")
        raw = base64.urlsafe_b64encode(hashlib.sha256(str(secret).encode("utf-8")).digest())
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    try:
        return Fernet(raw)
    except Exception as exc:  # noqa: BLE001
        raise DecryptError(f"AI_KEY_ENCRYPTION_KEY 不是合法的 Fernet key: {exc}") from exc


def encrypt(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt(token: str) -> str:
    value = (token or "").strip()
    if not value:
        return ""
    try:
        return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise DecryptError("API Key 解密失败（加密密钥可能已变更）") from exc


def mask(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}****{value[-4:]}"
