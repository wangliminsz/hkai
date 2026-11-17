"""Daily finance news: fetch sources -> DeepSeek brief -> Feishu card (no PNG cards)."""
from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
import time
from datetime import datetime
from html import escape
from pathlib import Path
from string import Formatter, Template

import markdown as _md
import requests
from django.conf import settings

from .news_fetch import rss_parser
from . import prompts

logger = logging.getLogger(__name__)

_NEWS_DIR = Path(__file__).resolve().parent / "news_fetch"

BUILTIN_KEYS = {
    "wallstreetcn", "36kr", "tencent", "weibo", "hackernews", "github", "producthunt",
    "v2ex", "lobsters", "devto", "sspai", "infoq_cn", "arxiv", "aihot", "tldr_ai",
    "import_ai", "international", "bbc_top", "bbc_world", "bbc_chinese",
    "guardian_world", "aljazeera", "france24", "reuters", "huggingface", "ai_newsletters",
}

BUILTIN_LABELS = {
    "wallstreetcn": "华尔街见闻", "36kr": "36氪", "tencent": "腾讯新闻", "weibo": "微博",
    "hackernews": "Hacker News", "github": "GitHub Trending", "producthunt": "Product Hunt",
    "v2ex": "V2EX", "reuters": "Reuters", "bbc_top": "BBC", "bbc_chinese": "BBC 中文",
    "guardian_world": "The Guardian", "aljazeera": "Al Jazeera", "france24": "France 24",
    "aihot": "AIHOT", "tldr_ai": "TLDR AI", "import_ai": "Import AI", "arxiv": "arXiv",
    "huggingface": "Hugging Face",
}


def _opt(name, default=None):
    return getattr(settings, name, None) or default


def _coerce_items(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        out = []
        for v in data.values():
            if isinstance(v, list):
                out.extend(v)
        return out
    return []


def fetch_builtin(key: str, limit: int = 15, keywords: str = "") -> list[dict]:
    args = [sys.executable, "fetch_news.py", "--source", key, "--limit", str(limit), "--no-save"]
    if keywords:
        args += ["--keyword", keywords]
    proc = subprocess.run(args, cwd=str(_NEWS_DIR), capture_output=True, text=True, timeout=180)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or "")[-500:] or f"fetch_news exit {proc.returncode}")
    return _coerce_items(json.loads(proc.stdout or "[]"))


def fetch_rss(url: str, name: str, limit: int = 10) -> list[dict]:
    return rss_parser.fetch_rss_feed(url, name, limit)


def collect(sources) -> tuple[list[dict], list[str]]:
    """Return (items, source display names) for enabled NewsSource rows."""
    items: list[dict] = []
    labels: list[str] = []
    seen: set[str] = set()
    for src in sources:
        kind = (src.kind or "").strip()
        value = (src.value or "").strip()
        if not value:
            continue
        display = src.name or BUILTIN_LABELS.get(value, value)
        labels.append(display)
        try:
            if kind == "builtin":
                rows = fetch_builtin(value, src.limit or 10, src.keywords or "")
            else:
                rows = fetch_rss(value, display, src.limit or 10)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[NEWS] source %s failed: %s", display, exc)
            rows = []
        for it in rows:
            if not isinstance(it, dict):
                continue
            title = (it.get("title") or "").strip()
            url = (it.get("url") or "").strip()
            key = url or title
            if not key or key in seen:
                continue
            seen.add(key)
            items.append({**it, "src_name": display})
    return items, labels


_SUMMARY_PROMPT = """你是资深金融资讯编辑。根据下面的「今日新闻 JSON」，写一份今日金融简报。
只输出 JSON，格式：
{{
  "title": "一句话定调（≤20字，如：AI 杠杆牛市信用验证期）",
  "summary": "飞书 lark_md 纯文本，≤700字。必须用以下结构，段与段之间空一行：\\n【美股】…\\n\\n【A股】…\\n\\n【三件事】①…②…③…\\n\\n【一句话】…"
}}

硬性要求：
- 只用 JSON 中出现的事实与数字，绝不编造；数字精确（百分比/金额）。
- 简体中文，客观中性，不写买入/卖出建议。
- 每个板块 1-3 句，按重要性取舍；某板块无素材就写「今日暂无显著信号」。
- summary 里不要出现 markdown 标题符号(#)，只用【】分块。

=== 今日新闻 JSON ===
{news_json}
"""

