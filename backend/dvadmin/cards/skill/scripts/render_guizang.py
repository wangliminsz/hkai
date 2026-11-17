#!/usr/bin/env python3
"""render_guizang.py — Guizang 杂志风 cards.json -> PNG 卡片 + 接触印样

用 Playwright 把每张卡片渲染成 1080×1440 的 HTML/CSS 杂志页，再截图为 PNG。
风格来自 referral/guizang-social-card-skill 的 Editorial Magazine × E-ink 模板：
  - 纸本底色 + 墨色正文 + 克制的衬线/无衬线对比
  - 顶部 issue-row、底部 issue-strip、kicker 小标签
  - ledger 账册行、pipeline 编号列表、editorial 表格、pullquote 引文

本地字体（C:\\Windows\\Fonts 已装）：Noto Serif SC / Noto Sans SC，与模板字体栈
完全一致，故无需联网加载 Google Fonts。WebGL 纸纹背景对批量渲染过重，改用
纯 CSS 的 .grain + .paper-wash 叠层，视觉接近且零依赖。

支持的 layout: cover / summary / table / list / article / ci-list / image
卡片数量不限——只要 cards.json 里列出的卡都会渲染。
"""
from __future__ import annotations

import argparse
import base64
import html
import json
import math
import sys
from pathlib import Path
from typing import Any

try:
    from playwright.sync_api import sync_playwright
except ImportError as exc:
    raise SystemExit("playwright is required. Install: python -m pip install playwright && python -m playwright install chromium") from exc


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_THEMES = SKILL_ROOT / "assets" / "guizang-themes.json"
POSTER_W = 1080
POSTER_H = 1440


# ── HTML 转义 ──────────────────────────────────────────────────────────────


def esc(text: Any) -> str:
    return html.escape(str(text), quote=True)


# ── 主题 CSS 变量 ──────────────────────────────────────────────────────────


def theme_css(theme: dict[str, Any]) -> str:
    """把主题 JSON 注入为 :root CSS 变量。归藏主题键名与模板完全一致。"""
    lines = [":root {"]
    for key in ("paper", "paper-2", "ink", "muted", "line", "accent", "accent-soft",
                "ink-rgb", "paper-rgb", "accent-rgb"):
        val = theme.get(key, "")
        if val:
            lines.append(f"  --{key}: {val};")
    lines.append("}")
    return "\n".join(lines)


# ── 基础 CSS（来自 template-editorial-card.html，裁剪到本渲染器所需）─────


