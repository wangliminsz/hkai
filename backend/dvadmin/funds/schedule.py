"""Daily fund schedule + message formatting (ported from refer-04 daily_feishu.py)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import requests
from django.conf import settings

from . import pb


@dataclass
class ScheduleEntry:
    collection: str
    sector: str
    target: str
    is_best: bool | None
    rank_from: int
    rank_to: int
    title: str
    desc: str


PERIOD_ROTATION = [
    ("W4", "近1个月"),
    ("W52", "近1年"),
    ("W162", "近3年"),
    ("YTD_CUM", "年初以来"),
]

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
ORDINALS = [
    "第一名", "第二名", "第三名", "第四名", "第五名",
    "第六名", "第七名", "第八名", "第九名", "第十名",
]


def theme_period(now: datetime | None = None) -> tuple[str, str]:
    week = (now or datetime.now()).isocalendar().week
    return PERIOD_ROTATION[week % len(PERIOD_ROTATION)]


# 2026-10-18 调整（缓解信息过载）:
#   周一/周二 = 本周销售量 Top（1-5 / 6-10）
#   周三/周四/周五 = 年初以来(YTD_CUM) 最佳 + 最差（1-3 / 4-7 / 8-10）
#   周六/周日 = 不推送
def build_schedule(weekday: int, now: datetime | None = None) -> list[ScheduleEntry]:
    if weekday == 0:
        return [ScheduleEntry("fund_snapshots_volume", "VOL", "1week", None, 1, 5, "本周销售量最大股票基金", "本周销售量 Top 1-5")]
    if weekday == 1:
        return [ScheduleEntry("fund_snapshots_volume", "VOL", "1week", None, 6, 10, "本周销售量最大股票基金", "本周销售量 Top 6-10")]
    if weekday == 2:
        return [
            ScheduleEntry("fund_snapshots", "EG", "YTD_CUM", True, 1, 3, "年初以来最佳前三", "年初以来最佳 Top 1-3"),
            ScheduleEntry("fund_snapshots", "EG", "YTD_CUM", False, 1, 3, "年初以来最差前三", "年初以来最差 Top 1-3"),
        ]
    if weekday == 3:
        return [
            ScheduleEntry("fund_snapshots", "EG", "YTD_CUM", True, 4, 7, "年初以来最佳 4-7", "年初以来最佳 Top 4-7"),
            ScheduleEntry("fund_snapshots", "EG", "YTD_CUM", False, 4, 7, "年初以来最差 4-7", "年初以来最差 Top 4-7"),
        ]
    if weekday == 4:
        return [
            ScheduleEntry("fund_snapshots", "EG", "YTD_CUM", True, 8, 10, "年初以来最佳 8-10", "年初以来最佳 Top 8-10"),
            ScheduleEntry("fund_snapshots", "EG", "YTD_CUM", False, 8, 10, "年初以来最差 8-10", "年初以来最差 Top 8-10"),
        ]
    return []


def weekday_desc(weekday: int, now: datetime | None = None) -> str:
    return {
        0: "本周销售量 Top 1-5",
        1: "本周销售量 Top 6-10",
        2: "年初以来最佳/最差 Top 1-3",
        3: "年初以来最佳/最差 Top 4-7",
        4: "年初以来最佳/最差 Top 8-10",
        5: "周末不推送",
        6: "周末不推送",
    }[weekday]


def latest_lot_number(token: str, collection: str) -> str:
    data = pb.get_records(collection, token, perPage=1, sort="-lotNumber", fields="lotNumber")
    items = data.get("items") or []
    return items[0]["lotNumber"] if items else "?"


def fetch_funds(token: str, lot: str, entry: ScheduleEntry) -> list[dict]:
    filt = (
        f'lotNumber="{lot}" && sectorCode="{entry.sector}" '
        f'&& targetPeriod="{entry.target}"'
    )
    if entry.is_best is not None:
        filt += f" && isBest={str(entry.is_best).lower()}"
    filt += f" && rank>={entry.rank_from} && rank<={entry.rank_to}"
    data = pb.get_records(
        entry.collection, token, filter=filt, sort="rank",
        perPage=entry.rank_to - entry.rank_from + 1,
        fields="rank,productName,returnValue,fund_sheet,targetPeriod,sectorCode,isBest,priceDateStr",
    )
    return data.get("items") or []


def collect_day_funds(token: str, weekday: int, now: datetime | None = None) -> list[dict]:
    out: list[dict] = []
    for entry in build_schedule(weekday, now):
        lot = latest_lot_number(token, entry.collection)
        try:
            for fund in fetch_funds(token, lot, entry):
                out.append({**fund, "lot": lot, "title": entry.title, "desc": entry.desc})
        except Exception:  # noqa: BLE001
            pass
    return out


def fmt_fund_block(fund: dict) -> str:
    pos = int(fund["rank"]) - 1
    return (
        f"{fund['title']}，{ORDINALS[pos]}\n"
        f"{fund['productName']}\n"
        f"回报率 {fund['returnValue']}%"
    )


def build_message_from_funds(lot: str, weekday: int, funds: list[dict], now: datetime | None = None) -> str:
    blocks: list[str] = [lot, f"{WEEKDAY_NAMES[weekday]}  {weekday_desc(weekday, now)}"]
    for fund in funds:
        blocks.append("~~~~~~~~~")
        blocks.append("")
        blocks.append(fmt_fund_block(fund))
        blocks.append("")
    return "\n".join(blocks).rstrip("\n")


def send_message(webhook: str, text: str) -> None:
    r = requests.post(webhook, json={"msg_type": "text", "content": {"text": text}}, timeout=15)
    r.raise_for_status()
    if r.json().get("StatusCode", -1) != 0:
        raise RuntimeError(f"Feishu webhook error: {r.json()}")


def build_fund_card(lot: str, weekday: int, funds: list[dict], now: datetime | None = None) -> dict:
    """带表头的飞书卡片(替代原来的纯文本 ~~~~~~~~~ 分隔)。"""
    header = f"【今日基金榜单 · {lot}】{WEEKDAY_NAMES[weekday]} {weekday_desc(weekday, now)}"[:148]
    elements: list[dict] = []
    if not funds:
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "今日暂无数据"}})
    for i, fund in enumerate(funds):
        pos = int(fund["rank"]) - 1
        content = (
            f"**{fund['title']}，{ORDINALS[pos]}**\n"
            f"{fund['productName']}\n"
            f"回报率 {fund['returnValue']}%"
        )
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": content}})
        if i < len(funds) - 1:
            elements.append({"tag": "hr"})
    elements.append({"tag": "note", "elements": [
        {"tag": "plain_text", "content": f"更多基金信息请访问 {app_homepage()}"}
    ]})
    return {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"tag": "plain_text", "content": header}, "template": "turquoise"},
        "elements": elements,
    }


def send_card(webhook: str, card: dict) -> None:
    r = requests.post(webhook, json={"msg_type": "interactive", "card": card}, timeout=15)
    r.raise_for_status()
    if r.json().get("StatusCode", -1) != 0:
        raise RuntimeError(f"Feishu webhook error: {r.json()}")


def app_homepage() -> str:
    return getattr(settings, "HKFUND_APP_HOMEPAGE", "https://hkfund.favor100.site")