_BRIEF_MD_PROMPT = """你是资深金融资讯编辑。根据下面的「今日新闻 JSON」，写一份**详细 markdown 文字版**简报。
只输出 JSON，格式：{{"brief_md": "……markdown 正文……"}}（markdown 里的换行用 \\n 转义）。

【markdown 要求】
- 必须以 `# 今日金融资讯 · {date}` 开头，且只包含以下章节（顺序固定）：
  `> **一句话定调**:…` → `---` → `## 一、隔夜美股与全球宏观` → `## 二、A股 / 港股 / 国内财经`
  → `## 三、加密与另类资产 / 其他` → `---` → `## 📌 关键数字`(3-5 行 markdown 表格)
  → `## ⚠️ 风险点` → `## 🎯 今日 Takeaway`(≤80 字引用块)。
- 每个板块 ≤5 条要点，按重要性排序；每条要点后**至少一条**来源子项，格式为 4 个空格缩进的
  `    - 来源: [来源名](url)`；同一条要点若有多个来源，则每个来源各占一行。
- 来源必须带 markdown 链接，url 一律取自 JSON，不要省略；正文 800-1500 字。
- 只用 JSON 中出现的事实与数字，绝不编造；简体中文，客观中性，不写买卖建议。
- 某板块无素材写「今日无重大消息」；不要用 ``` 代码围栏。

=== 今日新闻 JSON ===
{news_json}
"""

# JSON 输出失败时的兜底: 直接让模型输出 markdown，避免 JSON 转义/截断问题。
_BRIEF_MD_PLAIN_PROMPT = """你是资深金融资讯编辑。根据下面的「今日新闻 JSON」，直接输出一份**详细 markdown 文字版**简报。
不要输出 JSON，不要用 ``` 代码围栏，只输出 markdown 正文。

【markdown 要求】
- 必须以 `# 今日金融资讯 · {date}` 开头，且只包含以下章节（顺序固定）：
  `> **一句话定调**:…` → `---` → `## 一、隔夜美股与全球宏观` → `## 二、A股 / 港股 / 国内财经`
  → `## 三、加密与另类资产 / 其他` → `---` → `## 📌 关键数字`(3-5 行 markdown 表格)
  → `## ⚠️ 风险点` → `## 🎯 今日 Takeaway`(≤80 字引用块)。
- 每个板块 ≤5 条要点，按重要性排序；每条要点后**至少一条**来源子项，格式为 4 个空格缩进的
  `    - 来源: [来源名](url)`；同一条要点若有多个来源，则每个来源各占一行。
- 来源必须带 markdown 链接，url 一律取自 JSON，不要省略；正文 800-1500 字。
- 只用 JSON 中出现的事实与数字，绝不编造；简体中文，客观中性，不写买卖建议。
- 某板块无素材写「今日无重大消息」。

=== 今日新闻 JSON ===
{news_json}
"""


def _llm_json(prompt: str, max_tokens: int = 1600) -> dict:
    import litellm

    model = _opt("DEEPSEEK_MODEL", "deepseek-flash") or "deepseek-flash"
    if not model.startswith("openai/"):
        model = "openai/" + model
    base = _opt("DEEPSEEK_BASE", "https://api.deepseek.com")
    api_key = _opt("DEEPSEEK_API_KEY")

    last = None
    for attempt in range(2):
        kwargs = dict(model=model, api_key=api_key, base_url=base,
                      messages=[{"role": "system", "content": "你是资深金融资讯编辑，只输出 JSON。"},
                                {"role": "user", "content": prompt + ("\n\n务必只输出 JSON。" if attempt else "")}],
                      temperature=0.3, max_tokens=max_tokens,
                      response_format={"type": "json_object"})
        try:
            try:
                resp = litellm.completion(reasoning_effort="low", **kwargs)
            except Exception:
                try:
                    resp = litellm.completion(**kwargs)
                except Exception:
                    kwargs.pop("response_format", None)
                    resp = litellm.completion(**kwargs)
            msg = resp.choices[0].message
            text = (msg.content or "").strip() or (getattr(msg, "reasoning_content", "") or "").strip()
            if not text:
                finish = getattr(resp.choices[0], "finish_reason", "?")
                usage = getattr(resp, "usage", None)
                logger.warning("[NEWS] LLM returned empty content (finish=%s usage=%s attempt=%d)",
                               finish, usage, attempt + 1)
                last = RuntimeError(f"empty LLM response (finish={finish})")
                continue
            text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
            text = re.sub(r"```$", "", text).strip()
            m = re.search(r"\{.*\}", text, re.S)
            return json.loads(m.group(0) if m else text)
        except Exception as exc:  # noqa: BLE001
            last = exc
    raise last or RuntimeError("新闻简要生成失败")


