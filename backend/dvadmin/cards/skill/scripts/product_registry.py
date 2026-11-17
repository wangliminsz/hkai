#!/usr/bin/env python3
"""product_registry.py — 产品注册表：发现/读取 products/<id> 下的 parser.json
与 template.json，并提供基于 parser.json signature 的产品检测。

后端 /detect 与 /upload 用同一个注册表，保证「前端识别到的产品」与
「pipeline 实际走的模板」永远一致 —— 这是解耦的关键一环：
新增一个产品 = 在 products/ 下放一个目录，零代码改动。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parents[1]
PRODUCTS_DIR = SKILL_ROOT / "products"


class ProductNotFound(KeyError):
    pass


def list_products() -> list[str]:
    """返回所有已注册的产品 id（按目录名）。"""
    if not PRODUCTS_DIR.exists():
        return []
    return sorted(p.name for p in PRODUCTS_DIR.iterdir() if p.is_dir() and (p / "parser.json").exists())


def _load(folder: str, fname: str) -> dict:
    p = PRODUCTS_DIR / folder / fname
    if not p.exists():
        raise ProductNotFound(f"{folder}/{fname} not found")
    return json.loads(p.read_text(encoding="utf-8"))


def load_parser(product: str) -> dict:
    return _load(product, "parser.json")


def load_template(product: str) -> dict:
    return _load(product, "template.json")


def parser_path(product: str) -> Path:
    return PRODUCTS_DIR / product / "parser.json"


def template_path(product: str) -> Path:
    return PRODUCTS_DIR / product / "template.json"


def detect_product(first_page_text: str) -> tuple[str, str]:
    """根据首页文本返回 (product, plan_name)。

    遍历所有注册产品的 parser.json signature.keywords：任一关键字命中即返回。
    命中多个时按目录名序取第一个（优先级可在将来扩展为 ordered）。
    """
    for product in list_products():
        cfg = load_parser(product)
        keywords = cfg.get("signature", {}).get("keywords", [])
        if any(k in first_page_text for k in keywords):
            plan_name = _extract_plan_name(first_page_text, keywords)
            return product, plan_name
    return "unknown", ""


def _extract_plan_name(first_page_text: str, keywords: list[str]) -> str:
    for line in first_page_text.splitlines():
        line = line.strip()
        if any(k in line for k in keywords):
            return line
    return ""


def detect_variant(first_page_text: str, product: str) -> str:
    cfg = load_parser(product)
    rules = cfg.get("variant", {}).get("rules", [])
    for rule in rules:
        if any(k in first_page_text for k in rule.get("keywords", [])):
            return rule["key"]
    return ""


def card_structures_for(product: str, style: str = "llm") -> list[dict]:
    """由 template.json 生成 /detect 返回的卡片结构（idx/name/hint/is_text_card）。

    这是把 proposals.py 里硬编码的 CARD_STRUCTURES 替换为数据驱动的核心：
    卡片顺序 = 该风格下实际会渲染的卡顺序（idx 从 0 重编号），保证与
    builder 输出的 cards.json 顺序一致 —— 前端填的 overrides idx 才能对上。

    ``style`` 决定筛选：模板卡的 ``styles`` 字段 + ``omit_when``（产品）。
    """
    tpl = load_template(product)
    cards: list[dict] = []
    for i, card in enumerate(tpl.get("cards", [])):
        # 产品排除
        if product in (card.get("omit_when") or []):
            continue
        # 风格筛选（styles 字段缺省 = 全部风格）
        style_filter = card.get("styles")
        if style_filter and style not in style_filter:
            continue
        role = card.get("role", "card")
        overridable = card.get("overridable") or []
        # 纯文字卡（body 可整体覆盖）—— 由 llm 或 role 决定
        is_text = role in ("letter", "essay") or "body" in overridable
        has_items = any(k in overridable for k in ("items", "reasons", "examples"))
        hint = _role_hint(role)
        entry: dict[str, Any] = {"idx": i, "name": _role_name(role), "hint": hint, "is_text_card": is_text}
        if has_items:
            entry["has_items"] = True
            entry["item_count"] = _item_count(card)
        entry["overridable"] = overridable
        entry["role"] = role
        cards.append(entry)
    # idx 从 0 重编号（对齐该风格下的生成顺序）
    for new_idx, c in enumerate(cards):
        c["idx"] = new_idx
    return cards


_ROLE_NAMES = {
    "hero": "封面", "summary": "摘要", "numbers": "4 数字", "coverage": "保障重点",
    "multi": "多次赔付", "chart": "现金价值图", "irr": "收益率", "reasons": "4 个理由",
    "letter": "致受保人信", "essay": "人生阶段", "company": "公司实力", "note": "自定义卡",
}

_ROLE_HINTS = {
    "hero": "产品名 · 副标 (整段文案, 自动换行)",
    "summary": "受保人 / 保额 / 保费摘要",
    "numbers": "随年龄增长的现金价值演示副标",
    "coverage": "主要保障项副标",
    "multi": "多次赔付示例副标",
    "chart": "5 节点条形图 + 数字摘要",
    "irr": "IRR 演示 + 满期现金价值副标",
    "reasons": "差异化卖点副标 (或展开后逐条覆盖 01-04)",
    "letter": "完全替换正文 (整封信, 200-400字)",
    "essay": "完全替换正文 (200-400字)",
    "company": "品牌背书副标",
    "note": "自定义纯文字卡",
}


def _role_name(role: str) -> str:
    return _ROLE_NAMES.get(role, role)


def _role_hint(role: str) -> str:
    return _ROLE_HINTS.get(role, "可覆盖字段: subtitle")


def _item_count(card: dict) -> int:
    bd = card.get("bound_data") or {}
    for k in ("reasons", "examples", "items"):
        v = bd.get(k)
        if isinstance(v, list):
            return len(v)
    return 0