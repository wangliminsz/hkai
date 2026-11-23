from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.http import Http404, HttpResponse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import BasePermission

from dvadmin.proposal.permissions import InternalPermission
from dvadmin.utils.json_response import ErrorResponse, SuccessResponse

from . import news, pb, schedule
from . import prompts as prompts_store
from .models import AiPrompt, ChannelFeishuGroup, FundBroadcast, NewsSource
from .tasks import broadcast_fund_analysis, broadcast_funds, broadcast_news

logger = logging.getLogger(__name__)


class ChannelManagerPermission(BasePermission):
    message = "需要渠道管理员(tenant_manager)"

    def has_permission(self, request, view):
        u = getattr(request, "user", None)
        if not (u and u.is_authenticated):
            return False
        if u.is_superuser:
            return True
        if not getattr(u, "tenant_id", None):
            return False
        return u.role.filter(key="tenant_manager").exists()


def _serialize_group(g: ChannelFeishuGroup) -> dict:
    return {"id": g.id, "name": g.name, "webhook_url": g.webhook_url,
            "enabled": g.enabled, "remark": g.remark}


def _serialize_broadcast(b: FundBroadcast) -> dict:
    return {
        "id": b.id, "status": b.status, "status_label": b.get_status_display(),
        "kind": b.kind, "edition": b.edition, "title": b.title,
        "weekday": b.weekday, "lot": b.lot, "total_groups": b.total_groups,
        "ok_count": b.ok_count, "fail_count": b.fail_count, "logs": b.logs,
        "content": b.content,
        "created_at": b.create_datetime.strftime("%Y-%m-%d %H:%M:%S") if b.create_datetime else None,
    }


# --------------------------------------------------------------------------
# 渠道: 飞书群管理
# --------------------------------------------------------------------------

@api_view(["GET", "POST"])
@permission_classes([ChannelManagerPermission])
def groups(request):
    tenant = request.user.tenant
    if request.method == "GET":
        rows = ChannelFeishuGroup.objects.filter(tenant=tenant).order_by("-id")
        return SuccessResponse(data=[_serialize_group(g) for g in rows])

    name = str(request.data.get("name") or "").strip()
    url = str(request.data.get("webhook_url") or "").strip()
    if not name or not url:
        return ErrorResponse(msg=_("请填写群名称与飞书群 Webhook 链接"))
    if not url.startswith("https://open.feishu.cn/"):
        return ErrorResponse(msg=_("Webhook 链接应以 https://open.feishu.cn/ 开头"))
    obj = ChannelFeishuGroup.objects.create(
        tenant=tenant, name=name, webhook_url=url,
        enabled=bool(request.data.get("enabled", True)),
        remark=str(request.data.get("remark") or ""),
    )
    return SuccessResponse(data=_serialize_group(obj), msg=_("已添加"))


@api_view(["PUT", "DELETE"])
@permission_classes([ChannelManagerPermission])
def group_detail(request, pk: int):
    obj = ChannelFeishuGroup.objects.filter(id=pk, tenant=request.user.tenant).first()
    if obj is None:
        return ErrorResponse(msg=_("群不存在"))
    if request.method == "DELETE":
        obj.delete()
        return SuccessResponse(msg=_("已删除"))
    for field in ("name", "webhook_url", "remark"):
        if field in request.data:
            setattr(obj, field, str(request.data.get(field) or "").strip())
    if "enabled" in request.data:
        obj.enabled = bool(request.data.get("enabled"))
    obj.save()
    return SuccessResponse(data=_serialize_group(obj), msg=_("已保存"))


# --------------------------------------------------------------------------
# 内部/超管: 预览 / 推送 / 历史
# --------------------------------------------------------------------------

@api_view(["GET"])
@permission_classes([InternalPermission])
def schedule_preview(request):
    now = datetime.now()
    weekday = int(request.query_params.get("weekday")) if request.query_params.get("weekday") is not None else now.weekday()
    weekday = max(0, min(6, weekday))
    try:
        token = pb.admin_token()
        funds = schedule.collect_day_funds(token, weekday, now)
        lot = funds[0]["lot"] if funds else ""
        content = schedule.build_message_from_funds(lot, weekday, funds, now)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[FUNDS] schedule preview failed")
        return ErrorResponse(msg=f"读取基金数据失败: {exc}")
    groups = ChannelFeishuGroup.objects.filter(enabled=True).count()
    return SuccessResponse(data={
        "weekday": weekday,
        "weekday_name": schedule.WEEKDAY_NAMES[weekday],
        "send_today": weekday < 5,
        "lot": lot,
        "fund_count": len(funds),
        "requested_groups": groups,
        "funds": funds,
        "content": content,
    })


