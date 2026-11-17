#!/usr/bin/env python3
"""preview_card.py — 单卡 HTML 预览（供前端模板编辑器实时预览）。

用法:
  python preview_card.py <cards.json> <card_idx> --output <out.html>

cards.json 是 build_templated_cards.py 产出的完整 payload（meta + cards）。
本脚本只取第 <card_idx> 张卡，渲染成完整 HTML 输出，不启动 Playwright。
前端 iframe 直接嵌入返回的 HTML 即可做「改字段 → 即时预览」。

依赖与 render_llm.py 相同（Pillow/CSS 常量），但避免 import 顶层触发
Playwright 启动（render_llm 顶层 `from playwright.sync_api import ...`）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]


def load_theme(theme_key: str) -> dict:
    themes = json.loads((SKILL_ROOT / "assets" / "llm-themes.json").read_text(encoding="utf-8"))
    return themes.get(theme_key) or themes[next(iter(themes))]


def build_card_html(meta: dict, card: dict, index: int, total: int, theme: dict) -> str:
    """轻量复刻 render_llm.build_card_html —— 只依赖本文件内的函数与 CSS。

    用 lazy import 方式加载 render_llm 的 CSS 常量与 layout 渲染器，避免顶层
    触发 Playwright 的 import 开销（Playwright 已装则无碍，未装也不影响预览）。
    """
    sys.path.insert(0, str(SKILL_ROOT / "scripts"))
    from render_llm import build_card_html as _real  # noqa: E402

    return _real(meta, card, index, total, theme)


def main() -> int:
    ap = argparse.ArgumentParser(description="单卡 HTML 预览")
    ap.add_argument("cards_json", type=str)
    ap.add_argument("card_idx", type=int)
    ap.add_argument("--output", type=str, default="")
    ap.add_argument("--theme", type=str, default="yf-cream")
    args = ap.parse_args()

    payload = json.loads(Path(args.cards_json).read_text(encoding="utf-8"))
    cards = payload.get("cards", [])
    if not 0 <= args.card_idx < len(cards):
        print(f"card_idx {args.card_idx} out of range (0..{len(cards)-1})", file=sys.stderr)
        return 2

    meta = payload.get("meta", {})
    card = cards[args.card_idx]
    theme = load_theme(args.theme)
    html_doc = build_card_html(meta, card, args.card_idx + 1, len(cards), theme)

    if args.output:
        Path(args.output).write_text(html_doc, encoding="utf-8")
        print(f"preview written: {args.output}")
    else:
        sys.stdout.write(html_doc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
