#!/usr/bin/env python3
"""render_llm.py — llm 风格 cards.json → PNG 卡片 + 接触印样

与 render_guizang.py 同架构 (Playwright + HTML/CSS + 本地字体)，但视觉语言
从「杂志/编辑部」改为「小红书/朋友圈转发感」：

  - 整篇统一 YF 奶油底 + 品牌蓝主色，强调卡用品牌红
  - 大标题 + 短副标 + 短段落，无密集表格
  - 数据全部"巨号短句"呈现：$1.13M / 2.97× / 20年
  - 每张卡页码 (01/09) + 顶部 eyebrow + 底部品牌条
  - 7 个 layout (hero / summary / numbers / coverage / chart / irr / reasons / letter / essay / company / multi)
"""
from __future__ import annotations

import argparse
import base64
import html
import json
import sys
from pathlib import Path
from typing import Any

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
except ImportError as exc:
    raise SystemExit("playwright is required. Install: python -m pip install playwright && python -m playwright install chromium") from exc


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_THEMES = SKILL_ROOT / "assets" / "llm-themes.json"
POSTER_W = 1080
POSTER_H = 1440


# ── HTML 转义 ───────────────────────────────────────────────────────────


def esc(text: Any) -> str:
    return html.escape(str(text), quote=True)


# ── 主题 CSS 变量 ─────────────────────────────────────────────────────────


def theme_css(theme: dict[str, Any]) -> str:
    lines = [":root {"]
    for key in ("paper", "paper-2", "ink", "ink-2", "muted", "line",
                "accent", "accent-2", "accent-soft",
                "ink-rgb", "paper-rgb", "accent-rgb", "accent2-rgb"):
        val = theme.get(key, "")
        if val:
            lines.append(f"  --{key}: {val};")
    lines.append("}")
    return "\n".join(lines)


# ── 基础 CSS ─────────────────────────────────────────────────────────────


