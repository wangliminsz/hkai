"""AI 提示词仓库: 可在后台覆盖代码里的默认提示词。

`get_prompt(key, default)` 优先取数据库 `AiPrompt`(非空)，否则用默认值。
默认值来自 analysis.py / news.py 的常量，运行时惰性导入避免循环依赖。
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# key -> (标题, 说明)
PROMPT_META: dict[str, tuple[str, str]] = {
    "fund_analysis.system": ("基金深度分析 · 主提示词", "QVeris agent 的用户提示词(分析风格/输出要求)"),
    "fund_analysis.live_data": ("基金深度分析 · 实时数据要求", "附加到 agent system prompt，强制先查实时行情/新闻"),
    "news.summary": ("新闻播报 · 飞书摘要", "飞书卡片摘要提示词；必须保留 {news_json} 占位符"),
    "news.brief_md": ("新闻播报 · 详细文字版", "文字版 markdown 提示词；必须保留 {news_json} 与 {date} 占位符"),
    "docai.prompt": ("AI 文件分析 · 统一提示词", "上传 PDF/图片的分析要求（QVeris）"),
}


def default_prompts() -> dict[str, str]:
    from . import news
    from .analysis import LIVE_DATA_SYSTEM_PROMPT, QVERIS_PROMPT
    from dvadmin.docai import services as docai_services

    return {
        "fund_analysis.system": QVERIS_PROMPT,
        "fund_analysis.live_data": LIVE_DATA_SYSTEM_PROMPT,
        "news.summary": news._SUMMARY_PROMPT,
        "news.brief_md": news._BRIEF_MD_PROMPT,
        "docai.prompt": docai_services.DEFAULT_PROMPT,
    }


def get_prompt(key: str, default: str) -> str:
    """DB override (non-empty) else default."""
    try:
        from .models import AiPrompt

        row = AiPrompt.objects.filter(key=key).first()
        if row and (row.content or "").strip():
            return row.content
    except Exception as exc:  # noqa: BLE001 - never break the caller
        logger.warning("[PROMPT] load %s failed: %s", key, exc)
    return default


def get_fund_prompt(key: str) -> str:
    """Convenience for analysis.py (falls back to its own constants)."""
    return get_prompt(key, default_prompts().get(key, ""))