BASE_CSS = """
*,*::before,*::after { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  background: #1a1a1a;
  font-family: var(--sans-zh);
  color: var(--ink);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

:root {
  --serif-zh: "Noto Serif SC", "Noto Serif CJK SC", "STSong", "SimSun", serif;
  --serif-en: "Noto Serif SC", "Noto Serif CJK SC", "Times New Roman", serif;
  --sans-zh:  "Noto Sans SC", "Noto Sans CJK SC", "Microsoft YaHei UI", sans-serif;
  --sans-en:  "Noto Sans SC", "Noto Sans CJK SC", "Arial", sans-serif;
  --mono:     "IBM Plex Mono", ui-monospace, "Consolas", "Courier New", monospace;
}

.poster {
  position: relative;
  width: 1080px;
  height: 1440px;
  background: var(--paper);
  color: var(--ink);
  overflow: hidden;
  isolation: isolate;
  font-family: var(--sans-zh);
}

/* 背景叠层：纸纹颗粒 + 纸洗渐变（替代 WebGL，纯 CSS 零依赖）*/
.grain {
  position: absolute; inset: 0; z-index: 1; pointer-events: none;
  opacity: .35; mix-blend-mode: multiply;
  background-image: radial-gradient(rgba(0,0,0,.045) 1px, transparent 1px);
  background-size: 3px 3px;
}
.paper-wash {
  position: absolute; inset: 0; z-index: 1; pointer-events: none;
  background: linear-gradient(180deg, rgba(var(--ink-rgb),.02),
              rgba(var(--ink-rgb),.05) 60%, rgba(var(--ink-rgb),.08));
}

.content {
  position: relative; z-index: 2;
  width: 100%; height: 100%;
  padding: 96px 88px 88px;
  display: flex; flex-direction: column;
}

/* —— 排版角色 —— */
.kicker {
  font-family: var(--mono); font-size: 21px; letter-spacing: .22em;
  text-transform: uppercase; color: rgba(var(--ink-rgb), .55);
  margin: 0 0 18px;
}
.h-display { font-family: var(--serif-zh); font-weight: 500; font-size: 92px;
  line-height: 1.06; letter-spacing: .03em; margin: 0 0 20px; color: var(--ink); }
.h-xl { font-family: var(--serif-zh); font-weight: 500; font-size: 72px;
  line-height: 1.10; letter-spacing: .03em; margin: 0 0 20px; color: var(--ink); }
.h-md { font-family: var(--serif-zh); font-weight: 500; font-size: 52px;
  line-height: 1.18; letter-spacing: .02em; margin: 0 0 16px; color: var(--ink); }
.h-sub { font-family: var(--serif-en); font-style: italic; font-weight: 400;
  font-size: 32px; color: var(--muted); margin: 0 0 24px; line-height: 1.35; }
.lead { font-family: var(--serif-zh); font-weight: 400; font-size: 28px;
  line-height: 1.55; color: rgba(var(--ink-rgb), .82); margin: 0 0 24px; }
.body { font-family: var(--serif-zh); font-weight: 400; font-size: 25px;
  line-height: 1.75; color: rgba(var(--ink-rgb), .80); margin: 0 0 18px;
  white-space: pre-wrap; word-break: break-word; }
.meta, .label { font-family: var(--mono); font-size: 18px; letter-spacing: .20em;
  text-transform: uppercase; color: rgba(var(--ink-rgb), .55); }
.pullquote { font-family: var(--serif-zh); font-style: italic; font-weight: 500;
  font-size: 44px; line-height: 1.30; color: var(--ink); margin: 0; }

/* —— 顶部 issue 行 + 底部 issue-strip —— */
.issue-row {
  display: flex; align-items: center; gap: 16px;
  font-family: var(--mono); font-size: 20px; letter-spacing: .12em;
  text-transform: uppercase; color: var(--muted); margin-bottom: 28px;
}
.issue-row .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); }
.issue-strip {
  position: absolute; left: 88px; right: 88px; bottom: 56px; z-index: 3;
  display: flex; justify-content: space-between; align-items: center; gap: 32px;
  font-family: var(--mono); font-size: 18px; letter-spacing: .12em;
  text-transform: uppercase; color: var(--muted);
  border-top: 1px solid var(--line); padding-top: 18px;
}
.issue-strip span { white-space: nowrap; }

/* 标题装饰线 */
.rule-accent { height: 2px; background: var(--accent); border: 0;
  margin: 18px 0 28px; width: 96px; }
.rule { height: 1px; background: var(--line); border: 0; margin: 24px 0; }

/* —— 布局原语 —— */
.stack { display: flex; flex-direction: column; }
.gap-1 { gap: 12px; } .gap-2 { gap: 24px; } .gap-3 { gap: 36px; }
.gap-4 { gap: 48px; } .gap-5 { gap: 64px; }
.grow { flex: 1; }

/* 封面统计卡 */
.cover-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px; }
.cover-stats .stat {
  padding: 28px 24px; background: var(--paper-2);
  border-left: 3px solid var(--accent);
}
.cover-stats .stat-label { font-family: var(--mono); font-size: 18px;
  letter-spacing: .14em; text-transform: uppercase; color: var(--muted);
  margin-bottom: 10px; }
.cover-stats .stat-value { font-family: var(--serif-zh); font-weight: 500;
  font-size: 44px; letter-spacing: .02em; color: var(--ink); line-height: 1.1; }

/* 摘要 ledger 行 */
.ledger { display: flex; flex-direction: column; }
.ledger-row {
  display: grid; grid-template-columns: 200px 1fr auto; gap: 24px;
  align-items: baseline; padding: 22px 0;
  border-bottom: 1px solid var(--line);
}
.ledger-row:last-child { border-bottom: 0; }
.ledger-row .ledger-label {
  font-family: var(--mono); font-size: 17px; letter-spacing: .14em;
  text-transform: uppercase; color: var(--muted);
}
.ledger-row .ledger-value { font-family: var(--serif-zh); font-weight: 500;
  font-size: 30px; letter-spacing: .02em; color: var(--ink); text-align: right; }

/* editorial 表格 */
.ed-table { width: 100%; border-collapse: collapse;
  font-family: var(--sans-zh); }
.ed-table thead th {
  font-family: var(--mono); font-size: 18px; letter-spacing: .08em;
  text-transform: uppercase; color: var(--muted); font-weight: 500;
  text-align: right; padding: 18px 14px;
  border-bottom: 2px solid var(--ink);
  white-space: pre-line;
}
.ed-table thead th:first-child { text-align: left; }
.ed-table tbody td {
  font-family: var(--sans-zh); font-size: 24px; color: var(--ink);
  padding: 16px 14px; text-align: right;
  border-bottom: 1px solid var(--line);
}
.ed-table tbody td:first-child { text-align: left; font-family: var(--mono);
  font-size: 20px; color: var(--muted); letter-spacing: .04em; }
.ed-table tbody tr:nth-child(even) { background: rgba(var(--ink-rgb), .025); }
.table-note { font-family: var(--serif-zh); font-size: 21px; line-height: 1.55;
  color: var(--muted); margin-top: 22px; }

/* pipeline 编号列表 */
.pipeline-v { display: flex; flex-direction: column; gap: 22px; }
.pipeline-v .step {
  display: grid; grid-template-columns: 72px 1fr; gap: 24px;
  align-items: baseline; padding-bottom: 20px;
  border-bottom: 1px solid var(--line);
}
.pipeline-v .step:last-child { border-bottom: 0; padding-bottom: 0; }
.pipeline-v .step-nb { font-family: var(--mono); font-size: 30px;
  color: var(--accent); letter-spacing: .04em; }
.pipeline-v .step-desc { font-family: var(--serif-zh); font-weight: 400;
  font-size: 23px; line-height: 1.6; color: rgba(var(--ink-rgb), .80); margin: 0; }

/* callout 引文块 */
.callout {
  border-left: 3px solid var(--accent); padding: 22px 30px;
  font-family: var(--serif-zh); font-style: italic; font-size: 34px;
  line-height: 1.35; color: var(--ink); background: var(--paper-2);
  margin: 0;
}

/* CI 疾病清单 */
.ci-groups { display: flex; flex-direction: column; gap: 26px; }
.ci-group { }
.ci-group-head {
  display: flex; justify-content: space-between; align-items: baseline;
  gap: 16px; padding-bottom: 10px; border-bottom: 1px solid var(--line);
  margin-bottom: 14px;
}
.ci-group-tier { font-family: var(--serif-zh); font-weight: 500; font-size: 30px;
  color: var(--ink); letter-spacing: .02em; }
.ci-group-payout { font-family: var(--mono); font-size: 16px; letter-spacing: .10em;
  text-transform: uppercase; color: var(--accent); text-align: right; }
.ci-items {
  display: grid; grid-template-columns: 1fr 1fr; gap: 6px 28px;
  font-family: var(--serif-zh); font-size: 21px; line-height: 1.7;
  color: rgba(var(--ink-rgb), .80);
}
.ci-items .ci-item::before {
  content: "·"; color: var(--accent); margin-right: 8px; font-weight: 700;
}

/* image layout —— 全图嵌入卡 */
.image-body {
  position: relative; z-index: 2;
  width: 100%; height: 100%;
  padding: 96px 88px 88px;
  display: flex; flex-direction: column;
}
.image-body .image-stage {
  flex: 1; display: flex; align-items: flex-start; justify-content: center;
  margin: 0;
  padding: 4px 0 70px 0;
}
.image-body .image-stage .hero-img {
  max-width: 84%; max-height: 84%; object-fit: contain;
  border: 1px solid var(--line);
  box-shadow: 0 4px 32px rgba(0,0,0,.22);
}
.hero-missing {
  font-family: var(--serif-zh); font-size: 28px; color: var(--muted);
  border: 2px dashed var(--line); padding: 80px 120px;
}

/* 页码角标 */
.corner-tr {
  position: absolute; right: 88px; top: 56px; z-index: 3;
  font-family: var(--mono); font-size: 18px; letter-spacing: .12em;
  text-transform: uppercase; color: var(--muted);
}
"""