BASE_CSS = """
*,*::before,*::after { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }

:root {
  --serif-zh: "Noto Serif SC", "Noto Serif CJK SC", "STSong", "SimSun", serif;
  --serif-en: "Noto Serif SC", "Noto Serif CJK SC", "Times New Roman", serif;
  --sans-zh:  "Noto Sans SC", "Noto Sans CJK SC", "Microsoft YaHei UI", sans-serif;
  --sans-en:  "Noto Sans SC", "Noto Sans CJK SC", "Arial", sans-serif;
  --mono:     ui-monospace, "Consolas", "Courier New", monospace;
}

.poster {
  position: relative;
  width: 1080px;
  height: 1440px;
  overflow: hidden;
  isolation: isolate;
  font-family: var(--sans-zh);
  color: var(--ink);
  background: var(--paper);
}

/* 背景颗粒纸感 */
.grain {
  position: absolute; inset: 0; z-index: 1; pointer-events: none;
  opacity: .20; mix-blend-mode: multiply;
  background-image: radial-gradient(rgba(0,0,0,.045) 1px, transparent 1px);
  background-size: 3px 3px;
}

.content {
  position: relative; z-index: 2;
  width: 100%; height: 100%;
  padding: 84px 72px 100px;
  display: flex; flex-direction: column;
}

/* —— 排版角色 —— */
.eyebrow {
  font-family: var(--sans-zh);
  font-size: 22px;
  font-weight: 500;
  letter-spacing: 0.10em;
  text-transform: uppercase;
  color: var(--accent);
  margin: 0 0 24px;
  display: flex;
  align-items: center;
  gap: 14px;
}
.eyebrow .rule {
  display: inline-block;
  width: 32px; height: 2px;
  background: currentColor;
  opacity: .7;
}
.eyebrow .rule.red { background: var(--accent-2); }

.h-display { font-family: var(--serif-zh); font-weight: 800; font-size: 96px;
  line-height: 1.05; letter-spacing: -0.01em; margin: 0 0 18px; color: var(--ink); }
.h-xl { font-family: var(--serif-zh); font-weight: 800; font-size: 76px;
  line-height: 1.10; letter-spacing: -0.01em; margin: 0 0 18px; color: var(--ink); }
.h-lg { font-family: var(--serif-zh); font-weight: 800; font-size: 56px;
  line-height: 1.15; letter-spacing: -0.005em; margin: 0 0 14px; color: var(--ink); }
.h-md { font-family: var(--serif-zh); font-weight: 700; font-size: 36px;
  line-height: 1.20; letter-spacing: 0; margin: 0 0 10px; color: var(--ink); }

.sub {
  font-family: var(--sans-zh);
  font-size: 24px;
  font-weight: 500;
  color: var(--muted);
  margin: 0 0 32px;
  letter-spacing: 0.02em;
}

.lead {
  font-family: var(--serif-zh);
  font-weight: 400;
  font-size: 26px;
  line-height: 1.65;
  color: rgba(var(--ink-rgb), .82);
  margin: 0 0 16px;
}

.body {
  font-family: var(--serif-zh);
  font-weight: 400;
  font-size: 24px;
  line-height: 1.80;
  color: rgba(var(--ink-rgb), .85);
  margin: 0 0 16px;
  white-space: pre-wrap;
  word-break: break-word;
}

.pullquote {
  font-family: var(--serif-zh);
  font-weight: 600;
  font-size: 24px;
  line-height: 1.45;
  font-style: italic;
  color: var(--accent);
  margin: 20px 0 0;
  padding-left: 20px;
  border-left: 4px solid var(--accent);
}

.grow { flex: 1; }
.gap-1 { gap: 12px; } .gap-2 { gap: 24px; } .gap-3 { gap: 36px; } .gap-4 { gap: 48px; }
.stack { display: flex; flex-direction: column; }

/* 顶部 / 底部条 */
.issue-row {
  display: flex; align-items: center; gap: 14px;
  font-family: var(--mono); font-size: 18px; letter-spacing: 0.10em;
  color: var(--muted);
  margin-bottom: 18px;
}
.issue-row .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); }
.issue-row .index { color: var(--ink); font-weight: 600; }
.page-no {
  position: absolute; right: 72px; top: 60px; z-index: 3;
  font-family: var(--mono); font-size: 20px; letter-spacing: 0.10em;
  color: var(--muted);
}

.brand-strip {
  position: absolute; left: 0; right: 0; bottom: 0; z-index: 4;
  height: 56px;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 72px;
  font-family: var(--sans-zh);
  font-size: 17px;
  letter-spacing: 0.04em;
  background: var(--ink);
  color: var(--paper);
}
.brand-strip .logo {
  display: flex; align-items: center; gap: 10px;
  font-weight: 700; font-size: 18px;
}
.brand-strip .logo .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--accent-2); }
.brand-strip .disclaimer { opacity: 0.7; font-size: 16px; }

/* 摘要 ledger 行 */
.ledger { display: flex; flex-direction: column; }
.ledger-row {
  display: grid; grid-template-columns: 280px 1fr; gap: 32px;
  align-items: baseline;
  padding: 22px 0;
  border-bottom: 1px solid var(--line);
}
.ledger-row:last-child { border-bottom: 0; }
.ledger-row .k {
  font-family: var(--mono); font-size: 28px; letter-spacing: 0.10em;
  color: var(--muted); text-transform: uppercase;
  font-weight: 500;
}
.ledger-row .v {
  font-family: var(--serif-zh); font-weight: 700; font-size: 36px;
  color: var(--ink); text-align: right; letter-spacing: 0;
  line-height: 1.2;
}

/* 4 数字 2×2 */
.num-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 24px;
  margin-top: 24px;
}
.num-cell {
  background: var(--paper-2);
  border: 1px solid var(--line);
  border-radius: 18px;
  padding: 36px 32px;
  min-height: 220px;
  display: flex; flex-direction: column; justify-content: space-between;
}
.num-cell .label {
  font-family: var(--mono); font-size: 18px;
  letter-spacing: 0.10em; text-transform: uppercase;
  color: var(--muted);
}
.num-cell .value {
  font-family: var(--serif-zh); font-weight: 800; font-size: 64px;
  line-height: 1.0; letter-spacing: -0.02em;
  color: var(--ink);
  display: flex; align-items: baseline; gap: 6px;
}
.num-cell .value .unit {
  font-family: var(--sans-zh); font-size: 22px; font-weight: 500;
  color: var(--muted);
}
.num-cell .note {
  font-family: var(--sans-zh); font-size: 18px; font-weight: 500;
  color: var(--muted);
}

/* 4 数字 (深色背景：Y 蓝) */
.num-grid.dark .num-cell {
  background: rgba(255,255,255,.10);
  border-color: rgba(255,255,255,.20);
  color: #fff;
}
.num-grid.dark .num-cell .label { color: rgba(255,255,255,.75); }
.num-grid.dark .num-cell .value { color: #fff; }
.num-grid.dark .num-cell .note { color: rgba(255,255,255,.7); }

/* 4 理由 (4 horizontal cards) */
.reason-list { display: flex; flex-direction: column; gap: 18px; }
.reason-card {
  background: #FFFFFF;
  border-radius: 18px;
  padding: 26px 30px 26px 130px;
  position: relative;
  min-height: 140px;
  display: flex; flex-direction: column; justify-content: center;
  box-shadow: 0 2px 6px rgba(15,38,71,.04);
  border: 1px solid var(--line);
}
.reason-card .badge {
  position: absolute; left: 26px; top: 50%;
  transform: translateY(-50%);
  width: 76px; height: 76px;
  background: var(--accent);
  color: #fff;
  border-radius: 14px;
  display: flex; align-items: center; justify-content: center;
  font-family: var(--serif-zh); font-size: 36px; font-weight: 800;
  letter-spacing: -0.02em;
}
.reason-card .badge.b2 { background: var(--accent-2); }
.reason-card .badge.b3 { background: #1E3A2E; }
.reason-card .badge.b4 { background: #C9A24F; }
.reason-card h3 {
  font-family: var(--serif-zh); font-size: 30px; font-weight: 700;
  line-height: 1.2; color: var(--ink); margin: 0 0 6px;
  letter-spacing: -0.005em;
}
.reason-card p {
  font-family: var(--sans-zh); font-size: 19px; font-weight: 500;
  color: var(--muted); line-height: 1.4; margin: 0;
}

/* 要点清单卡 (llm-points) —— 与 reasons 视觉一致，每条要点一张子卡 */
.point-body {
  font-family: var(--serif-zh); font-size: 36px; font-weight: 600;
  color: var(--ink); line-height: 1.45; margin: 0;
  letter-spacing: 0;
}
.point-note {
  font-family: var(--sans-zh); font-size: 18px; color: var(--muted);
  margin-top: 10px; line-height: 1.6;
}


/* 条形图 */
.chart-stage {
  position: relative; height: 460px;
  display: flex; align-items: flex-end; gap: 32px;
  padding: 0 8px 76px;
  border-bottom: 2px solid var(--ink);
}
.chart-bar {
  flex: 1;
  display: flex; flex-direction: column; align-items: center; justify-content: flex-end;
  height: 100%; position: relative;
}
.chart-bar .bar {
  width: 100%;
  background: #FFFFFF;
  border: 2px solid var(--ink);
  border-bottom: 0;
  border-radius: 8px 8px 0 0;
  display: block;
  position: relative;
  transition: transform .2s;
}
/* 数值标签：绝对定位在柱子顶部外侧，小柱子也能完整显示数字 */
.chart-bar .bar .val {
  position: absolute;
  top: 0; left: 50%;
  transform: translate(-50%, -100%) translateY(-8px);
  font-family: var(--serif-zh); font-size: 26px; font-weight: 800;
  color: var(--ink); letter-spacing: -0.02em;
  white-space: nowrap;
}
.chart-bar.red .bar { background: var(--accent-2); color: #fff; border-color: var(--accent-2); }
.chart-bar.red .bar .val { color: var(--accent-2); }
.chart-bar .x {
  position: absolute; bottom: -64px; left: 50%; transform: translateX(-50%);
  text-align: center; line-height: 1.25;
  white-space: nowrap;
}
.chart-bar .x .yr {
  display: block; font-family: var(--serif-zh); font-size: 22px; font-weight: 800;
  color: var(--ink); margin-bottom: 2px;
}
.chart-bar .x .sub {
  display: block; font-family: var(--sans-zh); font-size: 16px; font-weight: 500;
  color: var(--muted);
}
.chart-stage.red { border-bottom-color: rgba(255,255,255,.4); }
.chart-stage.red .chart-bar .x .yr { color: #fff; }
.chart-stage.red .chart-bar .x .sub { color: rgba(255,255,255,.7); }
.chart-stage.red .chart-bar .bar { background: #fff; color: var(--accent-2); border-color: #fff; }
/* 深红背景下，柱子顶部数值标签必须是浅色，否则黑字看不清 */
.poster.red .chart-stage .bar .val,
.chart-stage.red .chart-bar .bar .val { color: #fff; }

/* pill 行 (IRR / chart takeaway) */
.pill-row {
  display: flex; gap: 24px;
  margin-top: 100px;
}
.pill {
  flex: 1;
  background: rgba(255,255,255,.10);
  border: 1px solid rgba(255,255,255,.20);
  border-radius: 14px;
  padding: 22px 24px;
  color: #fff;
}
.pill-row:not(.dark) .pill {
  background: var(--paper-2);
  border-color: var(--line);
  color: var(--ink);
}
.pill .k {
  font-family: var(--mono); font-size: 16px;
  letter-spacing: 0.08em; text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 8px;
}
.pill-row:not(.dark) .pill .k { color: var(--muted); }
.pill .v {
  font-family: var(--serif-zh); font-size: 32px; font-weight: 800;
  letter-spacing: -0.01em;
  color: #fff;
}
.pill-row:not(.dark) .pill .v { color: var(--ink); }
.pill .v .unit {
  font-family: var(--sans-zh); font-size: 18px; font-weight: 500;
  color: var(--muted); margin-left: 4px;
}

/* hero number 块 (IRR 卡片中的 "≈ 5.0%") */
.hero-num {
  display: flex; align-items: baseline; gap: 18px;
  padding: 24px 0 20px;
  border-top: 2px solid var(--ink);
  border-bottom: 1px solid var(--line);
  margin: 12px 0 0;
}
.hero-num__v {
  font-family: var(--serif-zh); font-size: 120px; font-weight: 800;
  line-height: 1; letter-spacing: -0.03em;
  color: var(--ink);
}
.hero-num__u {
  font-family: var(--sans-zh); font-size: 36px; font-weight: 600;
  color: var(--ink); margin-left: 6px;
}
.hero-num__l {
  font-family: var(--sans-zh); font-size: 22px; font-weight: 600;
  color: var(--muted); letter-spacing: 0.04em;
}

/* IRR 卡片在 dark 模式下 hero number 颜色 */
.poster.dark .hero-num { border-top-color: rgba(255,255,255,.4); border-bottom-color: rgba(255,255,255,.2); }
.poster.dark .hero-num__v, .poster.dark .hero-num__u { color: #fff; }
.poster.dark .hero-num__l { color: rgba(255,255,255,.7); }

/* headline 块 (保障重点卡) */
.headline-block {
  display: flex; align-items: baseline; gap: 18px;
  padding: 28px 0 32px;
  border-top: 2px solid var(--ink);
  border-bottom: 1px solid var(--line);
  margin-bottom: 28px;
}
.headline-block .v {
  font-family: var(--serif-zh); font-size: 96px; font-weight: 800;
  line-height: 1; letter-spacing: -0.02em;
  color: var(--ink);
}
.headline-block .v .u {
  font-family: var(--sans-zh); font-size: 26px; font-weight: 500;
  color: var(--muted); margin-left: 6px;
}
.headline-block .l {
  font-family: var(--sans-zh); font-size: 22px; font-weight: 600;
  color: var(--muted); letter-spacing: 0.04em;
}

.cov-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 18px 28px;
  margin-top: 8px;
}
.cov-row {
  display: flex; flex-direction: column; gap: 6px;
  padding: 18px 0;
  border-bottom: 1px solid var(--line);
}
.cov-row .k {
  font-family: var(--mono); font-size: 16px;
  letter-spacing: 0.08em; text-transform: uppercase;
  color: var(--muted);
}
.cov-row .v {
  font-family: var(--serif-zh); font-size: 30px; font-weight: 700;
  color: var(--ink);
}
.cov-row .note {
  font-family: var(--sans-zh); font-size: 17px; font-weight: 500;
  color: var(--muted);
}

/* 公司实力 (单列：每项独占一行，body 字号大) */
.company-list {
  display: flex; flex-direction: column; gap: 0;
  margin-top: 8px;
}
.company-item {
  display: grid; grid-template-columns: 96px 1fr; gap: 28px;
  align-items: start;
  padding: 24px 0;
  border-bottom: 1px solid var(--line);
}
.company-item:last-child { border-bottom: 0; }
.company-item .num {
  font-family: var(--serif-zh); font-size: 48px; font-weight: 800;
  color: var(--accent); letter-spacing: -0.02em;
  line-height: 1;
}
.company-item .body {
  display: flex; flex-direction: column; gap: 10px;
}
.company-item .title {
  font-family: var(--serif-zh); font-size: 30px; font-weight: 700;
  color: var(--ink); line-height: 1.25;
}
.company-item .desc {
  font-family: var(--serif-zh); font-size: 26px; font-weight: 500;
  color: var(--ink); line-height: 1.5;
  letter-spacing: 0.01em;
}

/* multi-claim examples (CI) */
.multi-list { display: flex; flex-direction: column; gap: 20px; }
.multi-card {
  background: var(--paper-2);
  border: 1px solid var(--line);
  border-radius: 18px;
  padding: 28px 32px;
  display: grid; grid-template-columns: 1fr auto; gap: 16px;
  align-items: center;
}
.multi-card .label {
  font-family: var(--mono); font-size: 16px;
  letter-spacing: 0.10em; text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 8px;
}
.multi-card .amount {
  font-family: var(--serif-zh); font-size: 56px; font-weight: 800;
  letter-spacing: -0.02em; color: var(--accent);
  line-height: 1;
}
.multi-card .note {
  font-family: var(--sans-zh); font-size: 20px; font-weight: 500;
  color: var(--muted); margin-top: 8px;
}
.multi-card .year {
  font-family: var(--serif-zh); font-size: 22px; font-weight: 700;
  color: var(--ink);
  background: #FFFFFF;
  padding: 12px 20px;
  border-radius: 100px;
  border: 1px solid var(--line);
  white-space: nowrap;
}

/* hero 楔形 */
.hero-wedge {
  position: absolute; top: 0; right: 0;
  width: 720px; height: 720px;
  background: var(--accent);
  clip-path: polygon(100% 0, 0 0, 100% 100%);
  z-index: 1;
}
.hero-wedge-text {
  position: absolute; top: 96px; right: 72px;
  text-align: right; color: #fff; z-index: 2;
}
.hero-wedge-text .tag {
  font-family: var(--sans-zh);
  font-size: 22px; font-weight: 500;
  letter-spacing: 0.10em; opacity: 0.85;
}
.hero-wedge-text .en {
  font-family: var(--serif-en);
  font-size: 28px; font-weight: 600; margin-top: 10px;
  letter-spacing: 0.02em;
}
.hero-photo {
  position: absolute; left: 72px; top: 220px;
  width: 540px; height: 480px;
  background: var(--paper-2);
  border-radius: 4px;
  display: flex; align-items: center; justify-content: center;
  font-size: 22px; color: var(--muted);
  letter-spacing: 0.10em;
  z-index: 1;
  overflow: hidden;
}
.hero-photo.has-image {
  background-color: transparent;
  background-size: cover;
  background-position: center 35%;
  background-repeat: no-repeat;
}
.hero-photo.placeholder {
  /* 缺图时的极简占位：双斜线分隔 + 浅奶油底，不出现任何「[ 家庭温馨场景照片 ]」字样 */
  background:
    linear-gradient(135deg, transparent calc(50% - 1px), var(--line) 50%, transparent calc(50% + 1px)),
    var(--paper-2);
}
.hero-title-block {
  position: absolute; left: 72px; top: 740px;
  right: 72px;
  z-index: 3;
}
.hero-eyebrow {
  display: flex; align-items: center; gap: 12px;
  font-family: var(--sans-zh);
  font-size: 22px; font-weight: 500;
  letter-spacing: 0.10em;
  color: var(--accent-2);
  margin-bottom: 18px;
}
.hero-eyebrow .rule {
  display: inline-block;
  width: 32px; height: 2px;
  background: var(--accent-2);
}
.hero-title-block h1 {
  font-family: var(--serif-zh); font-size: 96px; font-weight: 800;
  line-height: 1.05; letter-spacing: -0.01em;
  color: var(--ink); margin: 0;
}
.hero-title-block h1 .accent { color: var(--accent); }
.hero-hook {
  position: absolute; left: 72px; top: 920px;
  display: flex; align-items: center; gap: 16px;
  font-family: var(--serif-zh); font-size: 36px; font-weight: 600;
  color: var(--ink); letter-spacing: 0.02em;
  z-index: 3;
}
.hero-hook .pipe {
  display: inline-block;
  width: 5px; height: 36px;
  background: var(--accent-2);
}
.hero-stats-wrap {
  position: absolute; left: 72px; right: 72px; top: 1010px;
  z-index: 3;
}
.hero-stats {
  display: flex; gap: 16px;
}
.hero-stats .stat {
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 18px 22px;
  flex: 1;
}
.hero-stats .stat .l {
  font-family: var(--mono); font-size: 14px;
  letter-spacing: 0.08em; text-transform: uppercase;
  color: var(--muted); margin-bottom: 6px;
}
.hero-stats .stat .v {
  font-family: var(--serif-zh); font-size: 28px; font-weight: 800;
  color: var(--ink);
  letter-spacing: -0.01em;
}
.hero-stats .stat .v .u {
  font-family: var(--sans-zh); font-size: 16px; font-weight: 500;
  color: var(--muted); margin-left: 4px;
}

/* 文章卡 (信 / 随笔) */
.article-body {
  font-family: var(--serif-zh); font-size: 30px; line-height: 1.65;
  color: rgba(var(--ink-rgb), .88);
  white-space: pre-wrap; word-break: break-word;
}
.article-body p { margin: 0 0 18px; }
.article-sig {
  margin-top: 20px;
  font-family: var(--serif-zh); font-size: 28px; font-weight: 700;
  color: var(--ink);
  text-align: right;
  line-height: 1.5;
}

/* 强标题章节（蓝/红背景） */
.poster.dark { background: var(--accent); color: #fff; }
.poster.dark .eyebrow { color: rgba(255,255,255,.85); }
.poster.dark .h-xl, .poster.dark .h-lg, .poster.dark .h-md { color: #fff; }
.poster.dark .sub { color: rgba(255,255,255,.85); }
.poster.dark .lead, .poster.dark .body { color: rgba(255,255,255,.92); }
.poster.dark .pullquote { color: #fff; border-color: #fff; }
.poster.dark .page-no { color: rgba(255,255,255,.5); }
.poster.dark .grain { opacity: .10; mix-blend-mode: overlay; }

.poster.red { background: var(--accent-2); color: #fff; }
.poster.red .eyebrow { color: rgba(255,255,255,.85); }
.poster.red .h-xl, .poster.red .h-lg, .poster.red .h-md { color: #fff; }
.poster.red .sub { color: rgba(255,255,255,.9); }
.poster.red .page-no { color: rgba(255,255,255,.5); }
.poster.red .grain { opacity: .08; mix-blend-mode: overlay; }

/* 收益率卡 (llm-irr) —— 藏青背景，区别于红色 chart 卡 */
.poster.dark-ink { background: var(--ink-2); color: #fff; }
.poster.dark-ink .eyebrow { color: rgba(255,255,255,.85); }
.poster.dark-ink .h-xl, .poster.dark-ink .h-lg, .poster.dark-ink .h-md { color: #fff; }
.poster.dark-ink .sub { color: rgba(255,255,255,.85); }
.poster.dark-ink .lead, .poster.dark-ink .body { color: rgba(255,255,255,.92); }
.poster.dark-ink .pullquote { color: #fff; border-color: #fff; }
.poster.dark-ink .page-no { color: rgba(255,255,255,.5); }
.poster.dark-ink .grain { opacity: .12; mix-blend-mode: overlay; }
.poster.dark-ink .pill-row:not(.dark) .pill { background: rgba(255,255,255,.08); border-color: rgba(255,255,255,.2); }
.poster.dark-ink .pill-row:not(.dark) .pill .k { color: rgba(255,255,255,.75); }
.poster.dark-ink .pill-row:not(.dark) .pill .v { color: #fff; }
.poster.dark-ink .pill-row:not(.dark) .pill .unit { color: rgba(255,255,255,.7); }
.poster.dark-ink .hero-num { border-top-color: rgba(255,255,255,.4); border-bottom-color: rgba(255,255,255,.2); }
.poster.dark-ink .hero-num__v, .poster.dark-ink .hero-num__u { color: #fff; }
.poster.dark-ink .hero-num__l { color: rgba(255,255,255,.7); }

/* dark brand strip on red/blue cards (override default) */
.poster.dark .brand-strip { background: var(--ink); }
.poster.dark-ink .brand-strip { background: var(--ink); }
.poster.red .brand-strip { background: var(--ink); }
.poster:not(.dark):not(.dark-ink):not(.red) .brand-strip { background: var(--ink); }

/* 用户自定义纯文字卡 (llm-note) —— 品牌蓝全背景 + 大字标题 + 副文 */
.poster.llm-note-stage { background: var(--accent); color: #fff; }
.poster.llm-note-stage .eyebrow { color: rgba(255,255,255,.85); }
.poster.llm-note-stage .page-no { color: rgba(255,255,255,.5); }
.poster.llm-note-stage .grain { opacity: .10; mix-blend-mode: overlay; }
.poster.llm-note-stage .brand-strip { background: var(--ink); }
.poster.llm-note-stage .issue-row { color: rgba(255,255,255,.75); }
.poster.llm-note-stage .issue-row .index { color: #fff; }
.poster.llm-note-stage .issue-row .dot { background: #fff; }

.note-stage { justify-content: center; padding: 12px 0; }
.note-title {
  font-family: var(--serif-zh); font-weight: 800; font-size: 72px;
  line-height: 1.10; letter-spacing: -0.01em;
  color: #fff; margin: 0 0 24px;
  word-break: break-word;
}
.note-body {
  font-family: var(--serif-zh); font-weight: 400; font-size: 24px;
  line-height: 1.70;
  color: rgba(255,255,255,.92);
  white-space: pre-wrap; word-break: break-word;
}
.note-body p { margin: 0 0 14px; }
.note-body p:last-child { margin-bottom: 0; }
"""


