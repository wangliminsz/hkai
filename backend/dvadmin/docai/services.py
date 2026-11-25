# -*- coding: utf-8 -*-
"""AI 文件分析: PDF/图片 -> 文本 -> QVeris 分析 -> HTML 报告 -> 邮件。

Ported from refer-06 (fs_vue_fastapi): PyMuPDF full-text for PDFs, Qwen3-VL
vision transcription for images, QVeris agent for analysis, Django SMTP for
delivery. Prompts are DB-configurable (see funds/prompts.py).
"""
from __future__ import annotations

import base64
import html as html_mod
import io
import logging
import re
from datetime import datetime

import markdown as _md
import requests
from django.conf import settings
from django.core.mail import EmailMultiAlternatives

logger = logging.getLogger(__name__)

DEFAULT_PROMPT = (
    "你是一个极具洞察力的投资哲学家和金融分析师。"
    "下面是用户上传的 文件 中识别出的完整内容（可能是一份基金资料、报告、"
    "宣传单页或其他金融材料，可能是 PDF 或者图片）。请通读全文，提炼核心要点，"
    "分析其中体现的策略、逻辑与关键数据，并指出值得关注的信号。"
    "请结合内容本身的主题（例如基金、产品、行业等）展开，基于全部内容分析。"
    "给前端销售端用，充满洞察力与穿透力。"
    "最后，可以加一小段：适合怎样的客户，客户内心最关注的点，让销售可以迅速抓住让客户眼睛一亮的点。"
    "同时，让完全不懂的客户也能看懂\n\n"
    "在分析行情、涨跌原因或未来走势之前，必须先通过 discover/call 检索最新的市场行情与新闻数据。"
    "分析中必须明确引用这些实时数据（价格、涨跌幅、新闻要点）。"
    "禁止仅凭你训练时的旧知识谈论市场现状。"
)

MAX_FILE_BYTES = 30 * 1024 * 1024
_IMAGE_SIGNATURES = {
    "png": b"\x89PNG\r\n\x1a\n",
    "jpeg": b"\xff\xd8\xff",
    "gif": b"GIF8",
    "webp": b"RIFF",
    "bmp": b"BM",
}


def detect_kind(data: bytes) -> str:
    if data[:5] == b"%PDF-":
        return "pdf"
    for kind, sig in _IMAGE_SIGNATURES.items():
        if data[: len(sig)] == sig:
            if kind == "webp" and data[8:12] != b"WEBP":
                continue
            return "image"
    return ""


def extract_pdf_text(pdf_bytes: bytes, max_chars: int = 60000) -> str:
    import fitz  # PyMuPDF

    parts: list[str] = []
    used = 0
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for i, page in enumerate(doc):
            txt = (page.get_text("text") or "").strip()
            if not txt:
                continue
            block = f"--- PAGE {i + 1} ---\n{txt}"
            if used + len(block) > max_chars:
                parts.append(block[: max(0, max_chars - used)])
                break
            parts.append(block)
            used += len(block)
    return "\n\n".join(parts)


def extract_image_markdown(image_bytes: bytes, tenant_id=None) -> str:
    """Transcribe an uploaded image to markdown with Qwen3-VL (SiliconFlow)."""
    from PIL import Image, ImageOps

    from dvadmin.aikeys import resolver

    cred = resolver.get_single(tenant_id, "vllm", require=True, use_context=False)
    if cred is None:
        raise RuntimeError("视觉模型未配置")
    base = (cred.base_url or "").rstrip("/")
    model = cred.model or "Qwen/Qwen3-VL-30B-A3B-Instruct"
    key = cred.api_key
    if not base or not key:
        raise RuntimeError("视觉模型未配置（VLLM_BASE / VLLM_API_KEY）")

    max_px = 1568
    try:
        with Image.open(io.BytesIO(image_bytes)) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            w, h = im.size
            longest = max(w, h)
            if longest > max_px:
                scale = max_px / longest
                im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))))
            buf = io.BytesIO()
            im.save(buf, format="PNG")
            png = buf.getvalue()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"图片解析失败: {exc}") from exc

    system = (
        "You are a meticulous document reader for Chinese / English financial materials. "
        "You are given an IMAGE of a document. Transcribe the FULL content into well-structured Markdown. "
        "Preserve headings, lists, tables and numbers exactly; keep the original language. "
        "Reconstruct tables as Markdown tables. Include ALL visible text. "
        "Do not invent or interpret. Output ONLY Markdown."
    )
    payload = {
        "model": model, "temperature": 0.0, "max_tokens": 3000,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": [
                {"type": "text", "text": "Transcribe the entire document content into Markdown."},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64.b64encode(png).decode()}"}},
            ]},
        ],
    }
    resp = requests.post(f"{base}/v1/chat/completions", timeout=180,
                         headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                         json=payload)
    resp.raise_for_status()
    md = (resp.json()["choices"][0]["message"]["content"] or "").strip()
    if len(md) < 40:
        raise RuntimeError("未能识别图片内容（内容过短）")
    return md