# ── 各 layout 的内容生成 ────────────────────────────────────────────────────


def _issue_row(meta: dict, card: dict, index: int, total: int) -> str:
    vol = esc(meta.get("title", ""))
    page = f"{index:02d} / {total:02d}"
    eyebrow = esc(card.get("eyebrow", ""))
    return f"""<div class="issue-row"><span>{vol}</span><span class="dot"></span><span>{page}</span></div>"""


def _issue_strip(meta: dict, card: dict) -> str:
    footer = esc(meta.get("footer", "仅供说明参考，以保单条款为准"))
    kicker = esc(card.get("kicker", ""))
    return f"""<div class="issue-strip"><span>{kicker}</span><span>{footer}</span></div>"""


def _title_block(card: dict, *, display: bool = False) -> str:
    cls = "h-display" if display else "h-xl"
    subtitle = card.get("subtitle", "")
    sub_html = f'<p class="h-sub">{esc(subtitle)}</p>' if subtitle else ""
    return f"""<p class="kicker">{esc(card.get("kicker", ""))}</p>
      <h1 class="{cls}">{esc(card.get("title", ""))}</h1>
      {sub_html}
      <hr class="rule-accent"/>"""


def render_cover(meta: dict, card: dict, index: int, total: int) -> str:
    stats = card.get("stats", [])
    stat_html = ""
    if stats:
        cells = []
        for s in stats:
            cells.append(
                f'<div class="stat"><div class="stat-label">{esc(s.get("label",""))}</div>'
                f'<div class="stat-value">{esc(s.get("value",""))}</div></div>'
            )
        stat_html = f'<div class="cover-stats">{"".join(cells)}</div>'
    return f"""
    <div class="content">
      {_issue_row(meta, card, index, total)}
      <div class="stack gap-3 grow">
        {_title_block(card, display=True)}
        {stat_html}
        <div class="grow"></div>
        <p class="lead" style="font-size:30px;">{esc(card.get("subtitle",""))}</p>
      </div>
    </div>"""