# ── Layouts ──────────────────────────────────────────────────────────────


def _issue_row(meta: dict, card: dict, index: int, total: int) -> str:
    vol = esc(meta.get("title", ""))
    page = f"{index:02d} / {total:02d}"
    return (
        f'<div class="issue-row"><span>{vol}</span>'
        f'<span class="dot"></span>'
        f'<span class="index">{page}</span></div>'
    )


def _brand_strip(meta: dict, card: dict) -> str:
    footer = esc(meta.get("footer", "仅供说明参考 · 一切以保单条款为准"))
    # 品牌名可配置（meta.brand），不同公司显示各自名称；缺省用万通
    brand = esc(meta.get("brand", "YF Life 万通保险"))
    return (
        f'<div class="brand-strip">'
        f'<div class="logo"><span class="dot"></span>{brand}</div>'
        f'<div class="disclaimer">{footer}</div>'
        f'</div>'
    )


def _eyebrow(text: str, *, red: bool = False) -> str:
    cls = "rule red" if red else "rule"
    return f'<div class="eyebrow"><span class="{cls}"></span>{esc(text)}</div>'


def _load_image_data_uri(path: str, *, max_bytes: int = 4_000_000) -> str:
    """把本地图片读成 base64 data URI。文件不存在或超过 max_bytes 时返回 ''。

    max_bytes=4MB 是为避免 Playwright 单次 goto 时单张图就消耗大量内存；
    超大图可由 build 端在写入 cards.json 前压缩到合适尺寸。
    """
    if not path:
        return ""
    p = Path(path)
    if not p.is_file():
        return ""
    try:
        size = p.stat().st_size
        if size > max_bytes:
            sys.stderr.write(f"[render_llm] hero image too large ({size} > {max_bytes}): {path}\n")
            return ""
        data = base64.b64encode(p.read_bytes()).decode("ascii")
        suffix = p.suffix.lower().lstrip(".")
        mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}.get(suffix, "jpeg")
        return f"data:image/{mime};base64,{data}"
    except OSError as exc:
        sys.stderr.write(f"[render_llm] failed to load hero image {path}: {exc}\n")
        return ""


