"""Fund factsheet PDF -> top holdings (LLM-first, DeepSeek/VLLM compatible).

Ported (simplified) from refer-04 `pdf_extractor.py` / `llm_holdings.py`:
we take the PDF text via pdfplumber and ask the LLM to return the
TOP-HOLDINGS section as JSON. Results are cached by PDF hash in-process.
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import re
from collections import OrderedDict

import pdfplumber
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

_cache: "OrderedDict[str, list[dict]]" = OrderedDict()
_CACHE_MAX = 200

_SYSTEM = (
    "You are a financial data extractor for HK / China fund factsheets. "
    "Given the raw text of a fund factsheet PDF, find the TOP-HOLDINGS section "
    "(headings like 十大持股 / 5大持股 / 五大持股 / Top 10 Holdings / Top 5 Holdings "
    "/ 十大投資項目 / 前十大持倉 / 主要持有). Extract the holdings as JSON. "
    "Rules: output ONLY valid JSON {\"holdings\":[{\"name\":\"...\",\"weight_pct\":12.34}]}; "
    "at most {max_rows} rows; copy each company name EXACTLY as printed; "
    "weight_pct is a number in percent without the % sign; keep original order."
)


def _opt(name, default=None):
    return getattr(settings, name, None) or default


def _llm(tenant_id=None) -> tuple[str, str, str]:
    from dvadmin.aikeys import resolver

    cred = resolver.get_single(tenant_id, "deepseek", require=False, use_context=False)
    if cred is None:
        return "", "", ""
    base = cred.base_url or _opt("DEEPSEEK_BASE", "https://api.deepseek.com")
    model = cred.model or _opt("DEEPSEEK_MODEL", "deepseek-chat")
    return base.rstrip("/"), model, cred.api_key


_PDF_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36",
    "Accept": "application/pdf,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8",
    "Origin": "https://www.fsmglobal.hk",
    "Referer": "https://www.fsmglobal.hk/",
}


def fetch_pdf(url: str, timeout: int = 30) -> bytes:
    r = requests.get(url, headers=_PDF_HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.content


def pdf_text(pdf_bytes: bytes, max_pages: int = 6) -> str:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        pages = pdf.pages[:max_pages]
        return "\n".join((p.extract_text() or "") for p in pages)


def extract_top_holdings(pdf_bytes: bytes, max_rows: int | None = None, tenant_id=None) -> list[dict]:
    """Return [{rank, name, weight_pct}]. Empty list on failure (analysis continues)."""
    max_rows = int(max_rows or _opt("FUND_HOLDINGS_MAX", 10) or 10)
    ck = f"{tenant_id or 0}:{hashlib.sha256(pdf_bytes).hexdigest()}"
    if ck in _cache:
        _cache.move_to_end(ck)
        return [dict(h) for h in _cache[ck]]

    text = ""
    try:
        text = pdf_text(pdf_bytes)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[HOLDINGS] pdf text extract failed: %s", exc)
    if not text.strip():
        return []

    base, model, key = _llm(tenant_id)
    if not key:
        logger.warning("[HOLDINGS] no DEEPSEEK_API_KEY; skip extraction")
        return []

    prompt = _SYSTEM.replace("{max_rows}", str(max_rows)) + f"\n\n=== FACTSHEET TEXT ===\n{text[:14000]}"
    try:
        resp = requests.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "system", "content": "You output only JSON."},
                             {"role": "user", "content": prompt}],
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
            },
            timeout=180,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"] or ""
        content = re.sub(r"^```[a-zA-Z]*\s*", "", content)
        content = re.sub(r"```$", "", content).strip()
        m = re.search(r"\{.*\}", content, re.S)
        data = json.loads(m.group(0) if m else content)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[HOLDINGS] LLM extract failed: %s", exc)
        return []

    out: list[dict] = []
    for i, h in enumerate(data.get("holdings") or []):
        if not isinstance(h, dict):
            continue
        name = str(h.get("name") or "").strip()
        if not name:
            continue
        try:
            w = float(str(h.get("weight_pct") or "0").replace("%", "").strip())
        except (TypeError, ValueError):
            w = 0.0
        out.append({"rank": i + 1, "name": name, "weight_pct": w})
        if len(out) >= max_rows:
            break

    _cache[ck] = [dict(h) for h in out]
    _cache.move_to_end(ck)
    while len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)
    return out
