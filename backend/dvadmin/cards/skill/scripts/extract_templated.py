#!/usr/bin/env python3
"""extract_templated.py — 通用数据提取器（由 parser.json 驱动）.

输入：extract_proposal.py 生成的三个 md + products/<id>/parser.json.
输出：标准化的 data.json —— 首页 info + 命名列的 cash/death/scenario 行.

与 build_cards.parse_first_page / collect_rows 的区别：所有产品差异
（首页字段正则、表列下标、关键年度）全部来自 parser.json，代码不再
出现 ``if product == ...`` 分支。

用法:
  python extract_templated.py <output_dir> --parser products/pwl/parser.json
    --output data.json

  output_dir 内应包含 *-首页信息.md / *-所有保单年.md / *-不同投资回报.md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import card_lib  # noqa: E402


# ── 首页信息解析（parser.json first_page.extractors 驱动）──────────────


def apply_extractors(text: str, extractors: list[dict]) -> dict:
    """逐行应用命名正则提取器，按捕获顺序填入 fields。"""
    info: dict = {}
    for ex in extractors:
        fields = ex["fields"]
        regex = ex["regex"]
        for line in text.splitlines():
            m = re.search(regex, line)
            if not m:
                continue
            for i, f in enumerate(fields):
                if i < len(m.groups()):
                    info[f] = m.group(i + 1).strip()
            break  # 一行匹配即停，避免重复覆盖
    return info


def parse_plan_row(text: str, plan_row: dict | None) -> dict:
    """从产品代码行提取 sum_insured / premium_term / annual_premium_plan.

    模式 pwl: 找到含 PWL 代码的行，取代码前为 plan_name，代码后 ≥3 个数字
              依次为 sum_insured / premium_term / annual_premium_plan。
    模式 joy: 扫描 LDxx 行（LD1Pxx 特选 / LD2Pxx 特级），取满足 ≥3 个数字的
              行（跳过 rider LD2R 或数字不足的行）。
    """
    if not plan_row:
        return {}
    mode = plan_row.get("mode")
    code_re = plan_row.get("code_re", "")
    targets = plan_row.get("targets", ["sum_insured", "premium_term", "annual_premium_plan"])
    out: dict = {}

    if mode == "pwl":
        for line in text.splitlines():
            m = re.search(code_re, line) if code_re else None
            if not m:
                continue
            plan_name = line[: m.start()].strip()
            if plan_name.endswith("("):
                plan_name = plan_name[:-1].strip()
            nums = re.findall(r"[\d,]+\.?\d*", line[m.end():])
            if len(nums) >= 3:
                out["sum_insured"] = nums[0]
                out["premium_term"] = nums[1]
                out["annual_premium_plan"] = nums[-1]
                out["plan_name"] = plan_name
                break
    elif mode == "joy":
        for line in text.splitlines():
            m = re.search(code_re, line)
            if not m:
                continue
            plan_name = line[: m.start()].strip()
            if plan_name.endswith("("):
                plan_name = plan_name[:-1].strip()
            nums = re.findall(r"[\d,]+\.?\d*", line[m.end():])
            if len(nums) >= 3:
                out["sum_insured"] = nums[0]
                out["premium_term"] = nums[1]
                out["annual_premium_plan"] = nums[-1]
                out.setdefault("plan_name", plan_name)
                break

    return out


# ── 表格行提取（parser.json tables.*.cols 驱动）───────────────────────


def _pick(row: list, colmap: dict, names: tuple) -> dict:
    """按列名→下标的映射，从原始行抽出命名列。"""
    out = {}
    for name in names:
        idx = colmap.get(name)
        if idx is not None and idx < len(row):
            out[name] = str(row[idx]).strip()
    return out


def collect_named_rows(tables: list[dict], key_periods: list[str], colmap: dict, names: tuple) -> list[dict]:
    """收集关键年度行并转成命名列。missing 的年度跳过。"""
    rows = []
    for k in key_periods:
        for t in tables:
            for r in t["rows"]:
                if r and r[0].strip() == str(k):
                    rows.append(_pick(r, colmap, names))
                    break
            else:
                continue
            break
    return rows


# ── 变体识别（parser.json variant.rules 驱动）─────────────────────────


def detect_variant(text: str, variant_cfg: dict | None) -> str:
    if not variant_cfg or not variant_cfg.get("rules"):
        return ""
    for rule in variant_cfg["rules"]:
        if any(k in text for k in rule.get("keywords", [])):
            return rule["key"]
    return ""


# ── 主流程 ──────────────────────────────────────────────────────────────


def load_md_files(output_dir: Path) -> dict:
    files = {}
    for f in output_dir.iterdir():
        if not f.name.endswith(".md"):
            continue
        if "首页信息" in f.name:
            files["first"] = f
        elif "所有保单年" in f.name:
            files["years"] = f
        elif "不同投资回报" in f.name:
            files["scenario"] = f
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description="md + parser.json → data.json")
    parser.add_argument("output_dir", type=str, help="含三个 md 的目录")
    parser.add_argument("--parser", type=str, required=True, help="products/<id>/parser.json")
    parser.add_argument("--output", type=str, default="data.json")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    parser_path = Path(args.parser)
    parser_cfg = json.loads(parser_path.read_text(encoding="utf-8"))

    files = load_md_files(out_dir)
    missing = [k for k in ("first", "years", "scenario") if k not in files]
    if missing:
        print(f"缺少数据文件: {missing} 在 {out_dir}", file=sys.stderr)
        return 1

    first_text = files["first"].read_text(encoding="utf-8")
    years_text = files["years"].read_text(encoding="utf-8")
    scenario_text = files["scenario"].read_text(encoding="utf-8")

    # ── 首页 info ──
    info = apply_extractors(first_text, parser_cfg.get("first_page", {}).get("extractors", []))
    info.update(parse_plan_row(first_text, parser_cfg.get("first_page", {}).get("plan_row")))
    # annual_premium 缺失时回退 plan 行年保费
    if "annual_premium" not in info and "annual_premium_plan" in info:
        info["annual_premium"] = info["annual_premium_plan"]

    # premium_total 语义：真正总保费 = 年保费 × 缴费年期。
    # 首页提取的「投保時保費及徵費總額」含征费，不适合当「总保费」展示，
    # 因此计算后覆盖；原值保留到 premium_total_with_levy 供需要时使用。
    _ap = card_lib.num(info.get("annual_premium"))
    _pt = card_lib.num(info.get("premium_term"))
    if _ap and _pt:
        info["premium_total_with_levy"] = info.get("premium_total", "")
        info["premium_total"] = f"{int(round(_ap * _pt)):,}"

    variant = detect_variant(first_text, parser_cfg.get("variant"))
    info["variant"] = variant

    # ── 表格 ──
    years_tables = card_lib.parse_md_tables(years_text)
    scenario_tables = card_lib.parse_md_tables(scenario_text)

    years_cfg = parser_cfg["tables"]["years"]
    scen_cfg = parser_cfg["tables"]["scenario"]

    def _cash_names(cfg: dict) -> tuple:
        cols = cfg["cols"]
        names = [n for n in ("year", "premiums", "guaranteed", "state_bonus", "terminal", "total")
                 if n in cols]
        return tuple(names)

    def _scen_names(cfg: dict) -> tuple:
        cols = cfg["cols"]
        names = [n for n in ("year", "premiums", "guaranteed",
                             "worst_state_bonus", "worst_terminal", "worst_total",
                             "best_state_bonus", "best_terminal", "best_total")
                 if n in cols]
        return tuple(names)

    def _death_names(cfg: dict) -> tuple:
        cols = cfg["cols"]
        names = [n for n in ("year", "premiums", "guaranteed", "state_bonus", "terminal", "total")
                 if n in cols]
        return tuple(names)

    periods = parser_cfg["key_periods"]

    # years 表现金/身故来自同一张表（页内并列列组）
    cash_rows = collect_named_rows(
        years_tables, periods["cash"], years_cfg["cash"]["cols"], _cash_names(years_cfg["cash"])
    )
    death_rows = collect_named_rows(
        years_tables, periods["death"], years_cfg["death"]["cols"], _death_names(years_cfg["death"])
    )

    # scenario 表按标题分现金价值/身故保障两组
    def _scen_group(title_kind: str) -> list[dict]:
        kind = scen_cfg["cash"].get("title_kind", "") if title_kind == "cash" else scen_cfg["death"].get("title_kind", "")
        group = [t for t in scenario_tables if kind in (t.get("title") or "")]
        if not group:
            group = scenario_tables[:1] if title_kind == "cash" else (scenario_tables[1:2] or scenario_tables[:1])
        return group

    scen_cash_rows = collect_named_rows(
        _scen_group("cash"), periods["scenario"], scen_cfg["cash"]["cols"], _scen_names(scen_cfg["cash"])
    )
    scen_death_rows = collect_named_rows(
        _scen_group("death"), periods["scenario"], scen_cfg["death"]["cols"], _scen_names(scen_cfg["death"])
    )

    if not cash_rows:
        print("[extract_templated] 未找到现金价值表行，请人工检查所有保单年 md。", file=sys.stderr)
        return 2
    if not scen_cash_rows:
        print("[extract_templated] 未找到情景表行，请人工检查不同投资回报 md。", file=sys.stderr)
        return 2

    data = {
        "product": parser_cfg["product"],
        "variant": variant,
        "plan_name": info.get("plan_name", ""),
        "info": info,
        "tables": {
            "years": {"cash": cash_rows, "death": death_rows},
            "scenario": {"cash": scen_cash_rows, "death": scen_death_rows},
        },
    }

    out_path = Path(args.output)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"data.json 已生成: {out_path}")
    print(f"  产品: {parser_cfg['product']}  variant={variant or '-'}")
    print(f"  cash 行 {len(cash_rows)} · death 行 {len(death_rows)} · scen-cash 行 {len(scen_cash_rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())