def render_hero(meta: dict, card: dict, index: int, total: int) -> str:
    stats = card.get("stats", [])
    stats_html = "".join(
        f'<div class="stat"><div class="l">{esc(s.get("label",""))}</div>'
        f'<div class="v">{esc(s.get("value",""))} <span class="u">{esc(s.get("unit",""))}</span></div></div>'
        for s in stats
    )
    # 优先用卡片自带的实拍图，缺图时回退到灰色占位（不再写「家庭温馨场景照片」字样）
    img_uri = _load_image_data_uri(card.get("hero_image", ""))
    if img_uri:
        photo_html = f'<div class="hero-photo has-image" style="background-image:url(\'{img_uri}\');"></div>'
    else:
        photo_html = '<div class="hero-photo placeholder"></div>'
    return f"""
    <div class="hero-wedge"></div>
    <div class="hero-wedge-text">
      <div class="tag">{esc(card.get('eyebrow',''))}</div>
      <div class="en">{esc(card.get('english_name',''))}</div>
    </div>
    {photo_html}
    <div class="hero-title-block">
      <h1>{esc(card.get('title_zh_short', card.get('title','')))}</h1>
    </div>
    <div class="hero-hook">
      <span class="pipe"></span>
      <span>{esc(card.get('hook',''))}</span>
    </div>
    <div class="hero-stats-wrap">
      <div class="hero-stats">{stats_html}</div>
    </div>
    """


