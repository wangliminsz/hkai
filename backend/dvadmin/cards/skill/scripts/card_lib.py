#!/usr/bin/env python3
"""card_lib — style-agnostic card data building blocks.

Everything here is product-*independent*: it turns normalized proposal data
(parsed first-page info + years/scenario rows) plus a declarative product
``template.json`` into resolved card dictionaries. Product differences live in
JSON (parser.json / template.json), never in these functions.

Includes the markdown-table helpers that used to live in build_cards.py
(parse_md_tables / find_row / collect_rows) and the numeric/copy helpers that
lived in build_llm_cards.py, so the templated builder has a single shared lib
feedable to any renderer (classic / guizang / llm). All functions are pure.
"""
from __future__ import annotations

import re
from typing import Any


# ── markdown 表格解析 (原 build_cards.parse_md_tables) ─────────────────


def parse_md_tables(text: str) -> list[dict]:
    """把 markdown 拆成若干表格：list[dict(columns, rows, title)]。"""
    tables = []
    for block in re.split(r"\n\s*---\s*\n", text):
        lines = [l for l in block.splitlines() if l.strip()]
        title = ""
        for l in lines:
            m = re.match(r"##\s+(.+)", l.strip())
            if m:
                title = m.group(1).strip()
                break
        table_lines = [l for l in lines if l.strip().startswith("|")]
        if not table_lines:
            continue
        rows = []
        for l in table_lines:
            cells = [c.strip() for c in l.strip().strip("|").split("|")]
            rows.append(cells)
        rows = [r for r in rows if not all(re.fullmatch(r":?-{3,}:?", c.replace(" ", "")) for c in r)]
        if len(rows) < 2:
            continue
        columns = rows[0]
        data = rows[1:]
        tables.append({"title": title, "columns": columns, "rows": data})
    return tables


def find_row(tables: list[dict], key: str) -> list | None:
    """在多个表中找第一个首列为 key 的行。"""
    for t in tables:
        for row in t["rows"]:
            if row and row[0].strip() == str(key):
                return row
    return None


def collect_rows(tables: list[dict], keys: list[str]) -> tuple[list[list], list[str]]:
    """按顺序收集指定首列的行；缺失行跳过并在结果里记录 missing。"""
    collected = []
    missing = []
    for k in keys:
        row = find_row(tables, k)
        if row:
            collected.append(row)
        else:
            missing.append(str(k))
    return collected, missing


def tables_by_title(text: str, title_kind: str) -> list[dict]:
    """param tables (含 title) 里筛出标题含 title_kind 的表。

    ``text`` 是某个 md 的全文 —— 先 parse 再按标题过滤。
    """
    tables = parse_md_tables(text)
    return [t for t in tables if title_kind in (t.get("title") or "")]


# ── 数字工具 (原 build_llm_cards._num / _fmt_amount / _compact) ────────


def num(v: Any) -> float:
    """'1,234,567' / '1.5' / 1234567 → 1234567.0"""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace(",", "").replace(" ", "").strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def fmt_amount(v: Any) -> str:
    """1,234,567 → '1,234,567' （不带单位）；0 → '—'"""
    n = num(v)
    if n == 0:
        return "—"
    if n >= 1000:
        return f"{n:,.0f}"
    return f"{n:.0f}"


def compact(v: Any) -> str:
    """数字压缩：1,130,000 → '$1.13M'；407,000 → '$407K'；27,664 → '$27,664'"""
    n = num(v)
    if n == 0:
        return "—"
    if n >= 1_000_000:
        return f"${n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"${n / 1_000:.0f}K"
    return f"${n:,.0f}"


# ── 表格数据（classic / guizang 风格的 table 卡）───────────────────────


def cash_table_rows(rows: list[dict]) -> list[list]:
    """现金价值表行 → 展示行 [[year, premiums, guaranteed, terminal, total], ...]。

    有 state_bonus（joy）时插入「累积红利及利息」列，对齐 legacy 列序。
    """
    out = []
    for r in rows:
        row = [str(r.get("year", ""))]
        for k in ("premiums", "guaranteed"):
            row.append(fmt_amount(r.get(k)))
        if "state_bonus" in r:
            row.append(fmt_amount(r.get("state_bonus")))
        row.append(fmt_amount(r.get("terminal")))
        row.append(fmt_amount(r.get("total")))
        out.append(row)
    return out