def render_summary(meta: dict, card: dict, index: int, total: int) -> str:
    items = card.get("items", [])
    rows = []
    for label, value in items:
        rows.append(
            f'<div class="ledger-row"><div class="ledger-label">{esc(label)}</div>'
            f'<div></div><div class="ledger-value">{esc(value)}</div></div>'
        )
    return f"""
    <div class="content">
      {_issue_row(meta, card, index, total)}
      <div class="stack gap-2 grow">
        {_title_block(card)}
        <div class="ledger">{"".join(rows)}</div>
      </div>
    </div>"""


def render_table(meta: dict, card: dict, index: int, total: int) -> str:
    columns = [str(c) for c in card.get("columns", [])]
    rows = [[str(v) for v in r] for r in card.get("rows", [])]
    thead = "".join(f"<th>{esc(c)}</th>" for c in columns)
    body_rows = []
    for r in rows:
        cells = "".join(f"<td>{esc(v)}</td>" for v in r)
        body_rows.append(f"<tr>{cells}</tr>")
    note = card.get("note", "")
    note_html = f'<p class="table-note">{esc(note)}</p>' if note else ""
    return f"""
    <div class="content">
      {_issue_row(meta, card, index, total)}
      <div class="stack gap-2 grow">
        {_title_block(card)}
        <table class="ed-table">
          <thead><tr>{thead}</tr></thead>
          <tbody>{"".join(body_rows)}</tbody>
        </table>
        {note_html}
      </div>
    </div>"""


def render_list(meta: dict, card: dict, index: int, total: int) -> str:
    items = [str(i).strip() for i in card.get("items", []) if str(i).strip()]
    steps = []
    for i, item in enumerate(items, start=1):
        steps.append(
            f'<div class="step"><div class="step-nb">{i:02d}</div>'
            f'<p class="step-desc">{esc(item)}</p></div>'
        )
    return f"""
    <div class="content">
      {_issue_row(meta, card, index, total)}
      <div class="stack gap-2 grow">
        {_title_block(card)}
        <div class="pipeline-v">{"".join(steps)}</div>
      </div>
    </div>"""