def holdings_markdown(holdings: list[dict]) -> str:
    if not holdings:
        return ""
    lines = ["| # | 持仓 | 权重 |", "|---:|-----|------|"]
    for h in holdings:
        lines.append(f"| {h.get('rank', '')} | {h.get('name', '')} | {h.get('weight_pct', '')}% |")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# HTML report (self-contained; emailed)
# --------------------------------------------------------------------------

_CSS = """
:root{--ink:#111;--muted:#666;--line:#ddd;--accent:#c4262e;--paper:#fff;}
*{box-sizing:border-box;}
html,body{margin:0;padding:0;}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans CJK SC",sans-serif;background:var(--line);color:var(--ink);line-height:1.7;-webkit-font-smoothing:antialiased;}
.sheet{max-width:760px;margin:0 auto;background:var(--paper);padding:32px 28px 48px;}
.topbar{border-top:8px solid var(--accent);font-size:12px;letter-spacing:.12em;color:var(--muted);text-transform:uppercase;padding-top:12px;}
h1{font-size:26px;margin:14px 0 6px;line-height:1.3;letter-spacing:-.01em;}
.sub{color:var(--muted);font-size:14px;margin-bottom:6px;}
.meta{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0 8px;}
.badge{font-size:13px;padding:4px 10px;border:1px solid var(--ink);display:inline-block;border-radius:2px;white-space:nowrap;}
.badge.ret{background:var(--ink);color:var(--paper);font-weight:700;}
hr{border:0;border-top:1px solid var(--line);margin:24px 0;}
article{font-size:15px;}
article h2{border-bottom:2px solid var(--ink);padding-bottom:6px;font-size:20px;margin:1.6em 0 .5em;}
article h3{font-size:17px;margin:1.6em 0 .5em;}
article p{margin:.7em 0;}
article ul,article ol{padding-left:1.4em;}
article li{margin:.3em 0;}
article a{color:var(--accent);}
article blockquote{margin:1em 0;padding:.4em 1em;border-left:4px solid var(--accent);background:#fafafa;color:#444;}
article table{border-collapse:collapse;width:100%;margin:1em 0;font-size:14px;}
article th,article td{border:1px solid var(--line);padding:7px 10px;text-align:left;}
article th{background:#f6f6f6;}
.fulltext{background:#fafafa;border:1px solid var(--line);padding:16px;white-space:pre-wrap;font-size:12.5px;line-height:1.6;max-height:520px;overflow:auto;}
.foot{margin-top:40px;padding-top:16px;border-top:1px solid var(--line);font-size:12px;color:var(--muted);}
"""