def _llm_text(prompt: str, max_tokens: int = 6000) -> str:
    """纯文本/markdown 输出(不要求 JSON)，用于 JSON 解析失败时的兜底。"""
    import litellm

    model = _opt("DEEPSEEK_MODEL", "deepseek-flash") or "deepseek-flash"
    if not model.startswith("openai/"):
        model = "openai/" + model
    base = _opt("DEEPSEEK_BASE", "https://api.deepseek.com")
    api_key = _opt("DEEPSEEK_API_KEY")

    last = None
    for attempt in range(2):
        kwargs = dict(model=model, api_key=api_key, base_url=base,
                      messages=[{"role": "system", "content": "你是资深金融资讯编辑，只输出 markdown 正文。"},
                                {"role": "user", "content": prompt + ("\n\n直接输出 markdown 正文，不要 JSON。" if attempt else "")}],
                      temperature=0.3, max_tokens=max_tokens)
        try:
            try:
                resp = litellm.completion(reasoning_effort="low", **kwargs)
            except Exception:
                resp = litellm.completion(**kwargs)
            msg = resp.choices[0].message
            text = (msg.content or "").strip() or (getattr(msg, "reasoning_content", "") or "").strip()
            if not text:
                finish = getattr(resp.choices[0], "finish_reason", "?")
                usage = getattr(resp, "usage", None)
                logger.warning("[NEWS] LLM text returned empty content (finish=%s usage=%s attempt=%d)",
                               finish, usage, attempt + 1)
                last = RuntimeError(f"empty LLM response (finish={finish})")
                continue
            text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
            text = re.sub(r"```$", "", text).strip()
            return text
        except Exception as exc:  # noqa: BLE001
            last = exc
    raise last or RuntimeError("新闻文字版生成失败")


def _validate_brief_prompt(prompt: str) -> tuple[bool, str]:
    """检查 DB 覆盖的 news.brief_md 提示词是否可直接 .format()。"""
    try:
        fields = {name for _, name, _, _ in Formatter().parse(prompt) if name}
    except ValueError as exc:
        return False, f"invalid braces: {exc}"
    missing = {"news_json", "date"} - fields
    if missing:
        return False, "missing placeholders: " + ", ".join(sorted(missing))
    try:
        prompt.format(news_json="{}", date="2000-01-01")
    except Exception as exc:  # noqa: BLE001
        return False, f"format error: {exc}"
    return True, ""


def _extract_brief_md(data: dict) -> str:
    if not isinstance(data, dict):
        return ""
    md = str(data.get("brief_md") or data.get("brief") or data.get("markdown") or "").strip()
    if not md:
        for v in data.values():  # 兜底: 模型可能把 markdown 放在别的字段
            if isinstance(v, str) and v.strip().startswith("#"):
                md = v.strip()
                break
    return md


def _short_exc(exc: Exception) -> str:
    return f"{type(exc).__name__}: {str(exc)[:400]}"


