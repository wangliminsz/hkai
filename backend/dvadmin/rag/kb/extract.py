from __future__ import annotations

import json
import re

from .config import chat_model, llm_credentials

_SYS = "你是香港保险产品资料整理助手。只输出 JSON, 不要任何多余文字或解释。"

_PROMPT = (
    "根据以下保险产品 PDF 的文本片段, 提取产品信息, 只返回 JSON(字段缺失用 null/空):\n"
    "{\n"
    '  "name": "产品正式名称(繁体中文优先)。只填产品名本身, 不要包含「產品手冊/产品手册/產品介紹/計劃書」等字样或后缀",\n'
    '  "name_en": "英文产品名(通常紧跟在中文名下方; 找不到才留空)",\n'
    '  "insurer": "承保保险公司。格式固定为「英文名或缩写（中文名）」——英文在前、中文在括号内, 缩写可用, 如 YF Life（萬通保險）、AIA（友邦保險）、Prudential（保誠）",\n'
    '  "category": "类别(如 人壽 / 終身壽險, 嚴重疾病 / 危疾, 儲蓄及退休 / 儲蓄保險)",\n'
    '  "summary": "一句话概述(繁体中文, 供产品路由用)",\n'
    '  "tags": ["关键词", "..."],\n'
    '  "compare_group": "可对比分组的英文标识, 用类别英文简称(如 Critical Illness / Whole Life / Savings / Annuity / Retirement 等; 不确定填 null)",\n'
    '  "documents": [{"filename":"原文件名","doc_type":"brochure|contract|other","title":"文档标题"}]\n'
    "}\n\n"
)

# 名称里需要剥离的噪声后缀(忽略大小写/全半角差异)
_NAME_NOISE = [
    "產品手冊", "产品手册", "產品介紹", "产品介绍", "產品概覽", "产品概览",
    "計劃書", "计划书", "投保指南", "產品簡介", "产品简介", "小冊子", "小册子",
    "brochure", "leaflet", "flyer", "prospectus", "guide", "product manual",
]
_SEP = ["-", "－", "—", "–", "·", "|", "_", " ", "：", ":"]


def _parse_json(text: str) -> dict:
    text = (text or "").strip()
    text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
    text = re.sub(r"```$", "", text).strip()
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0) if m else text)


def _llm_json(prompt: str) -> dict:
    import litellm

    creds = llm_credentials()
    last_err: Exception | None = None
    for attempt in range(2):
        base = {
            "model": chat_model(),
            "messages": [
                {"role": "system", "content": _SYS},
                {"role": "user", "content": prompt + ("\n\n务必只输出 JSON。" if attempt else "")},
            ],
            "api_key": creds.get("api_key"),
            "base_url": creds.get("base_url"),
            "temperature": 0.2,
            "max_tokens": 2048,
        }
        try:
            try:
                resp = litellm.completion(reasoning_effort="low", **base)
            except Exception:
                resp = litellm.completion(**base)
            message = resp.choices[0].message
            text = (message.content or "").strip()
            if not text:
                text = (getattr(message, "reasoning_content", "") or "").strip()
            return _parse_json(text)
        except Exception as exc:  # noqa: BLE001
            last_err = exc
    raise last_err or RuntimeError("extract_metadata failed")


def extract_metadata(docs: list[dict], known_insurers=None) -> dict:
    """docs = [{'filename': str, 'text': str}] → 产品元数据 dict。"""
    parts = []
    for d in docs:
        parts.append(f"### 文件: {d.get('filename')}\n{(d.get('text') or '')[:3500]}")
    hint = ""
    if known_insurers:
        hint = "已有保险公司(若为同一家公司请原样沿用已有写法, 不要改写): " + "; ".join(known_insurers) + "\n\n"
    return _llm_json(_PROMPT + hint + "PDF 文本:\n" + "\n\n".join(parts))


def clean_name(name: str | None) -> str:
    """剥离名称里的 產品手冊/產品介紹 等噪声后缀与分隔符。"""
    if not name:
        return ""
    n = str(name).strip().strip("".join(_SEP))
    changed = True
    while changed:
        changed = False
        for w in _NAME_NOISE:
            low = n.lower()
            wl = w.lower()
            if low.endswith(wl):
                n = n[: -len(w)].strip("".join(_SEP))
                changed = True
                continue
            for sep in _SEP:
                if low.endswith((sep + wl)):
                    n = n[: -(len(sep) + len(w))].strip("".join(_SEP))
                    changed = True
                    break
        n = n.strip("".join(_SEP))
    return n or str(name).strip()


def guess_name_zh(text: str) -> str | None:
    """从 PDF 文本取最像产品名的中文行(通常是封面首行)。"""
    for line in (text or "").splitlines():
        s = line.strip()
        if 4 <= len(s) <= 40 and len(re.findall(r"[\u4e00-\u9fff]", s)) >= 4:
            if re.search(r"(保險|保险|計劃|计划|壽險|寿险|危疾|儲蓄|储蓄|年金|保障|理財|理财)", s):
                return s
    return None


def guess_name_en(text: str) -> str | None:
    """从 PDF 文本取英文产品名(纯 ASCII 且含保险关键词的行)。"""
    for line in (text or "").splitlines():
        s = line.strip()
        if not (6 <= len(s) <= 90):
            continue
        if re.search(r"[\u4e00-\u9fff]", s):
            continue
        if len(re.findall(r"[A-Za-z]", s)) < 6:
            continue
        if re.search(r"(Insurance|Assurance|Plan|Life|Savings|Protect|Care|Whole|Health|Annuity|Legacy)", s, re.I):
            return s
    return None
