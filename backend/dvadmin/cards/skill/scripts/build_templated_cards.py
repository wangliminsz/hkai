#!/usr/bin/env python3
"""build_templated_cards.py — 通用卡片构建器（由 template.json + data.json 驱动）.

输入：
  - data.json    (extract_templated.py 的输出：归一化 info + 命名列行)
  - template.json (products/<id>/template.json：卡片角色/文案/binds/variants)
可选：
  - --style      渲染目标风格，决定 role → layout 的映射（当前实现 'llm'）
  - --overrides  用户卡片文案覆盖 {card_idx: text|dict}

输出：cards.json —— 每张卡 = {file, layout, ...resolved data}。
产品的卡片结构、文案、binds 全部来自 template.json，此脚本不含任何
``if product == ...`` 分支。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import card_lib  # noqa: E402

SKILL_ROOT = Path(__file__).resolve().parents[1]

# 可选 LLM 写手（backend/ 提供，pipeline 注入 PYTHONPATH）
_LLM_SLOTS: dict[str, Any] = {}
try:
    from llm_writer import write_llm_essay, write_llm_letter
    _LLM_SLOTS = {
        "llm_letter": write_llm_letter,
        "llm_essay": write_llm_essay,
    }
except Exception as exc:  # pragma: no cover
    sys.stderr.write(f"[build_templated] LLM writer unavailable: {exc}\n")

# role → layout 映射（按风格）
# llm：小红书/朋友圈社交风；guizang：杂志编辑风；classic：数据密集 9 卡。
ROLE_TO_LAYOUT = {
    "llm": {
        "hero": "llm-hero",
        "summary": "llm-summary",
        "numbers": "llm-numbers",
        "coverage": "llm-coverage",
        "multi": "llm-multi",
        "chart": "llm-chart",
        "irr": "llm-irr",
        "reasons": "llm-4reasons",
        "letter": "llm-letter",
        "essay": "llm-essay",
        "company": "llm-company",
        "points": "llm-points",
        "note": "llm-note",
    },
    "guizang": {
        "hero": "cover",
        "summary": "summary",
        "numbers": "list",
        "coverage": "list",
        "multi": "ci-list",
        "chart": "table",
        "irr": "list",
        "reasons": "list",
        "letter": "article",
        "essay": "article",
        "company": "list",
        "note": "list",
        "cashvalue_table": "table",
        "scenario_table": "table",
        "death_table": "table",
        "features": "list",
        "risks": "list",
    },
    "classic": {
        "hero": "cover",
        "summary": "summary",
        "numbers": "list",
        "coverage": "list",
        "multi": "list",
        "chart": "table",
        "irr": "list",
        "reasons": "list",
        "letter": "list",
        "essay": "list",
        "company": "list",
        "note": "list",
        "cashvalue_table": "table",
        "scenario_table": "table",
        "death_table": "table",
        "features": "list",
        "risks": "list",
    },
}

# 每个风格的 meta.canvas（llm/guizang 1080x1440；classic 1080x1800）
CANVAS = {
    "llm": (1080, 1440),
    "guizang": (1080, 1440),
    "classic": (1080, 1800),
}

# 每个风格的主题默认值（llm 用 yf-cream；guizang 用 ink-classic；
# classic 用 premium-navy）。前端 theme 选择器按风格出不同色板。
DEFAULT_THEME = {
    "llm": "yf-cream",
    "guizang": "ink-classic",
    "classic": "premium-navy",
}

# role → 序号前缀（对齐 legacy 文件命名）
ROLE_FILE = {
    "hero": "hero", "summary": "summary", "numbers": "numbers", "coverage": "coverage",
    "multi": "multi", "chart": "chart", "irr": "irr", "reasons": "reasons",
    "letter": "letter", "essay": "essay", "company": "company", "points": "points", "note": "user_note",
    "cashvalue_table": "cashvalue_table", "scenario_table": "scenario_table",
    "death_table": "death_table", "features": "features", "risks": "risks",
}

# 各风格会渲染哪些角色。classic/guizang 依赖模板卡上的 styles 字段做精确筛选，
# 这里只作为「角色级」粗过滤（排除 llm 专属角色时由模板 styles 字段负责），
# 因此 classic/guizang 默认放行所有角色，避免误删 letter/essay/company 等共享卡。
ROLES_BY_STYLE = {
    "llm": {"hero", "summary", "numbers", "coverage", "multi", "chart", "irr", "reasons", "letter", "essay", "company", "points", "note", "cashvalue_table", "scenario_table", "death_table", "features", "risks"},
    "guizang": {"hero", "summary", "numbers", "coverage", "multi", "chart", "irr", "reasons", "letter", "essay", "company", "note", "cashvalue_table", "scenario_table", "death_table", "features", "risks"},
    "classic": {"hero", "summary", "numbers", "coverage", "multi", "chart", "irr", "reasons", "letter", "essay", "company", "note", "cashvalue_table", "scenario_table", "death_table", "features", "risks"},
}


# ── 占位符解析 ─────────────────────────────────────────────────────────


_CALC_RE = re.compile(r"\{calc:\s*([^}]+)\}")


def _resolve_calc(expr: str, ctx: dict) -> str:
    """解析 {calc: <表达式>} —— 用 info 数字字段做算术并千分位格式化。

    示例：
      {calc: sum_insured * 0.5}                            → 保额 × 50%
      {calc: sum_insured * 1.5}                            → 保额 × 150%
      {calc: sum_insured * (1.8 if age < 30 else 1.5)}     → 按年龄条件选比例
    表达式可引用 info 下的数字字段（用点号或裸名），支持 + - * / 与括号、
    Python 条件表达式（X if cond else Y）与比较运算。
    无法解析 / 非法时返回占位符原样，绝不猜测。
    """
    import re as _re

    # 先把 info 数字字段名替换成数值
    info = ctx.get("info") or {}
    safe_expr = expr

    def _field_val(name: str):
        # 支持 info.xxx 或裸 xxx
        field = name.split(".")[-1]
        raw = info.get(field)
        if raw is None:
            return None
        try:
            return float(str(raw).replace(",", "").replace(" ", "").strip())
        except ValueError:
            return None

    def _replace_field(m):
        name = m.group(0)
        val = _field_val(name)
        if val is None:
            # 非字段（如 if/else/age 未提取到）→ 保留原样（若 age 缺失会继续报错返回 —）
            return name
        return repr(val)

    # 只替换「确实存在于 info 的字段名」；if/else/and 等表达式关键字保留。
    # 用负向处理：先找出 info 中存在的字段，精确替换 info.xxx 或裸字段名。
    fields = [k for k in info.keys() if isinstance(k, str)]
    # 按名称长度降序，避免 info.age 被 age 先替换
    for f in sorted(fields, key=len, reverse=True):
        # 替换裸字段名（单词边界），但不替换表达式关键字
        if f in ("if", "else", "and", "or", "not", "True", "False", "None"):
            continue
        val = _field_val(f)
        if val is None:
            continue
        # 替换 info.f 和裸 f（单词边界）
        safe_expr = _re.sub(rf"\binfo\.{f}\b", repr(val), safe_expr)
        safe_expr = _re.sub(rf"\b{f}\b", repr(val), safe_expr)

    # 防御：只允许数字、运算符、比较符、条件关键字
    if not _re.fullmatch(
        r"[\d\s.+\-*/()<>=!,'\"a-zA-Z_]+", safe_expr
    ):
        return "—"
    # 禁止属性访问/函数调用：字段已替换为纯数字，若仍出现「字母.xxx」模式
    # 或 lambda/import → 拒绝（数字中的小数点 . 是允许的）。
    if re.search(r"[a-zA-Z_]\s*\.", safe_expr) or "lambda" in safe_expr or "import" in safe_expr:
        return "—"
    try:
        result = eval(safe_expr, {"__builtins__": {}}, {})
    except Exception:
        return "—"
    if result is None:
        return "—"
    # 千分位格式化（整数部分），保留两位小数若有
    if abs(result - round(result)) < 1e-9:
        return f"{int(round(result)):,}"
    return f"{result:,.2f}"


def _resolve_str(tpl: str, ctx: dict) -> str:
    """替换 {info.x} / {copy.y} / {variant} / {plan_name} / {calc: expr} 占位符。"""

    # 先处理 {calc: ...} 表达式
    tpl = _CALC_RE.sub(lambda m: _resolve_calc(m.group(1), ctx), tpl)

    def repl(m: re.Match) -> str:
        key = m.group(1)
        parts = key.split(".")
        node: Any = ctx
        try:
            for p in parts:
                if isinstance(node, dict):
                    node = node.get(p)
                else:
                    return m.group(0)
        except Exception:
            return m.group(0)
        if node is None or node == "":
            # 缺失 info 字段 → "—"（对齐 legacy 的 info.get(x, '—')）；
            # 其它（copy/meta）缺失 → 保留占位符以便发现模板 bug
            return "—" if parts[0] == "info" else m.group(0)
        return str(node)
    return re.sub(r"\{([a-zA-Z0-9_.]+)\}", repl, tpl)


def _resolve_value(value: Any, ctx: dict) -> Any:
    """递归解析字符串 / 列表 / dict 里的占位符。"""
    if isinstance(value, str):
        return _resolve_str(value, ctx)
    if isinstance(value, list):
        return [_resolve_value(v, ctx) for v in value]
    if isinstance(value, dict):
        return {k: _resolve_value(v, ctx) for k, v in value.items()}
    return value


def _deep_merge(base: dict, over: dict) -> dict:
    """把 over 深合并进 base（over 的 dict 值递归，list/标量直接覆盖）。"""
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


# ── 生成型数据 ─────────────────────────────────────────────────────────


def _generated_data(kind: str, data: dict) -> Any:
    tables = data["tables"]
    info = data["info"]
    if kind == "bar_chart":
        return card_lib.bar_chart_data(tables["years"]["cash"])
    if kind == "irr_pills":
        return card_lib.irr_pills(info, tables["scenario"]["cash"], tables["years"]["cash"])
    if kind in ("cashvalue_table", "death_table", "scenario_table"):
        map_kind = {"cashvalue_table": "cashvalue", "death_table": "death", "scenario_table": "scenario"}[kind]
        return card_lib.table_card_data(map_kind, data)
    return None


# ── 上下文构建 ─────────────────────────────────────────────────────────


def _build_ctx(data: dict, template: dict, variant: str) -> dict:
    info = dict(data.get("info") or {})
    info.setdefault("salutation", card_lib.salutation(info))
    info.setdefault("variant", variant)

    # 数字字段预格式化（对齐 legacy _fmt_amount：四舍五入 + 千分位，去掉 .00）
    for f in ("sum_insured", "annual_premium", "annual_premium_plan", "premium_total"):
        if info.get(f):
            info[f + "_fmt"] = card_lib.fmt_amount(info[f])

    # 保障年期显示：有 policy_term → "至 X 岁"；否则 "终身"
    info["policy_term_display"] = (
        f"至 {info.get('policy_term')} 岁" if info.get("policy_term") else "终身"
    )

    info.setdefault("plan_name", data.get("plan_name") or template.get("copy", {}).get("plan_default", ""))

    # 产品定位语：模板 copy.product_positioning 是可选的，供 LLM 生成信/随笔时
    # 对齐产品定位（如储蓄养老、财富传承、危疾守护）。有则注入 info，
    # llm_writer 读到后用于提示词；没有则回退到内部默认文案。
    positioning = (template.get("copy") or {}).get("product_positioning", "")
    if positioning:
        info["product_positioning"] = positioning
    # 可选：给 LLM 的产品卖点要点（换行分隔），进一步引导措辞
    positioning_points = (template.get("copy") or {}).get("positioning_points", [])
    if positioning_points:
        info["positioning_points"] = positioning_points

    copy = dict(template.get("copy") or {})
    # 子变体标签（如 CI 优越版/标准版）来自模板，让 {copy.variant} 落到正确标签
    variant_label = (copy.get("variant_labels") or {}).get(variant, variant or copy.get("variant", ""))
    copy["variant"] = variant_label or copy.get("variant", "")

    ctx = {
        "info": info,
        "copy": copy,
        "meta": template.get("meta") or {},
        "variant": variant_label,
        "plan_name": info.get("plan_name", ""),
    }
    return ctx


# ── 卡片组装 ───────────────────────────────────────────────────────────


def build_cards(data: dict, template: dict, *, style: str = "llm") -> list[dict]:
    product = data["product"]
    variant = data.get("variant") or ""
    ctx = _build_ctx(data, template, variant)
    role_layout = ROLE_TO_LAYOUT.get(style, ROLE_TO_LAYOUT["llm"])
    allowed_roles = ROLES_BY_STYLE.get(style, ROLES_BY_STYLE["llm"])

    cards: list[dict] = []
    for card_tpl in template.get("cards", []):
        if product in (card_tpl.get("omit_when") or []):
            continue
        style_filter = card_tpl.get("styles")
        if style_filter and style not in style_filter:
            continue
        role = card_tpl["role"]
        if role not in allowed_roles:
            continue
        layout = role_layout.get(role, "list")

        bound = dict(card_tpl.get("bound_data") or {})
        # variants 覆盖（检测到子变体时深合并）
        if variant:
            v_over = (card_tpl.get("variants") or {}).get(variant)
            if isinstance(v_over, dict):
                bound = _deep_merge(bound, v_over)

        resolved = _resolve_value(bound, ctx)

        card: dict = {"role": role, "file": "", "layout": layout}
        card.update(resolved)

        # 标题/副标/kicker 若模板顶层指定且 bound_data 未覆盖
        if "title" not in card and "title" in card_tpl:
            card["title"] = _resolve_str(card_tpl["title"], ctx)
        if "subtitle" not in card and "subtitle" in card_tpl:
            card["subtitle"] = _resolve_str(card_tpl["subtitle"], ctx)
        if "kicker" not in card and "kicker" in card_tpl:
            card["kicker"] = _resolve_str(card_tpl["kicker"], ctx)

        # LLM 生成正文
        if card_tpl.get("llm"):
            slot = card_tpl["llm"].get("slot", "")
            fn = _LLM_SLOTS.get(slot)
            body = ""
            if fn:
                try:
                    body = fn(ctx["info"])
                except Exception as exc:
                    sys.stderr.write(f"[build_templated] LLM {slot} failed: {exc}\n")
            body = card_lib.strip_salutation_prefix(body)
            body = card_lib.strip_signature_suffix(body)
            card["body"] = body

        # 生成型数据（bar_chart / irr_pills / 表格卡）——
        #   - data_keys 只有一个时（bars/pills）：直接写入该键
        #   - data_keys 多个时（columns/rows/note）：把返回 dict 按 keys 拆开合并
        if card_tpl.get("generated"):
            kind = card_tpl["generated"].get("kind", "")
            keys = card_tpl["generated"].get("data_keys") or [kind]
            value = _generated_data(kind, data)
            if value is not None:
                if len(keys) == 1:
                    card[keys[0]] = value
                elif isinstance(value, dict):
                    for k in keys:
                        if k in value:
                            card[k] = value[k]

        cards.append(card)

    # 文件命名：按顺序 01_hero.png ...（对齐 legacy）；随后剥离内部 role 字段
    for i, c in enumerate(cards):
        idx = i + 1
        suffix = ROLE_FILE.get(c.get("role", ""), "card")
        c["file"] = f"{idx:02d}_{suffix}.png"
        c["total"] = len(cards)
        c.pop("role", None)

    return cards


# ── 按风格适配 ─────────────────────────────────────────────────────────


def _dict_items_to_text(items: list) -> list[str]:
    """llm 风格 dict items → 渲染器需要的字符串列表。

    dict 形如 {"title","body"} 或 {"tag","title","body"} →
    "title：body"（去掉序号 tag，classic/guizang 的 list 渲染自带编号）。
    """
    out = []
    for it in items:
        if isinstance(it, dict):
            title = str(it.get("title", "")).strip()
            body = str(it.get("body", "")).strip()
            out.append(f"{title}：{body}" if title and body else (title or body))
        else:
            out.append(str(it).strip())
    return [s for s in out if s]


def _adapt_for_style(cards: list[dict], style: str) -> None:
    """把模板生成的 llm 型数据适配成 classic/guizang 渲染器期望的形状。"""
    if style == "llm":
        return
    for card in cards:
        # 列表卡的 dict items → 字符串 items
        if card.get("layout") == "list" and isinstance(card.get("items"), list):
            card["items"] = _dict_items_to_text(card["items"])
        # summary 的 items 必须是 [label, value] 元组列表 —— 模板已满足
        # cover 的 stats 忽略 unit（渲染器只读 label/value）


# ── 主流程 ─────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(description="data.json + template.json → cards.json")
    ap.add_argument("data_json", type=str, help="extract_templated 输出的 data.json")
    ap.add_argument("--template", type=str, required=True, help="products/<id>/template.json")
    ap.add_argument("--output", type=str, default="cards.json")
    ap.add_argument("--style", type=str, default="llm", choices=["llm", "classic", "guizang"])
    ap.add_argument("--overrides", type=str, default="{}")
    ap.add_argument("--cover-image", type=str, default=None,
                    help="用户上传的封面图路径；用作 hero/cover 卡图片（llm: hero_image, guizang: image）")
    args = ap.parse_args()

    data = json.loads(Path(args.data_json).read_text(encoding="utf-8"))
    template = json.loads(Path(args.template).read_text(encoding="utf-8"))
    try:
        overrides = json.loads(args.overrides) if (args.overrides or "").strip() else {}
        if not isinstance(overrides, dict):
            overrides = {}
    except Exception as exc:
        sys.stderr.write(f"[build_templated] overrides JSON 解析失败, 忽略: {exc}\n")
        overrides = {}

    cards = build_cards(data, template, style=args.style)
    _adapt_for_style(cards, args.style)

    # 封面图：绝对化 hero/cover 卡的图片路径。
    # 来源优先级：命令行 --cover-image（用户上传）> 模板 cover.image > 卡内已有图（如 variants 的 hero_image）。
    # 所有相对路径（assets/xx.jpg）都解析为相对 SKILL_ROOT 的绝对路径，
    # 否则渲染器（Path.is_file 按 CWD 判断）在后端 preview（CWD=backend）时读不到。
    hero_field = "hero_image" if args.style == "llm" else "image"
    cover_img = args.cover_image or (template.get("cover") or {}).get("image")
    for c in cards:
        if c.get("layout") not in ("llm-hero", "cover"):
            continue
        # 用户上传的 --cover-image 最高优先；否则卡内已有图；否则模板 cover.image
        img = args.cover_image or c.get(hero_field) or cover_img
        if img:
            p = Path(img)
            if not p.is_absolute():
                p = SKILL_ROOT / p
            if p.is_file():
                c[hero_field] = str(p.resolve())
            else:
                sys.stderr.write(f"[build_templated] cover image not found: {p}\n")
        break

    # 应用用户覆盖（card_idx → text|dict）
    text_slots = ("llm-letter", "llm-essay")
    for i, card in enumerate(cards):
        ov = overrides.get(str(i))
        if ov is not None:
            card_lib.apply_override(card, ov, text_slots=text_slots)

    # 用户自定义纯文字卡 (idx >= 卡片数)
    notes = []
    for k, v in overrides.items():
        try:
            idx = int(k)
        except (TypeError, ValueError):
            continue
        if idx >= len(cards) and ((isinstance(v, str) and v.strip()) or isinstance(v, dict)):
            notes.append(card_lib.user_note_card(idx, v))
    notes.sort(key=lambda c: c["file"])
    if notes:
        cards.extend(notes)
        total = len(cards)
        for c in cards:
            c["total"] = total

    w, h = CANVAS.get(args.style, CANVAS["llm"])
    theme = template.get("meta", {}).get("theme") or DEFAULT_THEME.get(args.style, "yf-cream")
    if args.style != "llm":
        theme = DEFAULT_THEME.get(args.style, theme)
    meta = {
        "title": _resolve_str(str(template.get("meta", {}).get("title", "")), _build_ctx(data, template, data.get("variant", ""))),
        "width": template["meta"].get("width", w),
        "height": template["meta"].get("height", h),
        "footer": template["meta"]["footer"],
        "brand": template.get("meta", {}).get("brand", "YF Life 万通保险"),
        "theme": theme,
        "style": args.style,
    }
    if args.style == "classic":
        meta["width"], meta["height"] = w, h

    payload = {"meta": meta, "cards": cards}
    out = Path(args.output)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"cards.json 已生成: {out}")
    print(f"  卡片数: {len(cards)} (产品: {data['product']}, 变体: {data.get('variant') or '-'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())