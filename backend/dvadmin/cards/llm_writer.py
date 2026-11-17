"""DeepSeek LLM writer — generates emotional article copy for Guizang cards.

Uses the OpenAI-compatible /chat/completions endpoint via httpx (already a
backend dependency), so no `openai` SDK is required. Reads credentials from
config.settings (which loads .env). All network calls are wrapped with a
generous timeout and graceful fallback: if the API fails or is unconfigured,
the caller receives a deterministic fallback string so the pipeline never
blocks on a missing LLM response.

The writer never touches financial figures — it only produces narrative
framing text (greetings, life-stage reflections, closing notes) keyed off
non-sensitive insured metadata (name, age, gender, product, coverage band).
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

import os

_DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
_DEEPSEEK_BASE = os.getenv("DEEPSEEK_BASE", "https://api.deepseek.com")
_DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")

log = logging.getLogger("llm_writer")

# Deterministic fallbacks used when the LLM is unavailable or returns nothing
# usable. Kept short and generic so they compose cleanly into a card.
_FALLBACK_LETTER = (
    "亲爱的{salutation}：\n\n"
    "这份保障，是为您此刻的人生而设。{age}岁的您，正站在责任与未来的交汇处——"
    "一份足额的保障，不只是数字，更是对家人一句安心的承诺。\n\n"
    "无论顺境逆境，保单都会替您守住这份承诺。愿您与所爱之人，岁岁安康。"
)
_FALLBACK_STAGE = (
    "{age}岁，是规划未来的关键节点。此时建立保障，保费相对可控，"
    "保障年期却足够长，能覆盖家庭责任最重的阶段。\n\n"
    "把不确定性留在门外，把确定性交给保单——这正是保障最朴素的意义。"
)


def _salutation(name: str, gender: str) -> str:
    """受保人称呼：先生/女士/朋友。

    重要：PDF 提取的 name 可能已含「先生/女士」(如 "Mr. Peng先生"),
    避免出现「Mr. Peng先生先生」重复。
    """
    name = (name or "").strip()
    g = (gender or "").strip()
    if name.endswith("先生") or name.endswith("女士"):
        return name
    if "女" in g:
        return f"{name}女士" if name else "女士"
    if "男" in g:
        return f"{name}先生" if name else "先生"
    return name or "朋友"


def _client() -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(60.0, connect=10.0),
        headers={
            "Authorization": f"Bearer {_DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        },
    )


def _chat(messages: list[dict[str, str]], *, max_tokens: int = 700) -> str:
    """Call DeepSeek chat completions. Returns the assistant text, or "" on any failure."""
    if not _DEEPSEEK_API_KEY:
        log.warning("DEEPSEEK_API_KEY not set — LLM disabled, using fallback copy.")
        return ""
    url = _DEEPSEEK_BASE.rstrip("/") + "/chat/completions"
    payload = {
        "model": _DEEPSEEK_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.85,
        "top_p": 0.9,
        "stream": False,
    }
    try:
        with _client() as c:
            r = c.post(url, json=payload)
        if r.status_code >= 400:
            log.warning("DeepSeek API %s: %s", r.status_code, r.text[:300])
            return ""
        data = r.json()
        return (data.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()
    except Exception as exc:  # network / parse / timeout — never raise to caller
        log.warning("DeepSeek call failed: %s", exc)
        return ""


def _strip_fences(text: str) -> str:
    """LLMs sometimes wrap prose in ```markdown fences — strip them."""
    t = text.strip()
    if t.startswith("```"):
        # drop leading fence (with optional language tag) and trailing fence
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        if t.endswith("```"):
            t = t[:-3]
    return t.strip()


# ── Public API ────────────────────────────────────────────────────────────