def render_summary(meta: dict, card: dict, index: int, total: int) -> str:
    items = card.get("items", [])
    rows = "".join(
        f'<div class="ledger-row"><div class="k">{esc(k)}</div>'
        f'<div class="v">{esc(v)}</div></div>'
        for k, v in items
    )
    return f"""
    <div class="content">
      {_issue_row(meta, card, index, total)}
      <div class="stack gap-2 grow">
        {_eyebrow(card.get('eyebrow',''))}
        <h1 class="h-xl">{esc(card.get('title',''))}</h1>
        <p class="sub">{esc(card.get('subtitle',''))}</p>
        <div class="ledger">{rows}</div>
      </div>
    </div>
    """


def render_numbers(meta: dict, card: dict, index: int, total: int, *, dark: bool = False) -> str:
    cells = "".join(
        f'<div class="num-cell"><div class="label">{esc(s.get("label",""))}</div>'
        f'<div class="value">{esc(s.get("value",""))}'
        + (f'<span class="unit">{esc(s.get("unit",""))}</span>' if s.get("unit") else "")
        + '</div>'
        + (f'<div class="note">{esc(s.get("note",""))}</div>' if s.get("note") else "")
        + '</div>'
        for s in card.get("stats", [])
    )
    grid_cls = "num-grid dark" if dark else "num-grid"
    return f"""
    <div class="content">
      {_issue_row(meta, card, index, total)}
      <div class="stack gap-2 grow">
        {_eyebrow(card.get('eyebrow',''))}
        <h1 class="h-xl">{esc(card.get('title',''))}</h1>
        <p class="sub">{esc(card.get('subtitle',''))}</p>
        <div class="{grid_cls}">{cells}</div>
      </div>
    </div>
    """