@api_view(["GET", "POST"])
@permission_classes([InternalPermission])
def broadcasts(request):
    if request.method == "GET":
        qs = FundBroadcast.objects.filter(kind="fund").order_by("-id")[:50]
        return SuccessResponse(data=[_serialize_broadcast(b) for b in qs])

    try:
        weekday = int(request.data.get("weekday")) if request.data.get("weekday") not in (None, "") else datetime.now().weekday()
    except (TypeError, ValueError):
        weekday = datetime.now().weekday()
    weekday = max(0, min(6, weekday))
    if weekday >= 5:
        return ErrorResponse(msg=_("周六/周日不推送，请选择周一至周五"))
    b = FundBroadcast.objects.create(user=request.user, kind="fund", weekday=weekday, status="queued")
    broadcast_funds.apply_async(args=[b.id], queue="funds")
    logger.info("[FUNDS] broadcast %s queued by %s", b.id, request.user.username)
    return SuccessResponse(data={"id": b.id}, msg=_("已提交，正在推送到全部渠道飞书群"))


@api_view(["GET"])
@permission_classes([InternalPermission])
def broadcast_detail(request, pk: int):
    b = FundBroadcast.objects.filter(id=pk).first()
    if b is None:
        return ErrorResponse(msg=_("任务不存在"))
    return SuccessResponse(data=_serialize_broadcast(b))


# --------------------------------------------------------------------------
# 单基金深度分析(内部/超管): QVeris 分析 -> HTML 报告 -> 飞书卡片
# --------------------------------------------------------------------------

@api_view(["GET", "POST"])
@permission_classes([InternalPermission])
def fund_analysis(request):
    if request.method == "GET":
        qs = FundBroadcast.objects.filter(kind="analysis").order_by("-id")[:50]
        return SuccessResponse(data=[_serialize_broadcast(b) for b in qs])

    try:
        weekday = int(request.data.get("weekday")) if request.data.get("weekday") not in (None, "") else datetime.now().weekday()
    except (TypeError, ValueError):
        weekday = datetime.now().weekday()
    weekday = max(0, min(6, weekday))
    if weekday >= 5:
        return ErrorResponse(msg=_("周六/周日不推送，请选择周一至周五"))
    b = FundBroadcast.objects.create(user=request.user, kind="analysis", weekday=weekday, status="queued")
    broadcast_fund_analysis.apply_async(args=[b.id], queue="fund-analysis")
    logger.info("[ANALYSIS] job %s queued by %s", b.id, request.user.username)
    return SuccessResponse(data={"id": b.id}, msg=_("已提交，正在逐只基金生成深度分析并推送（耗时较长，请稍候）"))


_FUND_NAME_RE = re.compile(r"^[^/\\]{1,140}$")


@require_GET
def fund_report(request, lot: str, name: str):
    """公开直出单基金分析报告 HTML(飞书「查看完整分析」按钮)。"""
    if not re.fullmatch(r"[0-9A-Za-z_-]{1,64}", lot) or not _FUND_NAME_RE.match(name) or ".." in name:
        raise Http404
    content: bytes | None = None
    data_dir = getattr(settings, "FUND_REPORT_DIR", "") or ""
    root = Path(data_dir) if data_dir else Path(settings.BASE_DIR) / "fund_reports"
    path = root / lot / name
    try:
        if path.is_file():
            content = path.read_bytes()
    except Exception:  # noqa: BLE001
        content = None
    if content is None:
        try:
            from dvadmin.cards import cos
            if cos.enabled():
                prefix = (getattr(settings, "FUND_REPORT_COS_PREFIX", "reports/") or "reports/").strip("/")
                content = cos.download_bytes(f"{prefix}/{lot}/{name}")
        except Exception:  # noqa: BLE001
            content = None
    if content is None:
        raise Http404
    resp = HttpResponse(content, content_type="text/html; charset=utf-8")
    resp["Content-Disposition"] = "inline"
    resp["Cache-Control"] = "public, max-age=600"
    return resp


# --------------------------------------------------------------------------
# Qveris API 额度(来自 Django DB 的 AI Key 池, 缓存 5 分钟)
# --------------------------------------------------------------------------

QVERIS_CACHE_KEY = "funds:qveris_credits"
QVERIS_CACHE_TTL = 300


def _qveris_credit_items(rows) -> list[dict]:
    items = []
    for row in rows:
        items.append({
            "id": row.id,
            "tenant_id": row.tenant_id,
            "tenant_name": row.tenant.name if row.tenant_id and row.tenant else "平台",
            "login_name": row.tenant.name if row.tenant_id and row.tenant else "平台",
            "key_env": row.get_provider_display(),
            "name": row.name,
            "masked_key": row.key_mask,
            "remain_credit": float(row.remain_credit) if row.remain_credit is not None else None,
            "is_active": row.is_active,
            "last_checked_at": row.last_checked_at.strftime("%Y-%m-%d %H:%M:%S") if row.last_checked_at else None,
            "last_error": row.last_error,
        })
    return items