def _generate_brief(date_str: str, news_json: str, small_news_json: str,
                    prompt_template: str, prompt_note: str = "") -> tuple[str, str]:
    """三次尝试: 全量 JSON -> 精简 JSON + 更大 max_tokens -> 纯 markdown。"""
    errors: list[str] = []
    if prompt_note:
        errors.append(prompt_note)

    delay = float(getattr(settings, "NEWS_LLM_CALL_DELAY", 2) or 0)
    max_tokens = int(getattr(settings, "NEWS_BRIEF_MAX_TOKENS", 6000) or 6000)
    retry_tokens = int(getattr(settings, "NEWS_BRIEF_RETRY_MAX_TOKENS", 18000) or 18000)

    # 1) 全量新闻 JSON，首次输出上限
    try:
        prompt = prompt_template.format(news_json=news_json, date=date_str)
        md = _extract_brief_md(_llm_json(prompt, max_tokens=max_tokens))
        if md:
            return md, "; ".join(errors)
        errors.append("attempt1 empty brief_md")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"attempt1 {_short_exc(exc)}")
    logger.warning("[NEWS] brief attempt1 failed: %s", errors[-1])

    if delay:
        time.sleep(delay)

    # 2) 精简新闻 JSON(减少输入/上下文压力)，重试上限可配置(默认 18000)
    try:
        prompt = prompt_template.format(news_json=small_news_json, date=date_str)
        md = _extract_brief_md(_llm_json(prompt, max_tokens=retry_tokens))
        if md:
            return md, "; ".join(errors)
        errors.append("attempt2 empty brief_md")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"attempt2 {_short_exc(exc)}")
    logger.warning("[NEWS] brief attempt2 failed: %s", errors[-1])

    if delay:
        time.sleep(delay)

    # 3) 纯 markdown(不经过 JSON)，max_tokens 用 6000 避免模型拒绝过大上限
    try:
        prompt = _BRIEF_MD_PLAIN_PROMPT.format(news_json=small_news_json, date=date_str)
        raw = _llm_text(prompt, max_tokens=6000)
        data = {}
        if raw.lstrip().startswith("{"):
            try:
                m = re.search(r"\{.*\}", raw, re.S)
                data = json.loads(m.group(0) if m else raw)
            except Exception:  # noqa: BLE001
                data = {}
        md = _extract_brief_md(data) or raw.strip()
        if md:
            return md, "; ".join(errors)
        errors.append("attempt3 empty markdown")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"attempt3 {_short_exc(exc)}")
    logger.warning("[NEWS] brief attempt3 failed: %s", errors[-1])

    return "", "; ".join(errors)


def _normalize_summary(text: str) -> str:
    parts = [p.strip() for p in re.split(r"\n+", text or "") if p.strip()]
    return "\n\n".join(parts)[:1200]


def synthesize(items: list[dict], date_str: str) -> dict:
    """返回 {title, summary, brief_md, brief_error}。

    摘要用一次 LLM 调用(小输出，稳定)；详细文字版单独调用，失败则降级为空串
    (文字版页面会退化为摘要分段)，并把失败原因写入 brief_error 供后台展示。
    """
    def _slim(rows: list[dict]) -> list[dict]:
        return [{k: (it.get(k) or "") for k in ("src_name", "title", "summary", "time", "url")} for it in rows]

    slim = _slim(items[:60])
    small_slim = _slim(items[:30])
    news_json = json.dumps(slim, ensure_ascii=False)[:30000]
    small_news_json = json.dumps(small_slim, ensure_ascii=False)[:18000]

    summary_prompt = prompts.get_prompt("news.summary", _SUMMARY_PROMPT).format(news_json=news_json)
    data = _llm_json(summary_prompt, max_tokens=2000)
    title = str(data.get("title") or "").strip()[:60]
    summary = _normalize_summary(str(data.get("summary") or ""))

    # 两次 LLM 调用之间稍作停顿，降低 TPM/瞬时限流导致的第二次调用失败
    delay = float(getattr(settings, "NEWS_LLM_CALL_DELAY", 2) or 0)
    if delay:
        time.sleep(delay)

    prompt_template = prompts.get_prompt("news.brief_md", _BRIEF_MD_PROMPT)
    valid, why = _validate_brief_prompt(prompt_template)
    prompt_note = ""
    if not valid:
        prompt_note = f"news.brief_md override invalid ({why}); using default"
        logger.warning("[NEWS] %s", prompt_note)
        prompt_template = _BRIEF_MD_PROMPT

    brief_md, brief_error = _generate_brief(
        date_str, news_json, small_news_json, prompt_template, prompt_note,
    )
    if not brief_md:
        logger.warning("[NEWS] brief_md generation failed (fallback to summary page): %s", brief_error)

    return {"title": title, "summary": summary, "brief_md": brief_md, "brief_error": brief_error}


