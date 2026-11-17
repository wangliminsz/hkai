"""Tencent COS helpers for card artifacts.

Config resolution: CARD_COS_* takes precedence; falls back to the project's
existing COS_* settings. Empty credentials => COS disabled (local-only).
"""
from __future__ import annotations

from pathlib import Path

from django.conf import settings
from qcloud_cos import CosConfig, CosS3Client

_client = None


def _conf(prefix: str | None = None) -> dict:
    def opt(name, fallback=""):
        return getattr(settings, name, None) or fallback

    return {
        "secret_id": opt("CARD_COS_SECRET_ID") or opt("COS_SECRET_ID"),
        "secret_key": opt("CARD_COS_SECRET_KEY") or opt("COS_SECRET_KEY"),
        "region": opt("CARD_COS_REGION") or opt("COS_REGION"),
        "bucket": opt("CARD_COS_BUCKET") or opt("COS_BUCKET"),
        "prefix": prefix or opt("CARD_COS_PREFIX", "cards/") or "cards/",
    }


def enabled() -> bool:
    c = _conf()
    return bool(c["secret_id"] and c["secret_key"] and c["bucket"] and c["region"])


def _client_singleton() -> CosS3Client:
    global _client
    if _client is None:
        c = _conf()
        cfg = CosConfig(Region=c["region"], SecretId=c["secret_id"],
                        SecretKey=c["secret_key"], Scheme="https", Timeout=120)
        _client = CosS3Client(cfg)
    return _client


def _full_key(key: str, prefix: str | None = None) -> str:
    c = _conf(prefix)
    return c["prefix"].rstrip("/") + "/" + key.lstrip("/")


def upload_file(key: str, path: Path, content_type: str = "application/octet-stream",
                prefix: str | None = None, disposition: str | None = None) -> str:
    c = _conf(prefix)
    full = _full_key(key, prefix)
    extra = {"ContentDisposition": disposition} if disposition else {}
    with open(path, "rb") as f:
        _client_singleton().put_object(Bucket=c["bucket"], Body=f, Key=full,
                                       ContentType=content_type, EnableMD5=False, **extra)
    return full


def upload_bytes(key: str, data: bytes, content_type: str = "application/octet-stream",
                 prefix: str | None = None, disposition: str | None = None) -> str:
    c = _conf(prefix)
    full = _full_key(key, prefix)
    extra = {"ContentDisposition": disposition} if disposition else {}
    _client_singleton().put_object(Bucket=c["bucket"], Body=data, Key=full,
                                   ContentType=content_type, EnableMD5=False, **extra)
    return full


def public_url(full_key: str) -> str:
    """Public HTTPS URL for a key returned by upload_file/upload_bytes.

    Uses ``COS_PUBLIC_BASE`` (e.g. a CDN/CNAME) when set, otherwise the
    default Tencent COS endpoint. The bucket must allow public read.
    """
    c = _conf()
    base = (getattr(settings, "COS_PUBLIC_BASE", "") or "").rstrip("/")
    key = full_key.lstrip("/")
    if base:
        return f"{base}/{key}"
    return f"https://{c['bucket']}.cos.{c['region']}.myqcloud.com/{key}"


def download_bytes(key: str) -> bytes:
    c = _conf()
    resp = _client_singleton().get_object(Bucket=c["bucket"], Key=key)
    body = resp["Body"]
    try:
        return b"".join(body.get_stream(chunk_size=64 * 1024))
    finally:
        try:
            body.close()
        except Exception:
            pass