def render_coverage(meta: dict, card: dict, index: int, total: int) -> str:
    rows = "".join(
        f'<div class="cov-row"><div class="k">{esc(it.get("k",""))}</div>'
        f'<div class="v">{esc(it.get("v",""))}</div>'
        f'<div class="note">{esc(it.get("note",""))}</div></div>'
        for it in card.get("items", [])
    )
    return f"""
    <div class="content">
      {_issue_row(meta, card, index, total)}
      <div class="stack gap-2 grow">
        {_eyebrow(card.get('eyebrow',''))}
        <h1 class="h-xl">{esc(card.get('title',''))}</h1>
        <p class="sub">{esc(card.get('subtitle',''))}</p>
        <div class="headline-block">
          <div class="v">{esc(card.get('headline',''))}<span class="u">{esc(card.get('headline_currency','美元'))}</span></div>
          <div class="l">{esc(card.get('headline_label',''))}</div>
        </div>
        <div class="cov-grid">{rows}</div>
      </div>
    </div>
    """


def render_multi(meta: dict, card: dict, index: int, total: int) -> str:
    cards_html = "".join(
        f'<div class="multi-card">'
        f'<div><div class="label">{esc(ex.get("label",""))}</div>'
        f'<div class="amount">{esc(ex.get("amount",""))}</div>'
        f'<div class="note">{esc(ex.get("note",""))}</div></div>'
        f'<div class="year">{esc(ex.get("year",""))}</div>'
        f'</div>'
        for ex in card.get("examples", [])
    )
    return f"""
    <div class="content">
      {_issue_row(meta, card, index, total)}
      <div class="stack gap-2 grow">
        {_eyebrow(card.get('eyebrow',''))}
        <h1 class="h-xl">{esc(card.get('title',''))}</h1>
        <p class="sub">{esc(card.get('subtitle',''))}</p>
        <div class="multi-list">{cards_html}</div>
      </div>
    </div>
    """


def render_chart(meta: dict, card: dict, index: int, total: int) -> str:
    bars = card.get("bars", [])
    if not bars:
        bars_html = '<div class="sub">无数据</div>'
    else:
        max_v = max((b.get("amount", 0) or 0) for b in bars) or 1
        bar_cells = []
        for b in bars:
            v = b.get("amount", 0) or 0
            # 真实比例：柱子高度与数值成正比。仅留 3% 保底避免数值过小柱子完全消失。
            h = max(3, int(round(v / max_v * 100)))
            label_yr = b.get("label", "")
            bar_cells.append(
                f'<div class="chart-bar"><div class="bar" style="height:{h}%">'
                f'<span class="val">{esc(b.get("compact",""))}</span></div>'
                f'<div class="x"><span class="yr">{esc(label_yr)}</span></div></div>'
            )
        bars_html = "".join(bar_cells)
    return f"""
    <div class="content">
      {_issue_row(meta, card, index, total)}
      <div class="stack gap-2 grow">
        {_eyebrow(card.get('eyebrow',''))}
        <h1 class="h-xl">{esc(card.get('title',''))}</h1>
        <p class="sub">{esc(card.get('subtitle',''))}</p>
        <div class="chart-stage red">{bars_html}</div>
      </div>
    </div>
    """


def render_irr(meta: dict, card: dict, index: int, total: int) -> str:
    pills = card.get("pills", [])
    # hero number：优先「100岁 IRR」；否则第一个 IRR/收益率 pill
    hero = (
        next((p for p in pills if "100" in p.get("label", "") and "IRR" in p.get("label", "")), None)
        or next(
            (p for p in pills if "收益率" in p.get("label", "") or "复利" in p.get("label", "") or "IRR" in p.get("label", "")),
            pills[0] if pills else None,
        )
    )
    other_pills = [p for p in pills if p is not hero]
    pill_html = "".join(
        f'<div class="pill"><div class="k">{esc(p.get("label",""))}</div>'
        f'<div class="v">{esc(p.get("value",""))}<span class="unit">{esc(p.get("unit",""))}</span></div></div>'
        for p in other_pills
    )
    hero_html = ""
    if hero:
        hero_html = (
            f'<div class="hero-num">'
            f'<div class="hero-num__v">{esc(hero.get("value",""))}<span class="hero-num__u">{esc(hero.get("unit",""))}</span></div>'
            f'<div class="hero-num__l">{esc(hero.get("label",""))}</div>'
            f'</div>'
        )
    return f"""
    <div class="content">
      {_issue_row(meta, card, index, total)}
      <div class="stack gap-3 grow">
        {_eyebrow(card.get('eyebrow',''))}
        <h1 class="h-xl">{esc(card.get('title',''))}</h1>
        <p class="sub">{esc(card.get('subtitle',''))}</p>
        {hero_html}
        <div class="pill-row">{pill_html}</div>
        <p class="lead" style="font-size:24px; line-height:1.7;">{esc(card.get('narrative',''))}</p>
      </div>
    </div>
    """


def render_reasons(meta: dict, card: dict, index: int, total: int) -> str:
    reasons = card.get("reasons", [])
    cards_html = "".join(
        f'<div class="reason-card"><div class="badge b{i+1}">{esc(r.get("tag",f"{i+1:02d}"))}</div>'
        f'<h3>{esc(r.get("title",""))}</h3>'
        f'<p>{esc(r.get("body",""))}</p></div>'
        for i, r in enumerate(reasons)
    )
    return f"""
    <div class="content">
      {_issue_row(meta, card, index, total)}
      <div class="stack gap-2 grow">
        {_eyebrow(card.get('eyebrow',''))}
        <h1 class="h-xl">{esc(card.get('title',''))}</h1>
        <p class="sub">{esc(card.get('subtitle',''))}</p>
        <div class="reason-list">{cards_html}</div>
      </div>
    </div>
    """


