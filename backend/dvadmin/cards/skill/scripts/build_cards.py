#!/usr/bin/env python3
"""build_cards.py - 计划书 md + 固定产品内容 -> cards.json

读取提取脚本生成的三个 md，按 card-plan.md 的固定 9 卡结构生成渲染器输入。
无法解析或关键数字缺失时打印错误并以非零码退出，绝不静默补 0。
"""

import argparse
import json
import os
import re
import sys


# ── markdown 表格解析 ─────────────────────────────────────────


def parse_md_tables(text):
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
        # 去掉分隔行
        rows = [r for r in rows if not all(re.fullmatch(r":?-{3,}:?", c.replace(" ", "")) for c in r)]
        if len(rows) < 2:
            continue
        columns = rows[0]
        data = rows[1:]
        tables.append({"title": title, "columns": columns, "rows": data})
    return tables


def parse_pipe_row(line):
    """解析首页信息中的表格行（pdfplumber 的 markdown 行）。"""
    return [c.strip() for c in line.strip().strip("|").split("|")]


# ── 首页信息解析 ──────────────────────────────────────────────


def parse_first_page(text):
    info = {}
    # Product detection: 尚悅人生 (joy, savings life) / 危疾加護保 (ci) / PWL.
    # Drives which fixed-card content, titles and table column indices main() uses.
    if "尚悅人生" in text or "尚悦人生" in text:
        info["product"] = "joy"
    elif "危疾加護保" in text or "危疾加护保" in text:
        info["product"] = "ci"
    elif "PWL" in text or "尚裕" in text or "終身壽險" in text or "终身寿险" in text:
        info["product"] = "pwl"
    else:
        info["product"] = "unknown"

    for line in text.splitlines():
        # name may contain spaces (e.g. "Mr. Peng先生", "Ms. VIP女士")
        m = re.search(r"受保人姓名:\s*(.+?)\s+性別:\s*(\S+)", line)
        if m:
            info["name"] = m.group(1)
            info["gender"] = m.group(2)
        m = re.search(r"年齡:\s*(\d+)\s*吸煙狀況:\s*(.+)", line)
        if m:
            info["age"] = m.group(1)
            info["smoking"] = m.group(2).strip()
        m = re.search(r"居住國家分類組別:\s*(\S+)", line)
        if m:
            info["country_group"] = m.group(1)
        # 保單貨幣: 美元 (PWL) or 保單貨幣 美元 (危疾加護保, no colon)
        m = re.search(r"保單貨幣:?\s+(\S+)", line)
        if m:
            info["currency"] = m.group(1)
        # PWL premium labels: 投保時每年總保費 / 一次過繳付保費
        m = re.search(r"(?:投保時每年總保費|一次過繳付保費)：\s*([\d,\.]+)", line)
        if m:
            info["annual_premium"] = m.group(1)
        m = re.search(r"投保時徵費：\s*([\d,\.]+)", line)
        if m:
            info["levy"] = m.group(1)
        m = re.search(r"投保時保費及徵費總額：\s*([\d,\.]+)", line)
        if m:
            info["premium_total"] = m.group(1)
        # 危疾加護保 labels
        m = re.search(r"基本計劃的每年保費\s*([\d,\.]+)", line)
        if m:
            info["annual_premium"] = m.group(1)
        m = re.search(r"基本計劃的保費總額\s*([\d,\.]+)", line)
        if m:
            info["premium_total"] = m.group(1)
        m = re.search(r"基本保障額\s*([\d,\.]+)", line)
        if m:
            info["sum_insured"] = m.group(1)
        # 繳付保費年期 由43歲至58歲(15年) -> premium_term=15
        m = re.search(r"繳付保費年期\s*由\d+歲至\d+歲\((\d+)年\)", line)
        if m:
            info["premium_term"] = m.group(1)
        # 保障年期 至100歲 -> policy_term=100
        m = re.search(r"保障年期\s*至(\d+)歲", line)
        if m:
            info["policy_term"] = m.group(1)
        # 危疾加護保 plan name: 基本計劃 : 萬通危疾加護保 (標準版) (15年繳付)
        m = re.search(r"基本計劃\s*:\s*(.+?)\s+保障及利益摘要", line)
        if m:
            info["plan_name"] = m.group(1).strip()

    # 计划表行：从含产品代码的行提取 保障额/缴费年期/年保费。
    # 尚悅人生 (joy): 代码 LD1Pxx(特选)/LD2Pxx(特级)；PWL: 代码 PWL。
    # 危疾加護保 (ci) 无代码行（已通过 基本保障額 提取）。
    if info["product"] == "joy":
        # The rider line (LD2R) also matches \(LD\w*\) but yields <3 numbers,
        # so we keep scanning until the real plan row (LD1Pxx / LD2Pxx).
        for line in text.splitlines():
            m = re.search(r"\(LD\w*\)", line)
            if not m:
                continue
            plan_name = line[: m.start()].strip()
            if plan_name.endswith("("):
                plan_name = plan_name[:-1].strip()
            rest = line[m.end() :]
            nums = re.findall(r"[\d,]+\.?\d*", rest)
            if len(nums) >= 3:
                info["sum_insured"] = nums[0]
                info["premium_term"] = nums[1]
                info["annual_premium_plan"] = nums[-1]
                info.setdefault("plan_name", plan_name)
                break
    elif info["product"] == "pwl" or "PWL" in text:
        for line in text.splitlines():
            if "PWL" not in line:
                continue
            if "|" in line:
                cells = parse_pipe_row(line)
                plan_name = cells[0] if cells else ""
                rest = " ".join(cells[1:])
            else:
                # 纯文本行：计划名在 PWL 代码之前，数字在 PWL 代码之后
                m = re.search(r"PWL\d*\)", line)
                if m:
                    plan_name = line[: m.start()].strip()
                    if plan_name.endswith("("):
                        plan_name = plan_name[:-1].strip()
                    rest = line[m.end() :]
                else:
                    plan_name = line.split("PWL")[0].strip()
                    rest = line.split("PWL")[-1]
            nums = re.findall(r"[\d,]+\.?\d*", rest)
            if len(nums) >= 3:
                info["sum_insured"] = nums[0]
                info["premium_term"] = nums[1]
                info["annual_premium_plan"] = nums[-1]
                info.setdefault("plan_name", plan_name)
            break

    # Fallback: if no labeled annual premium line was found, reuse the plan-row
    # premium (works for single-premium plans whose label differs).
    if "annual_premium" not in info and "annual_premium_plan" in info:
        info["annual_premium"] = info["annual_premium_plan"]

    return info