_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>{css}</style></head>
<body><div class="sheet">
<div class="topbar">{topbar}</div>
<h1>{title}</h1>
<div class="sub">{subtitle}</div>
<div class="meta">{badges}</div>
<hr>
<article>{body_html}</article>
{fulltext_block}
<div class="foot">数据来源：用户上传文件 · 生成于 {generated} · 内容由 AI 生成，仅供参考，不构成投资建议</div>
</div></body></html>
"""


def render_report_html(filename: str, kind: str, analysis_md: str, content_text: str,
                       holdings: list[dict] | None = None) -> str:
    safe_md = (analysis_md or "").replace("<", "&lt;")
    body = _md.markdown(safe_md, extensions=["tables", "fenced_code", "nl2br", "sane_lists"],
                        output_format="html")
    title = f"AI 文件分析 · {filename or '未命名文件'}"
    badges = [f'<span class="badge">{html_mod.escape(kind.upper())}</span>',
              f'<span class="badge">{html_mod.escape(filename or "")}</span>']
    if holdings:
        badges.append(f'<span class="badge ret">{len(holdings)} 项持仓</span>')
    fulltext = ""
    if content_text:
        label = "图片原文内容" if kind == "image" else "PDF 原文内容"
        fulltext = (f"<hr><h2 style='font-size:18px'>{label}</h2>"
                    f"<div class='fulltext'>{html_mod.escape(content_text[:20000])}</div>")
    return _TEMPLATE.format(
        css=_CSS, topbar=f"{html_mod.escape(kind.upper())} · {datetime.now():%Y-%m-%d %H:%M}",
        title=html_mod.escape(title),
        subtitle="基于上传文件的 AI 分析（QVeris + DeepSeek）",
        badges="".join(badges), body_html=body, fulltext_block=fulltext,
        generated=f"{datetime.now():%Y-%m-%d %H:%M}",
    )


_PRINT_CSS = """<style>@media print{
body{background:#fff!important}
.sheet{max-width:none!important;padding:0!important}
.fulltext{max-height:none!important;overflow:visible!important}
h1,h2,h3{break-after:avoid}
table,pre,blockquote{break-inside:avoid}
article table{page-break-inside:auto}
article tr{page-break-inside:avoid}
}</style>"""


def render_report_pdf(html_body: str) -> bytes:
    from playwright.sync_api import sync_playwright

    html = html_body.replace("</head>", _PRINT_CSS + "</head>", 1) if "</head>" in html_body else _PRINT_CSS + html_body
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page()
            page.set_content(html, wait_until="load")
            page.evaluate("document.fonts.ready")
            page.emulate_media(media="print")
            pdf = page.pdf(
                format="A4",
                print_background=True,
                margin={"top": "14mm", "bottom": "14mm", "left": "12mm", "right": "12mm"},
                display_header_footer=True,
                header_template="<div></div>",
                footer_template=(
                    "<div style='width:100%;font-size:9px;color:#777;text-align:center;"
                    "font-family:-apple-system,\"PingFang SC\",\"Noto Sans CJK SC\",sans-serif'>"
                    "<span class='pageNumber'></span> / <span class='totalPages'></span></div>"
                ),
            )
            return pdf
        finally:
            browser.close()


_MAX_ORIGINAL_ATTACH = 20 * 1024 * 1024


def send_report_email(to_email: str, filename: str, html_body: str,
                      pdf_bytes: bytes | None = None, pdf_name: str = "",
                      original_bytes: bytes | None = None, original_name: str = "",
                      original_mime: str = "application/octet-stream") -> list[str]:
    """Send the report to each recipient as a separate message.

    One message per recipient (instead of one message with many ``To`` addresses)
    avoids Chinese providers flagging multi-domain recipient lists as bulk mail and
    lets one rejection/drop not affect the others. Returns the failed addresses.
    """
    recipients = [x.strip() for x in re.split(r"[,;，；]", to_email or "") if x.strip()]
    if not recipients:
        raise RuntimeError("未填写收件邮箱")
    subject = f"AI 分析报告 - {filename or 'Finance Report'}"
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or getattr(settings, "EMAIL_HOST_USER", None)
    attach_original = bool(original_bytes) and len(original_bytes) <= _MAX_ORIGINAL_ATTACH
    if original_bytes and not attach_original:
        logger.warning("[DOCAI] original file too large to attach (%s bytes), skipped", len(original_bytes))

    failed: list[str] = []
    for to_addr in recipients:
        msg = EmailMultiAlternatives(
            subject,
            "请使用支持 HTML 的邮箱查看分析报告。",
            from_email,
            [to_addr],
        )
        msg.attach_alternative(html_body, "text/html")
        if pdf_bytes:
            msg.attach(pdf_name or "AI-analysis.pdf", pdf_bytes, "application/pdf")
        if attach_original:
            msg.attach(original_name or "original", original_bytes, original_mime)
        try:
            msg.send(fail_silently=False)
            logger.info("[DOCAI] report emailed to %s", to_addr)
        except Exception as exc:  # noqa: BLE001 - keep sending to the rest
            logger.warning("[DOCAI] email to %s failed: %s", to_addr, exc)
            failed.append(to_addr)

    if failed and len(failed) == len(recipients):
        raise RuntimeError("邮件发送失败: " + ", ".join(failed))
    return failed
