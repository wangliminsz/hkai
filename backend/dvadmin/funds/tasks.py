from __future__ import annotations

import logging
import time
from datetime import datetime

from celery import shared_task
from django.conf import settings

from . import news, pb, schedule
from .models import ChannelFeishuGroup, FundBroadcast, NewsSource

logger = logging.getLogger(__name__)


@shared_task(name="dvadmin.funds.broadcast")
def broadcast_funds(broadcast_id: int):
    b = FundBroadcast.objects.filter(id=broadcast_id).first()
    if b is None:
        return None
    FundBroadcast.objects.filter(id=broadcast_id).update(status="running")
    try:
        token = pb.admin_token()
        now = datetime.now()
        weekday = b.weekday if b.weekday is not None else now.weekday()
        funds = schedule.collect_day_funds(token, weekday, now)
        lot = funds[0]["lot"] if funds else ""
        text = schedule.build_message_from_funds(lot, weekday, funds, now)
        card = schedule.build_fund_card(lot, weekday, funds, now)

        groups = list(ChannelFeishuGroup.objects.filter(enabled=True).select_related("tenant"))
        logs: list[str] = []
        ok = fail = 0
        for g in groups:
            try:
                schedule.send_card(g.webhook_url, card)
                ok += 1
            except Exception as exc:  # noqa: BLE001
                fail += 1
                logs.append(f"[FAIL] {g.tenant.name if g.tenant_id else '-'} / {g.name}: {exc}")
            time.sleep(0.35)  # 飞书 webhook 限流

        FundBroadcast.objects.filter(id=broadcast_id).update(
            status="succeeded", weekday=weekday, lot=lot, content=text,
            total_groups=len(groups), ok_count=ok, fail_count=fail, logs="\n".join(logs),
        )
        logger.info("[FUNDS] summary card broadcast %s: %s/%s ok", broadcast_id, ok, len(groups))
    except Exception as exc:  # noqa: BLE001
        FundBroadcast.objects.filter(id=broadcast_id).update(
            status="failed", logs=f"{type(exc).__name__}: {exc}")
        logger.exception("[FUNDS] broadcast %s failed", broadcast_id)
    return None


@shared_task(name="dvadmin.funds.broadcast_news")
def broadcast_news(broadcast_id: int):
    b = FundBroadcast.objects.filter(id=broadcast_id).first()
    if b is None:
        return None
    FundBroadcast.objects.filter(id=broadcast_id).update(status="running")
    try:
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        now_label = now.strftime("%Y-%m-%d %H:%M")

        sources = NewsSource.objects.filter(enabled=True).order_by("sort", "id")
        items, labels = news.collect(sources)
        if not items:
            raise RuntimeError("没有抓到任何新闻（请检查新闻源）")
        brief = news.synthesize(items, date_str)
        brief_log = f"[BRIEF] {brief['brief_error']}" if brief.get("brief_error") else ""
        sources_label = " / ".join(dict.fromkeys(labels)) or "-"
        edition = b.edition or "manual"
        brief_url = report_url = None
        try:
            brief_html = news.render_brief_html(brief, sources_label, date_str, edition, now_label)
            report_html = news.render_report_html(brief, items, sources_label, date_str, edition, now_label)
            brief_url, report_url = news.publish_html(brief_html, report_html, date_str, edition)
            logger.info("[NEWS] html links: %s | %s", brief_url, report_url)
        except Exception as exc:  # noqa: BLE001 - card still goes out without buttons
            logger.warning("[NEWS] HTML publish failed: %s", exc)
        card = news.build_card(brief["title"], brief["summary"], sources_label, date_str, now_label,
                               brief_url=brief_url, report_url=report_url)

        groups = list(ChannelFeishuGroup.objects.filter(enabled=True).select_related("tenant"))
        logs: list[str] = [brief_log] if brief_log else []
        ok = fail = 0
        for g in groups:
            try:
                news.send_card(g.webhook_url, card)
                ok += 1
            except Exception as exc:  # noqa: BLE001
                fail += 1
                logs.append(f"[FAIL] {g.tenant.name if g.tenant_id else '-'} / {g.name}: {exc}")
            time.sleep(0.35)

        FundBroadcast.objects.filter(id=broadcast_id).update(
            status="succeeded", kind="news", title=brief["title"], content=brief["summary"],
            total_groups=len(groups), ok_count=ok, fail_count=fail, logs="\n".join(logs),
        )
        logger.info("[NEWS] broadcast %s: %s/%s ok", broadcast_id, ok, len(groups))
    except Exception as exc:  # noqa: BLE001
        FundBroadcast.objects.filter(id=broadcast_id).update(
            status="failed", kind="news", logs=f"{type(exc).__name__}: {exc}")
        logger.exception("[NEWS] broadcast %s failed", broadcast_id)
    return None