def write_emotional_letter(info: dict[str, Any]) -> str:
    """致受保人的一封信 — warm, short, grounded in the insured's actual info.

    ``info`` is the parsed first-page dict from build_cards.parse_first_page
    (name, age, gender, product, sum_insured, ...). Numbers are referenced as
    display strings; we never recompute financial figures.
    """
    name = str(info.get("name", "")).strip()
    gender = str(info.get("gender", "")).strip()
    age = str(info.get("age", "")).strip()
    product = str(info.get("product", "")).strip()
    sum_insured = str(info.get("sum_insured", "")).strip()
    salutation = _salutation(name, gender)

    product_label = {
        "ci": "危疾保障", "joy": "储蓄寿险", "pwl": "终身寿险",
    }.get(product, "保障计划")

    prompt = (
        "你是香港保险顾问的文案助手。请根据以下受保人信息，写一封简短、真挚、克制的"
        "「致受保人的一封信」，用于保险计划书图文卡片的其中一页。\n\n"
        "要求：\n"
        "1. 中文，120-180字，分2-3段；\n"
        "2. 语气温暖但不浮夸，避免营销话术与感叹号堆砌；\n"
        "3. 自然地带入受保人的年龄、性别、保障类型，但不要复述具体保额数字；\n"
        "4. 落款「此致 敬礼」+ 换行 + 「您的保险顾问」；\n"
        "5. 只输出信件正文，不要标题、不要解释、不要 markdown 代码块。\n\n"
        f"受保人信息：称呼={salutation}，年龄={age}岁，性别={gender}，"
        f"保障类型={product_label}。"
    )
    text = _chat(
        [{"role": "system", "content": "你是专业的保险文案撰稿人，擅长克制、有温度的中文写作。"},
         {"role": "user", "content": prompt}],
        max_tokens=520,
    )
    if text:
        return _strip_fences(text)
    return _FALLBACK_LETTER.format(salutation=salutation, age=age)


def write_life_stage_article(info: dict[str, Any]) -> str:
    """保障与人生阶段 — connect the coverage to the insured's life stage."""
    name = str(info.get("name", "")).strip()
    gender = str(info.get("gender", "")).strip()
    age = str(info.get("age", "")).strip()
    product = str(info.get("product", "")).strip()
    premium_term = str(info.get("premium_term", "")).strip()
    salutation = _salutation(name, gender)

    product_label = {
        "ci": "危疾保障", "joy": "储蓄寿险", "pwl": "终身寿险",
    }.get(product, "保障计划")

    prompt = (
        "你是香港保险顾问的文案助手。请根据受保人信息，写一段「保障与人生阶段」的短文，"
        "用于保险计划书图文卡片的其中一页。\n\n"
        "要求：\n"
        "1. 中文，140-200字，分2段；\n"
        "2. 解释在这个年龄建立保障的意义：保费可控、保障年期长、覆盖家庭责任期；\n"
        "3. 语气克制、有洞察，不要营销话术，不要感叹号；\n"
        "4. 可以带入受保人称呼和年龄，但不要复述保额与保费数字；\n"
        "5. 只输出正文，不要标题、不要解释、不要 markdown 代码块。\n\n"
        f"受保人信息：称呼={salutation}，年龄={age}岁，性别={gender}，"
        f"保障类型={product_label}，缴费年期={premium_term}年。"
    )
    text = _chat(
        [{"role": "system", "content": "你是专业的保险文案撰稿人，擅长把保障与人生阶段联系起来。"},
         {"role": "user", "content": prompt}],
        max_tokens=620,
    )
    if text:
        return _strip_fences(text)
    return _FALLBACK_STAGE.format(age=age)


def write_ci_diseases_intro(info: dict[str, Any]) -> str:
    """CI disease list intro — one short framing sentence for the disease card."""
    age = str(info.get("age", "")).strip()
    salutation = _salutation(str(info.get("name", "")), str(info.get("gender", "")))
    prompt = (
        "请用一句话（30-50字，中文）介绍危疾保险覆盖的疾病范围，"
        "语气克制专业，提及「早期疾病」「原位癌」「主要严重疾病」三个层级，"
        "不要感叹号，不要营销话术，只输出这一句话。"
        f"背景：受保人 {salutation}，{age}岁。"
    )
    text = _chat(
        [{"role": "system", "content": "你是保险医学文案撰稿人。"},
         {"role": "user", "content": prompt}],
        max_tokens=120,
    )
    if text:
        return _strip_fences(text)
    return "保障覆盖早期疾病、原位癌及主要严重疾病三个层级，按严重程度分级赔付。"