def render_article(meta: dict, card: dict, index: int, total: int) -> str:
    body = card.get("body", "") or ""
    pullquote = card.get("pullquote", "")
    # body 里保留换行；LLM 文本可能含多段
    body_html = "".join(
        f'<p class="body">{esc(para)}</p>' for para in body.split("\n\n") if para.strip()
    ) or f'<p class="body">{esc(body)}</p>'
    quote_html = f'<blockquote class="callout">{esc(pullquote)}</blockquote>' if pullquote else ""
    return f"""
    <div class="content">
      {_issue_row(meta, card, index, total)}
      <div class="stack gap-3 grow">
        {_title_block(card)}
        {body_html}
        {quote_html}
      </div>
    </div>"""


def render_ci_list(meta: dict, card: dict, index: int, total: int) -> str:
    groups = card.get("groups", [])
    intro = card.get("intro", "")
    intro_html = f'<p class="lead">{esc(intro)}</p>' if intro else ""
    group_html = []
    for g in groups:
        items = "".join(f'<div class="ci-item">{esc(it)}</div>' for it in g.get("items", []))
        group_html.append(
            f'<div class="ci-group"><div class="ci-group-head">'
            f'<div class="ci-group-tier">{esc(g.get("tier",""))}</div>'
            f'<div class="ci-group-payout">{esc(g.get("payout",""))}</div></div>'
            f'<div class="ci-items">{items}</div></div>'
        )
    note = card.get("note", "")
    note_html = f'<p class="table-note">{esc(note)}</p>' if note else ""
    return f"""
    <div class="content">
      {_issue_row(meta, card, index, total)}
      <div class="stack gap-2 grow">
        {_title_block(card)}
        {intro_html}
        <div class="ci-groups">{"".join(group_html)}</div>
        {note_html}
      </div>
    </div>"""


def _load_image_data_uri(filename: str) -> str:
    """从 assets/ 读取图片并转为 base64 data URI，供 <img> 直接内嵌。"""
    p = SKILL_ROOT / "assets" / filename
    if not p.exists():
        return ""
    suffix = p.suffix.lower().lstrip(".")
    mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "gif": "gif", "webp": "webp"}.get(suffix, "jpeg")
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:image/{mime};base64,{b64}"


def render_image(meta: dict, card: dict, index: int, total: int) -> str:
    """全图嵌入卡：使用标准杂志页眉（issue-row + title-block），图片下移居中。"""
    img_uri = _load_image_data_uri(card.get("image", ""))
    img_html = f'<img class="hero-img" src="{img_uri}" alt=""/>' if img_uri else \
        '<div class="hero-missing">图片缺失</div>'
    return f"""
    <div class="card-body image-body">
      {_issue_row(meta, card, index, total)}
      {_title_block(card)}
      <div class="image-stage">
        {img_html}
      </div>
    </div>"""


LAYOUTS = {
    "cover": render_cover,
    "summary": render_summary,
    "table": render_table,
    "list": render_list,
    "article": render_article,
    "ci-list": render_ci_list,
    "image": render_image,
}


def build_card_html(meta: dict, card: dict, index: int, total: int, theme: dict) -> str:
    layout = card.get("layout", "list")
    renderer = LAYOUTS.get(layout, render_list)
    inner = renderer(meta, card, index, total)
    page_no = f"{index:02d} / {total:02d}"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{esc(card.get("title", ""))}</title>
<style>
{theme_css(theme)}
{BASE_CSS}
</style>
</head>
<body>
  <section class="poster" id="card-{index}">
    <div class="grain"></div>
    <div class="paper-wash"></div>
    <div class="corner-tr">{page_no}</div>
    {inner}
    {_issue_strip(meta, card)}
  </section>
