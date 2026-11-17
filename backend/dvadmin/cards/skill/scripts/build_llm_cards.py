#!/usr/bin/env python3
"""build_llm_cards.py — 计划书 md → llm 风格 cards.json

参考 frontend/public/llm-refer-card.jpg + guide_line.txt：

  - 3:4 竖版小红书风格
  - 9 张（PWL/LD）/ 10 张（CI 优越版/标准版）
  - 整篇统一 YF 奶油+品牌蓝调性，1-2 张强调卡用品牌红
  - 数据全部"巨号短句"呈现，不放原始表格
  - LLM 仅用于 letter / essay 两张情感卡

支持的 layout（render_llm.py 实现）：
  llm-hero       — 封面 hero（Y 楔形 + 巨标题 + hook）
  llm-summary    — 摘要 ledger（受保人/保额/保费）
  llm-numbers    — 4 数字 2×2（保费/年期/杠杆）
  llm-coverage   — 保障重点 1 巨号 + 3 要点
  llm-multi      — 多次赔付（仅 CI，3 tier 例子）
  llm-chart      — 5 节点条形图（现金价值 + IRR pill）
  llm-irr        — 长期收益率（复利 + 5%）
  llm-4reasons   — 4 个理由（产品价值）
  llm-letter     — 致受保人的一封信（LLM）
  llm-essay      — 人生阶段随笔（LLM）
  llm-company    — 万通公司实力
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

# 复用同级 build_cards.py 的解析函数
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_cards  # noqa: E402

# 资源根目录 (= referral/insurance-proposal-cards/)，用于定位 assets/ 下的实拍图
SKILL_ROOT = Path(__file__).resolve().parents[1]

# llm 风格 LLM（位于 backend/，由 pipeline.py 通过 PYTHONPATH 注入）
try:
    from llm_writer import write_llm_essay, write_llm_letter
    _LLM_OK = True
except Exception as exc:  # pragma: no cover
    sys.stderr.write(f"[build_llm] LLM writer unavailable: {exc}\n")
    _LLM_OK = False


# ── 产品定位文案（沿用 build_guizang_cards.py 的口径）────────────────────


def product_meta(info: dict[str, Any]) -> dict[str, str]:
    """返回产品级品牌文案：plan_name / hook / 适用人群 / 副标题。

    区分 PWL（高端）/ joy（标准）/ ci（标准版/优越版），从 plan_name 中
    自动识别 CI 优越版 vs 标准版。
    """
    plan_name = info.get("plan_name", "")
    product = info.get("product", "pwl")

    if product == "ci":
        if "優越" in plan_name or "优越" in plan_name:
            variant = "优越版"
        else:
            variant = "标准版"
        return {
            "label": "危疾保障",
            "plan_short": "危疾加护保",
            "variant": variant,
            "plan_name": plan_name or f"萬通危疾加護保 ({variant})",
            "english_name": "Critical Illness Protection Plan",
            "audience": "中产 · 白领 · 金领",
            "audience_long": "中产家庭、白领与金领阶层——给家人一份应对重大疾病的安心",
            "hook": "一次诊断 · 一份从容",
            "tagline": "危疾保障 · 悉心守护",
        }
    if product == "joy":
        return {
            "label": "储蓄寿险",
            "plan_short": "尚悦人生",
            "variant": "特级计划",
            "plan_name": plan_name or "尚悅人生壽險計劃 (10年繳付) - 特級計劃",
            "english_name": "LifeDeluxe Insurance Plan",
            "audience": "中产 · 白领 · 金领",
            "audience_long": "中产家庭、白领与金领——以可控保费建立终身保障与稳健增值",
            "hook": "一份保单 · 三代安心",
            "tagline": "储蓄寿险 · 终身保障",
        }
    # 默认 PWL
    return {
        "label": "终身寿险",
        "plan_short": "尚裕",
        "variant": "Preeminence",
        "plan_name": plan_name or "尚裕終身壽險 Preeminence",
        "english_name": "Preeminence Whole Life Plan",
        "audience": "企业主 · 高净值人群",
        "audience_long": "企业主与高净值人群——以高额终身寿险实现财富传承与税务规划",
        "hook": "一份保单 · 一生底气",
        "tagline": "高端终身寿险 · 财富传承",
    }


# ── 4 理由（产品差异化文案）─────────────────────────────────────────────


def four_reasons(info: dict[str, Any]) -> list[dict[str, str]]:
    """每张卡 4 个理由，按产品分差异化短句。"""
    product = info.get("product", "pwl")
    name = info.get("name", "").strip() or "您"
    sum_insured = info.get("sum_insured", "")

    if product == "pwl":
        return [
            {"tag": "01",
             "title": "百万级保额 · 财富传承",
             "body": "百万美元级身故保障，可对接家族信托与企业传承需求"},
            {"tag": "02",
             "title": "港险高保额·内地难承保",
             "body": "高保额保单，内地保险公司很难承保"},
            {"tag": "03",
             "title": "有事保障 · 无事存钱",
             "body": "保证现金价值 + 终期红利，长期复合收益率约 5%"},
            {"tag": "04",
             "title": "起保即享 · 锁定费率",
             "body": "投保通过后即拥有终身保障，费率不再随年龄上涨"},
        ]
    if product == "joy":
        return [
            {"tag": "01",
             "title": "一张保单 · 三代共享",
             "body": "身故保障覆盖配偶与子女，财富有序传承"},
            {"tag": "02",
             "title": "港险性价比 · 优于内地",
             "body": "同等保额下，港险保费更低、回报更具竞争力"},
            {"tag": "03",
             "title": "有事保障 · 无事存钱",
             "body": "保证现金价值 + 累积红利 + 终期红利，复利增长"},
            {"tag": "04",
             "title": "10年缴清 · 终身受保",
             "body": "缴费年期短、保障年期长，尽早锁定终身保障"},
        ]
    # ci
    variant = product_meta(info)["variant"]
    major_benefit = "202,500 / 150,000"
    return [
        {"tag": "01",
         "title": "三层危疾 · 全面覆盖",
         "body": f"早期疾病 / 原位癌 / 主要严重疾病，按严重程度分级赔付"},
        {"tag": "02",
         "title": "早期赔付 10% / 30% / 50%",
         "body": "涵盖 42 种早期疾病 / 30 种原位癌或初期癌症 / 18 种儿童早期重疾"},
        {"tag": "03",
         "title": f"主要危疾 {major_benefit} 美元",
         "body": "首 10 年享 135% 保障（推广优惠），其后 100% 持续守护"},
        {"tag": "04",
         "title": "现金价值 · 不断累积",
         "body": "保证现金价值 + 非保证终期红利，兼顾保障与长线回报"},
    ]


# ── 公司文案 ─────────────────────────────────────────────────────────────


COMPANY_NOTES = [
    {"tag": "01",
     "title": "港交所上市 · 实力背书",
     "body": "云锋金融集团成员，背后是马云旗下金融生态与多家国际机构"},
    {"tag": "02",
     "title": "美国万通人寿 · 战略股东",
     "body": "全美 5 大互惠寿险公司之一，170+ 年寿险经验"},
    {"tag": "03",
     "title": "惠誉 A- 评级 · 财务稳健",
     "body": "国际三大评级机构之一给予「A-」（强劲）保险财务实力评级"},
    {"tag": "04",
     "title": "分红比例 ≥ 90%",
     "body": "分红保单目标：将不少于 90% 可分配盈余分配给保单持有人"},
]


# ── 多次赔付示例（仅 CI）─────────────────────────────────────────────────


CI_MULTI_CLAIM_EXAMPLES = [
    {
        "label": "首次主要危疾",
        "amount": "$202,500",
        "note": "135% 基本保障额（首 10 年推广优惠）",
        "year": "保单第 3 年",
    },
    {
        "label": "二次主要危疾",
        "amount": "$150,000",
        "note": "100% 基本保障额（不同疾病组）",
        "year": "保单第 8 年",
    },
    {
        "label": "三次主要危疾",
        "amount": "$150,000",
        "note": "100% 基本保障额（不同疾病组）",
        "year": "保单第 15 年",
    },
]


# ── 早期危疾示例（仅 CI 标准版）───────────────────────────────────────
# 强调 (標準版) 同样覆盖早期疾病/原位癌/儿童早期重疾, 但赔付比例与年龄
# 限制因病种细分而异, 简化为单一 $75,000 会丢失这些产品信息。
# 参考计划书 (不同投资回报下说明的"早期危疾"表), 三档的赔付规则:

#   1. 42 种早期疾病 —— 6 类细分, 10% / 30% / 50% 混搭
#      - 需手术之脑血管瘤: 50% (至 100 岁)
#      - 冠状动脉血管成形术: 30% × 最多 2 次 (至 100 岁)
#      - 黄斑部病变 / 早发性白内障: 30% (至 100 岁)
#      - 青光眼手术: 10% (至 65 岁)
#      - 骨质疏松症伴骨折: 30% (至 70 岁)
#      - 其他 37 种早期疾病: 30% (至 100 岁)
#   2. 30 种原位癌 / 初期癌症: 30% 基本保障额, 最多 1 次, 至 100 岁
#   3. 18 种儿童严重疾病: 30% 基本保障额, 18 项合共最多 1 次, 至 25 岁
#      (注意年龄上限是 25, 与成人保障不同)

CI_STD_EARLY_EXAMPLES = [
    {
        "label": "早期疾病",
        "amount": "10% / 30% / 50%",
        "note": "42 种 · 6 类细分 (青光眼 10% · 血管成形 30% × 2 · 脑血管瘤 50%)",
        "year": "至 100 / 65 / 70 岁",
    },
    {
        "label": "原位癌 / 初期癌症",
        "amount": "30%",
        "note": "30 种 · 最多可获赔偿 1 次",
        "year": "至 100 岁",
    },
    {
        "label": "儿童严重疾病",
        "amount": "30%",
        "note": "18 种 · 18 项合共最多 1 次",
        "year": "至 25 岁",
    },
]


# ── 卡片构建 ─────────────────────────────────────────────────────────────


def _num(v: Any) -> float:
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


def _fmt_amount(v: Any) -> str:
    """1,234,567 → '1,234,567' （不带单位）"""
    n = _num(v)
    if n == 0:
        return "—"
    if n >= 1000:
        return f"{n:,.0f}"
    return f"{n:.0f}"


def _compact(v: Any) -> str:
    """数字压缩：1,130,000 → '$1.13M'；407,000 → '$407K'；27,664 → '$27,664'"""
    n = _num(v)
    if n == 0:
        return "—"
    if n >= 1_000_000:
        return f"${n/1_000_000:.2f}M"
    if n >= 1_000:
        return f"${n/1_000:.0f}K"
    return f"${n:,.0f}"


def _salutation(info: dict) -> str:
    """根据 name + gender 生成称呼。

    重要：PDF 提取的 name 可能已含「先生/女士」(如 "Mr. Peng先生")，避免重复。
    也兼容 "Mr./Ms./Dr." 英文称谓 + "先生/女士" 同时存在的混合格式。
    """
    name = (info.get("name") or "").strip()
    gender = (info.get("gender") or "").strip()
    # 已含中文称谓 — 不再追加
    if name.endswith("先生") or name.endswith("女士"):
        return name
    # 已含英文称谓 + 性别 — 追加对应中文称谓
    if "女" in gender:
        return f"{name}女士" if name else "女士"
    if "男" in gender:
        return f"{name}先生" if name else "先生"
    return name or "您"


# 防御性 strip：LLM 经常在正文开头加 "亲爱的XXX："，与页面已有称呼重复。
# 这里剥掉最常见的几种开头，让正文真正从内容开始。
# 字符类只排除冒号/句号/换行 —— 名字里可能含空格（"Mr. Peng"）、小数点（"Ms."），都允许。
_SALUTATION_PREFIX_RE = re.compile(
    r"^\s*(亲爱的|您好|敬启者|致)\s*[^：:\n。]{1,60}[：:]\s*\n+"
)
# 防御性 strip：LLM 经常在信末写「此致 敬礼 您的保险顾问」，与 renderer
# 自带的 .article-sig 装饰块重复。允许中间夹空行 / 不同空白 / 「此致」前可空。
_SIGNATURE_SUFFIX_RE = re.compile(
    r"\n*\s*(?:此致|此致\n敬礼|\s*此\s*致)\s*\n+敬\s*礼\s*\n+\s*您的保险顾问\s*$"
)


def _strip_salutation_prefix(body: str) -> str:
    """如果 LLM 输出的 body 开头是「亲爱的XXX：」之类的称呼行，剥掉它。"""
    if not body:
        return body
    return _SALUTATION_PREFIX_RE.sub("", body, count=1)


def _strip_signature_suffix(body: str) -> str:
    """如果 LLM 在信末自己写了「此致/敬礼/您的保险顾问」, 剥掉以避免和
    render_letter 的 .article-sig 装饰块重复显示。"""
    if not body:
        return body
    return _SIGNATURE_SUFFIX_RE.sub("", body, count=1)


def _normalize_period(label: str) -> str:
    """把 years 表的「保单年度/受保人年龄」标签统一成可读格式。

    输入 (来自 md2-所有保单年.md 首列):
      - '10'            → '10年'   (单纯数字 = 保单年度)
      - '10年'          → '10年'
      - '65 歲' / '65歲' → '65岁' (数字+岁/歲 = 受保人年龄)
      - '65 岁'         → '65岁'

    关键修正：之前把「歲」盲替成「年」，导致 100 岁错显为 100 年
    （这是年龄不是保单年度），现按原始语义保留岁/年。
    """
    s = (label or "").strip()
    # 繁简统一 -> 简
    s = s.replace("歲", "岁")
    # 去除所有空白（半角/全角空格）便于判断
    s_no_space = s.replace(" ", "").replace("　", "")
    if s_no_space.endswith("岁"):
        return s_no_space
    if s_no_space.endswith("年"):
        return s_no_space
    # 纯数字 -> 视为保单年度
    return f"{s_no_space}年"


def _bar_chart_data(cash_rows, scen_rows, info) -> list[dict]:
    """从 years 表现金价值表里挑 5 个时间节点构建柱图数据。

    cash_rows[i] 来自 build_cards.collect_rows(), 列值是带逗号的字符串如
    "1,234,567", 因此必须先 _num() 转 float 再做除法/比较, 否则
    render_llm.py 里的 `v / max_v` 会 TypeError.

    节点选择策略（用 md2-所有保单年.md 的原始标签，保留岁/年区分）:
      1) cash_rows 首 5 行直接采用 —— 大多数计划书前 5 行就是连续保单年度
         (10/20/25/30/...) 或 (20/30/40/...), 已经是合理的「均匀间隔」
      2) 若 cash_rows 不足 5 行, 用等距下标补齐
      3) 若 cash_rows 超过 5 行, 用「5 等分点」抽取: 0, n/4, n/2, 3n/4, n-1
         —— 这就是「consistent period」: 永远是首/中/末均匀分布
    """
    if not cash_rows:
        return []
    product = info.get("product", "pwl")
    # joy: [year, premiums_total, guaranteed, div_int, terminal, total] (6 cols, total=5)
    # pwl/ci: [year, premiums_total, guaranteed, terminal, total] (5 cols, total=4)
    total_idx = 5 if product == "joy" else 4
    keys: list[tuple[str, float]] = []
    for r in cash_rows:
        if len(r) > total_idx:
            n = _num(r[total_idx])
            if n > 0:
                keys.append((str(r[0]), n))

    n = len(keys)
    if n == 0:
        return []

    # ── 选 5 个节点 (consistent period: 始终均匀分布) ──
    if n <= 5:
        chosen = list(keys)
    else:
        # 5 等分: {0, n/4, n/2, 3n/4, n-1}, 整数化并去重
        idxs = sorted({0, max(1, n // 4), n // 2, min(n - 2, 3 * n // 4), n - 1})
        chosen = [keys[i] for i in idxs if 0 <= i < n]
        # 万一上面去重后 < 5, 退回简单等距
        if len(chosen) < 5:
            step = max(1, n // 5)
            chosen = [keys[min(i * step, n - 1)] for i in range(5)]

    out = []
    for label, amount in chosen:
        out.append({
            "label": _normalize_period(label),
            "amount": amount,
            "compact": _compact(amount),
        })
    return out


def _irr_pills(info: dict, scen_rows, cash_rows) -> list[dict]:
    """长期收益率 pill —— 4 个关键数字, 一行排开。

    1. 总保费 (从 info.premium_total, 单笔/趸交/期缴 都适用)
    2. 100 岁满期现金价值 (取 cash_rows 最后一行 = 100 歲的现时假设总额,
       这是「正常情况下」的数字, 不是悲观/乐观两端)
    3. 长期复合收益率 (现时假设基础下的演示 IRR ≈ 5.0%)
    4. 杠杆倍数 (身故保额 / 年缴保费) —— 单独一列
    """
    product = info.get("product", "pwl")
    if scen_rows:
        # joy: 悲观在 [5], 乐观在 [8] (per build_guizang_cards.py scen_card_rows)
        # pwl/ci: 悲观在 [4], 乐观在 [6]
        if product == "joy":
            worst_idx, best_idx = 5, 8
        else:
            worst_idx, best_idx = 4, 6
        last = scen_rows[-1]
        worst = _num(last[worst_idx]) if len(last) > worst_idx else 0
        best = _num(last[best_idx]) if len(last) > best_idx else 0
        worst = _fmt_amount(worst)
        best = _fmt_amount(best)
    else:
        best, worst = "—", "—"

    total_premium = _fmt_amount(info.get("premium_total", "—"))

    # 100 岁满期现金价值: cash_rows 末行 (100 歲) 的现时假设总额。
    # pwl/ci: 列 0=year 1=premiums 2=guaranteed 3=terminal 4=total
    # joy:    列 0=year 1=premiums 2=guaranteed 3=div_int 4=terminal 5=total
    total_idx = 5 if product == "joy" else 4
    maturity_value = "—"
    if cash_rows:
        last = cash_rows[-1]
        if len(last) > total_idx:
            maturity_value = _fmt_amount(_num(last[total_idx]))

    return [
        {"label": "总保费", "value": total_premium, "unit": "美元"},
        {"label": "100 岁满期现金价值", "value": maturity_value, "unit": "美元"},
        {"label": "长期复合收益率", "value": "≈ 5.0", "unit": "%"},
    ]


def build_llm_cards(
    info: dict[str, Any],
    years_tables,
    scenario_tables,
) -> list[dict]:
    """构造 llm 风格的卡片列表（每张 dict 含 file / layout / data 字段）。"""
    meta = product_meta(info)
    product = info.get("product", "pwl")
    is_ci = product == "ci"

    cash_keys = ["10", "20", "25", "30", "65 歲", "75 歲", "80 歲", "100 歲"]
    scen_keys = ["10", "20", "25", "30", "80 歲", "100 歲"]

    cash_rows, cash_missing = build_cards.collect_rows(years_tables, cash_keys)
    scen_tables_cash = [t for t in scenario_tables if "現金" in t.get("title", "") or "现金" in t.get("title", "")]
    if not scen_tables_cash and scenario_tables:
        scen_tables_cash = [scenario_tables[0]]
    scen_rows, scen_missing = build_cards.collect_rows(scen_tables_cash, scen_keys) if scen_tables_cash else ([], [])

    if not cash_rows:
        raise SystemExit("[build_llm] 未找到现金价值表行，请人工检查所有保单年 md。")
    if not scen_rows:
        raise SystemExit("[build_llm] 未找到情景表行，请人工检查不同投资回报 md。")

    sum_insured = _fmt_amount(info.get("sum_insured", "—"))
    annual_premium = _fmt_amount(info.get("annual_premium", info.get("annual_premium_plan", "—")))
    premium_term = info.get("premium_term", "—")
    # 保障年期格式化: CI 是 "至 100 岁" 这种; PWL/LD 是 "终身"
    if is_ci:
        policy_term_display = f"至 {info.get('policy_term', 100)} 岁"
    else:
        policy_term_display = "终身"
    salutation = _salutation(info)

    # 卡片总数
    total_cards = 10 if is_ci else 9

    cards: list[dict] = []

    # ── 01 hero ─────────────────────────────────────────────────────
    # hero_image: 按产品类型 + 变体指向 assets/ 下的对应实拍图。
    # 缺图时 render_hero 自动回退到极简双斜线占位，
    # 所以新增/替换图只需在 SKILL_ROOT/assets/ 下放入同名文件即可。
    # CI 产品区分标准版/优越版（plan_name 关键字识别），分别走不同图。
    if product == "ci":
        variant_key = "advanced" if "优越" in meta["variant"] else "standard"
        ci_image_map = {
            "standard": SKILL_ROOT / "assets" / "ci-standard-hero.jpg",
            "advanced": SKILL_ROOT / "assets" / "ci-advanced-hero.jpg",
        }
        hero_image_path = ci_image_map[variant_key]
    else:
        hero_image_path = {
            "pwl": SKILL_ROOT / "assets" / "pwl-hero.jpg",
            "joy": SKILL_ROOT / "assets" / "joy-hero.jpg",
        }.get(product)
    if hero_image_path and not hero_image_path.exists():
        hero_image_path = None

    cards.append({
        "file": "01_hero.png",
        "layout": "llm-hero",
        # 删掉 "· 2026 Q1 计划书概览" — 这是一款长期在售的产品，季度不应当印在封面上
        "eyebrow": meta["tagline"],
        "title": meta["plan_name"],
        "title_zh_short": f"{meta['plan_short']}寿险计划" if not is_ci else f"{meta['plan_short']}({meta['variant']})",
        "english_name": meta["english_name"],
        "hook": meta["hook"],
        "salutation": salutation,
        "audience": meta["audience"],
        "age": info.get("age", ""),
        "product_label": meta["label"],
        "variant": meta["variant"],
        "kicker": "封面 · Cover",
        "stats": [
            {"label": "保额 / 身故保障", "value": f"${sum_insured}", "unit": "美元"},
            {"label": "年缴保费", "value": f"${annual_premium}", "unit": "美元/年"},
            {"label": "缴费年期", "value": f"{premium_term}", "unit": "年"},
        ],
        "hero_image": str(hero_image_path) if hero_image_path else None,
    })

    # ── 02 summary ──────────────────────────────────────────────────
    items = [
        ("受保人", info.get("name", "—")),
        ("性别 / 年龄", f"{info.get('gender', '—')} / {info.get('age', '—')} 岁"),
        ("吸烟状况", info.get("smoking", "—")),
        ("居住国家组别", info.get("country_group", "—")),
        ("保单货币", info.get("currency", "—")),
        ("保障额", f"${sum_insured} 美元"),
        ("年保费", f"${annual_premium} 美元 / 年"),
        ("缴费年期", f"{premium_term} 年"),
        ("保障年期", policy_term_display),
        ("适用人群", meta["audience"]),
    ]
    cards.append({
        "file": "02_summary.png",
        "layout": "llm-summary",
        "eyebrow": "保障摘要",
        "title": "一份保单 · 看懂核心",
        "subtitle": f"受保人 {info.get('name', '')} · {meta['plan_short']}({meta['variant']})" if is_ci else f"受保人 {info.get('name', '')} · {meta['plan_short']}",
        "kicker": "摘要 · Summary",
        "items": items,
    })

    # ── 03 numbers (4 数字 2×2) ──────────────────────────────────────
    # 杠杆: 首年 death / annual_premium
    initial_irr_label = "≈ 5.0%"  # placeholder; will be re-computed in irr card
    cards.append({
        "file": "03_numbers.png",
        "layout": "llm-numbers",
        "eyebrow": "4 个数字 · 读懂保单",
        "title": "一眼读懂的关键",
        "subtitle": f"{info.get('age', '')}岁 · {info.get('gender', '')} · {info.get('smoking', '标准体')}",
        "kicker": "数据 · Key Numbers",
        "stats": [
            {"label": "保额", "value": f"${sum_insured}", "unit": "美元"},
            {"label": "年缴保费", "value": f"${annual_premium}", "unit": "美元/年"},
            {"label": "缴费年期", "value": f"{premium_term}", "unit": "年"},
            {"label": "保障年期", "value": policy_term_display, "unit": ""},
        ],
    })

    # ── 04 coverage ─────────────────────────────────────────────────
    if is_ci:
        # CI 保障重点: 早期 + 主要两大模块, 早期赔付上限统一为 50% 基本保障额
        # (产品条款均如此; 标准版/优越版在「多次赔付」权益上有差异, 见 05 卡分流)
        cov_items = [
            {"k": "早期危疾", "v": "最高 $75,000 (50%)",
             "note": "42 种早期疾病 / 30 种原位癌或初期癌症 / 18 种儿童早期重疾"},
            {"k": "主要严重疾病", "v": "$150,000 (100%)", "note": "首 10 年 $202,500 (135%)"},
            {"k": "保障年期", "v": policy_term_display, "note": "终身保障"},
            {"k": "推广优惠", "v": "首 10 年额外 35%", "note": "即 $52,500 美元"},
        ]
        cov_title = "重大疾病保障"
        # 早期 + 主要 是两个独立模块, 不用「悉心守护 · 早 + 中 + 重」副标
        # (避免误导受众以为有「中疾」这一类不存在的中间档)
        cov_subtitle = ""
    else:
        cov_items = [
            {"k": "身故保障", "v": f"${sum_insured}", "note": "起保即享"},
            {"k": "保证现金价值", "v": "逐年递增", "note": "经济环境如何均提供"},
            {"k": "终期红利", "v": "非保证", "note": f"第3年起每年公布"},
            {"k": "保障年期", "v": policy_term_display, "note": "终身保障"},
        ]
        cov_title = "保什么"
        cov_subtitle = "身故 + 现金价值 + 终期红利"
    cards.append({
        "file": "04_coverage.png",
        "layout": "llm-coverage",
        "eyebrow": "保障重点",
        "title": cov_title,
        "subtitle": cov_subtitle,
        "kicker": "保障 · Coverage",
        # headline 不再带「美元」—— render_coverage 的 <span class="u"> 美元 </span> 会自动追加，
        # 避免出现「$10,000,000 美元美元」重复
        "headline": f"${sum_insured}",
        "headline_label": "起保即享的保障额",
        "items": cov_items,
    })

    # ── 05 (仅 CI) 多次赔付 / 早期危疾 ─────────────────────────────
    # 优越版: 「不止一次·三次守护」(不同疾病组累计赔付 100% × 3) 是核心卖点
    # 标准版: 没有多次赔付权益, 改用「早期危疾·亦有保障」强调早期疾病覆盖
    if is_ci:
        if "优越" in meta["variant"]:
            cards.append({
                "file": "05_multi.png",
                "layout": "llm-multi",
                "eyebrow": "多次重疾赔付",
                "title": "不止一次 · 三次守护",
                "subtitle": "不同疾病组可累计赔付至 100% × 3",
                "kicker": "赔付 · Multi-claim",
                "examples": CI_MULTI_CLAIM_EXAMPLES,
            })
        else:
            cards.append({
                "file": "05_multi.png",
                "layout": "llm-multi",
                "eyebrow": "早期危疾保障",
                "title": "早期危疾 · 亦有保障",
                "subtitle": "按病种与严重程度, 分级赔付",
                "kicker": "保障 · Early Stage",
                "examples": CI_STD_EARLY_EXAMPLES,
            })

    # ── chart (5/6 节点现金价值) ────────────────────────────────────
    bars = _bar_chart_data(cash_rows, scen_rows, info)
    chart_idx = "06" if is_ci else "05"
    cards.append({
        "file": f"{chart_idx}_chart.png",
        "layout": "llm-chart",
        "eyebrow": "时间 × 价值",
        "title": "5 个节点 · 看懂增长",
        "subtitle": "现金价值随保单年度稳步增长",
        "kicker": "图表 · Cash Value",
        "bars": bars,
    })

    # ── irr ─────────────────────────────────────────────────────────
    irr_idx = "07" if is_ci else "06"
    cards.append({
        "file": f"{irr_idx}_irr.png",
        "layout": "llm-irr",
        "eyebrow": "长期收益率",
        "title": "时间替你 · 累积复利",
        "subtitle": "保单长线持有，复利效应显著",
        "kicker": "收益率 · IRR",
        "pills": _irr_pills(info, scen_rows, cash_rows),
        "narrative": "有事保障，无事存钱——长期复合收益率约 5%，"
                     "让时间成为您最忠实的伙伴。",
    })

    # ── 4 reasons ───────────────────────────────────────────────────
    reasons_idx = "08" if is_ci else "07"
    cards.append({
        "file": f"{reasons_idx}_reasons.png",
        "layout": "llm-4reasons",
        "eyebrow": "为什么选这份保单",
        "title": "4 个理由 · 说清价值",
        "subtitle": "不是「保单有什么」，是「为什么选它」",
        "kicker": "价值 · Reasons",
        "reasons": four_reasons(info),
    })

    # ── letter (LLM) ────────────────────────────────────────────────
    letter_idx = "09" if is_ci else "08"
    letter_body = ""
    if _LLM_OK:
        try:
            letter_body = write_llm_letter(info)
        except Exception as exc:
            sys.stderr.write(f"[build_llm] letter LLM failed: {exc}\n")
    # 防御性剥离 LLM 在 body 开头加的「亲爱的XXX：」称呼行，避免与页面已有称呼重复
    letter_body = _strip_salutation_prefix(letter_body)
    # 防御性剥离 LLM 在信末自带的「此致/敬礼/您的保险顾问」三行落款，
    # render_letter 的 .article-sig 装饰块会统一负责这部分。
    letter_body = _strip_signature_suffix(letter_body)
    cards.append({
        "file": f"{letter_idx}_letter.png",
        "layout": "llm-letter",
        "eyebrow": "致受保人",
        "title": "致受保人的一封信",
        "subtitle": f"写给 {info.get('name', '您')} 的一段话",
        "kicker": "信笺 · Letter",
        "body": letter_body,
        "salutation": salutation,
        "pullquote": "一份保障，是一句无需开口的承诺。",
    })

    # ── essay (LLM) ─────────────────────────────────────────────────
    essay_idx = "10" if is_ci else "09"
    essay_body = ""
    if _LLM_OK:
        try:
            essay_body = write_llm_essay(info)
        except Exception as exc:
            sys.stderr.write(f"[build_llm] essay LLM failed: {exc}\n")
    cards.append({
        "file": f"{essay_idx}_essay.png",
        "layout": "llm-essay",
        "eyebrow": "保障与人生阶段",
        "title": f"{info.get('age', '')}岁的保障 · 此生的安心",
        "subtitle": "保费可控 / 年期长 / 复利积累",
        "kicker": "随笔 · Essay",
        "body": essay_body,
        "pullquote": "把不确定性留在门外，把确定性交给保单。",
    })

    # ── company (fixed) ─────────────────────────────────────────────
    company_idx = "11" if is_ci else "10"
    cards.append({
        "file": f"{company_idx}_company.png",
        "layout": "llm-company",
        "eyebrow": "承保公司",
        "title": "万通保险 · 实力背书",
        "subtitle": "YF Life · 国际保险集团",
        "kicker": "公司 · Company",
        "items": COMPANY_NOTES,
    })

    # 给每张卡补 total 字段
    total = len(cards)
    for c in cards:
        c["total"] = total

    return cards


def _apply_override(card: dict, override) -> None:
    """整体替换: 把 override 文本塞到该卡片最显眼的字段.

    支持两种格式:
      1. str  (向后兼容): 整段文本.
         - llm-letter / llm-essay 卡 (纯文字): 写入 body, 清空 subtitle 避免重复
         - 其他卡 (数据/图表为主): 写入 subtitle (副标是用户最常注意的位置)
         - 空字符串 = 跳过, 保留自动生成内容
         - 超过 500 字符硬截断

      2. dict  (新): 结构化覆盖, 用于「4 个理由」卡等带 items 列表的卡片.
         - {"subtitle": "...", "reasons": [{"title": "...", "body": "..."}, ...]}
         - subtitle: 可选, 非空时整体替换副标
         - reasons:  可选, 数组, 每个元素是 {"title", "body"} 或 null
           - 数组下标 i 对应 card["reasons"][i]
           - null/缺失 = 该条保留原值; 字段为空字符串 = 单独清空该字段
           - 超过原 reasons 长度 = 忽略

    不支持的类型 (int / list 等) = 静默忽略, 保留自动生成.
    """
    if not override:
        return

    # ── 格式 1: 整段字符串 (向后兼容) ──
    if isinstance(override, str):
        text = override.strip()
        if not text:
            return
        if len(text) > 500:
            text = text[:497] + "…"
        layout = card.get("layout", "")
        if layout in ("llm-letter", "llm-essay"):
            card["body"] = text
            card["subtitle"] = ""
        else:
            card["subtitle"] = text
        return

    # ── 格式 2: 结构化 dict (用于 4 个理由 等多 item 卡片) ──
    if not isinstance(override, dict):
        return

    # 副标覆盖 (可选)
    if "subtitle" in override:
        sub = (override.get("subtitle") or "").strip()
        if sub:
            if len(sub) > 500:
                sub = sub[:497] + "…"
            card["subtitle"] = sub

    # reasons 数组覆盖 (用于 llm-4reasons 卡)
    if "reasons" in override and isinstance(override["reasons"], list):
        existing = card.get("reasons")
        if not isinstance(existing, list):
            return
        for i, item in enumerate(override["reasons"]):
            if i >= len(existing):
                break
            if item is None:
                continue
            if not isinstance(item, dict):
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


def _make_user_note_card(idx: int, payload: Any) -> dict:
    """用户追加的「纯文字卡」(idx >= 11) 构造器。

    payload 既可能是:
      - dict {"title": "...", "body": "..."} (前端自定义卡)
      - str (简单覆盖, 当作 title)
      - 嵌套 JSON 字符串 (前端 JSON.stringify({title, body})) — 内部尝试再解一次

    返回一张 llm-note 布局的卡片, 由 render_llm.py 渲染.
    """
    # 防御性: 如果 payload 是字符串, 先尝试解析成 dict (前端常把 {title, body}
    # 二次 JSON 编码, 这里主动解开一层).
    if isinstance(payload, str):
        raw = payload.strip()
        if raw.startswith("{"):
            try:
                payload = json.loads(raw)
            except Exception:
                # 不是合法 JSON, 退化为整段作为 title
                payload = {"title": raw, "body": ""}
        else:
            payload = {"title": raw, "body": ""}
    if not isinstance(payload, dict):
        payload = {}
    title = (payload.get("title") or "").strip()
    body = (payload.get("body") or "").strip()
    # 截断
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


def _collect_user_notes(overrides: dict[str, Any]) -> list[dict]:
    """从 overrides 提取 idx>=11 的条目, 构造 llm-note 卡片列表."""
    notes: list[dict] = []
    for k, v in overrides.items():
        try:
            idx = int(k)
        except (TypeError, ValueError):
            continue
        if idx >= 11 and (isinstance(v, str) and v.strip() or isinstance(v, dict)):
            notes.append(_make_user_note_card(idx, v))
    # 按 idx 升序, 保证页码连续
    notes.sort(key=lambda c: c["file"])
    return notes


def main():
    parser = argparse.ArgumentParser(description="计划书 md → Pru cards.json")
    parser.add_argument("output_dir", type=str, help="包含三个 md 的目录")
    parser.add_argument("--output", type=str, default="cards.json")
    parser.add_argument("--overrides", type=str, default="{}",
                        help='JSON dict {card_idx: text | {"title":..,"body":..}}')
    args = parser.parse_args()

    # 解析 overrides (空字符串/None 视作空 dict)
    try:
        overrides = json.loads(args.overrides) if (args.overrides or "").strip() else {}
        if not isinstance(overrides, dict):
            overrides = {}
    except Exception as exc:
        sys.stderr.write(f"[build_llm] overrides JSON 解析失败, 忽略: {exc}\n")
        overrides = {}

    files = build_cards.load_md_files(args.output_dir)
    missing_files = [k for k in ("first", "years", "scenario") if k not in files]
    if missing_files:
        print(f"缺少数据文件: {missing_files} 在 {args.output_dir}")
        sys.exit(1)

    first_text = open(files["first"], encoding="utf-8").read()
    years_text = open(files["years"], encoding="utf-8").read()
    scenario_text = open(files["scenario"], encoding="utf-8").read()

    info = build_cards.parse_first_page(first_text)
    required = ["name", "age", "sum_insured", "annual_premium", "premium_term"]
    for k in required:
        if k not in info:
            print(f"首页信息缺少字段: {k}")
            sys.exit(1)

    years_tables = build_cards.parse_md_tables(years_text)
    scenario_tables = build_cards.parse_md_tables(scenario_text)

    cards = build_llm_cards(info, years_tables, scenario_tables)

    # 应用用户对已有 10/11 张的文案覆盖
    for i, card in enumerate(cards):
        _apply_override(card, overrides.get(str(i)))

    # 追加用户自定义纯文字卡 (idx>=11)
    user_notes = _collect_user_notes(overrides)
    if user_notes:
        cards.extend(user_notes)
        # 重新计算 total (因为多了自定义卡)
        total = len(cards)
        for c in cards:
            c["total"] = total
        print(f"[build_llm] 追加 {len(user_notes)} 张用户自定义卡")

    meta = {
        "title": product_meta(info)["plan_short"],
        "width": 1080,
        "height": 1440,
        "theme": "yf-cream",
        "style": "llm",
        "footer": "仅供说明参考 · 一切以保单条款为准",
    }

    payload = {"meta": meta, "cards": cards}
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"Pru cards.json 已生成: {args.output}")
    print(f"卡片数: {len(cards)} (产品: {info.get('product', 'unknown')}, 变体: {product_meta(info)['variant']})")
    if overrides:
        keys = sorted([k for k in overrides.keys() if int(k) < 11], key=lambda x: int(x))
        notes = sorted([k for k in overrides.keys() if int(k) >= 11], key=lambda x: int(x))
        if keys:
            print(f"  覆盖 {len(keys)} 张已有卡: idx={keys}")
        if notes:
            print(f"  追加 {len(notes)} 张用户卡: idx={notes}")


if __name__ == "__main__":
    main()