# ── 关键行筛选 ────────────────────────────────────────────────


def find_row(tables, key):
    """在多个表中找第一个首列为 key 的行。"""
    for t in tables:
        for row in t["rows"]:
            if row and row[0].strip() == str(key):
                return row
    return None


def collect_rows(tables, keys):
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


# ── 主流程 ────────────────────────────────────────────────────


def load_md_files(output_dir):
    """自动匹配 output 目录下 -首页信息 / -所有保单年 / -不同投资回报 md。"""
    files = {}
    for f in os.listdir(output_dir):
        if not f.endswith(".md"):
            continue
        if "首页信息" in f:
            files["first"] = os.path.join(output_dir, f)
        elif "所有保单年" in f:
            files["years"] = os.path.join(output_dir, f)
        elif "不同投资回报" in f:
            files["scenario"] = os.path.join(output_dir, f)
    return files


def fmt_amount(v):
    """金额转千分位整数展示（去掉小数 .00）。"""
    v = str(v).strip()
    if re.fullmatch(r"[\d,]+\.00", v):
        v = v[:-3]
    return v


def main():
    parser = argparse.ArgumentParser(description="计划书 md -> cards.json")
    parser.add_argument("output_dir", type=str, help="包含三个 md 的目录")
    parser.add_argument("--output", type=str, default="cards.json", help="输出 cards.json 路径")
    args = parser.parse_args()

    files = load_md_files(args.output_dir)
    missing = [k for k in ("first", "years", "scenario") if k not in files]
    if missing:
        print(f"缺少数据文件: {missing} 在 {args.output_dir}")
        sys.exit(1)

    first_text = open(files["first"], encoding="utf-8").read()
    years_text = open(files["years"], encoding="utf-8").read()
    scenario_text = open(files["scenario"], encoding="utf-8").read()

    info = parse_first_page(first_text)
    required = ["name", "age", "sum_insured", "annual_premium", "premium_term"]
    for k in required:
        if k not in info:
            print(f"首页信息缺少字段: {k}")
            print("请人工检查首页信息 md 后重试，或手动修正 build_cards.py 的解析规则。")
            sys.exit(1)

    years_tables = parse_md_tables(years_text)
    scenario_tables = parse_md_tables(scenario_text)

    # 现时假设表（所有保单年）：列 0 年度, 1 缴付保费总额, 2 保证(A), 3 终期红利(B), 4 总额(A+B), 5 保证(C), 6 终期红利(D), 7 总额(C+D)
    cash_keys = ["10", "20", "25", "30", "65 歲", "75 歲", "80 歲", "100 歲"]
    death_keys = ["20", "65 歲", "70 歲", "75 歲", "80 歲", "90 歲", "100 歲"]
    cash_rows, cash_missing = collect_rows(years_tables, cash_keys)
    death_rows, death_missing = collect_rows(years_tables, death_keys)

    # 情景表（不同投资回报）：列 0 年度, 1 缴付保费总额, 2 保证(A), 3 悲观终期红利(B), 4 悲观总额(A+B), 5 乐观终期红利(C), 6 乐观总额(A+C)
    scen_keys = ["10", "20", "25", "30", "80 歲", "100 歲"]
    scen_rows, scen_missing = collect_rows(scenario_tables, scen_keys)

    if not cash_rows:
        print("未找到现金价值表行，请人工检查所有保单年 md。")
        sys.exit(1)
    if not scen_rows:
        print("未找到情景表行，请人工检查不同投资回报 md。")
        sys.exit(1)

    print("缺失行（已省略）:")
    for label, missing in [("现金价值", cash_missing), ("身故", death_missing), ("情景", scen_missing)]:
        if missing:
            print(f"  {label}: {missing}")

    # ── 产品相关文案 ──────────────────────────────────────────
    # PWL（尚裕终身寿险）与 危疾加護保（Critical Illness）共享同一份
    # 8 列保单年表，因此卡片 03-05 的行索引通用；仅封面/摘要/身故 note
    # 及固定卡片 06-09 需按产品区分。
    product = info.get("product", "pwl")
    if product == "ci":
        meta_title = "萬通危疾加護保 (CI)"
        cover_eyebrow = "香港危疾保障 · 美元保單"
        cover_default_plan = "萬通危疾加護保 (標準版)"
        cover_subtitle_suffix = "保障至100歲"
        policy_term_label = f"至{info.get('policy_term', '100')}歲"
        death_note = "身故賠償取(100%基本保障額+終期紅利)與現金價值的較高者，扣除已支付嚴重疾病保障"
        cashvalue_note = "終期紅利為非保證金額，第5個保單週年起公佈，實際可能高於或低於演示"
    elif product == "joy":
        meta_title = "尚悅人生壽險計劃 (LD2)"
        cover_eyebrow = "香港储蓄寿险 · 美元保单"
        cover_default_plan = "尚悅人生壽險計劃 (10年繳付) - 特級計劃"
        cover_subtitle_suffix = "终身保障"
        policy_term_label = "终身"
        death_note = "身故赔偿取(保证身故保障+累积红利及利息+终期红利)与现金价值的较高者"
        cashvalue_note = "终期红利及累积红利为非保证金额，实际可能高于或低于演示"
    else:
        meta_title = "尚裕终身寿险 (PWL)"
        cover_eyebrow = "香港终身寿险 · 美元保单"
        cover_default_plan = "尚裕终身寿险"
        cover_subtitle_suffix = "终身保障"
        policy_term_label = "终身"
        death_note = "身故赔偿取(保证身故保障+终期红利+累积红利)与现金价值的较高者"
        cashvalue_note = "终期红利为非保证金额，实际可能高于或低于演示"

    meta = {
        "title": meta_title,
        "width": 1080,
        "height": 1800,
        "theme": "premium-navy",
        "footer": "仅供说明参考，非保证收益，以保单条款为准",
    }

    # ── 表格列索引（按产品区分）────────────────────────────────
    # 尚悅人生 (joy) 的保单年表是 10 列、情景表是 9 列：它把「累积红利及利息」
    # 和「终期红利」拆成两列，而 PWL/CI 合并为一列终期红利（8 列年表 / 7 列情景）。
    if product == "joy":
        cash_card_columns = ["保单年度", "缴付保费总额", "保证金额", "累积红利及利息", "终期红利", "总额"]
        death_card_columns = ["保单年度", "缴付保费总额", "保证身故保障", "累积红利及利息", "终期红利", "总额"]
        cash_card_rows = [
            [str(r[0]), fmt_amount(r[1]), fmt_amount(r[2]), fmt_amount(r[3]), fmt_amount(r[4]), fmt_amount(r[5])]
            for r in cash_rows
        ]
        scen_card_rows = [
            [str(r[0]), fmt_amount(r[5]), fmt_amount(r[8])]
            for r in scen_rows
        ]
        death_card_rows = [
            [str(r[0]), fmt_amount(r[1]), fmt_amount(r[6]), fmt_amount(r[7]), fmt_amount(r[8]), fmt_amount(r[9])]
            for r in death_rows
        ]
    else:
        cash_card_columns = ["保单年度", "缴付保费总额", "保证金额", "终期红利", "总额"]
        death_card_columns = ["保单年度", "缴付保费总额", "保证身故保障", "终期红利", "总额"]
        cash_card_rows = [
            [str(r[0]), fmt_amount(r[1]), fmt_amount(r[2]), fmt_amount(r[3]), fmt_amount(r[4])]
            for r in cash_rows
        ]
        scen_card_rows = [
            [str(r[0]), fmt_amount(r[4]), fmt_amount(r[6])]
            for r in scen_rows
        ]
        death_card_rows = [
            [str(r[0]), fmt_amount(r[1]), fmt_amount(r[5]), fmt_amount(r[6]), fmt_amount(r[7])]
            for r in death_rows
        ]

    cover_title = f"{info.get('plan_name', cover_default_plan)}"
    cards = [
        {
            "file": "01_cover.png",
            "layout": "cover",
            "eyebrow": cover_eyebrow,
            "title": cover_title,
            "subtitle": f"保障额 {fmt_amount(info['sum_insured'])} 美元 · {fmt_amount(info['premium_term'])} 年缴费 · {cover_subtitle_suffix}",
            "accent": "gold",
            "stats": [
                {"label": "保障额", "value": fmt_amount(info["sum_insured"])},
                {"label": "年保费", "value": fmt_amount(info["annual_premium"])},
                {"label": "缴费年期", "value": f"{fmt_amount(info['premium_term'])} 年"},
            ],
        },
        {
            "file": "02_summary.png",
            "layout": "summary",
            "eyebrow": "保障摘要",
            "title": "保障摘要",
            "subtitle": f"受保人 {info['name']} · {info['age']} 岁 {info['gender']}",
            "accent": "blue",
            "items": [
                ["受保人", info["name"]],
                ["性别 / 年龄", f"{info['gender']} / {info['age']}"],
                ["吸烟状况", info.get("smoking", "-")],
                ["居住国家组别", info.get("country_group", "-")],
                ["保单货币", info.get("currency", "-")],
                ["保障额", fmt_amount(info["sum_insured"])],
                ["缴费年期", f"{fmt_amount(info['premium_term'])} 年"],
                ["保障年期", policy_term_label],
                ["年保费", fmt_amount(info.get("annual_premium_plan", info["annual_premium"]))],
            ],
        },
        {
            "file": "03_cashvalue_table.png",
            "layout": "table",
            "eyebrow": "现金价值演示",
            "title": "现金价值（现时假设）",
            "subtitle": "单位：美元",
            "accent": "gold",
            "columns": cash_card_columns,
            "rows": cash_card_rows,
            "note": cashvalue_note,
        },
        {
            "file": "04_scenario.png",
            "layout": "table",
            "eyebrow": "不同投资回报情景",
            "title": "投资回报情景对比",
            "subtitle": "现金价值总额 · 单位：美元",
            "accent": "blue",
            "columns": ["保单年度", "悲观情景", "乐观情景"],
            "rows": scen_card_rows,
            "note": "悲观/乐观基于现时假设投资回报每年 ±约1.7%；不代表实际回报上下限",
        },
        {
            "file": "05_death_benefit.png",
            "layout": "table",
            "eyebrow": "身故保障演示",
            "title": "身故保障（现时假设）",
            "subtitle": "单位：美元",
            "accent": "coral",
            "columns": death_card_columns,
            "rows": death_card_rows,
            "note": death_note,
        },
    ]

    # 固定内容卡片（来自 product-facts.md）
    if product == "ci":
        fixed_cards = [
            {
                "file": "06_features.png",
                "layout": "list",
                "eyebrow": "产品特点",
                "title": "为什么选它",
                "subtitle": "萬通危疾加護保 (標準版)",
                "accent": "gold",
                "items": [
                    "严重疾病保障涵盖早期疾病、原位癌及主要严重疾病",
                    "主要严重疾病保障：首10个保单年度享额外35%保障额（推广优惠）",
                    "临床试验药物保障：癌症确诊后3年内资助临床试验药物费用",
                    "保证现金价值 + 非保证终期红利，第5个保单周年起公布",
                    "保证将来可保权益：符合条件可购买全新严重疾病保单",
                    "身故赔偿取(保障额+终期红利)与现金价值的较高者",
                ],
            },
            {
                "file": "07_coverage.png",
                "layout": "list",
                "eyebrow": "严重疾病保障结构",
                "title": "保障额分配",
                "subtitle": "基本保障额 150,000 美元为基数",
                "accent": "coral",
                "items": [
                    "早期疾病：可达 45,000 美元 (30%)",
                    "原位癌／初期癌症：可达 45,000 美元 (30%)",
                    "主要严重疾病（第1-10年）：可达 202,500 美元 (135%)",
                    "主要严重疾病（第11年起）：可达 150,000 美元 (100%)",
                    "临床试验药物保障：可达 30,000 美元 (20%)",
                    "推广优惠额外保障：首10年 52,500 美元",
                ],
            },
            {
                "file": "08_company.png",
                "layout": "list",
                "eyebrow": "承保公司",
                "title": "财务实力",
                "subtitle": "万通保险国际有限公司 (YF Life)",
                "accent": "blue",
                "items": [
                    "港交所上市公司云锋金融集团成员",
                    "主要股东包括美国万通人寿保险（全美5大互惠寿险公司之一）",
                    "惠誉国际给予「A-」（强劲）保险财务实力评级",
                    "分红计划目标：不少于90%的可分配盈余分配给保单持有人",
                ],
            },
            {
                "file": "09_risks.png",
                "layout": "list",
                "eyebrow": "重要提示",
                "title": "投保前必读",
                "subtitle": "请务必理解以下风险",
                "accent": "coral",
                "items": [
                    "终期红利非保证，某些情况下可能为零",
                    "严重疾病保障总额达100%基本保障额后，保单即终止",
                    "临床试验药物保障需符合特定资格条件（如癌症治疗已失效）",
                    "推广优惠额外保障不设现金价值，第10个保单周年日终止",
                    "保费征费由保监局收取，征费率与上限可能逐年变动",
                    "冷静期为21个历日；一切以保单条款为准",
                ],
            },
        ]
    elif product == "joy":
        fixed_cards = [
            {
                "file": "06_features.png",
                "layout": "list",
                "eyebrow": "产品特点",
                "title": "为什么选它",
                "subtitle": "尚悅人生壽險計劃 (10年繳付) - 特級計劃",
                "accent": "gold",
                "items": [
                    "分红储蓄寿险，10年缴费、终身保障",
                    "保证现金价值，经济环境如何均提供",
                    "非保证累积红利及利息，每年公布并滚存生息",
                    "非保证终期红利，第3个保单周年起每年公布",
                    "现金价值 = 保证现金价值 + 累积红利及利息 + 终期红利",
                ],
            },
            {
                "file": "07_rider.png",
                "layout": "list",
                "eyebrow": "附加保障",
                "title": "推广优惠：额外人寿保障",
                "subtitle": "推广优惠 (LD2R) · 首五个保单年度",
                "accent": "coral",
                "items": [
                    "额外人寿保障额为基本保障额的50%（即75,000美元）",
                    "保障期5年，不设现金价值",
                    "须于推广期内递交申请并获核保才可享此优惠",
                    "受保人于保障期内身故即支付额外保障额",
                    "第5个保单周年日终止，不影响基本计划延续",
                ],
            },
            {
                "file": "08_company.png",
                "layout": "list",
                "eyebrow": "承保公司",
                "title": "财务实力",
                "subtitle": "万通保险国际有限公司 (YF Life)",
                "accent": "blue",
                "items": [
                    "港交所上市公司云锋金融集团成员",
                    "主要股东包括美国万通人寿保险（全美5大互惠寿险公司之一）",
                    "惠誉国际给予「A-」（强劲）保险财务实力评级",
                    "分红计划目标：不少于90%的可分配盈余分配给保单持有人",
                ],
            },
            {
                "file": "09_risks.png",
                "layout": "list",
                "eyebrow": "重要提示",
                "title": "投保前必读",
                "subtitle": "请务必理解以下风险",
                "accent": "coral",
                "items": [
                    "终期红利及累积红利为非保证，某些情况下可能为零",
                    "本产品为长线持有而设，提早退保可能蒙受重大损失",
                    "保单日期起一年内自杀，责任只限于退还已缴保费",
                    "推广优惠额外保障不设现金价值，第5个保单周年日终止",
                    "保费征费由保监局收取，征费率与上限可能逐年变动",
                    "冷静期为21个历日；一切以保单条款为准",
                ],
            },
        ]
    else:
        fixed_cards = [
            {
                "file": "06_features.png",
                "layout": "list",
                "eyebrow": "产品特点",
                "title": "为什么选它",
                "subtitle": "尚裕终身寿险 Preeminence",
                "accent": "gold",
                "items": [
                    "终身寿险保障，保障年期至终身",
                    "保证现金价值，经济环境如何均提供",
                    "非保证终期红利，第3个保单周年起每年公布",
                    "第15年起可行使终期红利锁定权益，最高锁定60%",
                    "现金价值 = 保证现金价值 + 终期红利 + 累积红利及利息",
                ],
            },
            {
                "file": "07_diamond.png",
                "layout": "list",
                "eyebrow": "身故保障结构",
                "title": "钻石周年日规则",
                "subtitle": "钻石周年日 = 70岁生日后保单周年日 或 第20个保单周年日（较后者）",
                "accent": "coral",
                "items": [
                    "钻石周年日前身故：保证身故保障为 100% 保障额",
                    "钻石周年日起：保证身故保障自100%每年递减5%",
                    "第10年起维持于 50% 保障额",
                    "可选升级保障权益，将递减保障提升至最高100%",
                    "身故赔偿可一笔过或每月分期领取，毋须设立信托",
                ],
            },
            {
                "file": "08_company.png",
                "layout": "list",
                "eyebrow": "承保公司",
                "title": "财务实力",
                "subtitle": "万通保险国际有限公司 (YF Life)",
                "accent": "blue",
                "items": [
                    "港交所上市公司云锋金融集团成员",
                    "主要股东包括美国万通人寿保险（全美5大互惠寿险公司之一）",
                    "惠誉国际给予「A-」（强劲）保险财务实力评级",
                    "分红计划目标：不少于90%的可分配盈余分配给保单持有人",
                ],
            },
            {
                "file": "09_risks.png",
                "layout": "list",
                "eyebrow": "重要提示",
                "title": "投保前必读",
                "subtitle": "请务必理解以下风险",
                "accent": "coral",
                "items": [
                    "终期红利非保证，某些情况下可能为零",
                    "本产品为长线持有而设，提早退保可能蒙受重大损失",
                    "保单日期起一年内自杀，责任只限于退还已缴保费",
                    "保费征费由保监局收取，征费率与上限可能逐年变动",
                    "冷静期为21个历日；一切以保单条款为准",
                ],
            },
        ]
    cards.extend(fixed_cards)

    payload = {"meta": meta, "cards": cards}
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"cards.json 已生成: {args.output}")
    print(f"卡片数: {len(cards)} (现金价值行 {len(cash_rows)}, 情景行 {len(scen_rows)}, 身故行 {len(death_rows)})")
    if cash_missing or death_missing or scen_missing:
        print("提示: 部分关键行缺失，已省略。请人工核对。")
        sys.exit(2)


if __name__ == "__main__":
    main()