def render_letter(meta: dict, card: dict, index: int, total: int) -> str:
    body = card.get("body", "") or ""
    body_html = "".join(
        f'<p>{esc(p.strip())}</p>' for p in body.split("\n\n") if p.strip()
    ) or f'<p>{esc(body)}</p>'
    pullquote = card.get("pullquote", "")
    return f"""
    <div class="content">
      {_issue_row(meta, card, index, total)}
      <div class="stack gap-3 grow">
        {_eyebrow(card.get('eyebrow',''))}
        <h1 class="h-xl">{esc(card.get('title',''))}</h1>
        <p class="sub">{esc(card.get('subtitle',''))}</p>
        <div class="article-body">{body_html}</div>
        <div class="article-sig">
          此致<br>敬礼<br>您的保险顾问
        </div>
        {f'<blockquote class="pullquote">{esc(pullquote)}</blockquote>' if pullquote else ''}
      </div>
    </div>
    """


def render_essay(meta: dict, card: dict, index: int, total: int) -> str:
    body = card.get("body", "") or ""
    body_html = "".join(
        f'<p>{esc(p.strip())}</p>' for p in body.split("\n\n") if p.strip()
    ) or f'<p>{esc(body)}</p>'
    pullquote = card.get("pullquote", "")
    return f"""
    <div class="content">
      {_issue_row(meta, card, index, total)}
      <div class="stack gap-3 grow">
        {_eyebrow(card.get('eyebrow',''))}
        <h1 class="h-xl">{esc(card.get('title',''))}</h1>
        <p class="sub">{esc(card.get('subtitle',''))}</p>
        <div class="article-body">{body_html}</div>
        {f'<blockquote class="pullquote">{esc(pullquote)}</blockquote>' if pullquote else ''}
      </div>
    </div>
    """


def render_company(meta: dict, card: dict, index: int, total: int) -> str:
    """公司实力：单列布局，每项独占一行，body 字号大 (26px)。
    原 2 列网格对长尾文字会折成多行显得拥挤，单列更舒展也更易读。"""
    items = card.get("items", [])
    rows = "".join(
        f'<div class="company-item">'
        f'<div class="num">{esc(it.get("tag",""))}</div>'
        f'<div class="body">'
        f'<div class="title">{esc(it.get("title",""))}</div>'
        f'<div class="desc">{esc(it.get("body",""))}</div>'
        f'</div></div>'
        for it in items
    )
    return f"""
    <div class="content">
      {_issue_row(meta, card, index, total)}
      <div class="stack gap-2 grow">
        {_eyebrow(card.get('eyebrow',''))}
        <h1 class="h-xl">{esc(card.get('title',''))}</h1>
        <p class="sub">{esc(card.get('subtitle',''))}</p>
        <div class="company-list">{rows}</div>
      </div>
    </div>
    """


def render_note(meta: dict, card: dict, index: int, total: int) -> str:
    """用户自定义纯文字卡 (idx>=11).
    视觉: 品牌蓝全背景 + 大字标题 + 可选副文 + 完整 issue_row + 底部 brand strip.
    跟其他 llm-* 卡片保持同样的页码 / eyebrow / kicker 结构, 不会显得突兀."""
    body = card.get("subtitle", "") or ""
    body_html = ""
    if body.strip():
        paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [p.strip() for p in body.split("\n") if p.strip()]
        body_html = "".join(f'<p>{esc(p)}</p>' for p in paragraphs)
    return f"""
    <div class="content">
      {_issue_row(meta, card, index, total)}
      <div class="stack gap-3 grow note-stage">
        {_eyebrow(card.get('eyebrow',''))}
        <h1 class="note-title">{esc(card.get('title',''))}</h1>
        {f'<div class="note-body">{body_html}</div>' if body_html else ''}
      </div>
    </div>
    """


def render_points(meta: dict, card: dict, index: int, total: int) -> str:
    """要点清单卡：主标题 + 若干条要点。

    bound_data 结构：
      - 对象条目：{"items": [{"title": "标题", "body": "说明"}, ...]} → 与 reasons
        （四个价值）卡一致：徽章 + 大标题 + 正文。
      - 字符串条目：{"items": ["要点1", ...]} → 徽章 + 单行文字（兼容旧数据）。
    """
    items = card.get("items", []) or []
    palette = ["#1B6FB8", "#B82832", "#1E3A2E", "#C9A24F", "#6E4FA3", "#C05621"]
    cards_html = "".join(
        f'<div class="reason-card">'
        f'<div class="badge" style="background:{palette[i % len(palette)]}">{i + 1:02d}</div>'
        + (
            # 对象条目：大标题 + 正文（与 reasons 卡一致）
            f'<h3>{esc(str(it.get("title", "")))}</h3>'
            f'<p>{esc(str(it.get("body", "")))}</p>'
            if isinstance(it, dict)
            # 字符串条目：单行要点
            else f'<p class="point-body">{esc(str(it))}</p>'
        )
        + '</div>'
        for i, it in enumerate(items)
    )
    note = str(card.get("note", "") or "").strip()
    note_html = f'<p class="point-note">{esc(note)}</p>' if note else ""
    return f"""
    <div class="content">
      {_issue_row(meta, card, index, total)}
      <div class="stack gap-2 grow">
        {_eyebrow(card.get('eyebrow',''))}
        <h1 class="h-xl">{esc(card.get('title',''))}</h1>
        <p class="sub">{esc(card.get('subtitle',''))}</p>
        <div class="reason-list">{cards_html}</div>
        {note_html}
      </div>
    </div>
    """


LAYOUTS = {
    "llm-hero":     render_hero,
    "llm-summary":  render_summary,
    "llm-numbers":  render_numbers,
    "llm-coverage": render_coverage,
    "llm-multi":    render_multi,
    "llm-chart":    render_chart,
    "llm-irr":      render_irr,
    "llm-4reasons": render_reasons,
    "llm-letter":   render_letter,
    "llm-essay":    render_essay,
    "llm-company":  render_company,
    "llm-points":   render_points,
    "llm-note":     render_note,  # 用户自定义纯文字卡
}


# ── Page chrome ──────────────────────────────────────────────────────────