_FALLBACK_PRU_LETTER = (
    "感谢您花时间阅读这份计划书。{age}岁的您，正站在责任与未来的交汇处——"
    "一份足额的保障，不只是数字，更是对家人一句无需开口的承诺。\n\n"
    "这份保单将与您一同守护您所珍视的一切。无论顺境逆境，它都将在那里，"
    "替您守住这份承诺。愿您与所爱之人，岁岁安康。\n\n"
    "此致\n敬礼\n\n您的保险顾问"
)
_FALLBACK_PRU_ESSAY = (
    "{age}岁，是规划未来的关键节点。\n\n"
    "此时建立保障，保费相对可控，保障年期却足够长——"
    "能覆盖家庭责任最重的阶段，也能让时间替您累积复利。\n\n"
    "把不确定性留在门外，把确定性交给保单——"
    "这正是保障最朴素，也最有力的意义。"
)


def write_llm_letter(info: dict[str, Any]) -> str:
    """llm 风格 · 致受保人的一封信 — 热情 + 专业的中文信。

    与归藏版的 write_emotional_letter 区别：更长一些 (180-240字),
    落款改为「此致敬礼 + 您的保险顾问」, 第二段明确「与受保人共同守护」，
    整体温度略高、说理更扎实。

    若 info 里有 product_positioning / positioning_points（来自模板 copy），
    提示词会按产品定位定制措辞（如储蓄养老、财富传承、危疾守护）。
    """
    name = str(info.get("name", "")).strip()
    gender = str(info.get("gender", "")).strip()
    age = str(info.get("age", "")).strip()
    product = str(info.get("product", "")).strip()

    positioning = str(info.get("product_positioning", "")).strip()
    points = info.get("positioning_points") or []

    if positioning:
        product_label = positioning
    else:
        product_label = {
            "ci": "危疾保障", "joy": "储蓄寿险", "pwl": "终身寿险", "bis": "储蓄养老保障",
        }.get(product, "保障计划")

    # 卖点要点：仅作概括参考 —— 信要简短克制，只需自然带出 1-2 个核心价值，
    # 不必逐条罗列，避免篇幅过长被打断。
    points_text = ""
    if points:
        points_text = (
            "\n\n【产品卖点（仅供参考，信中只需概括体现核心价值，不要逐条罗列）】\n"
            + "\n".join(f"- {p}" for p in points)
        )

    prompt = (
        "你是香港保险顾问的文案助手。请根据以下受保人信息，写一封 llm 风格（小红书/朋友圈转发感）的"
        "「致受保人的一封信」，用于保险计划书图文卡片的其中一页。\n\n"
        "要求：\n"
        "1. 中文，150-200字，分3段；保持简洁，宁可精炼也不要写太长；\n"
        "2. 语气热情但保持专业、有洞察力，避免营销话术堆砌，避免感叹号；\n"
        "3. 第一段：感谢 + 受保人当前人生阶段；\n"
        "4. 第二段：概括这份保单的核心价值（贴合产品定位），只需自然带出 1-2 个卖点，"
        "其余一笔带过或概括，切忌逐条罗列卖点；\n"
        "5. 第三段：一句克制的祝愿；\n"
        "6. 落款：「此致」「敬礼」「您的保险顾问」三行；\n"
        "7. 【关键】正文完全不要出现受保人姓名/称呼（如「VIP女士」「王先生」等），"
        "统一用「您」或省略主语，正文从「感谢您...」或「45岁的您...」等内容开始；\n"
        "8. 只输出信件正文，不要标题、不要解释、不要 markdown 代码块；\n"
        "9. 【关键】正文中不要用「让{称呼}…」这种第三人称使动句式，"
        "这种写法不符合中文语境。需要用动作主体时直接用「您」（如「不妨以两年缴费为起点」或「您不妨以两年缴费为起点」），"
        "或省略主语。\n\n"
        f"受保人信息：年龄={age}岁，性别={gender}，"
        f"保障类型={product_label}。{points_text}"
    )
    text = _chat(
        [{"role": "system", "content": "你是专业的保险文案撰稿人，擅长热情而克制的中文写作。"},
         {"role": "user", "content": prompt}],
        max_tokens=2000,
    )
    if text:
        return _strip_fences(text)
    return _FALLBACK_PRU_LETTER.format(age=age)