</body>
</html>"""


# ── 渲染主流程 ──────────────────────────────────────────────────────────────


def create_contact_sheet(images: list[Path], output: Path) -> None:
    """3 列接触印样，沿用 Pillow（render_cards.py 也用 Pillow，依赖已具备）。"""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return
    if not images:
        return
    cols = 3
    thumb_w = 360
    gap = 24
    label_h = 48
    # Open first image to compute thumbnail height from its aspect ratio.
    first_img = Image.open(images[0]).convert("RGB")
    thumb_h = round(thumb_w * first_img.height / first_img.width)
    rows = math.ceil(len(images) / cols)
    sheet_w = cols * thumb_w + (cols + 1) * gap
    sheet_h = rows * (thumb_h + label_h) + (rows + 1) * gap
    sheet = Image.new("RGB", (sheet_w, sheet_h), (243, 240, 232))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.truetype("C:/Windows/Fonts/NotoSansSC-VF.ttf", 28)
    resampling = getattr(Image, "Resampling", Image).LANCZOS
    for i, p in enumerate(images, start=1):
        img = Image.open(p).convert("RGB")
        r, c = divmod(i - 1, cols)
        x = gap + c * (thumb_w + gap)
        y = gap + r * (thumb_h + label_h + gap)
        thumb = img.resize((thumb_w, thumb_h), resampling)
        sheet.paste(thumb, (x, y))
        draw.text((x, y + thumb_h + 10), f"{i:02d}", font=font, fill=(90, 84, 78))
    sheet.save(output, format="PNG", optimize=True)


def parse_args():
    p = argparse.ArgumentParser(description="Render Guizang editorial cards from JSON.")
    p.add_argument("input", type=Path, help="Path to cards.json")
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--theme-file", type=Path, default=DEFAULT_THEMES)
    p.add_argument("--theme", help="Override meta.theme (e.g. ink-classic).")
    p.add_argument("--no-contact-sheet", action="store_true")
    return p.parse_args()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate(payload: dict) -> tuple[dict, list[dict]]:
    meta = payload.get("meta")
    cards = payload.get("cards")
    if not isinstance(meta, dict) or not isinstance(cards, list) or not cards:
        raise SystemExit("cards.json must contain a meta object and a non-empty cards array")
    seen: set[str] = set()
    for i, c in enumerate(cards, start=1):
        fn = c.get("file")
        if not isinstance(fn, str) or not fn.lower().endswith(".png"):
            raise SystemExit(f"Card {i} requires a .png file name")
        if fn in seen:
            raise SystemExit(f"Duplicate card filename: {fn}")
        seen.add(fn)
        if not str(c.get("title", "")).strip():
            raise SystemExit(f"Card {fn} requires a title")
    return meta, cards


def main() -> None:
    args = parse_args()
    payload = load_json(args.input)
    meta, cards = validate(payload)
    themes = load_json(args.theme_file)
    theme_name = args.theme or meta.get("theme", "ink-classic")
    if theme_name not in themes:
        raise SystemExit(f"Theme '{theme_name}' not found. Available: {', '.join(sorted(themes))}")
    theme = themes[theme_name]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    total = len(cards)
    rendered_paths: list[Path] = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": POSTER_W, "height": POSTER_H},
                                      device_scale_factor=2)
        page = context.new_page()
        for index, card in enumerate(cards, start=1):
            html_doc = build_card_html(meta, card, index, total, theme)
            page.set_content(html_doc, wait_until="networkidle")
            # 等字体渲染稳定（本地字体，load 极快）
            page.wait_for_timeout(120)
            out = args.output_dir / card["file"]
            # 截取 .poster 元素，确保输出尺寸精确为 1080×1440
            poster = page.locator(".poster")
            poster.screenshot(path=str(out))
            rendered_paths.append(out)
            print(f"  [{index:02d}/{total}] {card['file']}")
        context.close()
        browser.close()

    if not args.no_contact_sheet:
        create_contact_sheet(rendered_paths, args.output_dir / "preview_contact_sheet.png")

    print(json.dumps({
        "cards": len(rendered_paths),
        "output_dir": str(args.output_dir.resolve()),
        "size": [POSTER_W, POSTER_H],
        "theme": theme_name,
        "style": "guizang",
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