_HTML_CSS = """
:root{--paper:#fafaf8;--ink:#0a0a0a;--accent:#002FA7;--accent-on:#fff;--grey-1:#f0f0ee;--grey-2:#d4d4d2;--grey-3:#737373;}
*,*::before,*::after{box-sizing:border-box;}
body{font-family:-apple-system,"PingFang SC","Microsoft YaHei UI","Noto Sans SC",Inter,sans-serif;background:var(--paper);color:var(--ink);margin:0;padding:48px 24px;line-height:1.6;-webkit-font-smoothing:antialiased;}
main{max-width:760px;margin:0 auto;}
h1{font-size:32px;font-weight:300;letter-spacing:-.02em;margin:0 0 8px;padding-bottom:16px;border-bottom:3px solid var(--accent);}
h2{font-size:22px;font-weight:500;margin:40px 0 16px;padding-left:12px;border-left:4px solid var(--accent);}
h3{font-size:18px;font-weight:500;margin:24px 0 12px;}
p{margin:12px 0;}
blockquote{margin:16px 0;padding:14px 18px;background:var(--grey-1);border-left:4px solid var(--accent);color:#333;border-radius:0 4px 4px 0;}
blockquote p{margin:0;}
ul,ol{padding-left:24px;}
li{margin:6px 0;}
li>ul,li>ol{margin-top:6px;}
ul ul li,ol ol li,ul ol li,ol ul li{font-size:13px;font-style:italic;color:var(--grey-3);margin:2px 0 8px;padding-left:4px;}
ul ul li::marker,ol ol li::marker,ul ol li::marker,ol ul li::marker{color:var(--grey-2);}
a{color:var(--accent);text-decoration:none;border-bottom:1px solid transparent;transition:border-color .15s;}
a:hover{border-bottom-color:var(--accent);}
code{font-family:ui-monospace,"SF Mono",Consolas,monospace;background:var(--grey-1);padding:2px 6px;border-radius:3px;font-size:14px;}
pre{background:#1a1a1a;color:#fafaf8;padding:16px;border-radius:6px;overflow-x:auto;}
pre code{background:none;padding:0;color:inherit;}
table{width:100%;border-collapse:collapse;margin:20px 0;font-size:14px;}
th,td{padding:10px 12px;text-align:left;border-bottom:1px solid var(--grey-2);}
th{background:var(--grey-1);font-weight:600;}
tr:hover td{background:rgba(0,47,167,.03);}
hr{border:0;border-top:1px solid var(--grey-2);margin:32px 0;}
.meta{color:var(--grey-3);font-size:13px;margin:0 0 32px;font-family:ui-monospace,monospace;letter-spacing:.04em;}
.fallback-note{background:#fff4e5;border-left:4px solid #e6a23c;color:#8a5a00;padding:12px 16px;border-radius:0 4px 4px 0;font-size:14px;margin:16px 0;}
.count{color:var(--grey-3);font-size:13px;font-weight:400;}
ul.news{list-style:none;padding:0;margin:0;}
ul.news>li{padding:14px 0;border-bottom:1px solid var(--grey-2);}
ul.news>li:last-child{border-bottom:0;}
.item-meta{color:var(--grey-3);font-size:12.5px;margin-top:6px;font-family:ui-monospace,Consolas,monospace;}
.footer{margin-top:48px;padding-top:16px;border-top:1px solid var(--grey-2);color:var(--grey-3);font-size:12px;font-family:ui-monospace,monospace;letter-spacing:.04em;}
@media (max-width:600px){body{padding:24px 16px;}h1{font-size:24px;}h2{font-size:18px;}table{font-size:12px;}th,td{padding:8px;}}
"""

_HTML_TEMPLATE = Template(
    '<!doctype html>\n<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
    "<title>$title</title>\n<style>\n$css\n</style>\n</head>\n<body>\n<main>\n$body\n"
    '<p class="footer">$footer</p>\n</main>\n</body>\n</html>\n'
)


def _esc(v) -> str:
    return escape(str(v or ""), quote=False)


def _safe_url(u) -> str:
    s = str(u or "").strip()
    return s if s.startswith(("http://", "https://")) else ""


def _paragraphs(text) -> str:
    return "\n".join(f"<p>{_esc(p)}</p>" for p in re.split(r"\n+", text or "") if p.strip())