def death_table_rows(rows: list[dict]) -> list[list]:
    """身故保障表行 → 展示行。列序与 cash_table_rows 一致，仅列名不同。"""
    out = []
    for r in rows:
        row = [str(r.get("year", ""))]
        for k in ("premiums", "guaranteed"):
            row.append(fmt_amount(r.get(k)))
        if "state_bonus" in r:
            row.append(fmt_amount(r.get("state_bonus")))
        row.append(fmt_amount(r.get("terminal")))
        row.append(fmt_amount(r.get("total")))
        out.append(row)
    return out


def scenario_table_rows(rows: list[dict]) -> list[list]:
    """情景对比表行 → 展示行 [[year, worst_total, best_total], ...]"""
    out = []
    for r in rows:
        out.append([
            str(r.get("year", "")),
            fmt_amount(r.get("worst_total")),
            fmt_amount(r.get("best_total")),
        ])
    return out


CASH_COLUMNS = ["保单年度", "缴付保费总额", "保证金额", "终期红利", "总额"]
CASH_COLUMNS_JOY = ["保单年度", "缴付保费总额", "保证金额", "累积红利及利息", "终期红利", "总额"]
CASH_COLUMNS_BIS = ["保单年度", "缴付保费总额", "保证金额", "复归红利", "终期红利", "总额"]
DEATH_COLUMNS = ["保单年度", "缴付保费总额", "保证身故保障", "终期红利", "总额"]
DEATH_COLUMNS_JOY = ["保单年度", "缴付保费总额", "保证身故保障", "累积红利及利息", "终期红利", "总额"]
DEATH_COLUMNS_BIS = ["保单年度", "缴付保费总额", "保证身故保障", "复归红利", "终期红利", "总额"]
SCENARIO_COLUMNS = ["保单年度", "悲观情景", "乐观情景"]


def table_card_data(kind: str, data: dict) -> dict | None:
    """生成 classic/guizang 的 table 卡数据（columns + rows + note）。

    kind: 'cashvalue' | 'death' | 'scenario' —— 直接产出渲染器需要的
    columns/rows。所有列名/序号来自 data.tables（已归一化），本函数不含
    任何产品分支。
    """
    tables = data["tables"]
    info = data.get("info") or {}
    product = data.get("product", "pwl")
    has_state = "state_bonus" in (tables["years"]["cash"][0] if tables["years"]["cash"] else {})

    if product == "bis":
        if kind == "cashvalue":
            return {
                "columns": CASH_COLUMNS_BIS,
                "rows": cash_table_rows(tables["years"]["cash"]),
                "note": _cash_note(product, info),
            }
        if kind == "death":
            return {
                "columns": DEATH_COLUMNS_BIS,
                "rows": death_table_rows(tables["years"]["death"]),
                "note": _death_note(product),
            }
        if kind == "scenario":
            return {"columns": SCENARIO_COLUMNS, "rows": scenario_table_rows(tables["scenario"]["cash"])}
        return None

    if kind == "cashvalue":
        rows = tables["years"]["cash"]
        return {
            "columns": CASH_COLUMNS_JOY if has_state else CASH_COLUMNS,
            "rows": cash_table_rows(rows),
            "note": _cash_note(product, info),
        }
    if kind == "death":
        rows = tables["years"]["death"]
        return {
            "columns": DEATH_COLUMNS_JOY if has_state else DEATH_COLUMNS,
            "rows": death_table_rows(rows),
            "note": _death_note(product),
        }
    if kind == "scenario":
        rows = tables["scenario"]["cash"]
        return {"columns": SCENARIO_COLUMNS, "rows": scenario_table_rows(rows)}
    return None