@api_view(["GET"])
@permission_classes([InternalPermission])
def qveris_credits(request):
    from dvadmin.aikeys import services as aikey_services
    from dvadmin.aikeys.models import PROVIDER_QVERIS, ApiKey

    force = str(request.query_params.get("refresh") or "").lower() in ("1", "true", "yes")
    data = None
    if not force:
        try:
            data = cache.get(QVERIS_CACHE_KEY)
        except Exception:  # noqa: BLE001 - cache outage shouldn't break the view
            data = None
    if data is None:
        try:
            rows = list(
                ApiKey.objects.select_related("tenant")
                .filter(provider=PROVIDER_QVERIS)
                .order_by("tenant_id", "priority", "id")
            )
            if force:
                for row in rows:
                    aikey_services.refresh_key(row)
                rows = list(
                    ApiKey.objects.select_related("tenant")
                    .filter(provider=PROVIDER_QVERIS)
                    .order_by("tenant_id", "priority", "id")
                )
            items = _qveris_credit_items(rows)
        except Exception as exc:  # noqa: BLE001
            logger.exception("[FUNDS] qveris credits fetch failed")
            return ErrorResponse(msg=f"读取 Qveris 额度失败: {exc}")
        values = [i["remain_credit"] for i in items if i["remain_credit"] is not None]
        data = {
            "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "count": len(items),
            "total": round(sum(values), 2) if values else 0,
            "lowest": min(values) if values else None,
            "items": items,
        }
        try:
            cache.set(QVERIS_CACHE_KEY, data, QVERIS_CACHE_TTL)
        except Exception:  # noqa: BLE001
            pass
    return SuccessResponse(data=data)


# --------------------------------------------------------------------------
# 新闻 HTML 公开直出(飞书「阅读文字版/详细版」按钮; 无需登录)
# --------------------------------------------------------------------------

_NEWS_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_NEWS_EDITION_RE = re.compile(r"^[0-9A-Za-z_-]{1,40}$")


@require_GET
def news_html(request, date: str, edition: str, kind: str):
    if kind not in ("brief", "report") or not _NEWS_DATE_RE.match(date) or not _NEWS_EDITION_RE.match(edition):
        raise Http404

    content: bytes | None = None
    data_dir = getattr(settings, "NEWS_DATA_DIR", "") or ""
    root = Path(data_dir) if data_dir else Path(settings.BASE_DIR) / "news_data"
    path = root / date / edition / f"{kind}.html"
    try:
        if path.is_file():
            content = path.read_bytes()
    except Exception:  # noqa: BLE001
        content = None

    if content is None:
        try:
            from dvadmin.cards import cos
            if cos.enabled():
                prefix = (getattr(settings, "NEWS_COS_PREFIX", "news/") or "news/").strip("/")
                content = cos.download_bytes(f"{prefix}/{date}/{edition}/{kind}.html")
        except Exception:  # noqa: BLE001
            content = None

    if content is None:
        raise Http404

    resp = HttpResponse(content, content_type="text/html; charset=utf-8")
    resp["Content-Disposition"] = "inline"
    resp["Cache-Control"] = "public, max-age=600"
    return resp


# --------------------------------------------------------------------------
# 新闻源 / 新闻推送(内部/超管)
# --------------------------------------------------------------------------

def _serialize_source(s: NewsSource) -> dict:
    return {"id": s.id, "name": s.name, "kind": s.kind, "value": s.value,
            "keywords": s.keywords, "limit": s.limit, "enabled": s.enabled, "sort": s.sort}


@api_view(["GET", "POST"])
@permission_classes([InternalPermission])
def news_sources(request):
    if request.method == "GET":
        rows = NewsSource.objects.order_by("sort", "id")
        return SuccessResponse(data=[_serialize_source(s) for s in rows])

    name = str(request.data.get("name") or "").strip()
    kind = str(request.data.get("kind") or "rss").strip()
    value = str(request.data.get("value") or "").strip()
    if not name or not value:
        return ErrorResponse(msg=_("请填写名称与键名/RSS地址"))
    if kind not in ("builtin", "rss"):
        return ErrorResponse(msg=_("类型必须是 builtin 或 rss"))
    if kind == "builtin" and value not in news.BUILTIN_KEYS:
        return ErrorResponse(msg=_("未知内置源"))
    if kind == "rss" and not value.startswith("http"):
        return ErrorResponse(msg=_("RSS 地址必须以 http 开头"))
    obj = NewsSource.objects.create(
        name=name, kind=kind, value=value,
        keywords=str(request.data.get("keywords") or ""),
        limit=int(request.data.get("limit") or 10),
        enabled=bool(request.data.get("enabled", True)),
        sort=int(request.data.get("sort") or 1),
    )
    return SuccessResponse(data=_serialize_source(obj), msg=_("已添加"))