def write_llm_essay(info: dict[str, Any]) -> str:
    """llm 风格 · 人生阶段随笔 — 热情 + 专业的短文。

    与归藏版的 write_life_stage_article 区别：更聚焦「保费可控 / 年期长 /
    复利积累」三件事，结尾有明确行动建议（「把不确定性留在门外」）。

    若 info 里有 product_positioning / positioning_points（来自模板 copy），
    提示词会按产品定位定制措辞（如储蓄养老、财富传承、危疾守护）。
    """
    name = str(info.get("name", "")).strip()
    gender = str(info.get("gender", "")).strip()
    age = str(info.get("age", "")).strip()
    product = str(info.get("product", "")).strip()
    premium_term = str(info.get("premium_term", "")).strip()
    salutation = _salutation(name, gender)

    positioning = str(info.get("product_positioning", "")).strip()
    points = info.get("positioning_points") or []

    if positioning:
        product_label = positioning
    else:
        product_label = {
            "ci": "危疾保障", "joy": "储蓄寿险", "pwl": "终身寿险", "bis": "储蓄养老保障",
        }.get(product, "保障计划")

    points_text = ""
    if points:
        points_text = (
            "\n\n【产品卖点（必须在本短文中尽量自然地体现，最好逐条覆盖，不要遗漏）】\n"
            + "\n".join(f"- {p}" for p in points)
        )

    prompt = (
        "你是香港保险顾问的文案助手。请根据受保人信息，写一段 llm 风格的"
        "「保障与人生阶段」短文，用于保险计划书图文卡片的其中一页。\n\n"
        "要求：\n"
        "1. 中文，160-220字，分2-3段；\n"
        "2. 聚焦三件事：(a) 此时投保保费相对可控、(b) 保障年期足够长覆盖家庭责任期、"
        "(c) 时间带来的复利积累；措辞要贴合产品定位，并尽量自然地融入下方产品卖点；\n"
        "3. 语气热情但克制、有洞察，避免营销话术，避免感叹号；\n"
        "4. 可以带入受保人年龄（如「45岁」），但不要复述保额与保费数字；\n"
        "5. 结尾给一个明确、克制的行动建议；\n"
        "6. 只输出正文，不要标题、不要解释、不要 markdown 代码块；\n"
        "7. 【关键】正文完全不要出现受保人姓名/称呼（如「VIP女士」「王先生」等），"
        "统一用「您」或省略主语；正文中也不要用「让{称呼}…」这种第三人称使动句式，"
        "动作主体直接用「您」（如「不妨以两年缴费为起点」或「您不妨以两年缴费为起点」）。\n\n"
        f"受保人信息：年龄={age}岁，性别={gender}，"
        f"保障类型={product_label}，缴费年期={premium_term}年。{points_text}"
    )
    text = _chat(
        [{"role": "system", "content": "你是专业的保险文案撰稿人，擅长把保障与人生阶段联系起来。"},
         {"role": "user", "content": prompt}],
        max_tokens=2000,
    )
    if text:
        return _strip_fences(text)
    return _FALLBACK_PRU_ESSAY.format(age=age)


if __name__ == "__main__":
    # Quick smoke test: python llm_writer.py
    import sys
    sample = {
        "name": "Ms. VIP", "gender": "女", "age": "45",
        "product": "ci", "sum_insured": "150,000", "premium_term": "15",
    }
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    print("--- LETTER ---")
    print(write_emotional_letter(sample))
    print("\n--- STAGE ---")
    print(write_life_stage_article(sample))
    print("\n--- CI INTRO ---")
    print(write_ci_diseases_intro(sample))
    print("\n--- PRU LETTER ---")
    print(write_llm_letter(sample))
    print("\n--- PRU ESSAY ---")
    print(write_llm_essay(sample))