def _cash_note(product: str, info: dict) -> str:
    if product == "ci":
        return "终期红利为非保证金额，第5个保单周年起公布，实际可能高于或低于演示"
    if product == "joy":
        return "终期红利及累积红利为非保证金额，实际可能高于或低于演示"
    if product == "bis":
        return "复归红利及终期红利为非保证金额，实际可能高于或低于演示"
    return "终期红利为非保证金额，实际可能高于或低于演示"


def _death_note(product: str) -> str:
    if product == "ci":
        return "身故赔偿取(100%基本保障额+终期红利)与现金价值的较高者，扣除已支付严重疾病保障"
    if product == "joy":
        return "身故赔偿取(保证身故保障+累积红利及利息+终期红利)与现金价值的较高者"
    if product == "bis":
        return "身故赔偿取(保证身故保障+复归红利+终期红利)与现金价值的较高者"
    return "身故赔偿取(保证身故保障+终期红利+累积红利)与现金价值的较高者"


def normalize_period(label: str) -> str:
    """把「保单年度/受保人年龄」首列标签统一成可读格式。

    '10' / '10年' → '10年'；'65 歲' / '65歲' / '65 岁' → '65岁'。
    保留岁/年原始语义（100 岁是年龄，不是 100 年）。
    """
    s = (label or "").strip().replace("歲", "岁")
    s_no_space = s.replace(" ", "").replace("　", "")
    if s_no_space.endswith("岁") or s_no_space.endswith("年"):
        return s_no_space
    return f"{s_no_space}年"


# ── 称呼 / LLM 防御 (原 build_llm_cards) ───────────────────────────────


def salutation(info: dict) -> str:
    """根据 name + gender 生成称呼（避免 "Mr. Peng先生先生" 重复）。"""
    name = (info.get("name") or "").strip()
    gender = (info.get("gender") or "").strip()
    if name.endswith("先生") or name.endswith("女士"):
        return name
    if "女" in gender:
        return f"{name}女士" if name else "女士"
    if "男" in gender:
        return f"{name}先生" if name else "先生"
    return name or "您"


_SALUTATION_PREFIX_RE = re.compile(r"^\s*(亲爱的|您好|敬启者|致)\s*[^：:\n。]{1,60}[：:]\s*\n+")
_SIGNATURE_SUFFIX_RE = re.compile(
    r"\n*\s*(?:此致|此致\n敬礼|\s*此\s*致)\s*\n+敬\s*礼\s*\n+\s*您的保险顾问\s*$"
)


def strip_salutation_prefix(body: str) -> str:
    if not body:
        return body
    return _SALUTATION_PREFIX_RE.sub("", body, count=1)


def strip_signature_suffix(body: str) -> str:
    if not body:
        return body
    return _SIGNATURE_SUFFIX_RE.sub("", body, count=1)


# ── 图表 / IRR 数据 (来自解析后的表格行，纯通用算法) ───────────────────