@api_view(["PUT", "DELETE"])
@permission_classes([InternalPermission])
def news_source_detail(request, pk: int):
    obj = NewsSource.objects.filter(id=pk).first()
    if obj is None:
        return ErrorResponse(msg=_("新闻源不存在"))
    if request.method == "DELETE":
        obj.delete()
        return SuccessResponse(msg=_("已删除"))
    for field in ("name", "kind", "value", "keywords"):
        if field in request.data:
            setattr(obj, field, str(request.data.get(field) or "").strip())
    if "limit" in request.data:
        obj.limit = int(request.data.get("limit") or 10)
    if "sort" in request.data:
        obj.sort = int(request.data.get("sort") or 1)
    if "enabled" in request.data:
        obj.enabled = bool(request.data.get("enabled"))
    obj.save()
    return SuccessResponse(data=_serialize_source(obj), msg=_("已保存"))


@api_view(["GET"])
@permission_classes([InternalPermission])
def news_preview(request):
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    try:
        sources = NewsSource.objects.filter(enabled=True).order_by("sort", "id")
        items, labels = news.collect(sources)
        if not items:
            return ErrorResponse(msg=_("没有抓到任何新闻（请检查新闻源）"))
        brief = news.synthesize(items, date_str)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[NEWS] preview failed")
        return ErrorResponse(msg=f"生成新闻简报失败: {exc}")
    return SuccessResponse(data={
        "date": date_str,
        "title": brief["title"],
        "summary": brief["summary"],
        "source_count": len(list(dict.fromkeys(labels))),
        "item_count": len(items),
        "sources": list(dict.fromkeys(labels)),
    })


@api_view(["GET", "POST"])
@permission_classes([InternalPermission])
def news_broadcasts(request):
    if request.method == "GET":
        qs = FundBroadcast.objects.filter(kind="news").order_by("-id")[:50]
        return SuccessResponse(data=[_serialize_broadcast(b) for b in qs])
    b = FundBroadcast.objects.create(user=request.user, kind="news",
                                     edition=str(request.data.get("edition") or "manual"),
                                     weekday=datetime.now().weekday(), status="queued")
    broadcast_news.apply_async(args=[b.id], queue="news")
    logger.info("[NEWS] broadcast %s queued by %s", b.id, request.user.username)
    return SuccessResponse(data={"id": b.id}, msg=_("已提交，正在生成并推送到全部渠道飞书群"))


@api_view(["GET"])
@permission_classes([InternalPermission])
def news_broadcast_detail(request, pk: int):
    b = FundBroadcast.objects.filter(id=pk, kind="news").first()
    if b is None:
        return ErrorResponse(msg=_("任务不存在"))
    return SuccessResponse(data=_serialize_broadcast(b))


# --------------------------------------------------------------------------
# AI 提示词(内部/超管可覆盖代码默认值)
# --------------------------------------------------------------------------

@api_view(["GET"])
@permission_classes([InternalPermission])
def prompt_list(request):
    defaults = prompts_store.default_prompts()
    rows = {r.key: r for r in AiPrompt.objects.all()}
    data = []
    for key, (title, hint) in prompts_store.PROMPT_META.items():
        r = rows.get(key)
        custom = bool(r and (r.content or "").strip())
        data.append({
            "key": key, "title": title, "hint": hint,
            "content": (r.content if custom else defaults.get(key, "")),
            "is_custom": custom,
        })
    return SuccessResponse(data=data)


@api_view(["PUT", "POST"])
@permission_classes([InternalPermission])
def prompt_update(request, key: str):
    if key not in prompts_store.PROMPT_META:
        return ErrorResponse(msg=_("未知提示词"))
    content = str(request.data.get("content") or "")
    AiPrompt.objects.update_or_create(
        key=key, defaults={"title": prompts_store.PROMPT_META[key][0], "content": content})
    logger.info("[PROMPT] %s updated by %s", key, request.user.username)
    return SuccessResponse(msg=_("已保存"))


@api_view(["POST"])
@permission_classes([InternalPermission])
def prompt_reset(request, key: str):
    if key not in prompts_store.PROMPT_META:
        return ErrorResponse(msg=_("未知提示词"))
    AiPrompt.objects.filter(key=key).delete()
    logger.info("[PROMPT] %s reset by %s", key, request.user.username)
    return SuccessResponse(msg=_("已恢复默认"))
