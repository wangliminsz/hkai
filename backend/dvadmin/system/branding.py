# -*- coding: utf-8 -*-
"""Runtime branding (app title + logo) stored in system_config.

The frontend falls back to its build-time env defaults when a value is empty.
The logo is stored as a small data URL or a URL/path, so it works identically
in development (Vite :8080) and production (same-origin nginx) without
depending on media/COS settings.
"""
import re

from django.conf import settings

from application import dispatch
from dvadmin.system.models import SystemConfig

LOGO_KEY = "login.site_logo"
TITLE_KEY = "login.site_title"
WEB_TITLE_KEY = "base.web_title"

MAX_TITLE_LEN = 50
MAX_LOGO_CHARS = 1_500_000  # ~1.1 MB binary as base64

_DATA_URL_RE = re.compile(
    r"^data:image/(?:png|jpe?g|gif|webp|svg\+xml);base64,[A-Za-z0-9+/=\s]+$",
    re.IGNORECASE,
)
_URL_RE = re.compile(r"^(?:https?://|/)\S+$", re.IGNORECASE)


def default_title() -> str:
    return str(getattr(settings, "APP_NAME", "") or "DayBetter")


def _ensure_row(parent_key: str, key: str, title: str, form_item_type: int = 0):
    parent = SystemConfig.objects.filter(key=parent_key, parent_id=None).first()
    if parent is None:
        parent = SystemConfig.objects.create(
            key=parent_key, title=parent_key, form_item_type=0, status=True
        )
    row = SystemConfig.objects.filter(key=key, parent=parent).first()
    if row is None:
        row = SystemConfig.objects.create(
            key=key, parent=parent, title=title, form_item_type=form_item_type, status=True, value=""
        )
    return row


def _set_value(parent_key: str, key: str, title: str, value, form_item_type: int = 0):
    row = _ensure_row(parent_key, key, title, form_item_type)
    row.value = value
    row.status = True
    row.save()  # SystemConfig.save() refreshes dispatch config
    return row


def get_brand_settings() -> dict:
    return {
        "title": str(dispatch.get_system_config_values(TITLE_KEY) or "").strip(),
        "logo": str(dispatch.get_system_config_values(LOGO_KEY) or "").strip(),
        "default_title": default_title(),
        "default_logo": "/db_trans.png",
    }


def save_brand_settings(title=None, logo=None, reset_logo: bool = False):
    """Validate + persist brand settings. Returns (data, error_message)."""
    if title is not None:
        title = str(title).strip()
        if len(title) > MAX_TITLE_LEN:
            return None, f"标题最多 {MAX_TITLE_LEN} 个字符"
        _set_value("login", "site_title", "网站标题", title)
        _set_value("base", "web_title", "网页标题", title)

    if reset_logo:
        _set_value("login", "site_logo", "登录网站Logo", "", form_item_type=7)
    elif logo is not None:
        logo = str(logo).strip()
        if len(logo) > MAX_LOGO_CHARS:
            return None, "Logo 图片过大（请上传 1MB 以内的图片）"
        if logo and not (_DATA_URL_RE.match(logo) or _URL_RE.match(logo)):
            return None, "Logo 格式不支持（请上传 png/jpg/gif/webp/svg 或填写图片 URL）"
        _set_value("login", "site_logo", "登录网站Logo", logo, form_item_type=7)

    dispatch.refresh_system_config()
    return get_brand_settings(), None
