#!/usr/bin/env python3
"""build_guizang_cards.py — 计划书 md -> Guizang 杂志风 cards.json

复用 build_cards.py 的解析逻辑（首页信息 / 现时假设表 / 情景表），
在固定 10 张数据/内容卡之上，追加归藏风格特有的扩展卡片：

  04. 身故保障（现时假设）—— 紧跟现金价值，两张现时假设表成对
  05. 投资回报情景对比（现金价值）—— 悲观/乐观总额
  06. 投资回报情景对比（身故保障）—— 悲观/乐观总额（归藏新增）
  07-10. 产品固定内容卡（特点 / 附加结构 / 公司 / 风险）
  11. CI 疾病清单（早期保障）—— 早期疾病 + 原位癌（仅 ci 产品）
  12. CI 疾病清单（主要严重疾病）—— 14 项主要危疾（仅 ci 产品）
  13. 「致受保人的一封信」—— 由 DeepSeek 生成，克制、有温度
  14. 「保障与人生阶段」—— 由 DeepSeek 生成，连接保障与受保人人生阶段

输出 cards.json 的 layout 类型扩展为：
  cover / summary / table / list / article / ci-list

归藏风格由 render_guizang.py 用 Playwright 渲染 HTML/CSS 完成，因此卡片
结构与原 Pillow 渲染器不互通——本脚本只负责生成数据，不负责绘制。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

# 复用同级 build_cards.py 的解析函数（同一目录下 import）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_cards  # noqa: E402

# DeepSeek LLM 写作器（位于 backend/，由 pipeline.py 通过 PYTHONPATH 注入）
# 这里做容错 import：单独跑此脚本时若 backend/ 不在 path，LLM 调用会被跳过。
try:
    from llm_writer import (
        write_ci_diseases_intro,
        write_emotional_letter,
        write_life_stage_article,
    )
    _LLM_OK = True
except Exception as exc:  # pragma: no cover - 仅在脱离后端单独调试时触发
    sys.stderr.write(f"[build_guizang] LLM writer unavailable: {exc}\n")
    _LLM_OK = False


# ── CI 疾病清单（固定产品知识，来自 product-facts.md / 危疾加護保條款）───
# 三层结构：早期疾病 / 原位癌及初期癌症 / 主要严重疾病。
# 每层给出代表性病种（非穷举），用于图文卡片的「疾病清单」页。
CI_DISEASE_GROUPS = [
    {
        "tier": "早期疾病",
        "payout": "最高 45,000 美元（30% 基本保障额）",
        "items": [
            "原位癌（乳房、子宫颈、子宫体）",
            "初期甲状腺癌或前列腺癌",
            "心脏瓣膜置换手术",
            "冠状动脉血管成形术",
            "糖尿病视网膜病变",
            "早期严重哮喘",
            "骨质疏松症连骨折",
        ],
    },
    {
        "tier": "原位癌 / 初期癌症",
        "payout": "最高 45,000 美元（30% 基本保障额）",
        "items": [
            "乳房原位癌",
            "子宫颈原位癌",
            "大肠原位癌",
            "胃原位癌",
            "肺原位癌",
            "肝脏原位癌",
        ],
    },
    {
        "tier": "主要严重疾病",
        "payout": "首10年 202,500 美元（135%）；其后 150,000 美元（100%）",
        "items": [
            "癌症（恶性肿瘤）",
            "急性心肌梗塞",
            "中风",
            "末期肾病（慢性肾衰竭）",
            "主要器官移植",
            "冠状动脉搭桥手术",
            "心脏瓣膜手术",
            "严重肝病 / 肝衰竭",
            "昏迷",
            "瘫痪",
            "柏金逊症",
            "阿兹海默症",
            "运动神经元病",
            "末期肺病",
        ],
    },
]


# ── 产品文案（沿用 build_cards.py，归藏风格措辞微调）────────────────────


def product_copy(info: dict[str, Any]) -> dict[str, str]:
    product = info.get("product", "pwl")
    if product == "ci":
        return {
            "meta_title": "萬通危疾加護保",
            "cover_eyebrow": "香港危疾保障 · 美元保單",
            "cover_default_plan": "萬通危疾加護保 (標準版)",
            "cover_subtitle_suffix": "保障至100歲",
            "policy_term_label": f"至{info.get('policy_term', '100')}歲",
            "death_note": "身故賠償取(100%基本保障額+終期紅利)與現金價值的較高者，扣除已支付嚴重疾病保障",
            "cashvalue_note": "終期紅利為非保證金額，第5個保單週年起公佈，實際可能高於或低於演示",
        }
    if product == "joy":
        return {
            "meta_title": "尚悅人生壽險計劃",
            "cover_eyebrow": "香港儲蓄壽險 · 美元保單",
            "cover_default_plan": "尚悅人生壽險計劃 (10年繳付) - 特級計劃",
            "cover_subtitle_suffix": "終身保障",
            "policy_term_label": "終身",
            "death_note": "身故賠償取(保證身故保障+累積紅利及利息+終期紅利)與現金價值的較高者",
            "cashvalue_note": "終期紅利及累積紅利為非保證金額，實際可能高於或低於演示",
        }
    return {
        "meta_title": "尚裕終身壽險",
        "cover_eyebrow": "香港終身壽險 · 美元保單",
        "cover_default_plan": "尚裕終身壽險 Preeminence",
        "cover_subtitle_suffix": "終身保障",
        "policy_term_label": "終身",
        "death_note": "身故賠償取(保證身故保障+終期紅利+累積紅利)與現金價值的較高者",
        "cashvalue_note": "終期紅利為非保證金額，實際可能高於或低於演示",
    }


def build_base_cards(info: dict[str, Any], years_tables, scenario_tables) -> tuple[list[dict], list[str]]:
    """构造基础 5 张数据卡 + 4 张固定内容卡，沿用 build_cards.py 的列索引逻辑。

    返回 (cards, missing) —— missing 是关键行缺失列表（用于状态提示，不阻断）。
    """
    copy = product_copy(info)
    product = info.get("product", "pwl")

    cash_keys = ["10", "20", "25", "30", "65 歲", "75 歲", "80 歲", "100 歲"]
    death_keys = ["20", "65 歲", "70 歲", "75 歲", "80 歲", "90 歲", "100 歲"]
    scen_keys = ["10", "20", "25", "30", "80 歲", "100 歲"]

    cash_rows, cash_missing = build_cards.collect_rows(years_tables, cash_keys)
    death_rows, death_missing = build_cards.collect_rows(years_tables, death_keys)

    # 情景表（不同投资回报）md 里有两张表：现金价值情景 + 身故保障情景。
    # build_cards.find_row() 只返回首个匹配（现金价值表），身故保障情景会被
    # 静默忽略。这里按标题拆分，分别取两张表的行，以便归藏风格多出一张
    # 「投资回报情景对比-身故保障」卡。
    scen_cash_tables = [t for t in scenario_tables if "現金" in t.get("title", "") or "现金" in t.get("title", "")]
    scen_death_tables = [t for t in scenario_tables if "身故" in t.get("title", "")]
    # 标题缺失时的容错：第一张视为现金价值，第二张视为身故保障。
    if not scen_cash_tables and scenario_tables:
        scen_cash_tables = [scenario_tables[0]]
    if not scen_death_tables and len(scenario_tables) > 1:
        scen_death_tables = [scenario_tables[1]]

    scen_rows, scen_missing = build_cards.collect_rows(scen_cash_tables, scen_keys)
    scen_death_rows, scen_death_missing = build_cards.collect_rows(scen_death_tables, scen_keys)

    if not cash_rows:
        raise SystemExit("未找到现金价值表行，请人工检查所有保单年 md。")
    if not scen_rows:
        raise SystemExit("未找到情景表行，请人工检查不同投资回报 md。")

    fmt = build_cards.fmt_amount

    # 列索引（按产品区分），与 build_cards.py 完全一致。
    # 情景表现金价值与身故保障列结构相同（同一 md 的两张表），
    # 故身故保障情景卡沿用同样的悲观/乐观总额列索引。
    if product == "joy":
        cash_card_columns = ["保单年度", "缴付保费总额", "保证金额", "累积红利及利息", "终期红利", "总额"]
        death_card_columns = ["保单年度", "缴付保费总额", "保证身故保障", "累积红利及利息", "终期红利", "总额"]
        cash_card_rows = [[str(r[0]), fmt(r[1]), fmt(r[2]), fmt(r[3]), fmt(r[4]), fmt(r[5])] for r in cash_rows]
        scen_card_rows = [[str(r[0]), fmt(r[5]), fmt(r[8])] for r in scen_rows]
        scen_death_card_rows = [[str(r[0]), fmt(r[5]), fmt(r[8])] for r in scen_death_rows]
        death_card_rows = [[str(r[0]), fmt(r[1]), fmt(r[6]), fmt(r[7]), fmt(r[8]), fmt(r[9])] for r in death_rows]
    else:
        cash_card_columns = ["保单年度", "缴付保费总额", "保证金额", "终期红利", "总额"]
        death_card_columns = ["保单年度", "缴付保费总额", "保证身故保障", "终期红利", "总额"]
        cash_card_rows = [[str(r[0]), fmt(r[1]), fmt(r[2]), fmt(r[3]), fmt(r[4])] for r in cash_rows]
        scen_card_rows = [[str(r[0]), fmt(r[4]), fmt(r[6])] for r in scen_rows]
        scen_death_card_rows = [[str(r[0]), fmt(r[4]), fmt(r[6])] for r in scen_death_rows]
        death_card_rows = [[str(r[0]), fmt(r[1]), fmt(r[5]), fmt(r[6]), fmt(r[7])] for r in death_rows]

    cover_title = info.get("plan_name", copy["cover_default_plan"])
    cards = [
        {
            "file": "01_cover.png",
            "layout": "cover",
            "eyebrow": copy["cover_eyebrow"],
            "title": cover_title,
            "subtitle": f"保障额 {fmt(info['sum_insured'])} 美元 · {fmt(info['premium_term'])} 年缴费 · {copy['cover_subtitle_suffix']}",
            "kicker": "封面 · Cover",
            "stats": [
                {"label": "保障额", "value": fmt(info["sum_insured"])},
                {"label": "年保费", "value": fmt(info["annual_premium"])},
                {"label": "缴费年期", "value": f"{fmt(info['premium_term'])} 年"},
            ],
        },
        {
            "file": "02_summary.png",
            "layout": "summary",
            "eyebrow": "保障摘要",
            "title": "保障摘要",
            "subtitle": f"受保人 {info['name']} · {info['age']} 岁 {info['gender']}",
            "kicker": "摘要 · Summary",
            "items": [
                ["受保人", info["name"]],
                ["性别 / 年龄", f"{info['gender']} / {info['age']}"],
                ["吸烟状况", info.get("smoking", "-")],
                ["居住国家组别", info.get("country_group", "-")],
                ["保单货币", info.get("currency", "-")],
                ["保障额", fmt(info["sum_insured"])],
                ["缴费年期", f"{fmt(info['premium_term'])} 年"],
                ["保障年期", copy["policy_term_label"]],
                ["年保费", fmt(info.get("annual_premium_plan", info["annual_premium"]))],
            ],
        },
        {
            "file": "03_cashvalue_table.png",
            "layout": "table",
            "eyebrow": "现金价值演示",
            "title": "现金价值（现时假设）",
            "subtitle": "单位：美元",
            "kicker": "数据 · Cash Value",
            "columns": cash_card_columns,
            "rows": cash_card_rows,
            "note": copy["cashvalue_note"],
        },
        {
            "file": "04_death_benefit.png",
            "layout": "table",
            "eyebrow": "身故保障演示",
            "title": "身故保障（现时假设）",
            "subtitle": "单位：美元",
            "kicker": "数据 · Death Benefit",
            "columns": death_card_columns,
            "rows": death_card_rows,
            "note": copy["death_note"],
        },
        {
            "file": "05_scenario.png",
            "layout": "table",
            "eyebrow": "不同投资回报情景",
            "title": "投资回报情景对比（现金价值）",
            "subtitle": "现金价值总额 · 单位：美元",
            "kicker": "情景 · Scenario",
            "columns": ["保单年度", "悲观情景", "乐观情景"],
            "rows": scen_card_rows,
            "note": "悲观/乐观基于现时假设投资回报每年 ±约1.7%；不代表实际回报上下限",
        },
        {
            "file": "06_scenario_death.png",
            "layout": "table",
            "eyebrow": "不同投资回报情景",
            "title": "投资回报情景对比（身故保障）",
            "subtitle": "身故保障总额 · 单位：美元",
            "kicker": "情景 · Scenario",
            "columns": ["保单年度", "悲观情景", "乐观情景"],
            "rows": scen_death_card_rows,
            "note": "身故保障总额 = 保证身故保障 + 累积红利及利息 + 终期红利；悲观/乐观基于现时假设投资回报每年 ±约1.7%",
        },
    ]

    # 固定内容卡 07-10（沿用 build_cards.py 的产品文案）
    if product == "ci":
        fixed = [
            {"file": "07_features.png", "layout": "list", "eyebrow": "产品特点", "title": "为什么选它",
             "subtitle": "萬通危疾加護保 (標準版)", "kicker": "特点 · Features", "items": [
                "严重疾病保障涵盖早期疾病、原位癌及主要严重疾病",
                "主要严重疾病保障：首10个保单年度享额外35%保障额（推广优惠）",
                "临床试验药物保障：癌症确诊后3年内资助临床试验药物费用",
                "保证现金价值 + 非保证终期红利，第5个保单周年起公布",
                "保证将来可保权益：符合条件可购买全新严重疾病保单",
                "身故赔偿取(保障额+终期红利)与现金价值的较高者",
            ]},
            {"file": "08_coverage.png", "layout": "list", "eyebrow": "严重疾病保障结构", "title": "保障额分配",
             "subtitle": "基本保障额 150,000 美元为基数", "kicker": "结构 · Allocation", "items": [
                "早期疾病：可达 45,000 美元 (30%)",
                "原位癌／初期癌症：可达 45,000 美元 (30%)",
                "主要严重疾病（第1-10年）：可达 202,500 美元 (135%)",
                "主要严重疾病（第11年起）：可达 150,000 美元 (100%)",
                "临床试验药物保障：可达 30,000 美元 (20%)",
                "推广优惠额外保障：首10年 52,500 美元",
            ]},
            {"file": "09_company.png", "layout": "list", "eyebrow": "承保公司", "title": "财务实力",
             "subtitle": "万通保险国际有限公司 (YF Life)", "kicker": "公司 · Company", "items": [
                "港交所上市公司云锋金融集团成员",
                "主要股东包括美国万通人寿保险（全美5大互惠寿险公司之一）",
                "惠誉国际给予「A-」（强劲）保险财务实力评级",
                "分红计划目标：不少于90%的可分配盈余分配给保单持有人",
            ]},
            {"file": "10_risks.png", "layout": "list", "eyebrow": "重要提示", "title": "投保前必读",
             "subtitle": "请务必理解以下风险", "kicker": "提示 · Notice", "items": [
                "终期红利非保证，某些情况下可能为零",
                "严重疾病保障总额达100%基本保障额后，保单即终止",
                "临床试验药物保障需符合特定资格条件（如癌症治疗已失效）",
                "推广优惠额外保障不设现金价值，第10个保单周年日终止",
                "保费征费由保监局收取，征费率与上限可能逐年变动",
                "冷静期为21个历日；一切以保单条款为准",
            ]},
        ]
    elif product == "joy":
        fixed = [
            {"file": "07_features.png", "layout": "list", "eyebrow": "产品特点", "title": "为什么选它",
             "subtitle": "尚悅人生壽險計劃 (10年繳付) - 特級計劃", "kicker": "特点 · Features", "items": [
                "分红储蓄寿险，10年缴费、终身保障",
                "保证现金价值，经济环境如何均提供",
                "非保证累积红利及利息，每年公布并滚存生息",
                "非保证终期红利，第3个保单周年起每年公布",
                "现金价值 = 保证现金价值 + 累积红利及利息 + 终期红利",
            ]},
            {"file": "08_rider.png", "layout": "list", "eyebrow": "附加保障", "title": "推广优惠：额外人寿保障",
             "subtitle": "推广优惠 (LD2R) · 首五个保单年度", "kicker": "附加 · Rider", "items": [
                "额外人寿保障额为基本保障额的50%（即75,000美元）",
                "保障期5年，不设现金价值",
                "须于推广期内递交申请并获核保才可享此优惠",
                "受保人于保障期内身故即支付额外保障额",
                "第5个保单周年日终止，不影响基本计划延续",
            ]},
            {"file": "09_company.png", "layout": "list", "eyebrow": "承保公司", "title": "财务实力",
             "subtitle": "万通保险国际有限公司 (YF Life)", "kicker": "公司 · Company", "items": [
                "港交所上市公司云锋金融集团成员",
                "主要股东包括美国万通人寿保险（全美5大互惠寿险公司之一）",
                "惠誉国际给予「A-」（强劲）保险财务实力评级",
                "分红计划目标：不少于90%的可分配盈余分配给保单持有人",
            ]},
            {"file": "10_risks.png", "layout": "list", "eyebrow": "重要提示", "title": "投保前必读",
             "subtitle": "请务必理解以下风险", "kicker": "提示 · Notice", "items": [
                "终期红利及累积红利为非保证，某些情况下可能为零",
                "本产品为长线持有而设，提早退保可能蒙受重大损失",
                "保单日期起一年内自杀，责任只限于退还已缴保费",
                "推广优惠额外保障不设现金价值，第5个保单周年日终止",
                "保费征费由保监局收取，征费率与上限可能逐年变动",
                "冷静期为21个历日；一切以保单条款为准",
            ]},
        ]
    else:  # pwl
        fixed = [
            {"file": "07_features.png", "layout": "list", "eyebrow": "产品特点", "title": "为什么选它",
             "subtitle": "尚裕终身寿险 Preeminence", "kicker": "特点 · Features", "items": [
                "终身寿险保障，保障年期至终身",
                "保证现金价值，经济环境如何均提供",
                "非保证终期红利，第3个保单周年起每年公布",
                "第15年起可行使终期红利锁定权益，最高锁定60%",
                "现金价值 = 保证现金价值 + 终期红利 + 累积红利及利息",
            ]},
            {"file": "08_diamond.png", "layout": "list", "eyebrow": "身故保障结构", "title": "钻石周年日规则",
             "subtitle": "钻石周年日 = 70岁生日后保单周年日 或 第20个保单周年日（较后者）", "kicker": "规则 · Rule", "items": [
                "钻石周年日前身故：保证身故保障为 100% 保障额",
                "钻石周年日起：保证身故保障自100%每年递减5%",
                "第10年起维持于 50% 保障额",
                "可选升级保障权益，将递减保障提升至最高100%",
                "身故赔偿可一笔过或每月分期领取，毋须设立信托",
            ]},
            {"file": "09_company.png", "layout": "list", "eyebrow": "承保公司", "title": "财务实力",
             "subtitle": "万通保险国际有限公司 (YF Life)", "kicker": "公司 · Company", "items": [
                "港交所上市公司云锋金融集团成员",
                "主要股东包括美国万通人寿保险（全美5大互惠寿险公司之一）",
                "惠誉国际给予「A-」（强劲）保险财务实力评级",
                "分红计划目标：不少于90%的可分配盈余分配给保单持有人",
            ]},
            {"file": "10_risks.png", "layout": "list", "eyebrow": "重要提示", "title": "投保前必读",
             "subtitle": "请务必理解以下风险", "kicker": "提示 · Notice", "items": [
                "终期红利非保证，某些情况下可能为零",
                "本产品为长线持有而设，提早退保可能蒙受重大损失",
                "保单日期起一年内自杀，责任只限于退还已缴保费",
                "保费征费由保监局收取，征费率与上限可能逐年变动",
                "冷静期为21个历日；一切以保单条款为准",
            ]},
        ]
    cards.extend(fixed)

    missing = []
    for label, m in [("现金价值", cash_missing), ("身故", death_missing),
                     ("情景-现金价值", scen_missing), ("情景-身故保障", scen_death_missing)]:
        missing.extend(m or [])
    return cards, missing


def build_extension_cards(info: dict[str, Any]) -> list[dict]:
    """扩展卡：CI 疾病清单 + 两张 LLM 文章卡。"""
    product = info.get("product", "pwl")
    ext: list[dict] = []
    next_no = 11

    # 11-12. CI 疾病清单卡（仅 ci 产品）—— 拆成两张避免单卡过长：
    #   11: 早期疾病 + 原位癌（13 项，赔付上限 45,000 美元 / 30%）
    #   12: 主要严重疾病（14 项，首10年 135% / 其后 100%）
    if product == "ci":
        early_groups = CI_DISEASE_GROUPS[:2]   # 早期疾病 + 原位癌
        major_groups = CI_DISEASE_GROUPS[2:]   # 主要严重疾病
        intro = ""
        if _LLM_OK:
            try:
                intro = write_ci_diseases_intro(info)
            except Exception as exc:
                sys.stderr.write(f"[build_guizang] CI intro LLM failed: {exc}\n")
        intro = intro or "保障覆盖早期疾病、原位癌及主要严重疾病三个层级，按严重程度分级赔付。"

        ext.append({
            "file": f"{next_no:02d}_ci_diseases_early.png",
            "layout": "ci-list",
            "eyebrow": "危疾保障范围 · 早期",
            "title": "覆盖疾病清单（早期保障）",
            "subtitle": "早期疾病 + 原位癌 · 赔付上限 45,000 美元 (30%)",
            "kicker": "清单 1/2 · Early Stage",
            "intro": intro,
            "groups": early_groups,
            "note": "以上为代表性病种，非穷举；具体以保单条款为准。早期疾病与原位癌合计赔付上限为基本保障额的 30%。",
        })
        next_no += 1

        ext.append({
            "file": f"{next_no:02d}_ci_diseases_major.png",
            "layout": "ci-list",
            "eyebrow": "危疾保障范围 · 主要",
            "title": "覆盖疾病清单（主要严重疾病）",
            "subtitle": "首10年 202,500 美元 (135%) · 其后 150,000 美元 (100%)",
            "kicker": "清单 2/2 · Major",
            "intro": "主要严重疾病保障在首10个保单年度享额外35%保障额（推广优惠），其后维持100%基本保障额。",
            "groups": major_groups,
            "note": "以上为代表性病种，非穷举；具体以保单条款为准。严重疾病保障总额达100%基本保障额后，保单即终止。",
        })
        next_no += 1

    # 13. 致受保人的一封信
    letter_body = ""
    if _LLM_OK:
        try:
            letter_body = write_emotional_letter(info)
        except Exception as exc:
            sys.stderr.write(f"[build_guizang] letter LLM failed: {exc}\n")
    ext.append({
        "file": f"{next_no:02d}_letter.png",
        "layout": "article",
        "eyebrow": "致受保人",
        "title": "致受保人的一封信",
        "subtitle": f"写给 {info.get('name', '')} 的一段话",
        "kicker": "信笺 · Letter",
        "body": letter_body,
        "pullquote": "一份保障，是一句无需开口的承诺。",
    })
    next_no += 1

    # 14. 保障与人生阶段
    stage_body = ""
    if _LLM_OK:
        try:
            stage_body = write_life_stage_article(info)
        except Exception as exc:
            sys.stderr.write(f"[build_guizang] stage LLM failed: {exc}\n")
    ext.append({
        "file": f"{next_no:02d}_stage.png",
        "layout": "article",
        "eyebrow": "保障与人生阶段",
        "title": "此刻的保障，此生的安心",
        "subtitle": f"{info.get('age', '')}岁的人生节点",
        "kicker": "随笔 · Essay",
        "body": stage_body,
        "pullquote": "把不确定性留在门外，把确定性交给保单。",
    })
    next_no += 1

    # 末卡. 卷首语引言图（jm.jpg，万通保险品牌引言）—— 全图嵌入，不额外加文字
    ext.append({
        "file": f"{next_no:02d}_epigraph.png",
        "layout": "image",
        "title": "保险的使命",
        "subtitle": "是给人安全感",
        "kicker": "卷首语 · Epigraph",
        "image": "jm.jpg",
    })
    return ext


def main():
    parser = argparse.ArgumentParser(description="计划书 md -> Guizang cards.json")
    parser.add_argument("output_dir", type=str, help="包含三个 md 的目录")
    parser.add_argument("--output", type=str, default="cards.json", help="输出 cards.json 路径")
    args = parser.parse_args()

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

    base_cards, missing = build_base_cards(info, years_tables, scenario_tables)
    ext_cards = build_extension_cards(info)
    cards = base_cards + ext_cards

    copy = product_copy(info)
    meta = {
        "title": copy["meta_title"],
        "width": 1080,
        "height": 1440,
        "theme": "ink-classic",
        "style": "guizang",
        "footer": "仅供说明参考，非保证收益，以保单条款为准",
    }

    payload = {"meta": meta, "cards": cards}
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"Guizang cards.json 已生成: {args.output}")
    print(f"卡片数: {len(cards)} (基础{len(base_cards)} + 扩展{len(ext_cards)})")
    if missing:
        print(f"提示: 部分关键行缺失已省略: {missing}")


if __name__ == "__main__":
    main()