def build_card_html(meta: dict, card: dict, index: int, total: int, theme: dict) -> str:
    layout = card.get("layout", "llm-letter")
    renderer = LAYOUTS.get(layout, render_letter)
    inner = renderer(meta, card, index, total)
    page_no = f"{index:02d} / {total:02d}"

    # 决定 poster class（深色背景卡片）
    poster_class = "poster"
    if layout == "llm-chart":
        poster_class += " red"  # 现金价值条形图用红色背景
    elif layout == "llm-irr":
        poster_class += " dark-ink"  # 收益率用深墨色背景（区别于红色 chart）
    elif layout == "llm-multi":
        poster_class += " dark"  # 多次赔付用品牌主色背景
    elif layout == "llm-note":
        poster_class += " llm-note-stage"  # 用户自定义纯文字卡: 品牌蓝全背景

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{esc(card.get('title',''))}</title>
<style>
{theme_css(theme)}
{BASE_CSS}
</style>
</head>
<body>
  <section class="{poster_class}" id="card-{index}">
    <div class="grain"></div>
    <div class="page-no">{page_no}</div>
    {inner}
    {_brand_strip(meta, card)}
  </section>
</body>
</html>"""


# ── Main render loop ─────────────────────────────────────────────────────


def _force_fonts_settled(page) -> None:
    """Eagerly load every font family used by the CSS, then wait (with a hard
    cap) for document.fonts to settle.

    Without this, Playwright's screenshot call can hang 30s+ in
    "waiting for fonts to load" when a family has no local match on a headless
    server. Pre-loading makes the font state deterministic.
    """
    try:
        page.evaluate(
            "Promise.race(["
            "  Promise.all(["
            "    'Noto Sans SC','Noto Serif SC','Noto Sans CJK SC','Noto Serif CJK SC',"
            "    'Microsoft YaHei UI','SimSun','Arial','Times New Roman'"
            "  ].map(f => document.fonts.load('16px \"' + f + '\"').catch(() => null))),"
            "  new Promise(r => setTimeout(r, 5000))"
            "]).then(() => document.fonts.ready).catch(() => {})"
        )
    except Exception:
        pass


def _screenshot(page, out_path: Path, i: int) -> None:
    """Screenshot a card; if the built-in font-wait still times out, fall back
    to a plain screenshot (fonts already loaded/forced above) so a single stuck
    font can't abort the whole render run."""
    try:
        page.screenshot(
            path=str(out_path),
            clip={"x": 0, "y": 0, "width": POSTER_W, "height": POSTER_H},
            timeout=25000,
        )
    except PlaywrightTimeoutError:
        print(f"  [warn] screenshot font-wait timed out on card {i}; retrying without font wait")
        page.screenshot(
            path=str(out_path),
            clip={"x": 0, "y": 0, "width": POSTER_W, "height": POSTER_H},
            timeout=25000,
            animations="disabled",
        )


def render_cards(cards_json: Path, out_dir: Path, theme_key: str = "yf-cream") -> None:
    payload = json.loads(cards_json.read_text(encoding="utf-8"))
    meta = payload.get("meta", {})
    cards = payload.get("cards", [])
    themes = json.loads(DEFAULT_THEMES.read_text(encoding="utf-8"))
    theme = themes.get(theme_key) or themes[next(iter(themes))]

    out_dir.mkdir(parents=True, exist_ok=True)
    total = len(cards)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport={"width": POSTER_W, "height": POSTER_H},
            device_scale_factor=2,
        )
        page = context.new_page()
        for i, card in enumerate(cards, start=1):
            html_doc = build_card_html(meta, card, i, total, theme)
            tmp = out_dir / f".tmp_{i:02d}.html"
            tmp.write_text(html_doc, encoding="utf-8")
            page.goto(tmp.as_uri(), wait_until="networkidle")
            _force_fonts_settled(page)
            out_path = out_dir / card.get("file", f"{i:02d}.png")
            _screenshot(page, out_path, i)
            tmp.unlink()
            print(f"  rendered {out_path.name}")
        # 接触印样 (3 列 grid)
        contact_sheet_html = _build_contact_sheet(cards, out_dir, total)
        sheet_path = out_dir / ".tmp_sheet.html"
        sheet_path.write_text(contact_sheet_html, encoding="utf-8")
        cols = 3
        rows = (total + cols - 1) // cols
        sheet_w = 320 * cols + 24 * (cols + 1)
        sheet_h = 426 * rows + 24 * (rows + 1)
        context2 = browser.new_context(
            viewport={"width": sheet_w, "height": sheet_h},
            device_scale_factor=1,
        )
        page2 = context2.new_page()
        page2.goto(sheet_path.as_uri(), wait_until="networkidle")
        page2.screenshot(path=str(out_dir / "preview_contact_sheet.png"), full_page=True)
        sheet_path.unlink()
        print(f"  rendered preview_contact_sheet.png")
        browser.close()


def _build_contact_sheet(cards: list, out_dir: Path, total: int) -> str:
    """3-column contact sheet, 320x426 thumbnails."""
    import base64
    tiles = []
    for i, c in enumerate(cards, start=1):
        png = (out_dir / c.get("file", f"{i:02d}.png")).read_bytes()
        b64 = base64.b64encode(png).decode("ascii")
        tiles.append(
            f'<div class="tile"><img src="data:image/png;base64,{b64}"/>'
            f'<div class="cap">{esc(c.get("file",""))}</div></div>'
        )
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
  html,body{{margin:0;background:#DDD;padding:24px;font-family:'Noto Sans SC',sans-serif;}}
  .grid{{display:grid;grid-template-columns:repeat(3,320px);gap:24px;}}
  .tile{{width:320px;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 2px 6px rgba(0,0,0,.08);}}
  .tile img{{width:100%;height:426px;display:block;}}
  .tile .cap{{padding:8px 12px;font-size:14px;color:#333;font-weight:600;}}
</style></head><body>
  <div class="grid">{''.join(tiles)}</div>
</body></html>"""


def main():
    parser = argparse.ArgumentParser(description="llm 风格 cards.json → PNG")
    parser.add_argument("cards_json", type=str, help="cards.json 路径")
    parser.add_argument("--output-dir", type=str, required=True)
    parser.add_argument("--theme", type=str, default="yf-cream")
    args = parser.parse_args()

    render_cards(Path(args.cards_json), Path(args.output_dir), theme_key=args.theme)


if __name__ == "__main__":
    main()