def pick_chart_nodes(keys: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """从 (label, amount) 对里选 5 个节点。

    节点选择（consistent period）：行数 ≤5 全取；>5 用 5 等分
    {0, n/4, n/2, 3n/4, n-1}，去重后不足 5 再退回简单等距。
    """
    n = len(keys)
    if n == 0:
        return []
    if n <= 5:
        return list(keys)
    idxs = sorted({0, max(1, n // 4), n // 2, min(n - 2, 3 * n // 4), n - 1})
    chosen = [keys[i] for i in idxs if 0 <= i < n]
    if len(chosen) < 5:
        step = max(1, n // 5)
        chosen = [keys[min(i * step, n - 1)] for i in range(5)]
    return chosen


def bar_chart_data(cash_rows: list[dict]) -> list[dict]:
    """从命名列 cash_rows（dict 含 year/total）里挑 5 个节点构建柱图。

    输入行已按 parser.json 的列映射归一化，因此本函数不含任何产品列下标。
    """
    keys: list[tuple[str, float]] = []
    for r in cash_rows:
        n = num(r.get("total"))
        if n > 0:
            keys.append((str(r.get("year", "")), n))
    out = []
    for label, amount in pick_chart_nodes(keys):
        out.append({"label": normalize_period(label), "amount": amount, "compact": compact(amount)})
    return out


def _irr_npv(r: float, premium: float, term: int, payout: float, n: int) -> float:
    """IRR 目标方程：期初缴费折现 + 期末领取折现 = 0。

    Σ(t=0..term-1) [-premium/(1+r)^t] + payout/(1+r)^n = 0
    """
    total = 0.0
    for t in range(term):
        total -= premium / (1.0 + r) ** t
    total += payout / (1.0 + r) ** n
    return total


def calculate_irr(premium: float, term: int, payout: float, n: int) -> float | None:
    """用二分法求 IRR（年复合收益率），精确到 1e-9。

    规则（严格遵循给定现金流）：
      - 期初每年流出 -premium，共 term 期（t=0..term-1）；
      - 第 n 年末一次性流入 payout；
      - IRR 方程固定为 Σ [-premium/(1+r)^t] + payout/(1+r)^n = 0。
    仅返回精确数值解；无解/非法输入返回 None（绝不估算）。
    """
    if premium <= 0 or term <= 0 or payout <= 0 or n <= term:
        return None
    # r ∈ (-1, +∞)。实际收益率 0~50% 常见；先探测符号区间。
    lo, hi = 0.0, 1.0
    flo = _irr_npv(lo, premium, term, payout, n)
    fhi = _irr_npv(hi, premium, term, payout, n)
    if flo * fhi > 0:
        # 单调递减函数：flo>0 且 fhi<0 为正常；否则按递减方向扩展上界
        if flo > 0 and fhi > 0:
            while hi < 100 and _irr_npv(hi, premium, term, payout, n) > 0:
                hi *= 2
            fhi = _irr_npv(hi, premium, term, payout, n)
        else:
            return None
        if flo * fhi > 0:
            return None
    for _ in range(200):
        mid = (lo + hi) / 2.0
        fm = _irr_npv(mid, premium, term, payout, n)
        if flo * fm <= 0:
            hi = mid
            fhi = fm
        else:
            lo = mid
            flo = fm
        if abs(hi - lo) < 1e-9:
            break
    return (lo + hi) / 2.0


def _age_from_label(label: str) -> int | None:
    """从年龄标签提取年龄：'65 歲'/'80 岁' → 65；纯年度 '10'/'20' → None。"""
    s = (label or "").strip().replace("歲", "岁").replace(" ", "")
    if "岁" not in s:
        return None
    import re as _re
    m = _re.search(r"\d+", s)
    return int(m.group()) if m else None


def irr_pills(
    info: dict,
    scen_rows: list[dict],
    cash_rows: list[dict],
) -> list[dict]:
    """长期收益率 pill —— 总保费 / 100岁满期现金价值 / 各年龄节点 IRR。

    ``scen_rows`` 现金价值情景行（命名列，含 worst_total/best_total），
    ``cash_rows`` 现时假设现金价值行（命名列，含 total）。

    IRR 由现金流方程精确求解（calculate_irr），不使用硬编码值。
    对每个「年龄标签」的行独立计算：期初每期缴 annual_premium 共
    premium_term 期，第 N 年末领取现金价值总额（N = 年龄 - 投保年龄）。
    """
    worst = fmt_amount(num(scen_rows[-1].get("worst_total"))) if scen_rows else "—"
    best = fmt_amount(num(scen_rows[-1].get("best_total"))) if scen_rows else "—"

    currency = str(info.get("currency", "")).strip() or "美元"

    total_premium = fmt_amount(info.get("premium_total", "—"))
    maturity_value = "—"

    premium = num(info.get("annual_premium"))
    term = int(num(info.get("premium_term")))
    age = int(num(info.get("age")))
    base_age = age if age > 0 else None

    pills: list[dict] = [
        {"label": "总保费", "value": total_premium, "unit": currency},
    ]

    # 100 岁满期现金价值（主 pill）
    if cash_rows:
        maturity_row = cash_rows[-1]
        maturity_value = fmt_amount(num(maturity_row.get("total")))
    pills.append({"label": "100 岁满期现金价值", "value": maturity_value, "unit": currency})

    # 各年龄节点 IRR（只对年龄标签行计算）
    irr_pill_labels: list[str] = []
    if premium > 0 and term > 0 and base_age:
        for row in cash_rows:
            target_age = _age_from_label(row.get("year", ""))
            if target_age is None:
                continue
            n = target_age - base_age  # 领取时保单年度
            if n <= term:
                continue  # 领取早于缴费结束 → 现金流定义不符，跳过（不估算）
            payout = num(row.get("total"))
            if payout <= 0:
                continue
            r = calculate_irr(premium, term, payout, n)
            if r is None:
                continue
            pill = {"label": f"{target_age} 岁 IRR", "value": f"{r * 100:.2f}", "unit": "%"}
            pills.append(pill)
            irr_pill_labels.append(str(target_age))

    # 若没有任何年龄 IRR 可用，保留占位（避免空白）
    if not irr_pill_labels:
        pills.append({"label": "长期复合收益率", "value": "—", "unit": "%"})

    return pills


# ── 通用 override 应用 (原 build_llm_cards._apply_override 泛化) ────────


def apply_override(card: dict, override: Any, *, text_slots: tuple[str, ...] = ()) -> None:
    """把用户覆盖文本 apply 到 card 最显眼的字段。

    支持：
      1. str —— 整段文本：若 card.layout 属 ``text_slots``（纯文字卡）写入 body 并清空
         subtitle；否则写入 subtitle。长度 500 截断。
      2. dict —— 结构化覆盖：
           {"subtitle": str, "<slot>": [{{"title","body"}, None, ...}]}
         任意 ``list`` 值会写入同名 slot（与现有 reasons 覆盖语义一致）。

    空字符串 / 不支持类型 = 静默忽略。
    """
    if not override:
        return

    if isinstance(override, str):
        text = override.strip()
        if not text:
            return
        if len(text) > 500:
            text = text[:497] + "…"
        if text_slots and (card.get("layout") or "") in text_slots:
            card["body"] = text
            card["subtitle"] = ""
        else:
            card["subtitle"] = text
        return

    if not isinstance(override, dict):
        return

    if "subtitle" in override:
        sub = (override.get("subtitle") or "").strip()
        if sub:
            if len(sub) > 500:
                sub = sub[:497] + "…"
            card["subtitle"] = sub

    for key, value in override.items():
        if key == "subtitle":
            continue
        # 标量字符串字段：hook/eyebrow/title 等 —— 直接写入同名槽
        if isinstance(value, str):
            text = value.strip()
            if text:
                if key == "title" and len(text) > 120:
                    text = text[:117] + "…"
                elif len(text) > 300:
                    text = text[:297] + "…"
                card[key] = text
            continue
        if not isinstance(value, list):
            continue
        existing = card.get(key)
        if not isinstance(existing, list):
            continue
        for i, item in enumerate(value):
            if i >= len(existing):
                break
            if item is None or not isinstance(item, dict):
                continue
            new_title = (item.get("title") or "").strip()
            new_body = (item.get("body") or "").strip()
            if new_title:
                if len(new_title) > 100:
                    new_title = new_title[:97] + "…"
                existing[i]["title"] = new_title
            if new_body:
                if len(new_body) > 200:
                    new_body = new_body[:197] + "…"
                existing[i]["body"] = new_body


def user_note_card(idx: int, payload: Any) -> dict:
    """用户自定义纯文字卡构造器（idx 为在 cards 里的追加序号，0-based）。"""
    if isinstance(payload, str):
        raw = payload.strip()
        if raw.startswith("{"):
            try:
                import json
                payload = json.loads(raw)
            except Exception:
                payload = {"title": raw, "body": ""}
        else:
            payload = {"title": raw, "body": ""}
    if not isinstance(payload, dict):
        payload = {}
    title = (payload.get("title") or "").strip()
    body = (payload.get("body") or "").strip()
    if len(title) > 80:
        title = title[:77] + "…"
    if len(body) > 500:
        body = body[:497] + "…"
    return {
        "file": f"{idx + 1:02d}_user_note.png",
        "layout": "llm-note",
        "eyebrow": "保险顾问的话",
        "title": title or "（未填标题）",
        "subtitle": body,
        "kicker": "User Note",
    }