def _fix_list_indent(md: str) -> str:
    """Normalize markdown list indentation to 4 spaces per level + dedupe sources.

    LLMs often emit nested bullets (e.g. `来源:` lines) with only 2 spaces,
    which `sane_lists` treats as a sibling item instead of a sub-item. This
    re-indents every list line to a 4-space grid so nesting renders correctly,
    and drops duplicate `来源:` sub-lines repeated under the same bullet.
    """
    out: list[str] = []
    seen_src: set[str] = set()
    for line in (md or "").split("\n"):
        m = re.match(r"^(\s*)([-*+])\s+(.*)$", line)
        if not m:
            out.append(line)
            if line.strip():
                seen_src = set()  # headings / paragraphs reset the source group
            continue
        indent, text = m.group(1), m.group(3)
        n = len(indent)
        level = 0 if n == 0 else (1 if n <= 4 else min(3, (n + 3) // 4))
        if level == 0:
            seen_src = set()
        elif text.lstrip().startswith("来源"):
            key = re.sub(r"\([^()]*\)", "", text).strip()  # 忽略链接 URL，只按来源名去重
            if key in seen_src:
                continue
            seen_src.add(key)
        out.append("    " * level + "- " + text)
    return "\n".join(out)


def _render_page(title: str, body: str, footer: str) -> str:
    return _HTML_TEMPLATE.substitute(title=_esc(title), css=_HTML_CSS, body=body, footer=_esc(footer))


def render_brief_html(brief: dict, sources_label: str, date_str: str, edition: str, now_label: str) -> str:
    """文字版: 详细 markdown brief(一句话定调 + 分板块要点 + 关键数字 + 风险点 + Takeaway)。

    若 LLM 未返回 brief_md，则退化为「标题 + 飞书摘要分段」。
    """
    title = f"今日金融资讯 · {date_str}"
    meta = f"发布于 {date_str} · {edition} · 数据来源: {sources_label}"
    md = str(brief.get("brief_md") or "").strip()
    if md:
        # 规范化缩进 + 转义 markdown 源里的原始 HTML，避免新闻标题注入 <script> 等
        safe_md = _fix_list_indent(md).replace("<", "&lt;")
        try:
            body_md = _md.markdown(safe_md, extensions=["extra", "tables", "fenced_code", "sane_lists", "nl2br"],
                                   output_format="html")
        except Exception as exc:  # noqa: BLE001
            logger.warning("[NEWS] markdown render failed: %s", exc)
            body_md = f"<pre>{_esc(md)}</pre>"
        body = f'<p class="meta">{_esc(meta)}</p>\n{body_md}'
    else:
        heading = f"【今日金融资讯 · {date_str}】{brief.get('title', '')}"
        note = ""
        if brief.get("brief_error"):
            note = '<p class="fallback-note">⚠️ 详细文字版生成失败，以下为摘要版。</p>\n'
        body = (f'<h1>{_esc(heading)}</h1>\n<p class="meta">{_esc(meta + " · " + now_label)}</p>\n'
                + note + _paragraphs(brief.get("summary", "")))
    return _render_page(title, body, "Generated by DayBetter · 新闻播报")


def render_report_html(brief: dict, items: list[dict], sources_label: str, date_str: str,
                       edition: str, now_label: str) -> str:
    """详细版: 摘要 + 按来源分组的全部资讯条目(标题/时间/摘要/原文链接)。"""
    title = f"今日金融资讯 · {date_str} · 详细版"
    meta = f"{date_str} · {edition} · {now_label} · 共 {len(items)} 条"
    parts = [f"<h1>{_esc(title)}</h1>", f'<p class="meta">{_esc(meta)}</p>',
             "<h2>今日摘要</h2>", _paragraphs(brief.get("summary", ""))]
    groups: dict[str, list] = {}
    for it in items:
        groups.setdefault(str(it.get("src_name") or "其他"), []).append(it)
    parts.append("<h2>分来源资讯</h2>")
    for src, rows in groups.items():
        parts.append(f'<h3>{_esc(src)} <span class="count">{len(rows)} 条</span></h3>')
        parts.append('<ul class="news">')
        for it in rows:
            t = _esc(it.get("title"))
            url = _safe_url(it.get("url"))
            t_html = (f'<a href="{escape(url, quote=True)}" target="_blank" rel="noopener">{t}</a>'
                      if url else t)
            bits = [x for x in (_esc(it.get("time")),) if x]
            summary = _esc(str(it.get("summary") or "")[:500])
            item = f"<li>{t_html}"
            if bits:
                item += f'<div class="item-meta">{" · ".join(bits)}</div>'
            if summary:
                item += f"<p>{summary}</p>"
            parts.append(item + "</li>")
        parts.append("</ul>")
    footer = f"Generated by DayBetter · 新闻播报 · 数据来源: {sources_label}"
    return _render_page(title, "\n".join(parts), footer)


def publish_html(brief_html: str, report_html: str, date_str: str, edition: str) -> tuple[str | None, str | None]:
    """保存 文字版/详细版 HTML 并返回公开 URL。

    - 本地写入 `NEWS_DATA_DIR`(默认 backend/news_data)，由后端 `/api/funds/news/html/...` 直出；
    - 同时上传 COS 归档(默认域名对 HTML 会强制下载，故仅作存档/CDN 用)；
    - URL 优先级: 配了 `COS_PUBLIC_BASE`(自定义域名) → 直连 COS；否则用 `NEWS_HTML_BASE` 后端直出。
    """
    from dvadmin.cards import cos

    safe_edition = re.sub(r"[^0-9A-Za-z_-]+", "-", str(edition or "manual")).strip("-") or "manual"
    base = f"{date_str}/{safe_edition}"
    prefix = (getattr(settings, "NEWS_COS_PREFIX", "news/") or "news/").strip("/")

    data_dir = getattr(settings, "NEWS_DATA_DIR", "") or ""
    root = Path(data_dir) if data_dir else Path(settings.BASE_DIR) / "news_data"
    try:
        (root / base).mkdir(parents=True, exist_ok=True)
        (root / base / "brief.html").write_text(brief_html, encoding="utf-8")
        (root / base / "report.html").write_text(report_html, encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        logger.warning("[NEWS] local HTML write failed: %s", exc)

    if cos.enabled():
        try:
            ctype = "text/html; charset=utf-8"
            cos.upload_bytes(f"{base}/brief.html", brief_html.encode("utf-8"), ctype,
                             prefix=prefix, disposition="inline")
            cos.upload_bytes(f"{base}/report.html", report_html.encode("utf-8"), ctype,
                             prefix=prefix, disposition="inline")
        except Exception as exc:  # noqa: BLE001
            logger.warning("[NEWS] COS upload failed (kept local): %s", exc)

    cos_base = (getattr(settings, "COS_PUBLIC_BASE", "") or "").rstrip("/")
    if cos_base:
        return (f"{cos_base}/{prefix}/{base}/brief.html", f"{cos_base}/{prefix}/{base}/report.html")
    html_base = (getattr(settings, "NEWS_HTML_BASE", "") or "").rstrip("/")
    if html_base:
        root_url = f"{html_base}/api/funds/news/html/{date_str}/{safe_edition}"
        return f"{root_url}/brief", f"{root_url}/report"
    return None, None


def build_card(title: str, summary: str, sources_label: str, date_str: str, now_label: str,
               brief_url: str | None = None, report_url: str | None = None) -> dict:
    header = f"【今日金融资讯 · {date_str}】{title}"[:148]
    elements = [
        {"tag": "div", "text": {"tag": "lark_md", "content": summary}},
        {"tag": "hr"},
        {"tag": "note", "elements": [
            {"tag": "plain_text", "content": f"数据来源: {sources_label} · {now_label}"}
        ]},
    ]
    actions = []
    if brief_url:
        actions.append({"tag": "button", "text": {"tag": "plain_text", "content": "📄 阅读文字版"},
                        "type": "primary", "url": brief_url})
    if report_url:
        actions.append({"tag": "button", "text": {"tag": "plain_text", "content": "📋 阅读详细版"},
                        "type": "default", "url": report_url})
    if actions:
        elements.append({"tag": "action", "actions": actions})
    return {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"tag": "plain_text", "content": header}, "template": "blue"},
        "elements": elements,
    }


def send_card(webhook: str, card: dict) -> None:
    r = requests.post(webhook, json={"msg_type": "interactive", "card": card}, timeout=15)
    r.raise_for_status()
    if r.json().get("StatusCode", -1) != 0:
        raise RuntimeError(f"Feishu webhook error: {r.json()}")
