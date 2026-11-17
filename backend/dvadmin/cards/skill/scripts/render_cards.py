#!/usr/bin/env python3
"""render_cards.py - cards.json -> 9 张 PNG + preview_contact_sheet.png

确定性文本渲染，保证中文可读。支持 layout: cover / summary / table / list。
主题来自 assets/themes.json，兼容深色（premium-navy）与浅色主题。

视觉增强（借鉴 baoyu-image-cards 设计令牌，仍为确定性 Pillow 渲染，数字绝不修改）：
  - 渐变背景 + 暗点/网格纹理
  - eyebrow 胶囊药丸 + accent 圆点
  - 标题装饰线（短横 + 菱形 ornament）
  - 卡片表面柔和投影
  - 表格：accent 淡色表头、柔和斑马纹、列分隔线、数字列右对齐
  - 列表：编号圆形 marker
  - 页脚：圆点 / 菱形 ornament 分隔，下移至 10% 安全区外
新增 visual 开关均为可选，旧主题不受影响。
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Any

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:
    raise SystemExit("Pillow is required. Install it with: python3 -m pip install Pillow") from exc


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_THEMES = SKILL_ROOT / "assets" / "themes.json"
COLOR_KEYS = {"background", "surface", "ink", "muted", "line", "soft"}

REGULAR_FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/msjh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]
BOLD_FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/msjhbd.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
]


# ── 颜色工具 ──────────────────────────────────────────────────


def hex_color(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    if len(value) != 6:
        raise SystemExit(f"Invalid color: #{value}")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))


def lerp_color(a, b, t: float) -> tuple[int, int, int]:
    """线性插值两个 RGB 颜色；t∈[0,1]。"""
    t = max(0.0, min(1.0, float(t)))
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def lighten(color, t: float) -> tuple[int, int, int]:
    return lerp_color(color, (255, 255, 255), t)


def darken(color, t: float) -> tuple[int, int, int]:
    return lerp_color(color, (0, 0, 0), t)


def _is_numeric(value) -> bool:
    s = str(value).strip().replace(",", "").replace(" ", "")
    if not s:
        return False
    try:
        float(s)
        return True
    except ValueError:
        return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render insurance proposal cards from JSON.")
    parser.add_argument("input", type=Path, help="Path to cards.json")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--theme-file", type=Path, default=DEFAULT_THEMES)
    parser.add_argument("--theme", help="Override meta.theme.")
    parser.add_argument("--font", type=Path, help="Optional CJK regular font")
    parser.add_argument("--bold-font", type=Path, help="Optional CJK bold font")
    parser.add_argument("--no-contact-sheet", action="store_true")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"Input file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {path}: {exc}") from exc


def choose_font(explicit: Path | None, candidates: list[str]) -> Path:
    if explicit:
        if explicit.exists():
            return explicit
        raise SystemExit(f"Font not found: {explicit}")
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return path
    raise SystemExit("No Chinese-capable font found. Pass --font and --bold-font.")


def validate_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    meta = payload.get("meta")
    cards = payload.get("cards")
    if not isinstance(meta, dict) or not isinstance(cards, list) or not cards:
        raise SystemExit("cards.json must contain a meta object and a non-empty cards array")
    width = int(meta.get("width", 1080))
    height = int(meta.get("height", 1800))
    if not (400 <= width <= 4000 and 400 <= height <= 4000):
        raise SystemExit("Canvas size must be between 400 and 4000 px")
    meta["width"], meta["height"] = width, height
    seen: set[str] = set()
    for index, card in enumerate(cards, start=1):
        if not isinstance(card, dict):
            raise SystemExit(f"Card {index} must be an object")
        filename = card.get("file")
        if not isinstance(filename, str) or not filename.lower().endswith(".png"):
            raise SystemExit(f"Card {index} requires a .png file name")
        if Path(filename).name != filename:
            raise SystemExit(f"Card {index} file must be a base name")
        if filename in seen:
            raise SystemExit(f"Duplicate card filename: {filename}")
        seen.add(filename)
        layout = card.get("layout", "list")
        if layout not in {"cover", "summary", "table", "list"}:
            raise SystemExit(f"Unsupported layout '{layout}' in {filename}")
        if not str(card.get("title", "")).strip():
            raise SystemExit(f"Card {filename} requires a title")
    return meta, cards


class Renderer:
    def __init__(self, meta, theme, regular_font, bold_font):
        self.meta = meta
        self.width = int(meta["width"])
        self.height = int(meta["height"])
        self.regular_font = str(regular_font)
        self.bold_font = str(bold_font)
        missing = COLOR_KEYS.difference(theme)
        if missing:
            raise SystemExit("Theme missing colors: " + ", ".join(sorted(missing)))
        self.colors = {key: hex_color(theme[key]) for key in COLOR_KEYS}
        self.accents = {key: hex_color(value) for key, value in theme.get("accents", {}).items()}
        self.dark = bool(theme.get("visual", {}).get("dark", False))
        self.visual = {
            "chrome": "band",
            "pattern": "none",
            "radius": 18,
            "outline_width": 1,
            "marker": "circle",
            "eyebrow_box": False,
            "title_rule": "short",
            "footer_rule": True,
            "margin_scale": 1.0,
            "shadow": False,
            "gradient": False,
            "divider": "line",
            **theme.get("visual", {}),
        }
        self.primary_accent = self.accents.get("gold") or next(iter(self.accents.values()), (200, 160, 60))

    def font(self, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(self.bold_font if bold else self.regular_font, size)

    @staticmethod
    def text_width(draw, text, font) -> int:
        if not text:
            return 0
        box = draw.textbbox((0, 0), text, font=font)
        return box[2] - box[0]

    def wrap_text(self, draw, text, font, max_width) -> list[str]:
        lines = []
        for paragraph in str(text).splitlines() or [""]:
            if not paragraph:
                lines.append("")
                continue
            line = ""
            for char in paragraph:
                candidate = line + char
                if line and self.text_width(draw, candidate, font) > max_width:
                    lines.append(line.rstrip())
                    line = char.lstrip() if char == " " else char
                else:
                    line = candidate
            if line:
                lines.append(line.rstrip())
        return lines or [""]

    def fit_text(self, draw, text, max_width, max_lines, start_size, min_size, bold=False):
        for size in range(start_size, min_size - 1, -2):
            font = self.font(size, bold=bold)
            lines = self.wrap_text(draw, text, font, max_width)
            if len(lines) <= max_lines:
                return font, lines
        font = self.font(min_size, bold=bold)
        return font, self.wrap_text(draw, text, font, max_width)

    def accent(self, card) -> tuple[int, int, int]:
        name = str(card.get("accent", "gold"))
        return self.accents.get(name, next(iter(self.accents.values())))

    @staticmethod
    def contrast_text(color) -> tuple[int, int, int]:
        lum = 0.2126 * color[0] + 0.7152 * color[1] + 0.0722 * color[2]
        return (20, 22, 21) if lum > 155 else (255, 255, 255)

    def draw_lines(self, draw, x, y, lines, font, fill, gap) -> int:
        for line in lines:
            draw.text((x, y), line, font=font, fill=fill)
            y += font.size + gap
        return y

    # ── 背景增强 ────────────────────────────────────────────────

    def draw_background(self, draw) -> None:
        bg = self.colors["background"]
        if bool(self.visual.get("gradient", False)):
            if self.dark:
                top = lerp_color(bg, self.colors["line"], 0.12)
            else:
                top = lighten(bg, 0.05)
            bands = 40
            for i in range(bands):
                t = i / max(1, bands - 1)
                c = lerp_color(top, bg, t)
                y0 = int(i * self.height / bands)
                y1 = int((i + 1) * self.height / bands) + 1
                draw.rectangle((0, y0, self.width, y1), fill=c)
        pattern = self.visual.get("pattern", "none")
        if pattern == "dots":
            dot_color = lerp_color(bg, self.colors["line"], 0.12 if self.dark else 0.10)
            spacing = 28
            r = 1
            for y in range(spacing // 2, self.height, spacing):
                for x in range(spacing // 2, self.width, spacing):
                    draw.ellipse((x - r, y - r, x + r, y + r), fill=dot_color)
        elif pattern == "grid":
            grid_color = lerp_color(bg, self.colors["line"], 0.08)
            spacing = 40
            for x in range(0, self.width, spacing):
                draw.line((x, 0, x, self.height), fill=grid_color, width=1)
            for y in range(0, self.height, spacing):
                draw.line((0, y, self.width, y), fill=grid_color, width=1)

    def draw_shadow(self, draw, box, radius) -> None:
        """在表面卡片下方画一个偏移 +6 的柔和阴影。"""
        if not bool(self.visual.get("shadow", False)):
            return
        shadow_color = lerp_color(self.colors["background"], (0, 0, 0), 0.15 if not self.dark else 0.30)
        draw.rounded_rectangle(
            (box[0], box[1] + 6, box[2], box[3] + 6),
            radius=radius + 2,
            fill=shadow_color,
        )

    def draw_surface(self, draw, box, radius, outline=True) -> None:
        self.draw_shadow(draw, box, radius)
        draw.rounded_rectangle(
            box,
            radius=radius,
            fill=self.colors["surface"],
            outline=self.colors["line"] if outline else None,
            width=max(1, int(self.visual.get("outline_width", 1))),
        )

    # ── 画布与页眉 ──────────────────────────────────────────────

    def base_canvas(self, card, index, total):
        image = Image.new("RGB", (self.width, self.height), self.colors["background"])
        draw = ImageDraw.Draw(image)
        self.draw_background(draw)
        accent = self.accent(card)
        band = max(14, int(self.height * 0.018))
        draw.rectangle((0, 0, self.width, band), fill=accent)

        margin_scale = float(self.visual.get("margin_scale", 1.0))
        metrics = {
            "margin": int(self.width * 0.08 * margin_scale),
            "top": int(self.height * 0.08),
            "bottom": int(self.height * 0.08),
        }
        margin = metrics["margin"]
        top = metrics["top"]

        eyebrow = str(card.get("eyebrow", self.meta.get("title", "")))
        eyebrow_font = self.font(40, bold=True)
        if bool(self.visual.get("eyebrow_box", False)):
            ew = self.text_width(draw, eyebrow, eyebrow_font)
            pad_x, pad_y = 22, 12
            pill_radius = (eyebrow_font.size + pad_y * 2) // 2
            draw.rounded_rectangle(
                (margin, top - pad_y, margin + ew + pad_x * 2, top + eyebrow_font.size + pad_y),
                radius=pill_radius,
                fill=accent,
            )
            draw.text((margin + pad_x, top), eyebrow, font=eyebrow_font, fill=self.contrast_text(accent))
        else:
            dot_cy = top + eyebrow_font.size // 2
            draw.ellipse((margin, dot_cy - 5, margin + 10, dot_cy + 5), fill=accent)
            draw.text((margin + 22, top), eyebrow, font=eyebrow_font, fill=accent)

        index_font = self.font(28)
        index_text = f"{index:02d}/{total:02d}"
        draw.text(
            (self.width - margin - self.text_width(draw, index_text, index_font), top),
            index_text,
            font=index_font,
            fill=self.colors["muted"],
        )
        return image, draw, accent, metrics

    def draw_footer(self, draw) -> None:
        margin = int(self.width * 0.08 * float(self.visual.get("margin_scale", 1.0)))
        y = self.height - int(self.height * 0.10)
        divider = self.visual.get("divider", "line")
        if bool(self.visual.get("footer_rule", True)):
            if divider == "dots":
                n = 5
                diameter = 6
                gap = 14
                total_w = n * diameter + (n - 1) * gap
                start_x = (self.width - total_w) // 2
                for i in range(n):
                    cx = start_x + i * (diameter + gap)
                    draw.ellipse((cx, y - 23, cx + diameter, y - 23 + diameter), fill=self.colors["line"])
            elif divider == "ornament":
                draw.line((margin, y - 22, self.width - margin, y - 22), fill=self.colors["line"], width=2)
                cx = self.width // 2
                s = 5
                draw.polygon(
                    [(cx, y - 22 - s), (cx + s, y - 22), (cx, y - 22 + s), (cx - s, y - 22)],
                    fill=self.colors["line"],
                )
            else:
                draw.line((margin, y - 22, self.width - margin, y - 22), fill=self.colors["line"], width=2)
        footer = str(self.meta.get("footer", "仅供说明参考，以保单条款为准"))
        font, lines = self.fit_text(draw, footer, self.width - 2 * margin - 20, 2, 27, 19)
        dot_cy = y + (font.size + max(0, len(lines) - 1) * (font.size + 4)) // 2 - 4
        draw.ellipse((margin, dot_cy, margin + 8, dot_cy + 8), fill=self.primary_accent)
        self.draw_lines(draw, margin + 20, y, lines, font, self.colors["muted"], 4)

    def draw_title_block(self, draw, card, metrics, accent, cover=False) -> int:
        margin = metrics["margin"]
        y = metrics["top"] + 118
        max_width = self.width - 2 * margin
        start_size = 92 if cover else 76
        min_size = 58 if cover else 48
        max_lines = 3 if cover else 2
        title_font, title_lines = self.fit_text(
            draw, str(card.get("title", "")), max_width, max_lines, start_size, min_size, bold=True
        )
        y = self.draw_lines(draw, margin, y, title_lines, title_font, self.colors["ink"], 12)

        rule_y = y + 18
        if self.visual.get("title_rule") == "ornament":
            rule_width = int(self.width * 0.12)
            draw.line((margin, rule_y, margin + rule_width, rule_y), fill=accent, width=6)
            cx = margin + rule_width
            s = 7
            draw.polygon(
                [(cx, rule_y - s), (cx + s, rule_y), (cx, rule_y + s), (cx - s, rule_y)], fill=accent
            )
            y = rule_y + 42
        else:
            rule_width = int(self.width * 0.2)
            draw.line((margin, rule_y, margin + rule_width, rule_y), fill=accent, width=7)
            y = rule_y + 42

        subtitle = str(card.get("subtitle", "")).strip()
        if subtitle:
            sub_font, sub_lines = self.fit_text(draw, subtitle, max_width, 2, 44, 30)
            y = self.draw_lines(draw, margin, y, sub_lines, sub_font, self.colors["muted"], 8)
        return y

    def draw_cover_stats(self, draw, card, y, metrics, accent) -> int:
        stats = card.get("stats", [])
        if not stats:
            return y
        margin = metrics["margin"]
        gap = 24
        count = len(stats)
        col_w = (self.width - 2 * margin - gap * (count - 1)) // count
        box_h = 190
        radius = int(self.visual.get("radius", 18))
        for i, stat in enumerate(stats):
            x = margin + i * (col_w + gap)
            self.draw_surface(draw, (x, y, x + col_w, y + box_h), radius)
            label = str(stat.get("label", ""))
            value = str(stat.get("value", ""))
            label_font = self.font(30)
            draw.text((x + col_w // 2 - self.text_width(draw, label, label_font) // 2, y + 26),
                      label, font=label_font, fill=self.colors["muted"])
            vfont, vlines = self.fit_text(draw, value, col_w - 24, 2, 52, 30, bold=True)
            vy = y + 66
            for line in vlines:
                draw.text((x + col_w // 2 - self.text_width(draw, line, vfont) // 2, vy),
                          line, font=vfont, fill=self.colors["ink"])
                vy += vfont.size + 6
        return y + box_h

    def draw_summary(self, draw, card, y, metrics, accent) -> int:
        margin = metrics["margin"]
        items = card.get("items", [])
        if not items:
            return y
        gap = 22
        box_h = 104
        radius = int(self.visual.get("radius", 18))
        for label, value in items:
            bottom = y + box_h
            self.draw_surface(draw, (margin, y, self.width - margin, bottom), radius)
            label_font = self.font(32)
            draw.text((margin + 30, y + (box_h - label_font.size) // 2 - 4),
                      str(label), font=label_font, fill=self.colors["muted"])
            value_font, vlines = self.fit_text(
                draw, str(value), self.width - 2 * margin - 320, 1, 36, 26, bold=True
            )
            draw.text((self.width - margin - 30 - self.text_width(draw, vlines[0], value_font),
                       y + (box_h - value_font.size) // 2 - 4),
                      vlines[0], font=value_font, fill=self.colors["ink"])
            y += box_h + gap
        return y

    def draw_table(self, draw, card, y, metrics, accent) -> int:
        margin = metrics["margin"]
        columns = [str(c) for c in card.get("columns", [])]
        rows = [[str(v) for v in r] for r in card.get("rows", [])]
        if not columns or not rows:
            return y
        header_h = 76
        row_h = 74
        footer_top = self.height - int(self.height * 0.18)
        if len(rows) > 0:
            n_rows = len(rows)
            header_h = 72
            row_h = min(84, (footer_top - y - header_h - (n_rows - 1) * 4) // n_rows)
            row_h = max(48, row_h)
        total_rows = len(rows) + 1
        table_bottom = y + header_h + len(rows) * row_h + max(0, len(rows) - 1) * 4

        first_w = max(int(self.width * 0.2), max(self.text_width(draw, r[0], self.font(26)) for r in rows) + 40)
        rest_w = (self.width - 2 * margin - first_w) // max(1, len(columns) - 1)
        widths = [first_w] + [rest_w] * (len(columns) - 1)
        total_w = sum(widths)
        if total_w > self.width - 2 * margin:
            scale = (self.width - 2 * margin) / total_w
            widths = [int(w * scale) for w in widths]

        # 数字列检测（首列除外）——仅用于对齐，绝不修改数字
        numeric_cols: set[int] = set()
        for c_i in range(1, len(columns)):
            if all(_is_numeric(r[c_i]) for r in rows if c_i < len(r)):
                numeric_cols.add(c_i)

        bg = self.colors["background"]
        surface = self.colors["surface"]
        header_fill = lerp_color(accent, bg, 0.82)
        zebra_fill = lerp_color(bg, surface, 0.5)

        # Wrap long column headers to fit their column width so they don't
        # overflow into adjacent columns (e.g. "累积红利及利息" in 6-col joy
        # tables). Grow the header band to fit the tallest wrapped block, then
        # recompute row height / table bottom so body rows stay above footer.
        header_font = self.font(26, bold=True)
        header_pad = 16
        wrapped: list[list[str]] = []
        max_lines = 1
        for i, c in enumerate(columns):
            lines = self.wrap_text(draw, c, header_font, widths[i] - header_pad)
            wrapped.append(lines)
            max_lines = max(max_lines, len(lines))
        header_h = max(header_h, max_lines * (header_font.size + 4) + 20)
        row_h = min(84, (footer_top - y - header_h - (len(rows) - 1) * 4) // len(rows))
        row_h = max(48, row_h)
        table_bottom = y + header_h + len(rows) * row_h + max(0, len(rows) - 1) * 4

        header_y = y + (header_h - max_lines * (header_font.size + 4)) // 2
        draw.rectangle((margin, y, self.width - margin, y + header_h), fill=header_fill)
        x = margin
        for i, lines in enumerate(wrapped):
            w = widths[i]
            line_y = header_y
            for line in lines:
                cx = x + (w - self.text_width(draw, line, header_font)) // 2
                draw.text((cx, line_y), line, font=header_font, fill=self.colors["ink"])
                line_y += header_font.size + 4
            x += w

        cy = y + header_h + 4
        body_font = self.font(27)
        for r_i, row in enumerate(rows):
            if r_i % 2 == 1:
                draw.rectangle((margin, cy, self.width - margin, cy + row_h), fill=zebra_fill)
            x = margin
            for c_i, cell in enumerate(row):
                w = widths[c_i] if c_i < len(widths) else widths[-1]
                f = body_font
                cell_text = cell
                if self.text_width(draw, cell_text, f) > w - 20:
                    f, lines = self.fit_text(draw, cell_text, w - 20, 1, 27, 20, bold=False)
                    cell_text = lines[0]
                tw = self.text_width(draw, cell_text, f)
                if c_i == 0:
                    cx = x + 22
                elif c_i in numeric_cols:
                    cx = x + w - tw - 22
                else:
                    cx = x + (w - tw) // 2
                draw.text((cx, cy + (row_h - f.size) // 2), cell_text, font=f, fill=self.colors["ink"])
                x += w
            # 列分隔细线（从表头底到当前行底）
            x = margin
            for c_i in range(len(columns) - 1):
                x += widths[c_i] if c_i < len(widths) else widths[-1]
                draw.line((x, y, x, cy + row_h), fill=self.colors["line"], width=1)
            cy += row_h + 4

        note = str(card.get("note", "")).strip()
        if note:
            note_y = cy + 18
            note_font, note_lines = self.fit_text(draw, note, self.width - 2 * margin, 2, 26, 20)
            self.draw_lines(draw, margin, note_y, note_lines, note_font, self.colors["muted"], 6)
        return table_bottom

    def draw_list(self, draw, card, y, metrics, accent) -> int:
        margin = metrics["margin"]
        items = [str(i).strip() for i in card.get("items", []) if str(i).strip()]
        if not items:
            return y
        gap = 22
        box_h = 132
        footer_top = self.height - int(self.height * 0.16)
        if (y + len(items) * (box_h + gap)) > footer_top:
            box_h = max(96, (footer_top - y - gap * (len(items) - 1)) // len(items))
        radius = int(self.visual.get("radius", 18))
        marker = self.visual.get("marker", "circle")
        for i, item in enumerate(items):
            bottom = y + box_h
            self.draw_surface(draw, (margin, y, self.width - margin, bottom), radius)
            dot_cx = margin + 36
            dot_cy = y + box_h // 2
            if marker == "number":
                r = 18
                draw.ellipse((dot_cx - r, dot_cy - r, dot_cx + r, dot_cy + r), fill=accent)
                num = str(i + 1)
                nf = self.font(22, bold=True)
                nw = self.text_width(draw, num, nf)
                draw.text((dot_cx - nw // 2, dot_cy - nf.size // 2 - 2), num, font=nf,
                          fill=self.contrast_text(accent))
            else:
                draw.ellipse((dot_cx - 12, dot_cy - 12, dot_cx + 12, dot_cy + 12), fill=accent)
            text_font, lines = self.fit_text(draw, item, self.width - 2 * margin - 110, 2, 35, 26)
            text_y = y + (box_h - len(lines) * text_font.size - max(0, len(lines) - 1) * 6) // 2
            self.draw_lines(draw, margin + 70, text_y, lines, text_font, self.colors["ink"], 6)
            y += box_h + gap
        return y

    def render_card(self, card, index, total) -> Image.Image:
        image, draw, accent, metrics = self.base_canvas(card, index, total)
        layout = str(card.get("layout", "list"))
        cover = layout == "cover"
        y = self.draw_title_block(draw, card, metrics, accent, cover=cover)
        y += 46

        if layout == "cover":
            y = self.draw_cover_stats(draw, card, y, metrics, accent)
            extra = str(card.get("extra", "")).strip()
            if extra:
                y += 46
                extra_font, extra_lines = self.fit_text(
                    draw, extra, self.width - 2 * metrics["margin"], 3, 34, 26
                )
                y = self.draw_lines(draw, metrics["margin"], y, extra_lines, extra_font,
                                    self.colors["muted"], 10)
        elif layout == "summary":
            y = self.draw_summary(draw, card, y, metrics, accent)
        elif layout == "table":
            y = self.draw_table(draw, card, y, metrics, accent)
        else:
            y = self.draw_list(draw, card, y, metrics, accent)

        self.draw_footer(draw)
        return image


def create_contact_sheet(images, output: Path) -> None:
    if not images:
        return
    columns = 3
    thumb_width = 300
    thumb_height = round(thumb_width * images[0].height / images[0].width)
    gap = 24
    label_height = 42
    rows = math.ceil(len(images) / columns)
    sheet_width = columns * thumb_width + (columns + 1) * gap
    sheet_height = rows * (thumb_height + label_height) + (rows + 1) * gap
    sheet = Image.new("RGB", (sheet_width, sheet_height), (235, 235, 229))
    draw = ImageDraw.Draw(sheet)
    label_font = ImageFont.truetype(str(choose_font(None, REGULAR_FONT_CANDIDATES)), 24)
    resampling = getattr(Image, "Resampling", Image).LANCZOS
    for index, image in enumerate(images, start=1):
        row, column = divmod(index - 1, columns)
        x = gap + column * (thumb_width + gap)
        y = gap + row * (thumb_height + label_height + gap)
        thumb = image.resize((thumb_width, thumb_height), resampling)
        sheet.paste(thumb, (x, y))
        draw.text((x, y + thumb_height + 8), f"{index:02d}", font=label_font, fill=(55, 58, 56))
    sheet.save(output, format="PNG", optimize=True)


def main() -> None:
    args = parse_args()
    payload = load_json(args.input)
    meta, cards = validate_payload(payload)
    themes = load_json(args.theme_file)
    theme_name = str(args.theme or meta.get("theme", "premium-navy"))
    if theme_name not in themes:
        raise SystemExit(f"Theme '{theme_name}' not found. Available: {', '.join(sorted(themes))}")

    regular_font = choose_font(args.font, REGULAR_FONT_CANDIDATES)
    bold_font = choose_font(args.bold_font, BOLD_FONT_CANDIDATES)
    renderer = Renderer(meta, themes[theme_name], regular_font, bold_font)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    rendered = []
    for index, card in enumerate(cards, start=1):
        image = renderer.render_card(card, index, len(cards))
        image.save(args.output_dir / card["file"], format="PNG", optimize=True)
        rendered.append(image)

    if not args.no_contact_sheet:
        create_contact_sheet(rendered, args.output_dir / "preview_contact_sheet.png")

    print(json.dumps({
        "cards": len(rendered),
        "output_dir": str(args.output_dir.resolve()),
        "size": [meta["width"], meta["height"]],
        "theme": theme_name,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