@shared_task(name="dvadmin.funds.analyze_funds")
def broadcast_fund_analysis(broadcast_id: int):
    """单基金深度分析: QVeris 分析 -> HTML 报告 -> 每只基金一张卡片。

    每只基金之间间隔 `FUND_ANALYSIS_INTERVAL` 秒(默认 20)以避免 QVeris 429。
    单只基金失败只记录到 logs，不影响其它基金。
    """
    from . import analysis, holdings

    b = FundBroadcast.objects.filter(id=broadcast_id).first()
    if b is None:
        return None
    FundBroadcast.objects.filter(id=broadcast_id).update(status="running", kind="analysis")
    try:
        token = pb.admin_token()
        now = datetime.now()
        weekday = b.weekday if b.weekday is not None else now.weekday()
        funds = schedule.collect_day_funds(token, weekday, now)
        lot = funds[0]["lot"] if funds else ""
        groups = list(ChannelFeishuGroup.objects.filter(enabled=True).select_related("tenant"))
        interval = float(getattr(settings, "FUND_ANALYSIS_INTERVAL", 20) or 20)

        logs: list[str] = []
        analyses: list[str] = []
        ok = fail = 0
        for i, fund in enumerate(funds, 1):
            if i > 1:
                time.sleep(interval)
            name = fund.get("productName", "?")
            logger.info("[ANALYSIS] %s/%s %s", i, len(funds), name)
            try:
                pdf = holdings.fetch_pdf(fund["fund_sheet"]) if fund.get("fund_sheet") else b""
                hs = holdings.extract_top_holdings(pdf) if pdf else []
                text = analysis.qveris_analyze(fund, hs)
                html = analysis.render_report_html(lot, fund.get("desc") or fund.get("title") or "", fund, text)
                url = analysis.publish_report(lot, fund, html)
                card = analysis.build_analysis_card(fund, url)
                for g in groups:
                    try:
                        schedule.send_card(g.webhook_url, card)
                        ok += 1
                    except Exception as exc:  # noqa: BLE001
                        fail += 1
                        logs.append(f"[FAIL] {name} -> {g.tenant_id}/{g.name}: {exc}")
                    time.sleep(0.35)
                analyses.append(f"## {name}（{fund.get('title', '')} 第{fund.get('rank', '')}名）\n{text}")
            except Exception as exc:  # noqa: BLE001
                fail += 1
                logs.append(f"[FAIL] {name}: {type(exc).__name__}: {exc}")
                logger.exception("[ANALYSIS] %s failed", name)

        FundBroadcast.objects.filter(id=broadcast_id).update(
            status="succeeded", kind="analysis", lot=lot,
            title=f"{lot} 深度分析", content="\n\n".join(analyses)[:100000],
            total_groups=len(groups), ok_count=ok, fail_count=fail, logs="\n".join(logs),
        )
        logger.info("[ANALYSIS] job %s: %s funds, %s/%s sends ok", broadcast_id, len(funds), ok, len(groups) * len(funds))
    except Exception as exc:  # noqa: BLE001
        FundBroadcast.objects.filter(id=broadcast_id).update(
            status="failed", kind="analysis", logs=f"{type(exc).__name__}: {exc}")
        logger.exception("[ANALYSIS] job %s failed", broadcast_id)
    return None
